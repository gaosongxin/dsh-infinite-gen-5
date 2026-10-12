# darwin-x64 适配实验记录

记录为在 macOS Intel 上运行 IG5 所做的全部移植工作、遇到的问题与解决过程。
按时间顺序，包含失败尝试——失败路径本身也是资产。

- 日期：2026-10-12
- 宿主：MacBookPro15,1 / Intel i7-8850H / macOS 15.5 / darwin-x64
- 上游：`Minglink/dsh-infinite-gen-5` @ `314d896`
- 结果：静态分析（Ghidra）与动态调试（lldb）双车道可用

---

## 0. 阶段总览

| 阶段 | 目标 | 结果 |
| --- | --- | --- |
| 1 | 安装插件 | ✅ 插件加载，但引擎不可用 |
| 2 | 构建 darwin-x64 运行时 | ✅ Ghidra 12.1.4 全套本地构建 |
| 3 | 打通项目路径 | ✅ 应用 `ig5-ghidra-local-project-path-v1` |
| 4 | 建立 fork 工作流 | ✅ git 分支 + 上游同步脚本 |
| 5 | 接入 lldb 调试后端 | ✅ 与 x64dbg 协议对齐 |
| 6 | 自动处理 SIP 限制 | ✅ 签名探测 + 自动准备 |
| 7 | 固化为文档资产 | ✅ docs/DARWIN_X64.md · LLDB_LANE.md |

---

## 1. 起点：插件能装，引擎不能跑

### 观察

官方 `install.ps1` 在 macOS 上无法运行（无 PowerShell），
手动用 `dsh plugin --profile web add` 装入源码后：

```
ig5_doctor → Error: No matching IG5 runtime is supported for darwin-x64
```

### 定位

`source/host_platform.js:13`：

```js
const supported = id === 'win32-x64' || id === 'linux-arm64';
```

宿主 `darwin-x64` 不在白名单。发行附件
`IG5-1.0.0-Windows-x64-*.zip` 也只有 Windows。

### 关键发现

上游 `Ghidra/Features/Decompiler/buildNatives.gradle:44` 列出了
`mac_x86_64` 目标平台，但官方发行 ZIP 只打包了 `linux_x86_64` 与
`win_x86_64`。**移植可行，缺的是预编译产物。**

---

## 2. 构建运行时

### 2.1 组件获取

| 组件 | 来源 | 大小 |
| --- | --- | --- |
| Ghidra 12.1.4 PUBLIC | `ghidra_12.1.4_PUBLIC_20260921.zip` | 570 MB |
| Temurin JDK 21.0.12.1+1 | Adoptium API `os=mac&architecture=x64` | 185 MB |
| CPython 3.12.15 | uv 管理的 `macos-x86_64-none` 发行版 | 72 MB |

### 2.2 下载中断问题

JDK 下载两次触发 `curl: (92) HTTP/2 stream not closed cleanly`，
用 `--retry 5 --retry-all-errors -C -` 断点续传解决：

```bash
curl -sSL --retry 5 --retry-delay 3 --retry-all-errors -C - -o jdk.tar.gz "<url>"
```

### 2.3 编译 native decompiler

```bash
cd Ghidra/Features/Decompiler/src/decompile/cpp
make ghidra_opt -j4 && make sleigh_opt -j4
mkdir -p ../../os/mac_x86_64
cp ghidra_opt ../../os/mac_x86_64/decompile
cp sleigh_opt ../../os/mac_x86_64/sleigh
```

Makefile 已有 `Darwin` 分支，无需改源码。产出：

```
ghidra_opt: Mach-O 64-bit executable x86_64   3,315,584 字节
sleigh_opt: Mach-O 64-bit executable x86_64     896,936 字节
```

### 2.4 Python 依赖版本配对

**第一版用错了**：装 PyPI 的 PyGhidra 2.2.1 + JPype 1.7.1，
扩展文件名是 `_jpype.so`，与校验器期望的 ABI 名不符。

改为使用 **Ghidra 自带 `pypkg/dist`** 的 wheel：

```
jpype1-1.5.2-cp312-cp312-macosx_10_9_universal2.whl
packaging-25.0-py3-none-any.whl
pyghidra-3.1.0-py3-none-any.whl
```

结果扩展名 `_jpype.cpython-312-darwin.so`，与 PyGhidra 3.1.0 严格配对。

另外需要清除 PEP 668 标记并补 `LICENSE.txt`：

```bash
find python/lib -name "EXTERNALLY-MANAGED" -delete
curl -sSL -o python/LICENSE.txt https://raw.githubusercontent.com/python/cpython/v3.12.15/LICENSE
```

### 2.5 第一次成功

```
engine: Ghidra 12.1.4 | python: 3.12.15 | pyghidra: 3.1.0 | jpype: 1.5.2
jvmBootstrap: native | capabilities: 37 项 | unsupported: ["dbg","emulate"]
```

---

## 3. 项目路径：`.dsh` 被拒绝

### 观察

引擎起来了，但 `ig5_open` 失败：

```
java.lang.IllegalArgumentException: Path element starting with '.' is not permitted
```

### 定位

对照实验：

| projectRoot | 结果 |
| --- | --- |
| `/tmp/ig5-test-proj` | ✅ |
| `/Users/wangshuang/ig5/projects` | ✅ |
| `~/.dsh/ig5/projects` | ❌ |

反编译 `Project.jar` 找到调用链：

```
ProjectLocator → GhidraURL.checkLocalAbsolutePath → NamingUtilities.checkName
```

```java
// NamingUtilities.java:107
if (pathElement.startsWith(".")) {
    throw new IllegalArgumentException(type + " starting with '.' is not permitted");
}
```

**这不是 macOS 特有的问题** —— Windows 上
`C:\Users\<user>\.dsh\ig5\projects` 同样含 `.dsh`。

### 解决

上游已预备补丁 `adapters/ghidra/local-project-path/`，但需要两个前置条件：

1. 从官方 `Project-src.zip` 提取上游 `GhidraURL.java` 作为基准
   （校验 SHA-256 = `5c24fa79...cd0dcd`，与脚本内置常量一致）
2. 补丁脚本的 javac 路径要按平台选择（原为 `javac.exe`）

```python
javac = java_home / ('bin/javac.exe' if os.name == 'nt' else 'bin/javac')
```

补丁只改两个本地路径调用点，放行合法点目录，仍拒绝 `.` / `..` / `.. ` 穿越。

### 验证

```
✅ 干净 path + 干净 name
❌ 干净 path + 点开头 name    ← 项目名仍拒绝（正确）
✅ 点开头 path + 干净 name    ← 本地路径放行
✅ 真实默认 path + 干净 name
```

---

## 4. 建立 fork 工作流

### 动机

最初的方案是把 4 个 `.patch` 文件放进插件目录 —— 手工维护，
上游更新后要逐个重新应用。改为 fork + 分支后，同步变成一次 rebase。

### 结构

```
pyt111/dsh-infinite-gen-5
├── master       带 darwin-x64 补丁（clone 即用）
└── darwin-x64   同上（上游同步工作分支）
```

### 同步脚本

`sync-upstream.sh` 四个步骤：`fetch` → 展示双方新提交 → `rebase` →
语法检查 + 打印部署命令。支持 `--check`（只看不动）与 `--merge`。

### 踩坑

脚本里一行中文注释导致 `BRANCH: unbound variable` ——
全角引号被 shell 当成变量名的一部分。改用 ASCII 输出：

```sh
echo "      switching to ${BRANCH} (from ${CURRENT})"
```

---

## 5. 接入 lldb 调试后端

### 5.1 为什么不是"再写个独立工具"

翻代码发现 x64dbg 的接入方式是**进程 + JSONL 协议**：

```
index.js performDebug() → spawn → adapters/x64dbg/adapter.py → NamedPipe → x64dbg
```

最干净的接法是照写一个 lldb adapter，协议与结果字段
（`runId`/`stopSeq`/`state`/`context`）全部对齐，`ig5_dbg` 工具面不用分叉。

### 5.2 LLDB Python 绑定

Apple 不提供独立 wheel，绑定在 Xcode 内且为 Python 3.9 编译：

```
/Applications/Xcode.app/Contents/SharedFrameworks/LLDB.framework/Resources/Python/
└── _lldb.cpython-39-darwin.so
```

系统 python3（3.11）导入 `_lldb` 失败，必须用 Xcode 的解释器。
因此写了包装脚本 `bin/ig5-lldb-python` 在运行时解析路径。

### 5.3 API 试错记录

文档与实际不符的地方（全部实测确认）：

| 文档写法 | 实际可用 |
| --- | --- |
| `lldb.eStateAttached` | 不存在；常量从 `eStateUnloaded=1` 到 `eStateSuspended=11` |
| `SBLaunchInfo.SetStopOnEntry()` | 不存在；`SetLaunchFlags(flags \| eLaunchFlagStopAtEntry)` |
| `SBFile.Create(fd)` | 只接受文件对象：`Create(sys.stderr, borrow=True)` |
| `SBModule.GetObjectFileSize()` | 不存在；用 section 推算 |
| `SBFileSpec.GetPath()` | 需 `dst_path`/`dst_len`；用 `str(filespec)` |
| `SBValueList.GetRegisterSetAtIndex()` | 不存在；用 `GetValueAtIndex()` |

### 5.4 协议对齐

x64dbg adapter 在 `main()` 里先发 `{"ig5":"ready",...}` 再进主循环。
第一版 lldb adapter 漏了这一步，host 等了 30 秒超时。补上后立即通过。

### 5.5 start 语义

需要让 host 拿到**暂停且可检查**的进程，而不是让目标跑完退出。
用 `eLaunchFlagStopAtEntry` 停在入口，与 x64dbg 的 `init` 语义一致：

```
start: true | state: suspended | pc: 0x100007d90 _dyld_start
```

### 5.6 实测

```
cont → pc: 0x10000047c check_serial | rva: 0x47c
regs: rdi = 0x7ff7bfeffe87 | rip = 0x10000047c
readmem: 488b7df0e8af0000004883f8087409c7
callstack: check_serial -> main -> start
step: new pc: 0x100000480
```

---

## 6. SIP 处理：从手动到自动

### 6.1 问题

macOS 拒绝对平台签名二进制做 ptrace 附加：

```
process exited with status -1 (attach failed (Not allowed to attach to process...))
```

第一版只把这段说明写进 `runtime.json` 的 notes，使用者仍需自己查、自己跑
`codesign`。

### 6.2 改进

新增两个操作，adapter 自己判定并处理：

**`signature`** — 只读探测，返回 `unsigned` / `debuggable` / `protected` / `unknown`

**`prepare`** — 复制 + 重签名，附加 `com.apple.security.get-task-allow`

`start` 遇到受保护目标时不再抛内核错误，而是返回可执行的诊断：

```json
{
  "ok": false, "code": "ESIGNATURE", "signature": "protected",
  "remedy": "call again with prepare=true to run the target from a re-signed copy",
  "prepareAvailable": true
}
```

### 6.3 两个实现细节

**哈希语义分开** —— 重签名会改变文件字节（签名附加到镜像上）：

```
/bin/ls            154624 字节  d6b646ec...
重签名副本          155088 字节  f5b0a0c1...
```

所以返回 `imageSha256`（签名前载荷，等于原文件摘要）与 `signingSha256`
（签名后整文件）两个字段，不用单个 hash 混淆"载荷身份"与"落盘文件身份"。

**host 层校验不用改** —— `performDebug` 里 `params.path` 始终是原始路径，
副本路径由 adapter 内部产生，哈希校验照常通过。最初加过例外，后确认多余撤回。

### 6.4 两个 bug

**权限位丢失** —— `shutil.copyfile` 不带 mode：

```
-rw-r--r--  ls-ig5dbg    ← 缺执行位
→ 内核拒绝启动：Permission denied
```

修法：`copymode` + 显式补 `0o111`。

**工作目录取错** —— 原用镜像路径的父目录，当 `prepare_to` 指向文件本身时
父目录就是文件：

```
[Errno 20] Not a directory: '/private/tmp/ig5-prepared/ls-ig5dbg'
```

修法：显式校验目录存在。

---

## 7. 最终状态

### 引擎

| 引擎 | darwin-x64 |
| --- | --- |
| `reverse` / `ghidra` | ✅ `structure-and-macho-headers` |
| `lldb` | ✅ `host-debugger-presence` |
| `x64dbg` | ❌ Windows 专属 |

### 与上游的差异

```
10 个文件改动 + 2 个新文档 + 3 个新文件
1304 insertions(+), 51 deletions(-)
```

### 提交历史

```
7c83e05  feat(lldb): 自动处理 SIP 保护的调试目标
c6826b5  feat: 新增 lldb 调试后端（macOS 原生调试车道）
3be7d82  docs: 添加 darwin-x64 维护说明
58331ec  chore: 添加上游同步脚本
4701474  feat: 支持 darwin-x64（macOS Intel）本地运行时
────────
314d896  Update README.md          ← 上游分叉点
```

---

## 8. 经验总结

### 有效的方法

**先读代码再动手** —— 平台硬编码点集中在少数几处，
找出这些点就知道改哪里，不用猜。

**用上游自己的补丁** —— 项目路径问题上游早已备好补丁，
只是没在 macOS 上跑过。复用比自己写强。

**对照实验** —— 判断"路径问题还是平台问题"时，
用不同 projectRoot 跑同一段代码，结论比推理可靠。

**实测 API 而非信文档** —— LLDB Python 绑定有 6 处名字与常见写法不同，
全部靠 `dir()` 与逐项测试确认。

### 走过的弯路

**第一版 Python 依赖用 PyPI** —— 版本不配对，扩展名不对，重来一遍。

**哈希校验加例外** —— 以为 prepare 会破坏 host 层校验，
实际不会（原路径始终不变），白改一轮。

**漏发 ready 消息** —— 照抄协议时只看了方法分发，没看主循环开头。

**中文注释进 shell 脚本** —— 全角标点被当成变量名。

### 不适合的做法

**不要用官方 `install.ps1`** —— 硬校验 `platform == 'win32-x64'` 且
`engines` 含 `x64dbg`，为 Windows 设计的完整性检查在 macOS 上必然拒绝。

**不要期待测试脚本跨平台** —— `test_host_platform.mjs` 等写死了
Windows 路径与无平台子目录的布局，在未改动的上游副本上同样失败。

---

## 9. 相关资产

| 路径 | 内容 |
| --- | --- |
| [DARWIN_X64.md](DARWIN_X64.md) | 平台适配完整文档（含重建步骤） |
| [LLDB_LANE.md](LLDB_LANE.md) | lldb 后端设计、API 差异、SIP 处理 |
| [../.ig5-local/README.md](../.ig5-local/README.md) | 维护速查 |
| [../sync-upstream.sh](../sync-upstream.sh) | 上游同步脚本 |
| [../verify-darwin.sh](../verify-darwin.sh) | 环境自检脚本 |
| [../adapters/lldb/adapter.py](../adapters/lldb/adapter.py) | lldb 后端实现 |
| `runtimes/darwin-x64/` | 自建运行时（1.3 GB，gitignore） |
| `~/ig5-darwin-backup/` | 改动补丁应急备份 |
