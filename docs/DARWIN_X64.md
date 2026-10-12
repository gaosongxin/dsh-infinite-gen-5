# darwin-x64 平台适配

本 fork 为 **macOS Intel (darwin-x64)** 增加了完整的分析与调试能力。
上游 IG5 只支持 `win32-x64` 与 `linux-arm64`，且发行附件仅有 Windows x64 包。

- fork：<https://github.com/pyt111/dsh-infinite-gen-5>
- 上游：<https://github.com/Minglink/dsh-infinite-gen-5>
- 分叉点：`314d896 Update README.md`
- 分支：`master` 与 `darwin-x64` 内容一致

---

## 一、能力矩阵

| 引擎 | 平台 | 状态 | 说明 |
| --- | --- | --- | --- |
| `reverse` / `ghidra` | darwin-x64 | ✅ 可用 | 静态分析，本地构建运行时 |
| `lldb` | darwin-x64 | ✅ 可用 | 原生调试，见 [LLDB_LANE](LLDB_LANE.md) |
| `x64dbg` | darwin-x64 | ❌ 不可用 | Windows 专属，无跨平台实现 |
| `ig5_emulate` | darwin-x64 | ❌ 不可用 | 随包 Unicorn 仅 Windows DLL |

38 项工具中 36 项在 darwin-x64 可用；缺失的是 `ig5_dbg` 的 x64dbg 后端
（已由 lldb 后端替代）与 `ig5_emulate`。

---

## 二、上游平台的硬编码点

上游把平台判定集中在少数位置，这是移植的入手点：

| 位置 | 上游逻辑 | 影响 |
| --- | --- | --- |
| `source/host_platform.js:13` | `supported = id === 'win32-x64' \|\| id === 'linux-arm64'` | 白名单，darwin 直接判不支持 |
| `engine_runtime.js` `windows` 分支 | JDK/JPype/decompiler 路径全部按 Windows 或 Linux-ARM64 写死 | 校验必然失败 |
| `engine_runtime.js:68` | `engine === 'x64dbg' && !windows` | 调试器平台门禁 |
| `source/reverse_runtime.js:31` | `if (host.id !== 'win32-x64') return fail('platform')` | 商业 Reverse 也仅 Windows |
| `source/worker_transport.js:16` | 仅 `linux` 使用 posix 路径与 `detached` | darwin 走错分支 |
| `scripts/runtime_pack.ps1:147` | 清单 `platform` 必须为 `win32-x64` | 官方安装器拒绝非 Windows 运行时 |

上游 `Ghidra/Features/Decompiler/buildNatives.gradle` 本身**列出**了
`mac_x86_64` 目标平台，只是官方发行 ZIP 未预编译该产物。这是移植可行的前提。

---

## 三、改动清单

### 3.1 平台白名单

`source/host_platform.js`

```js
const supported = id === 'win32-x64' || id === 'linux-arm64' || id === 'darwin-x64';
```

补充 darwin 的平台不支持说明文案（区分 Apple Silicon 与 Intel）。

### 3.2 Mach-O 校验

`engine_runtime.js` 新增 `machoArchitecture()`，替代非 Windows 分支里的
`elfArchitecture()`。支持单架构与 universal binary（检查是否含 x86_64 slice）：

```js
const MH_MAGIC_64 = 0xfeedfacf, FAT_MAGIC = 0xcafebabe;
const CPU_TYPE_X86_64 = 0x01000007;
// 单架构：读 cputype；fat：遍历 20 字节表项找 x86_64
```

### 3.3 平台分支拆分

`engine_runtime.js` 原本用 `windows ? A : B` 二选一，现在拆出 darwin：

| 组件 | Windows | Linux-ARM64 | darwin-x64 |
| --- | --- | --- | --- |
| JVM | `bin/server/jvm.dll` | `lib/server/libjvm.so` | `lib/server/libjvm.dylib` |
| JVM 启动器 | `bin/java.exe` | `lib/jli/libjli.so` | `lib/libjli.dylib` |
| decompiler | `os/win_x86_64/decompile.exe` | `os/linux_arm_64/decompile` | `os/mac_x86_64/decompile` |
| JDK 架构标记 | `OS_ARCH="x86_64"` | `OS_ARCH="aarch64"` | `OS_ARCH="x86_64"` |
| JPype | `_jpype.cp312-win_amd64.pyd` | `_jpype.cpython-312-aarch64-linux-gnu.so` | `_jpype.cpython-312-darwin.so` |
| validation 标签 | `structure-and-pe-headers` | `structure-and-elf-headers` | `structure-and-macho-headers` |

### 3.4 进程组

`source/worker_transport.js` — POSIX 进程组从只认 linux 扩到 darwin，
使超时清理能覆盖 native decompiler 子进程：

```js
const posixHost = cfg.host?.platform === 'linux' || cfg.host?.platform === 'darwin';
const paths = posixHost ? path.posix : path;
// ...
...(posixHost ? { detached: true } : {}),
```

### 3.5 补丁构建脚本

`adapters/ghidra/local-project-path/build_patch.py` — javac 路径按平台选择：

```python
javac = java_home / ('bin/javac.exe' if os.name == 'nt' else 'bin/javac')
```

---

## 四、运行时构建

### 4.1 目录结构

```
runtimes/darwin-x64/
├── manifest.json                        8168 个文件的 SHA-256 清单
├── ghidra/
│   ├── runtime.json
│   ├── ghidra_12.1.4_PUBLIC/            Ghidra 12.1.4（官方）
│   │   └── Ghidra/Features/Decompiler/os/mac_x86_64/
│   │       ├── decompile                ★ 本地编译
│   │       └── sleigh                   ★ 本地编译
│   ├── jdk-21.0.12.1+1/                 Temurin JDK 21 x86_64
│   └── python/                          CPython 3.12.15 + PyGhidra 3.1.0 + JPype 1.5.2
└── lldb/
    ├── runtime.json
    └── bin/ig5-lldb-python              启动包装脚本
```

总计约 1.3 GB。`runtimes/` 在 `.gitignore` 中，不入库。

### 4.2 组件版本

| 组件 | 版本 | 来源 |
| --- | --- | --- |
| Ghidra | 12.1.4 PUBLIC | `Ghidra_12.1.4_build` / `ghidra_12.1.4_PUBLIC_20260921.zip` |
| JDK | Temurin 21.0.12.1+1 | Adoptium `x64_mac` |
| CPython | 3.12.15 | uv 管理的 `cpython-3.12.15-macos-x86_64-none` |
| PyGhidra | 3.1.0 | **Ghidra 自带** `Ghidra/Features/PyGhidra/pypkg/dist/` |
| JPype | 1.5.2 | 同上（必须与引擎版本配对，不用 PyPI 最新版） |
| lldb | lldb-1700.0.9.502 | Xcode 自带 |

### 4.3 编译 native decompiler

官方 ZIP 只含 `linux_x86_64` 与 `win_x86_64`，`mac_x86_64` 需本地编译：

```bash
cd runtimes/darwin-x64/ghidra/ghidra_12.1.4_PUBLIC/Ghidra/Features/Decompiler/src/decompile/cpp
make ghidra_opt -j4      # → Mach-O 64-bit executable x86_64
make sleigh_opt  -j4
mkdir -p ../../os/mac_x86_64
cp ghidra_opt ../../os/mac_x86_64/decompile
cp sleigh_opt ../../os/mac_x86_64/sleigh
chmod +x ../../os/mac_x86_64/*
```

Makefile 本身有 `Darwin` 分支（`OSDIR=mac_x86_64`），无需修改源码。
工具链：Apple clang 17 / GNU Make 3.81。

### 4.4 Python 依赖

使用 **Ghidra 自带 wheel**，不用 PyPI：

```bash
GH=runtimes/darwin-x64/ghidra/ghidra_12.1.4_PUBLIC
PY=runtimes/darwin-x64/ghidra/python/bin/python3.12
$PY -m pip install --no-index \
  "$GH/Ghidra/Features/PyGhidra/pypkg/dist/jpype1-1.5.2-cp312-cp312-macosx_10_9_universal2.whl" \
  "$GH/Ghidra/Features/PyGhidra/pypkg/dist/packaging-25.0-py3-none-any.whl" \
  "$GH/Ghidra/Features/PyGhidra/pypkg/dist/pyghidra-3.1.0-py3-none-any.whl"
```

同时补上 `python/LICENSE.txt`（校验器要求存在）。

### 4.5 项目路径补丁

Ghidra 的 `ProjectLocator` 拒绝任何以 `.` 开头的本地路径段，
而默认项目根 `~/.dsh/ig5/projects` 含 `.dsh`。上游已预备补丁，
需先提供上游源码基准再运行：

```bash
# 从官方 Project-src.zip 提取基准（校验 SHA-256 = 5c24fa79...cd0dcd）
python3 -c "
import zipfile, pathlib
src = 'runtimes/darwin-x64/ghidra/ghidra_12.1.4_PUBLIC/Ghidra/Framework/Project/lib/Project-src.zip'
entry = 'ghidra/framework/protocol/ghidra/GhidraURL.java'
dest = pathlib.Path('third_party/sources/ghidra-12.1.4/Ghidra/Framework/Project/src/main/java') / entry
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_bytes(zipfile.ZipFile(src).read(entry))
"

# 打补丁
runtimes/darwin-x64/ghidra/python/bin/python3.12 -I -B \
  adapters/ghidra/local-project-path/build_patch.py \
  --project "$PWD" \
  --runtime-root "$PWD/runtimes/darwin-x64/ghidra" \
  --artifact-root ~/.dsh/ig5/artifacts/ghidra-local-project-path-build
```

补丁 `ig5-ghidra-local-project-path-v1` 只改 `GhidraURL.java` 的两个本地路径
调用点：放行 `.dsh` 这类合法点目录，仍拒绝 `.` / `..` / `.. ` 穿越别名，
项目名与仓库路径保持原有严格校验。

证明文件落在 `runtimes/darwin-x64/ghidra/licenses/ig5-local-project-path/`，
`runtime.json` 记录 `localProjectPathPatch` 字段。

### 4.6 生成清单

```bash
cd runtimes/darwin-x64 && python3 - <<'PY'
import os, json, hashlib
root = os.getcwd(); files = []
for dirpath, _, filenames in os.walk(root):
    for name in filenames:
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, root).replace('\\', '/')
        if os.path.islink(full): continue
        h = hashlib.sha256()
        with open(full, 'rb') as fh:
            for c in iter(lambda: fh.read(1 << 20), b''): h.update(c)
        files.append({'path': rel, 'bytes': os.path.getsize(full), 'sha256': h.hexdigest()})
files.sort(key=lambda e: e['path'])
m = {'schemaVersion': 1, 'pluginVersion': '1.0.0', 'platform': 'darwin-x64',
     'engines': ['ghidra', 'lldb'], 'files': files}
json.dump(m, open(os.path.join(root, 'manifest.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
print('文件数:', len(files))
PY
```

**改动运行时后必须重新生成**，否则 `readRuntime` 的 inventory 校验会因
字节数不符而拒绝加载。

---

## 五、部署

### 5.1 一键安装（推荐）

```bash
git clone https://github.com/pyt111/dsh-infinite-gen-5.git
cd dsh-infinite-gen-5
./install-darwin.sh
```

脚本自动完成：平台前置检查 → 下载并解压 Ghidra/JDK → 编译 native decompiler
→ 准备 Python 运行时（含 PyGhidra/JPype）→ 打项目路径补丁 → 生成清单
→ 部署到插件目录 → 注册 web profile → 运行自检。

| 参数 | 用途 |
| --- | --- |
| （无） | 完整安装 |
| `--runtime-only` | 只构建运行时，不部署 |
| `--deploy-only` | 只部署（运行时已就绪） |
| `--reuse <路径>` | 从已有插件目录复制运行时（约 20 秒，免下载） |

**`--reuse` 是跨机器迁移的最快路径**：已装好的机器上运行
`./install-darwin.sh --reuse ~/.dsh/plugins/dsh-infinite-gen-5`，
把 1.3 GB 运行时直接搬过来，跳过全部下载与编译。

### 5.2 手动部署

```bash
rsync -av --delete \
      --exclude='runtimes' --exclude='third_party' \
      --exclude='.git' --exclude='.ig5-local' \
      ~/DshWorkspace/dsh-infinite-gen-5/ \
      ~/.dsh/plugins/dsh-infinite-gen-5/

# 重启 DSH（无 --expose-internals，代码不热加载）
# 然后 ig5_doctor 确认 runtimeReady / startupVerified
```

**两个 `--exclude` 是关键**：`runtimes` 保住 1.3 GB 自建运行时，
`third_party` 保住补丁基准源码。

### 5.3 profile 注册的坑

pnpm 以 `nodeLinker: hoisted` 把插件做成**硬链接副本**放进
`~/.dsh/profiles/web/node_modules/`。这个副本**不含 `runtimes/`**
（`file:` 依赖只复制 git 跟踪的文件），而 `engine_runtime.js` 按
**已加载插件物理目录**解析运行时：

```js
const PLUGIN_ROOT = fs.realpathSync(path.dirname(fileURLToPath(import.meta.url)));
const BUNDLED_RUNTIME_ROOT = path.join(PLUGIN_ROOT, 'runtimes');
```

因此必须让 profile 里的条目指向插件真身：

```bash
PROFILE_NM="$HOME/.dsh/profiles/web/node_modules"
mv "$PROFILE_NM/dsh-infinite-gen-5" "$PROFILE_NM/.dsh-infinite-gen-5.hoisted-bak"   # 备份
ln -s "$HOME/.dsh/plugins/dsh-infinite-gen-5" "$PROFILE_NM/dsh-infinite-gen-5"
```

`install-darwin.sh` 已包含这一步。

### 5.4 清单不能包含自身

上游校验器明确禁止清单自引用：

```
runtime_pack.ps1:161
if ($relative -eq 'manifest.json' -or ...) { throw "清单不能包含自身或运行缓存: $relative" }
```

生成清单时必须排除 `manifest.json` 自身，否则
`verify-darwin.sh --runtime` 的完整性校验会失败。

---

## 六、上游同步

```bash
cd ~/DshWorkspace/dsh-infinite-gen-5
./sync-upstream.sh --check    # 只看上游新提交
./sync-upstream.sh            # 拉取并 rebase
```

冲突时停在 rebase 中间，处理后 `git add <file> && git rebase --continue`。

### 更新后的恢复检查

| 情形 | 处理 |
| --- | --- |
| 插件代码被覆盖 | `git checkout` 恢复，或重新应用 4 个文件的改动 |
| Ghidra 版本升级 | 按 §4.3 重新编译 decompiler，重新打路径补丁，重新生成清单 |
| 上游改了 `host_platform.js` | 检查白名单是否仍需加 `darwin-x64` |
| 上游改了 `runtime_pack.ps1` | 检查 Windows 清单硬编码是否变化 |

---

## 七、已知边界

**不要用官方 `install.ps1`** — `Assert-IG5RuntimePack` 硬性要求
`platform == 'win32-x64'` 且 `engines` 含 `x64dbg`，遇到 darwin 运行时直接 throw。
用 `rsync` 或 `dsh plugin --profile web add`。

**x64dbg 不可用** — 依赖 Windows 调试 API、PE 加载、NT 内核对象，
macOS 无对应实现。`ig5_doctor` 的 `unsupported` 中明确标注，不静默降级。

**`ig5_emulate` 不可用** — 随包 `worker/vendor/unicorn/lib/unicorn.dll` 是
Windows DLL；`worker.py` 在非 Windows 上主动摘除该方法：

```python
if os.name != 'nt':
    METHODS.pop('emulate', None)
```

**SIP 限制** — 见 [LLDB_LANE](LLDB_LANE.md) §4。

**Ghidra 版本耦合** — `engine_runtime.js` 会核对清单版本与实际版本：

```js
if (raw.version && raw.version !== actualVersion) throw new Error('Ghidra application version does not match its manifest');
```

上游升级 Ghidra 时运行时必须同步重建。

**测试脚本的平台假设** — `scripts/test_host_platform.mjs` /
`test_runtime_bundle.mjs` / `test_engine_integration.mjs` 在 macOS 上失败，
原因是脚本写死了 Windows 路径与 `runtimes/ghidra`（无平台子目录）布局。
这些失败在未改动的上游副本上同样存在，与本次移植无关。

---

## 八、验证记录

移植后实测（真实执行，非 mock）：

```
ig5_doctor        → engine: reverse 12.1.4 | python 3.12.15 | pyghidra 3.1.0 | jpype 1.5.2
                    jvmBootstrap: native | 37 项 capability | startupVerified: true
ig5_open /bin/ls  → n_funcs: 220 | proc: x86 | bits: 64 | 17 个 segment
                    languageId: x86:LE:64:default | compilerSpec: gcc
ig5_decompile     → FUN_10000073f 正确还原 _strcoll 调用与数据偏移
ig5_cfg           → 7 块 9 边，含 Mermaid 图
ig5_xrefs         → 3 条引用（含 UNCONDITIONAL_CALL）
ig5_funcs         → 136 个函数
ig5_strings       → 306 条（含 Mach-O 版本串）
ig5_bytes         → 原始 hex
工作台 /ig5-data  → 200，返回真实会话数据
```

---

## 九、相关文档

- [LLDB_LANE.md](LLDB_LANE.md) — lldb 调试后端
- [../.ig5-local/README.md](../.ig5-local/README.md) — 维护速查
- [../sync-upstream.sh](../sync-upstream.sh) — 上游同步脚本
