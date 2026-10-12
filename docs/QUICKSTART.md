# 快速开始

从零到能用的最短路径。

---

## 我需要看哪份文档？

| 我想…… | 看这份 |
| --- | --- |
| **装起来用** | 本文件（往下读） |
| 排查装不上的问题 | [../verify-darwin.sh](../verify-darwin.sh) 先跑一遍 |
| 了解改了哪些代码、为什么 | [DARWIN_X64.md](DARWIN_X64.md) |
| 用 lldb 调试 / SIP 报错 | [LLDB_LANE.md](LLDB_LANE.md) |
| 日常维护、上游更新 | [../.ig5-local/README.md](../.ig5-local/README.md) |
| 知道当初踩过哪些坑 | [DARWIN_X64_NOTES.md](DARWIN_X64_NOTES.md) |
| 上游 IG5 本身怎么用（38 工具、工作流） | [../README.md](../README.md) |
| 用 Python 脚本扩展 Ghidra 分析 | [SCRIPT_API.md](SCRIPT_API.md) |
| 调查任务（持久化分析进度） | [INVESTIGATION_WORKFLOW.md](INVESTIGATION_WORKFLOW.md) |
| 解密 / 协议分析 | [CRYPTO_PROTOCOL.md](CRYPTO_PROTOCOL.md) · [AUTODISCOVERY.md](AUTODISCOVERY.md) |

**三份 darwin 文档的分工**：

```
DARWIN_X64.md          怎么做（配置、构建、部署、边界）
LLDB_LANE.md           调试车道（协议、API、SIP）
DARWIN_X64_NOTES.md    为什么这么做（移植过程、失败路径）
```

---

## 前置条件

```bash
# 必需
macOS Intel (x86_64)        uname -m        # 应为 x86_64
Node.js 22+                 node -v
git / curl / python3

# 可选但推荐
完整 Xcode                   ls /Applications/Xcode.app
```

**关于 Xcode**：没有它静态分析照样能用，只是 `ig5_dbg` 的 lldb 后端不可用。
仅装 Command Line Tools 不够——lldb 的 Python 绑定在 Xcode.app 内部。

**关于 Apple Silicon**：当前运行时是 x86_64 的。M 系列机器需要另建 arm64
运行时（`make` 时 `uname -m` 会得到 arm64，Ghidra 也支持 `mac_arm_64`），
本仓库尚未覆盖。

---

## 场景 A：全新机器，从零构建

```bash
# 1. 拿到代码（38 MB）
git clone https://github.com/pyt111/dsh-infinite-gen-5.git
cd dsh-infinite-gen-5

# 2. 一键安装（下载 1.5 GB + 编译，约 10-30 分钟）
./install-darwin.sh

# 3. 重启 DSH
```

脚本会自动完成：平台检查 → 下载 Ghidra 12.1.4 与 Temurin JDK 21 → 解压 →
用 Apple clang 编译 `mac_x86_64` decompiler → 准备 CPython 3.12
+ PyGhidra + JPype → 打项目路径补丁 → 生成清单 → 部署到
`~/.dsh/plugins/dsh-infinite-gen-5/` → 注册 web profile → 跑自检。

---

## 场景 B：已有另一台装好的 Mac（最快）

```bash
# 旧机器上找到插件目录
#   ~/.dsh/plugins/dsh-infinite-gen-5

# 新机器
git clone https://github.com/pyt111/dsh-infinite-gen-5.git
cd dsh-infinite-gen-5

# 把旧机器的插件目录拷过来（AirDrop / scp / 移动硬盘都行）
# 然后直接复用它的运行时，跳过下载与编译
./install-darwin.sh --reuse /path/to/old/.dsh/plugins/dsh-infinite-gen-5
```

实测**约 20 秒完成**。

---

## 场景 C：本机重装 / 只更新代码

```bash
cd dsh-infinite-gen-5
./install-darwin.sh --deploy-only
```

运行时已在 `~/.dsh/plugins/dsh-infinite-gen-5/runtimes/`，不会被删除。

---

## 装完必须做的

**重启 DSH**。插件代码不会热加载（DSH 未启用 `--expose-internals`），
不重启就还在跑旧代码。

重启后在会话里验证：

```
ig5_doctor
```

期望看到：

```json
{
  "host": { "id": "darwin-x64", "supported": true },
  "engines": [
    { "id": "reverse", "available": true, "startupVerified": true },
    { "id": "ghidra",  "available": true },
    { "id": "lldb",    "available": true },
    { "id": "x64dbg",  "available": false,
      "reason": "x64dbg requires a Windows x64 host..." }
  ]
}
```

`x64dbg` 显示 `available: false` 是**正常的**——它是 Windows 专属，
macOS 上用 `lldb` 替代。

---

## 第一次用

### 静态分析

```
ig5_open /bin/ls              → 建项目、跑分析
ig5_funcs                     → 列函数
ig5_decompile ea=0x10000073f  → 反编译
ig5_cfg ea=0x10000073f        → 控制流图
ig5_strings                   → 字符串
ig5_xrefs ea=0x10000073f      → 交叉引用
```

更多工具（共 38 项，默认只加载 8 个核心）：

```
ig5_profile toolset=full      → 展开全部工具
```

### 动态调试

```
ig5_open /path/to/target                                    → 先静态打开
ig5_dbg op=load     backend=lldb                            → 加载调试器
ig5_dbg op=start    backend=lldb                            → 启动（停在入口）
ig5_dbg op=bpt      backend=lldb ea=0x10000047c             → 下断点
ig5_dbg op=cont     backend=lldb                            → 继续
ig5_dbg op=regs     backend=lldb                            → 读寄存器
ig5_dbg op=readmem  backend=lldb ea=<addr> size=64          → 读内存
ig5_dbg op=step     backend=lldb                            → 单步
ig5_dbg op=stop     backend=lldb                            → 停止
```

**遇到 SIP 报错**（调试系统二进制时）：

```
{ "code": "ESIGNATURE", "signature": "protected",
  "remedy": "call again with prepare=true ..." }
```

加一个参数即可，会自动复制并重签名：

```
ig5_dbg op=start backend=lldb path=/bin/ls prepare=true
```

**注意**：`ig5_dbg` 是审批门工具，`start` 会执行目标，每次都需要你批准。

---

## 出问题先跑自检

```bash
./verify-darwin.sh --plugin          # 检查已部署的插件（约 5 秒）
./verify-darwin.sh --plugin --runtime # 额外校验 8167 项文件哈希（约 20 秒）
```

输出示例：

```
[1] 源码文件      7 项 ✓
[2] 语法检查      5 项 ✓
[3] 平台白名单    3 项 ✓
[4] 运行时       12 项 ✓
[5] Xcode 与 lldb 5 项 ✓
[6] DSH 宿主      4 项 ✓
[7] 引擎可用性    ghidra ✓  lldb ✓  x64dbg ·（不适用）

通过 36 / 警告 1
✅ 全部检查通过
```

失败时脚本会给出对应的处理建议。

---

## 常见问题

**Q：`ig5_doctor` 报 `No matching IG5 runtime is supported for darwin-x64`**

平台白名单被覆盖了。检查：

```bash
grep -n "darwin-x64" ~/.dsh/plugins/dsh-infinite-gen-5/source/host_platform.js
```

没有输出说明改动丢了，重新部署：`./install-darwin.sh --deploy-only`

**Q：改了代码不生效**

DSH 不热加载。必须完全退出并重启。

**Q：`ig5_dbg` 报 x64dbg 不可用**

正常。用 `backend=lldb`。

**Q：能用官方 `install.ps1` 吗**

不能。它硬校验 `platform == 'win32-x64'` 且 `engines` 含 `x64dbg`，
遇到 macOS 运行时直接报错。用 `install-darwin.sh`。

**Q：Apple Silicon 能用吗**

当前不行，运行时是 x86_64 的。需要另建 arm64 版本。

---

## 文档地图

```
README.md                      上游 IG5 总览 + macOS 分支说明
docs/QUICKSTART.md             ← 你在这里
docs/DARWIN_X64.md             macOS 适配：改了什么、怎么构建、边界在哪
docs/LLDB_LANE.md              lldb 调试车道：协议、API 差异、SIP 处理
docs/DARWIN_X64_NOTES.md       移植实验记录：走过的弯路
.ig5-local/README.md           维护速查：日常命令、上游同步

── 以下是上游原有文档（未改动）─────────────────────
docs/ARCHITECTURE.md           IG5 内部结构
docs/SCRIPT_API.md             Ghidra Python 脚本 API
docs/INVESTIGATION_WORKFLOW.md 持久化调查任务
docs/CRYPTO_PROTOCOL.md        解密与协议分析
docs/AUTODISCOVERY.md          密钥恢复与协议推断
docs/SELF_CONTAINED_KERNEL.md  独立内核（ig5_ir level=kernel）
docs/DSH_COMPATIBILITY.md      宿主版本兼容说明
docs/BUILD.md                  上游维护者构建流程（Windows）
docs/MOBILE.md                 手机端适配现状
docs/REMEDIATION.md            1.0.0 缺陷修复对账
```
