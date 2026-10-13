"""IG5 LLDB supervisor for macOS hosts.

Internal JSONL transport; the host owns approvals, ownership and revision checks.
This adapter mirrors the x64dbg adapter's protocol so `ig5_dbg` needs only a new
backend branch: same ops, same result keys (runId/stopSeq/state/context).

Starting this module, doctor and open never execute a target. `load` creates an
empty debugger; `start` is the only target launch operation.

Platform note: this adapter drives Apple's LLDB through its Python bindings.
LLDB's ptrace-based attach is blocked for platform-signed binaries under SIP;
re-signing the target with `com.apple.security.get-task-allow` restores it.
"""
from __future__ import annotations

import collections
import contextlib
import hashlib
import json
import os
import plistlib
import queue
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

# macOS refuses ptrace attach to platform-signed binaries unless the image
# carries this entitlement. Unsigned local builds and already-prepared copies
# are unaffected, so the check below only fires when it is actually needed.
GET_TASK_ALLOW = "com.apple.security.get-task-allow"


def signature_state(path):
    """Report whether LLDB can attach to `path` without re-signing.

    Returns one of:
      unsigned  - no code signature; the kernel allows debugging it
      debuggable- signed and already carrying get-task-allow
      protected - signed without get-task-allow (typically Apple-signed)
      unknown   - codesign could not report; callers must not guess
    """
    try:
        described = subprocess.run(["codesign", "-dv", str(path)],
                                   capture_output=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    report = (described.stdout or "") + (described.stderr or "")
    if "not signed at all" in report:
        return "unsigned"
    if described.returncode != 0 and "code object is not signed" not in report:
        return "unknown"
    try:
        entitlements = subprocess.run(["codesign", "-d", "--entitlements", "-", str(path)],
                                      capture_output=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    text = (entitlements.stdout or "") + (entitlements.stderr or "")
    if GET_TASK_ALLOW in text:
        return "debuggable"
    # A signature that is present but reports no entitlements is protected.
    return "protected"


def prepare_target(path, destination=None):
    """Copy a protected image and re-sign it so LLDB may attach.

    The original file is never modified: re-signing an Apple binary in place
    invalidates its seal and can break the rest of the system. The copy keeps
    the original bytes and only gains the debugging entitlement.
    """
    source = Path(path).expanduser().resolve(strict=True)
    state = signature_state(source)
    if state in ("unsigned", "debuggable"):
        return {"prepared": False, "state": state, "path": str(source), "reason": "already debuggable"}
    if state == "unknown":
        raise RpcError("ESIGNATURE", "codesign could not classify the target; prepare it manually before debugging")

    if destination:
        out = Path(destination).expanduser()
        if out.is_dir():
            out = out / (source.name + "-ig5dbg")
    else:
        out = Path(tempfile.mkdtemp(prefix="ig5-lldb-")) / (source.name + "-ig5dbg")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, out)
    # copyfile does not carry the mode; without the executable bit the kernel
    # refuses to launch the copy even when the signature is valid.
    shutil.copymode(source, out)
    out.chmod(out.stat().st_mode | 0o111)
    # Hash the copy before touching its signature. This equals the original's
    # digest, which is the host's proof that the prepared image is the very
    # binary the caller opened rather than something else on the same path.
    sha_before = hashlib.sha256(out.read_bytes()).hexdigest()
    if sha_before != hashlib.sha256(source.read_bytes()).hexdigest():
        raise RpcError("ESIGNATURE", "copied image does not match the original bytes; refusing to sign")
    # The copy inherits the original extended attributes and signature; both
    # must go before an ad-hoc signature can be applied.
    with contextlib.suppress(OSError):
        subprocess.run(["xattr", "-c", str(out)], capture_output=True, timeout=20)
    removed = subprocess.run(["codesign", "--remove-signature", str(out)],
                             capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    if removed.returncode != 0 and "not signed" not in ((removed.stderr or "") + (removed.stdout or "")):
        raise RpcError("ESIGNATURE", f"failed to strip the original signature: {(removed.stderr or '').strip()[:300]}")

    entitlements = out.parent / "ig5-debug-entitlements.plist"
    with entitlements.open("wb") as stream:
        plistlib.dump({GET_TASK_ALLOW: True}, stream)
    signed = subprocess.run(["codesign", "--force", "--sign", "-", "--entitlements", str(entitlements), str(out)],
                            capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    if signed.returncode != 0:
        raise RpcError("ESIGNATURE", f"ad-hoc signing failed: {(signed.stderr or '').strip()[:300]}")
    with contextlib.suppress(OSError):
        subprocess.run(["xattr", "-c", str(out)], capture_output=True, timeout=20)
    verified = signature_state(out)
    if verified != "debuggable":
        raise RpcError("ESIGNATURE", f"re-signed copy does not report {GET_TASK_ALLOW}; refusing to launch")
    return {"prepared": True, "state": verified, "original": str(source), "path": str(out),
            # imageSha256 is the payload identity: it equals the original's
            # digest and is what the host compares against the opened artifact.
            # signingSha256 covers the whole file after signing and therefore
            # differs, because the ad-hoc signature is appended to the image.
            "imageSha256": sha_before,
            "signingSha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "originalSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "note": "the copy keeps the original payload bytes; only the appended code signature differs"}

OPS = ["load", "start", "bpt", "unbpt", "regs", "setreg", "step", "stepover",
       "cont", "suspend", "readmem", "writemem", "stop", "state", "event",
       "modules", "trace", "threads", "callstack",
       # signature inspection and target preparation for SIP-protected images
       "signature", "prepare"]
CAPABILITIES = ["doctor", "open", "close", "dbg", *["dbg." + op for op in OPS],
                "dbg.hardware_breakpoint", "dbg.thread_return", "dbg.memory_regions",
                "dbg.signature", "dbg.prepare", "cancel"]

# Mach-O CPU types we accept as launch targets.
CPU_TYPE_X86_64 = 0x01000007
CPU_TYPE_ARM64 = 0x0100000C


class RpcError(Exception):
    def __init__(self, code, message, **detail):
        super().__init__(message)
        self.code, self.detail = code, detail


def integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("expected an integer or integer string")
    return int(value, 0) if isinstance(value, str) else int(value)


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, int) and abs(value) > 2 ** 53 - 1:
        return hex(value)
    return value


def inspect_macho(path):
    """Validate a Mach-O image and report its bit width and architecture."""
    path = Path(path).expanduser().resolve(strict=True)
    with path.open("rb") as f:
        head = f.read(8)
    if len(head) < 8:
        raise ValueError("target is not a Mach-O executable")
    magic = struct.unpack_from(">I", head, 0)[0]
    MH_MAGIC_64 = 0xFEEDFACF
    MH_CIGAM_64 = 0xCFFAEDFE
    FAT_MAGIC = 0xCAFEBABE
    FAT_CIGAM = 0xBEBAFECA
    if magic == FAT_MAGIC or magic == FAT_CIGAM:
        swap = magic == FAT_CIGAM
        count = struct.unpack_from("<I" if swap else ">I", head, 4)[0]
        if not 1 <= count <= 64:
            raise ValueError("invalid Mach-O fat header")
        with path.open("rb") as f:
            f.seek(8)
            table = f.read(20 * count)
        cputype = None
        for i in range(count):
            off = i * 20
            c = struct.unpack_from("<i" if swap else ">i", table, off)[0]
            if c in (CPU_TYPE_X86_64, CPU_TYPE_ARM64):
                cputype = c
                break
        if cputype is None:
            raise ValueError("Mach-O universal binary has no supported slice")
    elif magic in (MH_MAGIC_64, MH_CIGAM_64):
        cputype = struct.unpack_from("<i" if magic == MH_MAGIC_64 else ">i", head, 4)[0]
    else:
        raise ValueError("target is not a 64-bit Mach-O executable")
    bits = 64
    return {"path": str(path), "bits": bits, "cputype": cputype,
            "arch": "arm64" if cputype == CPU_TYPE_ARM64 else "x86_64",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class LldbClient:
    """Thin wrapper over the LLDB Python API. All calls are synchronous."""

    def __init__(self, adapter):
        self.adapter = adapter
        self.debugger = None
        self.target = None
        self.process = None

    # ── lifecycle ────────────────────────────────────────────────────────────
    def connect(self):
        import lldb
        self.lldb = lldb
        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(False)
        # Redirect LLDB's own chatter to stderr so stdout stays a pure JSONL
        # protocol channel; the host parser must never see raw LLDB text.
        # SBFile.Create takes a Python file object, not a raw descriptor.
        with contextlib.suppress(Exception):
            self.debugger.SetOutputFile(lldb.SBFile.Create(sys.stderr, borrow=True))
            self.debugger.SetErrorFile(lldb.SBFile.Create(sys.stderr, borrow=True))
        return True

    def close(self):
        if self.process is not None:
            with contextlib.suppress(Exception):
                if self.process.GetState() in (self.lldb.eStateRunning, self.lldb.eStateStepping):
                    self.process.Stop()
                self.process.Kill()
        self.process = self.target = None
        if self.debugger is not None:
            with contextlib.suppress(Exception):
                self.lldb.SBDebugger.Destroy(self.debugger)
        self.debugger = None
        return True

    def cmd(self, command):
        result = self.lldb.SBCommandReturnObject()
        self.debugger.GetCommandInterpreter().HandleCommand(command, result)
        return result

    def is_debugging(self):
        return bool(self.process is not None and self.process.IsValid()
                    and self.process.GetState() != self.lldb.eStateDetached)

    def is_running(self):
        if self.process is None or not self.process.IsValid():
            return False
        return self.process.GetState() in (self.lldb.eStateRunning, self.lldb.eStateStepping)

    def get_debugger_pid(self):
        return self.process.GetProcessID() if self.process and self.process.IsValid() else None

    # ── target / launch ──────────────────────────────────────────────────────
    def create_target(self, path):
        self.target = self.debugger.CreateTarget(str(path))
        if not self.target.IsValid():
            raise RpcError("ETARGET", f"LLDB rejected target: {path}")
        return self.target

    def start_target(self, path, args, directory):
        if self.target is None or not self.target.IsValid():
            self.create_target(path)
        argv = [str(path)] + ([str(args)] if args else [])
        info = self.lldb.SBLaunchInfo(argv)
        if directory:
            info.SetWorkingDirectory(str(directory))
        # Stop at the entry point so the host receives a paused, inspectable
        # process instead of racing the target to its own exit. SBLaunchInfo
        # has no SetStopOnEntry in this binding; the flag is the supported path.
        info.SetLaunchFlags(info.GetLaunchFlags() | self.lldb.eLaunchFlagStopAtEntry)
        error = self.lldb.SBError()
        self.process = self.target.Launch(info, error)
        if error.Fail():
            raise RpcError("ELAUNCH", error.GetCString() or "launch failed")
        return self.process.IsValid()

    # ── threads / frames ─────────────────────────────────────────────────────
    def thread(self):
        if self.process is None or not self.process.IsValid():
            raise RpcError("ESTATE", "no process")
        return self.process.GetSelectedThread()

    def frame(self):
        th = self.thread()
        if th is None or not th.IsValid() or th.GetNumFrames() == 0:
            raise RpcError("ESTATE", "no selected frame")
        return th.GetFrameAtIndex(0)

    def get_threads(self):
        if self.process is None or not self.process.IsValid():
            raise RpcError("ESTATE", "no process")
        out = []
        for i in range(self.process.GetNumThreads()):
            th = self.process.GetThreadAtIndex(i)
            out.append({"index": i, "tid": th.GetThreadID(),
                        "name": th.GetName() or None,
                        "selected": i == self.process.GetSelectedThread().GetIndexID(),
                        "frames": th.GetNumFrames(),
                        "stopReason": th.GetStopReason()})
        return {"threads": out, "count": len(out)}

    def get_callstack(self):
        th = self.thread()
        frames = []
        for i in range(th.GetNumFrames()):
            fr = th.GetFrameAtIndex(i)
            frames.append({"index": i, "pc": hex(fr.GetPC()),
                           "function": fr.GetFunctionName() or None,
                           "module": fr.GetModule().GetFileSpec().GetFilename() if fr.GetModule() else None})
        return {"callstack": frames, "count": len(frames)}

    # ── registers ────────────────────────────────────────────────────────────
    REGISTERS = ("rax rbx rcx rdx rsi rdi rip rsp rbp r8 r9 r10 r11 r12 r13 r14 r15 "
                 "eax ebx ecx edx esi edi eip esp ebp eflags").split()

    def get_regs(self):
        fr = self.frame()
        out = {}
        for name in self.REGISTERS:
            reg = fr.FindRegister(name)
            if reg.IsValid():
                out[name] = reg.GetValueAsUnsigned()
        return {"regs": out}

    def set_reg(self, name, value):
        fr = self.frame()
        reg = fr.FindRegister(name)
        if not reg.IsValid():
            raise RpcError("ENOTSUPPORTED", f"register unavailable: {name}")
        if not reg.SetValueFromCString(hex(value)):
            raise RpcError("EWRITE", f"failed to set register: {name}")
        return True

    def evaluate(self, expression):
        fr = self.frame()
        value = fr.EvaluateExpression(str(expression))
        if not value.IsValid() or value.GetError().Fail():
            raise RpcError("EEXPR", value.GetError().GetCString() or "expression failed")
        return value.GetValueAsUnsigned()

    # ── breakpoints ──────────────────────────────────────────────────────────
    def set_breakpoint(self, ea, kind="software", access="execute", size=1):
        if kind == "hardware":
            r = self.cmd(f"breakpoint set --address {hex(ea)} --hardware")
            ok = r.Succeeded()
        else:
            r = self.cmd(f"breakpoint set --address {hex(ea)}")
            ok = r.Succeeded()
        if not ok:
            raise RpcError("EBREAK", (r.GetError() or "breakpoint failed").strip())
        return {"ok": True, "output": (r.GetOutput() or "").strip()[:400]}

    def clear_breakpoint(self, ea, kind="software", access="execute", size=1):
        r = self.cmd(f"breakpoint delete --address {hex(ea)}")
        return {"ok": r.Succeeded(), "output": (r.GetOutput() or "").strip()[:400]}

    # ── memory ───────────────────────────────────────────────────────────────
    def read_memory(self, ea, size):
        error = self.lldb.SBError()
        data = self.process.ReadMemory(ea, size, error)
        if error.Fail():
            raise RpcError("EMEMORY", error.GetCString() or "read failed")
        return data

    def write_memory(self, ea, data):
        error = self.lldb.SBError()
        written = self.process.WriteMemory(ea, data, error)
        if error.Fail():
            raise RpcError("EMEMORY", error.GetCString() or "write failed")
        return written

    def memmap(self):
        regions = self.process.GetMemoryRegions()
        out = []
        info = self.lldb.SBMemoryRegionInfo()
        for i in range(regions.GetSize()):
            regions.GetMemoryRegionAtIndex(i, info)
            out.append({"base": hex(info.GetRegionBase()), "end": hex(info.GetRegionEnd()),
                        "read": info.IsReadable(), "write": info.IsWritable(), "execute": info.IsExecutable()})
        return out

    def module_info(self, ea=None):
        out = []
        for i in range(self.target.GetNumModules()):
            m = self.target.GetModuleAtIndex(i)
            header = m.GetObjectFileHeaderAddress().GetLoadAddress(self.target)
            # SBModule exposes no image size; the module's first section marks
            # the loaded extent, and an unmatched address simply yields no hit.
            size = 0
            if m.GetNumSections() > 0:
                sec = m.GetSectionAtIndex(0)
                size = max(0, sec.GetFileAddress() - header) if sec.GetFileAddress() else 0
            matched = ea is not None and header <= ea < header + max(size, 1 << 24)
            if ea is None or matched:
                out.append({"path": str(m.GetFileSpec()), "name": m.GetFileSpec().GetFilename(),
                            "base": hex(header), "matched": matched})
        return out

    # ── execution ────────────────────────────────────────────────────────────
    def step(self, over=False):
        th = self.thread()
        if over:
            th.StepOver(False)
        else:
            th.StepInstruction(False)
        return self.process.GetState()

    def cont(self):
        self.process.Continue()
        return self.process.GetState()

    def suspend(self):
        self.process.Stop()
        return self.process.GetState()

    def thread_return(self, value):
        r = self.cmd(f"thread return {value}")
        return {"ok": r.Succeeded(), "output": (r.GetOutput() or "").strip()[:400]}


class Adapter:
    def __init__(self, config_path=None, client_factory=None):
        bundled = Path(__file__).resolve().parents[2] / "runtimes/darwin-x64/lldb/runtime.json"
        loc = Path(config_path or os.environ.get("IG5_LLDB_RUNTIME") or bundled)
        self.config_path = loc / "runtime.json" if loc.is_dir() else loc
        self.config = json.loads(self.config_path.read_text(encoding="utf-8-sig")) if self.config_path.is_file() else {}
        self.root = self.config_path.parent
        data_home = Path(os.environ.get("IG5_HOME") or Path.home() / ".dsh/ig5")
        self.state_root = Path(os.environ.get("IG5_LLDB_STATE_ROOT") or data_home / "state/lldb").expanduser().resolve()
        self.client_factory = client_factory
        self.client = None
        self.target = None
        self.run_id = None
        self.stop_seq = 0
        self.event_seq = 0
        self.events = collections.deque(maxlen=256)
        self.event_lock = threading.Lock()
        self.cancel = threading.Event()
        self.closed = False
        self.requests = queue.Queue(maxsize=32)
        self.wake = object()
        self.request_lock = threading.Lock()
        self.queued_ids, self.cancelled_ids, self.active_ids = set(), set(), set()
        self.shutting_down = False
        self.respond = None
        self.request_serial = 0
        self.regular_head = self.control_head = None

    # ── config ───────────────────────────────────────────────────────────────
    def resolve(self, key):
        value = self.config.get(key)
        if not value:
            return None
        p = Path(value)
        return p if p.is_absolute() else self.root / p

    def doctor(self):
        import lldb as _lldb
        return {"ok": True, "engine": "lldb", "backend": "lldb",
                "lldb": _lldb.SBDebugger.GetVersionString().splitlines()[0] if _lldb.SBDebugger.GetVersionString() else "unknown",
                "python": sys.version.split()[0],
                "host": sys.platform,
                "capabilities": CAPABILITIES,
                "notes": "ptrace attach requires a target re-signed with com.apple.security.get-task-allow"}

    def check(self):
        if self.closed:
            raise RpcError("ECLOSED", "adapter is closed")
        return True

    def call(self, name, *args):
        if self.client is None:
            raise RpcError("ESTATE", "debugger is not loaded")
        return getattr(self.client, name)(*args)

    # ── events / state ───────────────────────────────────────────────────────
    def record_event(self, kind, data=None):
        self.event_seq += 1
        self.events.append({"seq": self.event_seq, "type": kind, "data": data or {}})

    def state(self):
        if self.client is None:
            return {"state": "no-task", "stateCode": -1, "runId": self.run_id, "stopSeq": self.stop_seq}
        lldb = self.client.lldb
        proc = self.client.process
        if proc is None or not proc.IsValid():
            return {"state": "no-task", "stateCode": -1, "runId": self.run_id, "stopSeq": self.stop_seq}
        code = proc.GetState()
        names = {lldb.eStateUnloaded: "unloaded", lldb.eStateConnected: "connected",
                 lldb.eStateAttaching: "attaching", lldb.eStateLaunching: "launching",
                 lldb.eStateStopped: "suspended", lldb.eStateRunning: "running",
                 lldb.eStateStepping: "stepping", lldb.eStateCrashed: "crashed",
                 lldb.eStateDetached: "detached", lldb.eStateExited: "exited",
                 lldb.eStateSuspended: "suspended", lldb.eStateInvalid: "invalid"}
        name = names.get(code, "unknown")
        return {"state": name, "stateCode": code, "pid": proc.GetProcessID(),
                "runId": self.run_id, "stopSeq": self.stop_seq,
                "debuggerPid": proc.GetProcessID()}

    def context(self, ea=None):
        if self.client is None or not self.client.is_debugging():
            return {}
        try:
            fr = self.client.frame()
        except RpcError:
            return {}
        pc = fr.GetPC()
        ctx = {"pc": hex(pc), "function": fr.GetFunctionName() or None,
               "module": fr.GetModule().GetFileSpec().GetFilename() if fr.GetModule() else None}
        if ea is not None:
            ctx["ea"] = hex(ea)
        base = self.target["bits"] if self.target else None
        if base:
            ctx["bits"] = base
        for m in self.client.module_info(pc):
            if m.get("matched"):
                ctx["moduleBase"] = m["base"]
                with contextlib.suppress(Exception):
                    ctx["rva"] = hex(pc - int(m["base"], 16))
                break
        return ctx

    def event_list(self, after=0):
        with self.event_lock:
            return [e for e in self.events if e["seq"] > after]

    def address(self, params, span=1):
        if params.get("rva"):
            rva = integer(params["rva"])
            base = self.context().get("moduleBase")
            if not base:
                raise RpcError("EADDRESS", "rva requires a loaded main module")
            return int(base, 16) + rva
        if params.get("ea") in (None, ""):
            raise RpcError("EADDRESS", "ea or rva is required")
        return integer(params["ea"])

    def require_pause(self):
        st = self.state()
        if st["state"] in ("running", "stepping"):
            raise RpcError("ERUNNING", "debugger is running; suspend or wait for a stop first")
        if st["state"] == "no-task":
            raise RpcError("ESTATE", "no active debuggee")
        return st

    # ── launch ───────────────────────────────────────────────────────────────
    def launch(self):
        if self.client is not None and self.client.is_debugging():
            return True
        if self.client is None:
            factory = self.client_factory or LldbClient
            self.client = factory(self)
            self.client.connect()
        return True

    # ── request queue ────────────────────────────────────────────────────────
    def enqueue(self, request):
        ident = request["id"]
        with self.request_lock:
            if ident in self.queued_ids or ident in self.active_ids:
                raise RpcError("EDUP", "duplicate request id")
            self.queued_ids.add(ident)
        with contextlib.suppress(queue.Full):
            self.requests.put_nowait(request)
            return
        with self.request_lock:
            self.queued_ids.discard(ident)
        raise RpcError("EBUSY", "request queue is full")

    def next_request(self):
        while True:
            if self.cancelled_ids:
                with self.request_lock:
                    self.cancelled_ids.clear()
            item = self.requests.get()
            if item is self.wake:
                return None
            with self.request_lock:
                if item["id"] in self.cancelled_ids:
                    self.cancelled_ids.discard(item["id"])
                    self.queued_ids.discard(item["id"])
                    continue
                self.queued_ids.discard(item["id"])
                self.active_ids.add(item["id"])
            return item

    def finish_request(self, ident):
        with self.request_lock:
            self.active_ids.discard(ident)

    def cancel_request(self, params):
        ident = params.get("id")
        with self.request_lock:
            if ident in self.active_ids:
                self.cancel.set()
                return {"ok": True, "cancelled": ident, "active": True}
            if ident in self.queued_ids:
                self.cancelled_ids.add(ident)
                return {"ok": True, "cancelled": ident, "active": False}
        return {"ok": True, "cancelled": ident, "unknown": True}

    def error_result(self, error):
        if isinstance(error, RpcError):
            return {"code": error.code, "message": str(error), **error.detail}
        return {"code": "EFAILED", "message": str(error)}

    # ── main dispatch ────────────────────────────────────────────────────────
    def dbg(self, p):
        op = str(p.get("op", ""))
        if op not in OPS:
            raise ValueError("unsupported debug operation")

        if op == "load":
            self.launch()
            self.record_event("debugger-loaded")
            return {"ok": True, "op": op, "debugger": "lldb", "targetExecuted": False, **self.state()}

        if op == "state":
            return {"ok": True, **self.state(), "context": self.context()}

        if op == "event":
            st = self.state()
            after = integer(p.get("after", 0))
            events = self.event_list(after)
            return {"ok": True, "events": events[-128:], "eventSeq": self.event_seq,
                    "truncated": len(events) > 128, **st}

        if op == "stop":
            if self.client is not None and self.client.is_debugging():
                with contextlib.suppress(Exception):
                    self.client.close()
            self.record_event("stopped")
            self.run_id = None
            return {"ok": True, "op": op, **self.state()}

        if op == "start":
            if p.get("path"):
                target = inspect_macho(p["path"])
                if self.target and target["bits"] != self.target["bits"]:
                    if self.client is not None:
                        self.client.close()
                self.target = target
            if self.target is None:
                raise RpcError("ETARGET", "no target path provided and none loaded")
            # macOS refuses ptrace attach to platform-signed images. Report the
            # classification instead of launching something that cannot be
            # attached, so the caller can decide rather than read a kernel error.
            prepared = None
            state = signature_state(self.target["path"])
            if state == "protected":
                if p.get("prepare"):
                    prepared = prepare_target(self.target["path"], p.get("prepare_to"))
                    self.target = inspect_macho(prepared["path"])
                else:
                    return {"ok": False, "op": op, "error": "target is code-signed without the debugging entitlement",
                            "code": "ESIGNATURE", "signature": state, "path": self.target["path"],
                            "remedy": "call again with prepare=true to run the target from a re-signed copy",
                            "prepareAvailable": True, **self.state()}
            self.launch()
            self.run_id, self.stop_seq = uuid.uuid4().hex, 0
            with self.event_lock:
                self.events.clear()
            try:
                # `prepare_to` may name the destination file itself, so the
                # default working directory must come from the parent, never
                # from the image path.
                working = p.get("dir") or str(Path(self.target["path"]).parent)
                if not Path(working).is_dir():
                    raise RpcError("EINVAL", f"working directory is not a directory: {working}")
                self.client.start_target(self.target["path"], p.get("args", ""), working)
            except RpcError as error:
                if error.code == "ELAUNCH":
                    # The kernel can still refuse a signature that looked fine,
                    # e.g. a hardened runtime without the entitlement honoured.
                    return {"ok": False, "op": op, "error": str(error), "code": "ESIGNATURE",
                            "signature": signature_state(self.target["path"]), "path": self.target["path"],
                            "remedy": "call again with prepare=true to run the target from a re-signed copy",
                            "prepareAvailable": True, **self.state()}
                raise
            st = self.state()
            if st["state"] == "exited":
                self.record_event("process-exited")
                return {"ok": False, "op": op, "error": "process exited before any stop", **st}
            self.record_event("process-started", {"pid": st.get("pid")})
            result = {"ok": True, "op": op, **st, "context": self.context()}
            if prepared:
                # Carry the full prepare record, including both digests: an
                # execution that ran a re-signed copy must be able to prove
                # which payload was actually launched.
                result["signature"] = dict(prepared)
            return result

        if op == "signature":
            # Read-only probe: classify a target without loading or launching it.
            path = p.get("path") or (self.target or {}).get("path")
            if not path:
                raise RpcError("ETARGET", "signature requires a path or a registered target")
            resolved = Path(path).expanduser().resolve(strict=True)
            state = signature_state(resolved)
            return {"ok": True, "op": op, "path": str(resolved), "signature": state,
                    "debuggable": state in ("unsigned", "debuggable"),
                    "prepareAvailable": state == "protected"}

        if op == "prepare":
            path = p.get("path") or (self.target or {}).get("path")
            if not path:
                raise RpcError("ETARGET", "prepare requires a path or a registered target")
            prepared = prepare_target(path, p.get("destination"))
            if p.get("register", True):
                self.target = inspect_macho(prepared["path"])
            return {"ok": True, "op": op, "signature": prepared}

        if self.client is None:
            raise RpcError("ESTATE", "debugger is not loaded")

        # Read-only operations never require a paused target.
        if op in ("modules", "threads", "callstack"):
            if op == "threads":
                return {"ok": True, "op": op, **self.client.get_threads(), "context": self.context(), **self.state()}
            if op == "callstack":
                return {"ok": True, "op": op, **self.client.get_callstack(), "context": self.context(), **self.state()}
            ea = integer(p["ea"]) if p.get("ea") not in (None, "") else None
            mods = self.client.module_info(ea)
            return {"ok": True, "op": op, "modules": mods, "count": len(mods), **self.state()}

        if op in ("regs", "setreg", "bpt", "unbpt", "step", "stepover", "cont",
                  "suspend", "readmem", "writemem", "trace", "thread_return"):
            self.require_pause()

        if op == "regs":
            data = self.client.get_regs()
            return {"ok": bool(data["regs"]), "op": op, "regs": {k: hex(v) for k, v in data["regs"].items()},
                    "bits": self.target["bits"], "context": self.context(), **self.state()}

        if op == "setreg":
            name = str(p.get("reg", "")).lower()
            if name not in LldbClient.REGISTERS:
                raise ValueError("unsupported target register")
            value = integer(p["value"])
            width = 32 if name == "eflags" or name.startswith("e") and name not in ("eip", "esp", "ebp") else 64
            if value < 0 or value >= 1 << (32 if name == "eflags" else self.target["bits"]):
                raise ValueError("register value is outside target width")
            before = self.client.evaluate(f"${name}")
            if "expected" in p and before != integer(p["expected"]):
                return {"ok": False, "error": "register expected value mismatch", "before": hex(before)}
            self.client.set_reg(name, value)
            after = self.client.evaluate(f"${name}")
            return {"ok": after == value, "op": op, "reg": name, "before": hex(before),
                    "after": hex(after), **self.state()}

        if op in ("bpt", "unbpt"):
            kind, access = str(p.get("kind", "software")), str(p.get("access", "execute"))
            size = integer(p.get("size", 1))
            if kind not in ("software", "hardware") or access not in ("execute", "write", "readwrite"):
                raise ValueError("invalid breakpoint kind or access")
            if kind == "software" and (access != "execute" or size != 1):
                raise ValueError("software breakpoints require execute access and size 1")
            if size not in (1, 2, 4, 8) or (access == "execute" and size != 1):
                raise ValueError("invalid hardware breakpoint size")
            ea = self.address(p, size)
            if kind == "hardware" and ea % size:
                raise ValueError("hardware breakpoint address must be aligned to size")
            name = "set_breakpoint" if op == "bpt" else "clear_breakpoint"
            detail = self.call(name, ea, kind, access, size)
            self.record_event("breakpoint-set" if op == "bpt" else "breakpoint-cleared", {"ea": hex(ea)})
            return {"ok": bool(detail.get("ok")), "op": op, "ea": hex(ea), "kind": kind,
                    "access": access, "size": size, "breakpoint": detail,
                    "context": self.context(ea), **self.state()}

        if op in ("readmem", "writemem"):
            if op == "readmem":
                size = integer(p.get("size", 64))
                if not 1 <= size <= 4096:
                    raise ValueError("readmem size must be 1..4096")
                ea = self.address(p, size)
                data = self.call("read_memory", ea, size)
                return {"ok": True, "op": op, "ea": hex(ea), "size": len(data),
                        "hex": data.hex(), "context": self.context(ea), **self.state()}
            payload = bytes.fromhex(str(p.get("hex", "")))
            if not payload or len(payload) > 4096:
                raise ValueError("writemem hex must be 1..4096 bytes")
            ea = self.address(p, len(payload))
            if p.get("expected") is not None:
                current = self.call("read_memory", ea, len(payload))
                if current.hex() != bytes.fromhex(str(p["expected"])).hex():
                    return {"ok": False, "error": "memory expected value mismatch",
                            "before": current.hex(), **self.state()}
            written = self.call("write_memory", ea, payload)
            readback = self.call("read_memory", ea, len(payload))
            return {"ok": readback == payload, "op": op, "ea": hex(ea), "written": written,
                    "readback": readback.hex(), "context": self.context(ea), **self.state()}

        if op in ("step", "stepover"):
            self.client.step(over=op == "stepover")
            self.stop_seq += 1
            self.record_event("stepped")
            return {"ok": True, "op": op, **self.state(), "context": self.context()}

        if op == "cont":
            self.client.cont()
            self.record_event("resumed")
            return {"ok": True, "op": op, **self.state()}

        if op == "suspend":
            self.client.suspend()
            self.stop_seq += 1
            self.record_event("paused")
            return {"ok": True, "op": op, **self.state(), "context": self.context()}

        if op == "trace":
            budget = integer(p.get("max_steps", 100))
            if not 1 <= budget <= 10000:
                raise ValueError("trace max_steps must be 1..10000")
            until = integer(p["until"]) if p.get("until") not in (None, "") else None
            steps = 0
            for _ in range(budget):
                fr = self.client.frame()
                if until is not None and fr.GetPC() == until:
                    break
                self.client.step()
                steps += 1
                st = self.state()
                if st["state"] != "suspended":
                    break
            self.stop_seq += 1
            self.record_event("trace-complete", {"steps": steps})
            return {"ok": True, "op": op, "traceCounter": steps, "recording": False,
                    "until": hex(until) if until is not None else None, **self.state(), "context": self.context()}

        if op == "thread_return":
            value = integer(p.get("value", 0))
            result = self.client.thread_return(value)
            self.record_event("thread-return", {"value": value})
            return {"ok": bool(result.get("ok")), "op": op, "value": value, "result": result, **self.state()}

        raise ValueError("unsupported debug operation")


def main():
    sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    sys.stdout.reconfigure(encoding="utf-8", errors="strict", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    # LLDB's Python bindings live inside the Xcode framework and are built for
    # the interpreter Xcode ships; prepend that path before importing anything.
    framework = "/Applications/Xcode.app/Contents/SharedFrameworks/LLDB.framework/Resources/Python"
    if framework not in sys.path:
        sys.path.insert(0, framework)

    output_lock = threading.Lock()

    def send(value):
        with output_lock:
            print(json.dumps(plain(value), ensure_ascii=False, separators=(",", ":")), flush=True)

    adapter = Adapter()
    adapter.respond = send

    def reader():
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if (not isinstance(request, dict) or isinstance(request.get("id"), bool)
                        or not isinstance(request.get("id"), (str, int))
                        or not isinstance(request.get("method"), str)):
                    raise ValueError("expected {id,method,params}")
                if request["method"] == "cancel":
                    params = request.get("params") or {}
                    send({"id": request["id"], "result": adapter.cancel_request(params)})
                else:
                    adapter.enqueue(request)
            except RpcError as error:
                send({"id": request.get("id"), "error": {"code": error.code, "message": str(error), **error.detail}})
            except Exception as error:
                send({"id": None, "error": {"code": "EPROTOCOL", "message": str(error)}})
        with adapter.request_lock:
            adapter.shutting_down = True
            adapter.cancel.set()
        with contextlib.suppress(queue.Full):
            adapter.requests.put_nowait(adapter.wake)

    thread = threading.Thread(target=reader, name="ig5-lldb-stdin", daemon=True)
    thread.start()

    # Announce readiness only after the LLDB framework resolves, so the host
    # never routes a request into a worker whose bindings are missing.
    try:
        import lldb as _lldb  # noqa: F401
        send({"ig5": "ready", "engine": "lldb", "capabilities": CAPABILITIES,
              "lldb": _lldb.SBDebugger.GetVersionString().splitlines()[0] if _lldb.SBDebugger.GetVersionString() else None})
    except Exception as error:
        send({"ig5": "ready", "engine": "lldb", "capabilities": [],
              "startupError": f"LLDB Python bindings unavailable: {error}"})

    while True:
        request = adapter.next_request()
        if request is None:
            break
        ident, method, params = request["id"], request["method"], request.get("params") or {}
        try:
            if not isinstance(params, dict):
                raise RpcError("EINVAL", "params must be an object")
            if method == "doctor":
                result = adapter.doctor()
            elif method == "open":
                # Registering a target must never launch it; `dbg start` is the
                # only operation that executes a debuggee.
                target = inspect_macho(params.get("path") or params.get("target"))
                if adapter.client is not None and adapter.client.is_debugging():
                    raise RpcError("ESTATE", "close the debugger before changing the registered target")
                adapter.target = target
                result = {"ok": True, "engine": "lldb", "target": target,
                          "targetExecuted": False, "mode": adapter.config.get("mode", "headless")}
            elif method == "close":
                if adapter.client is not None:
                    with contextlib.suppress(Exception):
                        adapter.client.close()
                adapter.client = None
                adapter.target = None
                adapter.run_id = None
                result = {"ok": True, "engine": "lldb", "closed": True}
            elif method == "dbg":
                result = adapter.dbg(params)
            elif method == "cancel":
                result = adapter.cancel_request(params)
            else:
                raise RpcError("ENOTSUPPORTED", f"unsupported method: {method}")
            send({"id": ident, "result": result})
        except RpcError as error:
            send({"id": ident, "error": adapter.error_result(error)})
        except Exception as error:
            send({"id": ident, "error": adapter.error_result(error)})
        finally:
            adapter.finish_request(ident)
            adapter.cancel.clear()

    if adapter.client is not None:
        with contextlib.suppress(Exception):
            adapter.client.close()


if __name__ == "__main__":
    main()
