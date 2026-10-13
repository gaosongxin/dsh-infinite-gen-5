#!/usr/bin/env bash
# darwin-x64 一键安装。
#
# 用法:
#   ./install-darwin.sh                # 完整安装（构建运行时 + 部署到 DSH）
#   ./install-darwin.sh --runtime-only # 只构建运行时，不部署
#   ./install-darwin.sh --deploy-only  # 只部署（运行时已就绪）
#   ./install-darwin.sh --reuse <路径> # 从已有插件目录复制运行时（最快）
#
# 前置条件:
#   · macOS Intel (darwin-x64)
#   · Node.js 22+ / pnpm / python3 / git / curl
#   · 完整 Xcode（lldb 车道需要其 Python 绑定；仅 Command Line Tools 不够）
#
# 退出码: 0 成功 / 1 失败
set -euo pipefail

cd "$(dirname "$0")"
REPO="$(pwd)"
PLUGIN_DIR="$HOME/.dsh/plugins/dsh-infinite-gen-5"
RUNTIME="$REPO/runtimes/darwin-x64"
GHIDRA_VER="12.1.4"
GHIDRA_ZIP="ghidra_${GHIDRA_VER}_PUBLIC_20260921.zip"
GHIDRA_URL="https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VER}_build/${GHIDRA_ZIP}"
JDK_URL="https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_mac_hotspot_21.0.12.1_1.tar.gz"
BUILD_DIR="${IG5_BUILD_DIR:-$HOME/.cache/ig5-build}"

MODE="full"; REUSE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --runtime-only) MODE="runtime" ;;
    --deploy-only)  MODE="deploy" ;;
    --reuse)        REUSE="${2:-}"; shift ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
  shift
done

step() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
ok()   { printf "    \033[32m✓\033[0m %s\n" "$1"; }
info() { printf "    %s\n" "$1"; }
die()  { printf "    \033[31m✗ %s\033[0m\n" "$1"; exit 1; }

# ── 0. 平台前置检查 ─────────────────────────────────────────────────────────
step "平台检查"
[ "$(uname -s)" = "Darwin" ] || die "仅支持 macOS"
ARCH="$(uname -m)"
[ "$ARCH" = "x86_64" ] || die "当前只支持 Intel (x86_64)；检测到 $ARCH。Apple Silicon 需要单独构建 arm64 运行时"
ok "macOS $(sw_vers -productVersion) / $ARCH"

for cmd in git curl node python3; do
  command -v "$cmd" >/dev/null || die "缺少命令: $cmd"
done
ok "git / curl / node $(node -v) / python3 $(python3 -V 2>&1 | cut -d' ' -f2)"

XCODE_PY="/Applications/Xcode.app/Contents/Developer/usr/bin/python3.9"
if [ ! -x "$XCODE_PY" ]; then
  info "⚠️  未找到完整 Xcode ($XCODE_PY)"
  info "    lldb 调试车道依赖 Xcode 自带的 LLDB Python 绑定"
  info "    安装 Xcode 后可重跑本脚本补齐；静态分析不受影响"
  LLDB_OK=0
else
  ok "Xcode Python $("$XCODE_PY" -V 2>&1 | cut -d' ' -f2)"
  LLDB_OK=1
fi

# ── 1. 运行时 ───────────────────────────────────────────────────────────────
if [ "$MODE" = "full" ] || [ "$MODE" = "runtime" ]; then

  if [ -n "$REUSE" ]; then
    step "从已有安装复制运行时"
    SRC="$REUSE/runtimes/darwin-x64"
    [ -d "$SRC" ] || die "源运行时不存在: $SRC"
    info "源: $SRC ($(du -sh "$SRC" | cut -f1))"
    mkdir -p "$RUNTIME"
    rsync -a --delete "$SRC/" "$RUNTIME/"
    ok "运行时已复制 ($(du -sh "$RUNTIME" | cut -f1))"

  elif [ -f "$RUNTIME/manifest.json" ] && [ -x "$RUNTIME/ghidra/python/bin/python3.12" ]; then
    step "运行时已存在，跳过构建"
    ok "$(du -sh "$RUNTIME" | cut -f1)"

  else
    step "构建运行时 (约 1.5 GB 下载，视网络 10-30 分钟)"
    mkdir -p "$BUILD_DIR" "$RUNTIME/ghidra"
    cd "$BUILD_DIR"

    # 1.1 下载
    if [ ! -f "$GHIDRA_ZIP" ]; then
      info "下载 Ghidra $GHIDRA_VER (570 MB)..."
      curl -fSL --retry 5 --retry-delay 3 --retry-all-errors -C - -o "$GHIDRA_ZIP" "$GHIDRA_URL" \
        || die "Ghidra 下载失败"
    fi
    ok "Ghidra 包 $(du -h "$GHIDRA_ZIP" | cut -f1)"

    if [ ! -f "jdk.tar.gz" ]; then
      info "下载 Temurin JDK 21 (185 MB)..."
      curl -fSL --retry 5 --retry-delay 3 --retry-all-errors -C - -o "jdk.tar.gz" "$JDK_URL" \
        || die "JDK 下载失败"
    fi
    tar tzf jdk.tar.gz >/dev/null 2>&1 || die "JDK 包损坏，删除 $BUILD_DIR/jdk.tar.gz 后重试"
    ok "JDK 包 $(du -h jdk.tar.gz | cut -f1)"

    # 1.2 解压
    if [ ! -d "$RUNTIME/ghidra/ghidra_${GHIDRA_VER}_PUBLIC" ]; then
      info "解压 Ghidra…"
      unzip -q -o "$GHIDRA_ZIP" -d "$RUNTIME/ghidra/"
      # 官方 zip 顶层目录名可能与版本号不同，统一改名为期望值。
      # 过滤模式必须双引号展开，否则排除条件失效、mv 会把目录移进它自己。
      ACTUAL="$(find "$RUNTIME/ghidra" -maxdepth 1 -type d -name 'ghidra_*' ! -name "ghidra_${GHIDRA_VER}_PUBLIC" | head -1)"
      if [ -n "$ACTUAL" ] && [ "$ACTUAL" != "$RUNTIME/ghidra/ghidra_${GHIDRA_VER}_PUBLIC" ]; then
        mv "$ACTUAL" "$RUNTIME/ghidra/ghidra_${GHIDRA_VER}_PUBLIC"
      fi
    fi
    ok "Ghidra 已解压"

    if [ ! -d "$RUNTIME/ghidra/jdk-21.0.12.1+1" ]; then
      info "解压 JDK…"
      tar xzf jdk.tar.gz -C "$RUNTIME/ghidra/"
    fi
    ok "JDK 已解压"

    GH="$RUNTIME/ghidra/ghidra_${GHIDRA_VER}_PUBLIC"
    JDK_HOME="$RUNTIME/ghidra/jdk-21.0.12.1+1/Contents/Home"

    # 1.3 编译 native decompiler
    if [ ! -x "$GH/Ghidra/Features/Decompiler/os/mac_x86_64/decompile" ]; then
      step "编译 native decompiler（Apple clang）"
      CPP="$GH/Ghidra/Features/Decompiler/src/decompile/cpp"
      [ -d "$CPP" ] || die "缺少 decompiler 源码目录"
      ( cd "$CPP" && make ghidra_opt -j"$(sysctl -n hw.ncpu)" >/dev/null 2>&1 ) \
        || die "ghidra_opt 编译失败，手动运行: cd $CPP && make ghidra_opt"
      ( cd "$CPP" && make sleigh_opt -j"$(sysctl -n hw.ncpu)" >/dev/null 2>&1 ) \
        || die "sleigh_opt 编译失败"
      mkdir -p "$GH/Ghidra/Features/Decompiler/os/mac_x86_64"
      cp "$CPP/ghidra_opt" "$GH/Ghidra/Features/Decompiler/os/mac_x86_64/decompile"
      cp "$CPP/sleigh_opt" "$GH/Ghidra/Features/Decompiler/os/mac_x86_64/sleigh"
      chmod +x "$GH/Ghidra/Features/Decompiler/os/mac_x86_64/"*
      ok "decompile + sleigh 已编译部署"
    else
      ok "native decompiler 已存在"
    fi
    file "$GH/Ghidra/Features/Decompiler/os/mac_x86_64/decompile" | grep -q "x86_64" \
      || die "decompiler 架构不符"

    # 1.4 Python 运行时
    if [ ! -x "$RUNTIME/ghidra/python/bin/python3.12" ]; then
      step "准备 Python 3.12 运行时"
      # 优先用 uv 已下载的 CPython；否则用官方 python-build-standalone
      PYSRC=""
      for cand in "$HOME"/.local/share/uv/python/cpython-3.12.*-macos-x86_64-none; do
        [ -x "$cand/bin/python3.12" ] && PYSRC="$cand" && break
      done
      if [ -z "$PYSRC" ]; then
        info "未找到本地 CPython 3.12，从 python-build-standalone 下载..."
        PBS_TAG="20261009"
        PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-3.12.12+${PBS_TAG}-x86_64-apple-darwin-install_only.tar.gz"
        curl -fSL --retry 3 -o "$BUILD_DIR/python.tar.gz" "$PBS_URL" || die "Python 下载失败"
        mkdir -p "$BUILD_DIR/pyextract"
        tar xzf "$BUILD_DIR/python.tar.gz" -C "$BUILD_DIR/pyextract"
        PYSRC="$BUILD_DIR/pyextract/python"
      fi
      [ -x "$PYSRC/bin/python3.12" ] || die "Python 3.12 源不可用"
      mkdir -p "$RUNTIME/ghidra/python"
      for d in bin lib include share; do
        [ -d "$PYSRC/$d" ] && cp -R "$PYSRC/$d" "$RUNTIME/ghidra/python/"
      done
      cp "$PYSRC/BUILD" "$RUNTIME/ghidra/python/" 2>/dev/null || true
      PY="$RUNTIME/ghidra/python/bin/python3.12"
      find "$RUNTIME/ghidra/python/lib" -name "EXTERNALLY-MANAGED" -delete 2>/dev/null || true
      info "安装 PyGhidra 与 JPype (用 Ghidra 自带 wheel，版本必须配对)..."
      "$PY" -m pip install -q --no-warn-script-location --no-index \
        "$GH/Ghidra/Features/PyGhidra/pypkg/dist/jpype1-1.5.2-cp312-cp312-macosx_10_9_universal2.whl" \
        "$GH/Ghidra/Features/PyGhidra/pypkg/dist/packaging-25.0-py3-none-any.whl" \
        "$GH/Ghidra/Features/PyGhidra/pypkg/dist/pyghidra-3.1.0-py3-none-any.whl" \
        || die "Python 依赖安装失败"
      # 校验器要求 LICENSE.txt 存在
      curl -fsSL -o "$RUNTIME/ghidra/python/LICENSE.txt" \
        "https://raw.githubusercontent.com/python/cpython/v3.12.15/LICENSE" 2>/dev/null \
        || echo "Python License" > "$RUNTIME/ghidra/python/LICENSE.txt"
      "$PY" -c "import pyghidra, jpype" || die "PyGhidra/JPype 导入失败"
      ok "Python $("$PY" -V 2>&1 | cut -d' ' -f2) + PyGhidra + JPype"
    else
      ok "Python 运行时已存在"
    fi

    # 1.45 ghidra 引擎描述
    # 上游只在 Windows 包里由 runtime_pack.ps1 生成这份 runtime.json；
    # 宿主的 readRuntime 校验器与 build_patch.py 都要求它存在，darwin 侧需自行落盘。
    if [ ! -f "$RUNTIME/ghidra/runtime.json" ]; then
      step "生成 ghidra/runtime.json"
      cat > "$RUNTIME/ghidra/runtime.json" <<JSON
{
  "schemaVersion": 1,
  "engine": "Ghidra",
  "version": "${GHIDRA_VER}",
  "platform": "darwin-x64",
  "pythonVersion": "3.12",
  "pythonExe": "python/bin/python3.12",
  "pythonLibrary": "python/lib/libpython3.12.dylib",
  "pythonStdlib": "python/lib/python3.12",
  "pythonModules": "python/lib/python3.12/site-packages",
  "jpypeLibrary": "python/lib/python3.12/site-packages/_jpype.cpython-312-darwin.so",
  "ghidraHome": "ghidra_${GHIDRA_VER}_PUBLIC",
  "javaHome": "jdk-21.0.12.1+1/Contents/Home",
  "projectRoot": "projects"
}
JSON
      ok "ghidra/runtime.json 已生成"
    else
      ok "ghidra/runtime.json 已存在"
    fi

    # 1.5 项目路径补丁
    if ! grep -q "localProjectPathPatch" "$RUNTIME/ghidra/runtime.json" 2>/dev/null; then
      step "应用项目路径补丁 (让 .dsh 目录可用)"
      UPSTREAM_JAVA="third_party/sources/ghidra-${GHIDRA_VER}/Ghidra/Framework/Project/src/main/java/ghidra/framework/protocol/ghidra/GhidraURL.java"
      if [ ! -f "$REPO/$UPSTREAM_JAVA" ]; then
        info "从官方 Project-src.zip 提取补丁基准..."
        mkdir -p "$(dirname "$REPO/$UPSTREAM_JAVA")"
        python3 - "$GH" "$REPO/$UPSTREAM_JAVA" <<'PY'
import sys, zipfile, pathlib
gh, dest = sys.argv[1], pathlib.Path(sys.argv[2])
entry = 'ghidra/framework/protocol/ghidra/GhidraURL.java'
src = pathlib.Path(gh) / 'Ghidra/Framework/Project/lib/Project-src.zip'
dest.write_bytes(zipfile.ZipFile(src).read(entry))
PY
      fi
      "$RUNTIME/ghidra/python/bin/python3.12" -I -B \
        "$REPO/adapters/ghidra/local-project-path/build_patch.py" \
        --project "$REPO" --runtime-root "$RUNTIME/ghidra" \
        --artifact-root "$HOME/.dsh/ig5/artifacts/ghidra-local-project-path-build" \
        || die "项目路径补丁失败"
      ok "补丁 ig5-ghidra-local-project-path-v1 已应用"
    else
      ok "项目路径补丁已应用"
    fi

    # 1.6 生成清单
    step "生成运行时清单"
    ( cd "$RUNTIME" && python3 - <<'PY'
import os, json, hashlib
root = os.getcwd(); files = []
for dirpath, _, filenames in os.walk(root):
    for name in filenames:
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, root).replace('\\', '/')
        if os.path.islink(full) or rel == 'manifest.json': continue
        h = hashlib.sha256()
        with open(full, 'rb') as fh:
            for c in iter(lambda: fh.read(1 << 20), b''): h.update(c)
        files.append({'path': rel, 'bytes': os.path.getsize(full), 'sha256': h.hexdigest()})
files.sort(key=lambda e: e['path'])
json.dump({'schemaVersion': 1, 'pluginVersion': '1.0.0', 'platform': 'darwin-x64',
           'engines': ['ghidra', 'lldb'], 'files': files},
          open('manifest.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f"    {len(files)} 个文件")
PY
    ) || die "清单生成失败"
    ok "manifest.json 已生成"
  fi

  [ "$MODE" = "runtime" ] && { step "完成（--runtime-only，未部署）"; exit 0; }
fi

# ── 2. 部署 ─────────────────────────────────────────────────────────────────
step "部署到 DSH 插件目录"
mkdir -p "$PLUGIN_DIR"

if [ -d "$PLUGIN_DIR/runtimes" ] && [ "$MODE" = "deploy" ]; then
  info "保留已有运行时"
fi

# The deployment direction is repository -> plugin. Editing the plugin directly
# and forgetting to copy back means the next deploy silently reverts that work,
# so surface the difference before overwriting anything.
if [ -d "$PLUGIN_DIR" ] && [ "$(cd "$REPO" && git rev-parse --git-dir 2>/dev/null)" ]; then
  DRIFT=""
  for rel in index.js client.js engine_runtime.js advanced_tools.js analysis_tools.js \
             integration_tools.js workflow.js source adapters; do
    [ -e "$REPO/$rel" ] || continue
    # Ignore compiled caches and editor droppings: they are not source and are
    # regenerated, so treating them as drift would cry wolf on every run.
    if ! diff -rq -x '__pycache__' -x '*.pyc' -x '.DS_Store' "$REPO/$rel" "$PLUGIN_DIR/$rel" >/dev/null 2>&1; then
      DRIFT="$DRIFT $rel"
    fi
  done
  if [ -n "$DRIFT" ]; then
    info "⚠️  插件目录存在仓库中没有的改动:$DRIFT"
    info "    部署会覆盖它们。确认不需要保留后再继续；"
    info "    要保留请先复制回仓库并提交。"
    printf "    继续部署？[y/N] "
    read -r answer
    case "$answer" in
      y|Y) ;;
      *) die "已取消（未改动任何文件）" ;;
    esac
  fi
fi

rsync -a --delete \
  --exclude='runtimes' --exclude='third_party' \
  --exclude='.git' --exclude='.ig5-local' \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
  "$REPO/" "$PLUGIN_DIR/"
ok "源码已同步"

if [ ! -d "$PLUGIN_DIR/runtimes/darwin-x64" ]; then
  info "复制运行时 (1.3 GB，约 1 分钟)..."
  mkdir -p "$PLUGIN_DIR/runtimes"
  rsync -a "$RUNTIME/" "$PLUGIN_DIR/runtimes/darwin-x64/"
fi
ok "运行时已就位 ($(du -sh "$PLUGIN_DIR/runtimes/darwin-x64" | cut -f1))"

# profile 注册：用软链接指向插件真身，避免 pnpm 硬链接副本缺 runtimes
PROFILE_NM="$HOME/.dsh/profiles/web/node_modules"
if [ -d "$HOME/.dsh/profiles/web" ]; then
  step "注册到 web profile"
  if [ -f "$HOME/.dsh/profiles/web/package.json" ] \
     && ! grep -q "dsh-infinite-gen-5" "$HOME/.dsh/profiles/web/package.json"; then
    info "使用官方命令注册..."
    ( cd "$HOME/.dsh/profiles/web" && dsh plugin --profile web add "file:$PLUGIN_DIR" >/dev/null 2>&1 ) \
      || info "注册命令失败，请手动运行: dsh plugin --profile web add file:$PLUGIN_DIR"
  fi
  if [ -d "$PROFILE_NM" ]; then
    if [ -d "$PROFILE_NM/dsh-infinite-gen-5" ] && [ ! -L "$PROFILE_NM/dsh-infinite-gen-5" ]; then
      mv "$PROFILE_NM/dsh-infinite-gen-5" "$PROFILE_NM/.dsh-infinite-gen-5.hoisted-bak"
      info "已备份 pnpm 硬链接副本"
    fi
    rm -f "$PROFILE_NM/dsh-infinite-gen-5"
    ln -s "$PLUGIN_DIR" "$PROFILE_NM/dsh-infinite-gen-5"
    ok "软链接已建立 (pnpm 副本不含 runtimes，必须指向真身)"
  fi
else
  info "未找到 web profile，跳过注册 (首次启动 DSH 后再运行本脚本 --deploy-only)"
fi

# ── 3. 验证 ─────────────────────────────────────────────────────────────────
step "验证"
"$REPO/verify-darwin.sh" --plugin 2>&1 | tail -18 || true

cat <<EOF

$(printf '\033[1m完成\033[0m')

下一步：
  1. 完全退出并重启 DSH（无 --expose-internals，代码不热加载）
  2. 在会话中确认：
       ig5_doctor                       → runtimeReady / startupVerified 为 true
       ig5_dbg op=signature backend=lldb path=/bin/ls
  3. 静态分析：ig5_open <目标路径>，然后 ig5_funcs / ig5_decompile / ig5_cfg …
  4. 动态调试：ig5_dbg op=start backend=lldb path=<目标> prepare=true

文档：docs/DARWIN_X64.md · docs/LLDB_LANE.md
EOF
