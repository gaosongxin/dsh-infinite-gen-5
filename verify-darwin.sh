#!/usr/bin/env bash
# darwin-x64 环境自检。
#
# 用法:
#   ./verify-darwin.sh              # 检查源码仓库
#   ./verify-darwin.sh --plugin     # 检查已部署的插件目录
#   ./verify-darwin.sh --runtime    # 额外校验运行时包完整性（较慢）
#
# 退出码: 0 全部通过 / 1 有检查项失败
set -uo pipefail

cd "$(dirname "$0")"

TARGET="$(pwd)"
CHECK_RUNTIME=0
for arg in "$@"; do
  case "$arg" in
    --plugin)  TARGET="$HOME/.dsh/plugins/dsh-infinite-gen-5" ;;
    --runtime) CHECK_RUNTIME=1 ;;
  esac
done

PASS=0; FAIL=0; WARN=0
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; WARN=$((WARN+1)); }
section() { printf "\n\033[1m%s\033[0m\n" "$1"; }

echo "检查目标: $TARGET"

# ── 1. 源码文件 ──────────────────────────────────────────────────────────────
section "[1] 源码文件"
for f in engine_runtime.js index.js source/host_platform.js source/worker_transport.js \
         adapters/lldb/adapter.py runtimes/darwin-x64/lldb/runtime.json \
         runtimes/darwin-x64/lldb/bin/ig5-lldb-python; do
  [ -e "$TARGET/$f" ] && ok "$f" || bad "$f 缺失"
done

# ── 2. 语法 ─────────────────────────────────────────────────────────────────
section "[2] 语法检查"
for f in engine_runtime.js index.js source/host_platform.js source/worker_transport.js; do
  if [ -f "$TARGET/$f" ]; then
    node --check "$TARGET/$f" 2>/dev/null && ok "$f" || bad "$f 语法错误"
  fi
done
if [ -f "$TARGET/adapters/lldb/adapter.py" ]; then
  python3 -m py_compile "$TARGET/adapters/lldb/adapter.py" 2>/dev/null \
    && ok "adapters/lldb/adapter.py" || bad "adapters/lldb/adapter.py 语法错误"
fi

# ── 3. 平台白名单 ───────────────────────────────────────────────────────────
section "[3] 平台白名单"
if grep -q "darwin-x64" "$TARGET/source/host_platform.js" 2>/dev/null; then
  ok "host_platform.js 含 darwin-x64"
else
  bad "host_platform.js 未含 darwin-x64（上游更新可能覆盖了改动）"
fi
if grep -q "'lldb'" "$TARGET/engine_runtime.js" 2>/dev/null; then
  ok "engine_runtime.js 注册 lldb 引擎"
else
  bad "engine_runtime.js 未注册 lldb"
fi
if grep -q "DEBUG_ENGINES" "$TARGET/index.js" 2>/dev/null; then
  ok "index.js 含 DEBUG_ENGINES 集合"
else
  bad "index.js 缺少 DEBUG_ENGINES"
fi

# ── 4. 运行时 ───────────────────────────────────────────────────────────────
section "[4] 运行时"
RT="$TARGET/runtimes/darwin-x64"
if [ ! -d "$RT" ]; then
  if [ "$TARGET" = "$HOME/.dsh/plugins/dsh-infinite-gen-5" ]; then
    bad "运行时目录缺失: $RT"
  else
    warn "源码仓库不含运行时（由 .gitignore 排除，属正常）"
  fi
else
  ok "运行时目录存在: $(du -sh "$RT" 2>/dev/null | cut -f1)"
  for f in manifest.json ghidra/runtime.json lldb/runtime.json; do
    [ -f "$RT/$f" ] && ok "$f" || bad "$f 缺失"
  done

  GH="$RT/ghidra/ghidra_12.1.4_PUBLIC"
  if [ -d "$GH" ]; then
    ok "Ghidra: $(grep '^application.version=' "$GH/Ghidra/application.properties" 2>/dev/null | cut -d= -f2)"
    for f in Ghidra/Features/Decompiler/os/mac_x86_64/decompile \
             Ghidra/Features/Decompiler/os/mac_x86_64/sleigh \
             Ghidra/Features/Base/lib/Base.jar \
             Ghidra/Features/PyGhidra/lib/PyGhidra.jar; do
      [ -e "$GH/$f" ] && ok "$(basename "$f")" || bad "$f 缺失"
    done
    # decompiler 必须是 Mach-O x86_64
    if file "$GH/Ghidra/Features/Decompiler/os/mac_x86_64/decompile" 2>/dev/null | grep -q "Mach-O 64-bit executable x86_64"; then
      ok "native decompiler 是 Mach-O x86_64"
    else
      bad "native decompiler 架构不符（需本地编译 mac_x86_64）"
    fi
  else
    bad "Ghidra 目录缺失"
  fi

  PY="$RT/ghidra/python/bin/python3.12"
  if [ -x "$PY" ]; then
    ok "Python: $("$PY" -V 2>&1)"
    "$PY" -c "import pyghidra, jpype" 2>/dev/null && ok "PyGhidra + JPype 可导入" || bad "PyGhidra/JPype 导入失败"
  else
    bad "python3.12 缺失"
  fi

  [ -x "$RT/lldb/bin/ig5-lldb-python" ] && ok "lldb 启动包装脚本可执行" || bad "lldb 包装脚本缺失或不可执行"

  if [ "$CHECK_RUNTIME" = "1" ]; then
    echo "  … 校验清单（8168 项，约 20 秒）"
    if python3 - "$RT" <<'PY' 2>/dev/null
import os, json, hashlib, sys
root = sys.argv[1]
manifest = json.load(open(os.path.join(root, 'manifest.json'), encoding='utf-8'))
bad = 0
for entry in manifest['files']:
    full = os.path.join(root, entry['path'])
    if not os.path.isfile(full):
        bad += 1; continue
    if os.path.getsize(full) != entry['bytes']:
        bad += 1; continue
    h = hashlib.sha256()
    with open(full, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''): h.update(chunk)
    if h.hexdigest() != entry['sha256']:
        bad += 1
sys.exit(1 if bad else 0)
PY
    then
      ok "清单校验通过"
    else
      bad "清单校验失败（运行时被改动后需重新生成 manifest.json）"
    fi
  fi
fi

# ── 5. Xcode / lldb ─────────────────────────────────────────────────────────
section "[5] Xcode 与 lldb"
FRAMEWORK="/Applications/Xcode.app/Contents/SharedFrameworks/LLDB.framework"
[ -d "$FRAMEWORK" ] && ok "LLDB.framework 存在" || bad "LLDB.framework 缺失（需安装 Xcode）"
[ -d "$FRAMEWORK/Resources/Python/lldb" ] && ok "LLDB Python 绑定存在" || bad "LLDB Python 绑定缺失"
XPY="/Applications/Xcode.app/Contents/Developer/usr/bin/python3.9"
if [ -x "$XPY" ]; then
  ok "Xcode Python: $("$XPY" -V 2>&1)"
  LLDB_VER=$("$XPY" -c "import sys; sys.path.insert(0,'$FRAMEWORK/Resources/Python'); import lldb; print(lldb.SBDebugger.GetVersionString().splitlines()[0])" 2>/dev/null)
  [ -n "$LLDB_VER" ] && ok "lldb: $LLDB_VER" || bad "lldb Python 绑定无法导入"
else
  bad "Xcode Python 3.9 缺失（lldb 车道依赖它）"
fi
command -v codesign >/dev/null && ok "codesign 可用" || bad "codesign 缺失"

# ── 6. 宿主 DSH ─────────────────────────────────────────────────────────────
section "[6] DSH 宿主"
DSH_ROOT=/usr/local/lib/node_modules/@deepseek-ai/dsh
if [ -f "$DSH_ROOT/package.json" ]; then
  VER=$(python3 -c "import json;print(json.load(open('$DSH_ROOT/package.json'))['version'])" 2>/dev/null)
  ok "DSH $VER"
  case "$VER" in
    0.2.*) ok "版本落在声明范围 >=0.2.0-rc.1 <0.3.0-0" ;;
    *) warn "版本 $VER 超出声明范围" ;;
  esac
else
  warn "未找到 DSH 安装"
fi
if [ -f "$HOME/.dsh/profiles/web/package.json" ]; then
  grep -q "dsh-infinite-gen-5" "$HOME/.dsh/profiles/web/package.json" \
    && ok "插件已注册到 web profile" || bad "插件未注册到 web profile"
fi
pgrep -f "dsh web" >/dev/null 2>&1 && ok "DSH 进程运行中" || warn "DSH 未运行"

# ── 7. 引擎可用性 ───────────────────────────────────────────────────────────
section "[7] 引擎可用性"
if [ -f "$TARGET/engine_runtime.js" ] && [ -d "$RT" ]; then
  node -e "
    import('$TARGET/engine_runtime.js').then(m => {
      const c = m.runtimeConfiguration({});
      const line = (n, v, d) => console.log('  ' + (v ? '\033[32m✓\033[0m' : '\033[31m✗\033[0m') + ' ' + n.padEnd(10) + (d || ''));
      // x64dbg is Windows-only by design; report it as expected-absent, not a failure.
      const x64 = c.x64dbg.available ? '\033[32m✓\033[0m' : '\033[33m·\033[0m';
      line('host', true, c.host.id + ' supported=' + c.host.supported);
      line('ghidra', c.ghidra.available, c.ghidra.validation);
      line('lldb', c.lldb.available, c.lldb.validation);
      console.log('  ' + x64 + ' x64dbg    ' + (c.x64dbg.available ? 'available' : 'Windows 专属，darwin 不适用'));
      process.exit(0);
    }).catch(e => { console.log('  \033[31m✗\033[0m 加载失败: ' + e.message); process.exit(0); });
  " 2>/dev/null
else
  warn "跳过（缺 engine_runtime.js 或运行时目录）"
fi

# ── 汇总 ────────────────────────────────────────────────────────────────────
section "汇总"
printf "  通过 %d" "$PASS"
[ "$WARN" -gt 0 ] && printf " / 警告 %d" "$WARN"
[ "$FAIL" -gt 0 ] && printf " / \033[31m失败 %d\033[0m" "$FAIL"
printf "\n"

if [ "$FAIL" -gt 0 ]; then
  cat <<'EOF'

失败项处理建议：
  · host_platform.js / engine_runtime.js / index.js 缺改动 → 上游更新覆盖，
    用 git checkout 恢复或重新应用 fork 的改动
  · 运行时目录缺失或清单校验失败 → 见 docs/DARWIN_X64.md §4 重建
  · Xcode / lldb 缺失 → 安装 Xcode（lldb 车道依赖其 Python 绑定）
EOF
  exit 1
fi
echo "  ✅ 全部检查通过"
