# lldb 调试车道

macOS 上 x64dbg 不可用（Windows 专属）。本 fork 接入 Apple LLDB 作为第二个
调试后端，使 `ig5_dbg` 在该平台可用。

---

## 一、设计

复用 x64dbg adapter 的 **JSONL 协议**与结果字段，`ig5_dbg` 的工具面不分叉：

```
index.js  performDebug()
              │
              ├── backend=x64dbg ──→ adapters/x64dbg/adapter.py ──→ NamedPipe ──→ x64dbg headless
              └── backend=lldb  ──→ adapters/lldb/adapter.py  ──→ Python 绑定 ──→ LLDB
```

两条车道的差异：

| | x64dbg | lldb |
| --- | --- | --- |
| 目标格式 | PE | Mach-O |
| 通信 | 自建 NamedPipe bridge | LLDB Python 绑定（进程内） |
| 宿主 | Windows x64 | macOS |
| 运行时 | 随包（`runtimes/x64dbg`） | 复用 Xcode 安装（不随包） |

---

## 二、支持的操作

`adapters/lldb/adapter.py` 的 `OPS`：

```
load  start  bpt  unbpt  regs  setreg  step  stepover  cont  suspend
readmem  writemem  stop  state  event  modules  trace  threads  callstack
signature  prepare
```

除与 x64dbg 对齐的部分外，lldb 车道提供三项额外能力：

| 能力 | 说明 |
| --- | --- |
| `hardware_breakpoint` | `breakpoint set --hardware`，支持 execute/write/readwrite |
| `thread_return` | **跳过函数直接返回指定值**，破解校验路径时无需改代码 |
| `memory_regions` | 内存区域权限枚举 |

---

## 三、LLDB Python 绑定

Apple **不提供独立的 lldb wheel**，绑定随 Xcode 分发，且为 Python 3.9 编译：

```
/Applications/Xcode.app/Contents/SharedFrameworks/LLDB.framework/Resources/Python/lldb/
└── _lldb.cpython-39-darwin.so     Mach-O universal (x86_64 + arm64)
```

因此启动包装脚本在运行时解析解释器路径：

```sh
# runtimes/darwin-x64/lldb/bin/ig5-lldb-python
PY="${IG5_LLDB_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in \
    /Applications/Xcode.app/Contents/Developer/usr/bin/python3.9 \
    /Applications/Xcode-beta.app/Contents/Developer/usr/bin/python3.9
  do [ -x "$candidate" ] && PY="$candidate" && break; done
fi
exec "$PY" "$@"
```

adapter 在导入前把框架路径插入 `sys.path`：

```python
framework = "/Applications/Xcode.app/Contents/SharedFrameworks/LLDB.framework/Resources/Python"
if framework not in sys.path:
    sys.path.insert(0, framework)
```

### 用到的 API

| 用途 | API |
| --- | --- |
| 调试器 | `SBDebugger.Create()` / `SetAsync(False)` |
| 目标 | `CreateTarget(path)` |
| 启动 | `SBLaunchInfo(argv)` + `eLaunchFlagStopAtEntry` |
| 进程 | `SBProcess` / `ReadMemory` / `WriteMemory` / `Continue` / `Stop` / `GetState` |
| 线程 | `SBThread` / `StepInstruction` / `StepOver` / `GetNumFrames` |
| 栈帧 | `SBFrame` / `FindRegister` / `EvaluateExpression` / `GetPC` |
| 断点 | `BreakpointCreateByName` / `breakpoint set --address --hardware` |
| 模块 | `SBModule` / `GetObjectFileHeaderAddress` |

### 踩过的 API 差异

这几个名字与常见文档不同，实测确认：

| 想用的 | 实际可用的 |
| --- | --- |
| `lldb.eStateAttached` | 不存在；状态常量从 `eStateUnloaded=1` 到 `eStateSuspended=11` |
| `SBLaunchInfo.SetStopOnEntry()` | 不存在；用 `SetLaunchFlags(flags \| eLaunchFlagStopAtEntry)` |
| `SBFile.Create(fd)` | 只接受 Python 文件对象：`SBFile.Create(sys.stderr, borrow=True)` |
| `SBModule.GetObjectFileSize()` | 不存在；用 section 或模块头地址推算 |
| `SBFileSpec.GetPath()` | 需要 `dst_path`/`dst_len` 参数；用 `str(filespec)` |
| `SBValueList.GetRegisterSetAtIndex()` | 不存在；用 `GetValueAtIndex()` |

---

## 四、SIP 与目标准备

macOS 拒绝 `ptrace` 附加到平台签名的二进制。adapter 自动处理，
**不需要使用者手写 `codesign` 命令**。

### 4.1 签名状态分类

```python
def signature_state(path):
    """返回 unsigned / debuggable / protected / unknown"""
    # codesign -dv            → 判断 "not signed at all"
    # codesign -d --entitlements - → 判断 get-task-allow
```

实测：

```
/bin/ls                    → protected     debuggable=false  prepareAvailable=true
自编译目标                  → unsigned      debuggable=true   prepareAvailable=false
已准备的副本                → debuggable    debuggable=true   prepareAvailable=false
```

### 4.2 start 的三种路径

**未签名目标** — 直接启动：

```
start: true | state: suspended | pc: 0x100007d90 _dyld_start
```

**受保护目标，未加 prepare** — 不抛内核错误，给出可执行的诊断：

```json
{
  "ok": false,
  "code": "ESIGNATURE",
  "signature": "protected",
  "path": "/bin/ls",
  "remedy": "call again with prepare=true to run the target from a re-signed copy",
  "prepareAvailable": true
}
```

**prepare=true** — 自动复制 + 重签名 + 启动：

```json
{
  "ok": true, "state": "suspended", "pid": 84553,
  "context": { "function": "_dyld_start" },
  "signature": {
    "prepared": true,
    "path": "/var/folders/.../ig5-lldb-xxx/ls-ig5dbg",
    "original": "/bin/ls",
    "state": "debuggable",
    "imageSha256": "d6b646ec...",     ← 签名前载荷摘要，等于原文件摘要
    "signingSha256": "a896f6a6...",   ← 签名后整文件摘要
    "note": "the copy keeps the original payload bytes; only the appended code signature differs"
  }
}
```

内核在签名看似可用时仍可能拒绝启动（硬化运行时未兑现 entitlement），
这种情况同样归一为 `ESIGNATURE` 而不是裸的 `ELAUNCH`。

### 4.3 两个哈希为什么分开

重签名**会改变文件字节**——签名附加到镜像上：

```
/bin/ls                  154624 字节  d6b646ec1ebdd416...
重签名副本                155088 字节  f5b0a0c13debcb8b...
```

| 字段 | 含义 |
| --- | --- |
| `imageSha256` | 签名前的载荷摘要，**等于原文件摘要**——证明"确实是打开的那个二进制" |
| `signingSha256` | 签名后整文件摘要，因附加签名而不同 |

用单个 hash 会混淆"载荷身份"与"落盘文件身份"。

host 层的哈希校验（`index.js` `performDebug`）传的始终是**原始路径**，
副本路径由 adapter 内部产生，因此校验照常通过，不需要开例外。

### 4.4 安全约束

- **原始文件从不修改** — 就地重签名会破坏 Apple 二进制自身的密封，
  可能影响系统其余部分。
- **签名前核对字节一致** — 不一致则拒绝签名，防止张冠李戴。
- **签名后验证 entitlement 生效** — 未生效则拒绝启动。
- **补回可执行位** — `shutil.copyfile` 不带 mode，缺执行位会导致内核拒绝启动。

### 4.5 手动等价流程

需要脱离 IG5 操作时：

```bash
cat > ent.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict><key>com.apple.security.get-task-allow</key><true/></dict>
</plist>
EOF

cp /path/to/target ./target-copy
codesign --remove-signature ./target-copy
codesign --force --sign - --entitlements ent.plist ./target-copy
```

---

## 五、使用

```
# 探测签名状态（只读，不加载也不启动）
ig5_dbg op=signature backend=lldb path=/bin/ls

# 未签名目标直接启动
ig5_dbg op=start backend=lldb path=./target

# 受保护目标自动准备
ig5_dbg op=start backend=lldb path=/bin/ls prepare=true

# 显式准备到指定位置
ig5_dbg op=prepare backend=lldb path=/bin/ls prepare_to=/tmp/prepared

# 常规调试
ig5_dbg op=bpt     backend=lldb ea=0x10000047c
ig5_dbg op=cont    backend=lldb
ig5_dbg op=regs    backend=lldb
ig5_dbg op=readmem backend=lldb ea=0x10000047c size=64
ig5_dbg op=threads backend=lldb
ig5_dbg op=step    backend=lldb
ig5_dbg op=stop    backend=lldb
```

`ig5_dbg` 是**审批门工具**（`IG5_WRITE_TOOLS` 成员），`start` 会执行目标，
每次都需要批准。这条约束没有因为新增 lldb 后端而放宽。

`start` 要求目标与已打开的 artifact 哈希一致，因此**先 `ig5_open`**。

---

## 六、地址空间

`ea` 默认按运行时虚拟地址解释。`addressSpace=database` 时，
`performDebug` 会把数据库地址按 `session.info.imageBase` 转成 RVA：

```js
if (debuggerEngine === 'x64dbg' && params.addressSpace === 'database' && params.ea) {
  // 校验地址落在已加载镜像的 segment 内，再转 rva
}
```

返回的 `context` 含 `moduleBase` 与 `rva`，便于把调试地址映射回静态分析视图。

---

## 七、实测记录

三个场景在真实进程中执行（非 mock）：

```
=== 场景 1：未签名目标 ===
  signature: unsigned | debuggable: true
  start: true | state: suspended | pc: 0x100007d90 _dyld_start
  cont → state: suspended | pc: 0x10000047c check_serial | rva: 0x47c
  regs: rdi = 0x7ff7bfeffe87 | rip = 0x10000047c
  readmem: 488b7df0e8af0000004883f8087409c7
  callstack: check_serial -> main -> start
  step: new pc: 0x100000480

=== 场景 2：受保护目标（不 prepare）===
  signature: protected | debuggable: false | prepareAvailable: true
  start: false | code: ESIGNATURE
  remedy: call again with prepare=true to run the target from a re-signed copy

=== 场景 3：prepare 后调试 ===
  prepare: true | imageSha256 == 原始 sha256: ✅
  start: true | state: suspended | pid: 84553 | pc: 0x100012d90
  regs: rip = 0x100012d90
  modules: 2 | 主模块: ig5-prepared-e2e
```

`start` 使用 `eLaunchFlagStopAtEntry` 停在入口，返回暂停且可检查的进程，
而不是让它跑完退出——语义与 x64dbg 的 `init` 一致。

---

## 八、文件清单

| 文件 | 说明 |
| --- | --- |
| `adapters/lldb/adapter.py` | 调试器监督进程（952 行） |
| `runtimes/darwin-x64/lldb/runtime.json` | 引擎描述 |
| `runtimes/darwin-x64/lldb/bin/ig5-lldb-python` | 解释器包装脚本 |
| `engine_runtime.js` | `engineId` 白名单、`readRuntime` lldb 分支 |
| `source/worker_transport.js` | `IG5_LLDB_RUNTIME` / `IG5_LLDB_STATE_ROOT` |
| `index.js` | `DEBUG_ENGINES` 集合、`defaultDebugger` 平台选择 |

### 校验方式与其他引擎不同

lldb 车道复用宿主安装的调试器，不随包原生二进制，因此
`readRuntime` 不查 Mach-O 头，而是验证 launcher 是带 shebang 的脚本
且 Xcode 框架目录存在：

```js
validation: 'host-debugger-presence', portable: false
```

---

## 九、相关文档

- [DARWIN_X64.md](DARWIN_X64.md) — 平台适配与运行时构建
- [DARWIN_X64_NOTES.md](DARWIN_X64_NOTES.md) — 移植实验记录（含 API 试错）
- [../.ig5-local/README.md](../.ig5-local/README.md) — 维护速查
