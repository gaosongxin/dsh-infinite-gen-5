# darwin-x64 维护说明

本仓库是 [Minglink/dsh-infinite-gen-5](https://github.com/Minglink/dsh-infinite-gen-5)
的 fork，用于在 **macOS Intel (darwin-x64)** 上运行 IG5。

## 仓库结构

```
pyt111/dsh-infinite-gen-5          ← fork
├── master          ← 带 darwin-x64 补丁（日常使用）
└── darwin-x64      ← 同上（上游同步工作分支）
```

两个分支内容一致。`master` 便于 clone 即用，`darwin-x64` 用于 rebase 上游。

## 与上游的差异（4 个文件）

| 文件 | 改动 |
|---|---|
| `source/host_platform.js` | 平台白名单加 `darwin-x64`；补 darwin reason 文案 |
| `engine_runtime.js` | 新增 `machoArchitecture()`；拆出 darwin 分支（JDK dylib / mac_x86_64 decompiler / OS_ARCH=x86_64 / JPype darwin ABI / validation 标签） |
| `source/worker_transport.js` | `detached: true` 进程组从 linux 扩到 darwin |
| `adapters/ghidra/local-project-path/build_patch.py` | `javac` 按 `os.name` 选 `.exe` |

另加 `sync-upstream.sh`（上游同步脚本）。

## 上游同步

```bash
cd ~/DshWorkspace/dsh-infinite-gen-5
./sync-upstream.sh --check    # 只看上游有什么新提交
./sync-upstream.sh            # 拉取并 rebase
```

冲突时停在 rebase 中间，手动处理后 `git add <file> && git rebase --continue`。

## 部署到 DSH

```bash
rsync -av --delete --exclude='runtimes' --exclude='third_party' \
      --exclude='.git' --exclude='.ig5-local' \
      ~/DshWorkspace/dsh-infinite-gen-5/ ~/.dsh/plugins/dsh-infinite-gen-5/

# 重启 DSH（无 --expose-internals，代码不热加载）
# 然后 ig5_doctor 确认 runtimeReady / startupVerified
```

**关键**：`--exclude='runtimes'` 保住 1.3G 自建运行时（含本地编译的
`mac_x86_64/decompile` 与 `.dsh` 路径补丁），`--exclude='third_party'`
保住补丁基准源码。

## 运行时包（不入库，本地构建）

`runtimes/darwin-x64/` 1.3G：

- Ghidra 12.1.4 PUBLIC（官方）
- `mac_x86_64/decompile` + `sleigh` — 官方源码 + Apple clang 编译
- Temurin JDK 21.0.12.1 x86_64
- CPython 3.12.15 + PyGhidra 3.1.0 + JPype 1.5.2（Ghidra 自带 pypkg）
- `ig5-ghidra-local-project-path-v1` 补丁（让 `.dsh` 路径可用）

### 重建步骤

```bash
# 1. 下载
curl -L -o ghidra.zip https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip
curl -L -o jdk.tar.gz "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_mac_hotspot_21.0.12.1_1.tar.gz"

# 2. 解压到 runtimes/darwin-x64/ghidra/
# 3. 编译 native decompiler
cd runtimes/darwin-x64/ghidra/ghidra_12.1.4_PUBLIC/Ghidra/Features/Decompiler/src/decompile/cpp
make ghidra_opt -j4 && make sleigh_opt -j4
mkdir -p ../../os/mac_x86_64
cp ghidra_opt ../../os/mac_x86_64/decompile
cp sleigh_opt ../../os/mac_x86_64/sleigh

# 4. Python 运行时（用 Ghidra 自带 wheel，版本必须配对）
#    装到 runtimes/darwin-x64/ghidra/python/
#    Ghidra/Features/PyGhidra/pypkg/dist/{jpype1-1.5.2-cp312-*,packaging-25.0-*,pyghidra-3.1.0-*}.whl

# 5. 打项目路径补丁
runtimes/darwin-x64/ghidra/python/bin/python3.12 -I -B \
  adapters/ghidra/local-project-path/build_patch.py \
  --project <repo> --runtime-root <repo>/runtimes/darwin-x64/ghidra \
  --artifact-root ~/.dsh/ig5/artifacts/ghidra-local-project-path-build

# 6. 重新生成 manifest.json（8155+ 个文件的 SHA-256 清单）
```

## 注意事项

- **不要用官方 `install.ps1`** — 它硬性要求 `platform == 'win32-x64'` 且
  `engines` 含 `x64dbg`，会直接 throw。
- **x64dbg 不可用** — Windows 专属，`ig5_doctor` 的 `unsupported` 里明确标注。
- **`ig5_emulate` 不可用** — 依赖随包 Unicorn native 运行时（仅 Windows DLL）。
- **Ghidra 版本升级** — 若上游把 Ghidra 从 12.1.4 升级，需要按上面第 2-6 步重建运行时。
