# darwin-x64 维护速查

本 fork 为 **macOS Intel (darwin-x64)** 增加了分析与调试能力。

- 仓库：<https://github.com/pyt111/dsh-infinite-gen-5>（fork of Minglink/dsh-infinite-gen-5）
- 本地：`~/DshWorkspace/dsh-infinite-gen-5`
- 部署：`~/.dsh/plugins/dsh-infinite-gen-5`
- 详细文档：[docs/DARWIN_X64.md](../docs/DARWIN_X64.md) · [docs/LLDB_LANE.md](../docs/LLDB_LANE.md)

---

## 分支

`master` 与 `darwin-x64` 内容一致。`master` 便于 clone 即用，
`darwin-x64` 用于 rebase 上游。

---

## 与上游的差异

```
 .ig5-local/README.md                              |  96 ++
 adapters/ghidra/local-project-path/build_patch.py |   3 +-
 adapters/lldb/adapter.py                          | 952 ++++++++++++++++++++++
 engine_runtime.js                                 |  87 +-
 index.js                                          |  77 +-
 runtimes/darwin-x64/lldb/bin/ig5-lldb-python      |  26 +
 runtimes/darwin-x64/lldb/runtime.json             |  17 +
 source/host_platform.js                           |   6 +-
 source/worker_transport.js                        |  11 +-
 sync-upstream.sh                                  |  80 ++
 docs/DARWIN_X64.md                                | 新增
 docs/LLDB_LANE.md                                 | 新增
```

| 文件 | 改动 |
| --- | --- |
| `source/host_platform.js` | 白名单加 `darwin-x64` |
| `engine_runtime.js` | `machoArchitecture()`；darwin 分支（JDK dylib / mac_x86_64 decompiler / JPype darwin ABI）；lldb 引擎注册 |
| `source/worker_transport.js` | posix 进程组从 linux 扩到 darwin；lldb 环境变量 |
| `index.js` | `DEBUG_ENGINES` 集合；`defaultDebugger` 平台选择；`ig5_dbg` 支持 lldb |
| `adapters/ghidra/local-project-path/build_patch.py` | javac 按平台选 `.exe` |
| `adapters/lldb/adapter.py` | lldb 调试后端（新增） |

---

## 上游同步

```bash
cd ~/DshWorkspace/dsh-infinite-gen-5
./sync-upstream.sh --check    # 只看上游有什么新提交
./sync-upstream.sh            # 拉取并 rebase
./sync-upstream.sh --merge    # 保留分叉历史
```

冲突时停在 rebase 中间：

```bash
git add <file> && git rebase --continue
# 或放弃
git rebase --abort
```

---

## 部署

```bash
./install-darwin.sh            # 一键：构建运行时 + 部署 + 注册 + 自检
./install-darwin.sh --deploy-only      # 只部署
./install-darwin.sh --runtime-only     # 只构建运行时
./install-darwin.sh --reuse <路径>     # 从已有安装复制运行时（约 20 秒）
```

手动部署：

```bash
rsync -av --delete \
      --exclude='runtimes' --exclude='third_party' \
      --exclude='.git' --exclude='.ig5-local' \
      ~/DshWorkspace/dsh-infinite-gen-5/ \
      ~/.dsh/plugins/dsh-infinite-gen-5/

# 重启 DSH（无 --expose-internals，代码不热加载）
```

**关键**：`--exclude='runtimes'` 保住 1.3 GB 自建运行时，
`--exclude='third_party'` 保住补丁基准源码。

**profile 软链接**：pnpm 的硬链接副本不含 `runtimes/`，
必须让 `~/.dsh/profiles/web/node_modules/dsh-infinite-gen-5`
指向插件真身（`install-darwin.sh` 已处理）。

---

## 运行时

```
runtimes/darwin-x64/
├── manifest.json                    8168 个文件 SHA-256 清单
├── ghidra/                          1.3 GB
│   ├── ghidra_12.1.4_PUBLIC/        含本地编译的 os/mac_x86_64/{decompile,sleigh}
│   ├── jdk-21.0.12.1+1/             Temurin JDK 21 x86_64
│   └── python/                      CPython 3.12.15 + PyGhidra 3.1.0 + JPype 1.5.2
└── lldb/
    ├── runtime.json
    └── bin/ig5-lldb-python
```

重建步骤见 [docs/DARWIN_X64.md §4](../docs/DARWIN_X64.md)。

**改动运行时后必须重新生成 manifest.json**，否则 inventory 校验会因
字节数不符拒绝加载。

---

## 日常操作

```bash
# 语法检查
node --check engine_runtime.js && node --check index.js && \
node --check source/host_platform.js && node --check source/worker_transport.js
python3 -m py_compile adapters/lldb/adapter.py

# 验证运行时
node -e "import('./engine_runtime.js').then(m => {
  const c = m.runtimeConfiguration({});
  console.log('ghidra:', c.ghidra.available, '| lldb:', c.lldb.available);
})"

# 重新生成清单（改运行时后）
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
json.dump({'schemaVersion': 1, 'pluginVersion': '1.0.0', 'platform': 'darwin-x64',
           'engines': ['ghidra', 'lldb'], 'files': files},
          open('manifest.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('文件数:', len(files))
PY
```

---

## 注意事项

- **不要用官方 `install.ps1`** — 硬性要求 `platform == 'win32-x64'` 且
  `engines` 含 `x64dbg`，遇到 darwin 运行时直接 throw。
- **x64dbg 不可用** — Windows 专属。
- **`ig5_emulate` 不可用** — 随包 Unicorn 是 Windows DLL。
- **Ghidra 升级需重建运行时** — `engine_runtime.js` 会核对清单版本与实际版本。
- **SIP 保护的目标** — `ig5_dbg op=start ... prepare=true` 自动处理，
  详见 [docs/LLDB_LANE.md §4](../docs/LLDB_LANE.md)。

---

## 备份位置

```
~/ig5-darwin-backup/.ig5-local/    改动补丁（git 之外的第二份）
```

改动的权威来源是 git 分支，备份目录仅作应急。
