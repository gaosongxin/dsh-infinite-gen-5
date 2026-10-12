# ⚒️ DeepSeek Harness AI 驱动专业逆向工作台（无限五代 ∞ IG5）v1.0.0
（本工具仅限用于合法授权的软件逆向工程、安全审计与学术研究）

> ## 🍎 macOS Intel (darwin-x64) 分支
>
> 本仓库是 [Minglink/dsh-infinite-gen-5](https://github.com/Minglink/dsh-infinite-gen-5)
> 的 fork，为 **macOS Intel** 增加了完整的分析与调试能力。
>
> | 引擎 | 状态 | 说明 |
> | --- | --- | --- |
> | `reverse` / `ghidra` | ✅ | 静态分析，本地构建运行时（Ghidra 12.1.4 + 自编译 mac_x86_64 decompiler） |
> | `lldb` | ✅ | 原生调试，复用 Xcode 的 LLDB（新增后端） |
> | `x64dbg` | ❌ | Windows 专属 |
> | `ig5_emulate` | ❌ | 随包 Unicorn 仅 Windows DLL |
>
> **安装（macOS）**：不要用 `install.ps1`（硬校验 `win32-x64`）。
>
> ```bash
> git clone https://github.com/pyt111/dsh-infinite-gen-5.git
> cd dsh-infinite-gen-5
> ./install-darwin.sh          # 一键安装：构建运行时 + 部署 + 注册 + 自检
> ```
>
> 已有装好的机器？用 `--reuse` 跳过下载与编译（约 20 秒）：
>
> ```bash
> ./install-darwin.sh --reuse /path/to/existing/.dsh/plugins/dsh-infinite-gen-5
> ```
>
> 装完重启 DSH 即可使用。`./verify-darwin.sh --plugin` 可随时自检。
>
> **文档**：👉 [**快速开始**](docs/QUICKSTART.md) · [平台适配](docs/DARWIN_X64.md) · [lldb 调试车道](docs/LLDB_LANE.md) · [实验记录](docs/DARWIN_X64_NOTES.md) · [维护速查](.ig5-local/README.md)
>
> 上游同步：`./sync-upstream.sh`（rebase 到 `darwin-x64` 分支）

首次使用：从 [Windows x64 完整包发布页](https://github.com/Minglink/dsh-infinite-gen-5/releases/latest) 下载完整 Windows ZIP → 完整解压 → 运行 & .\plugin\install.ps1 → 重启 DSH → /ig5 engines → /ig5 open --engine ghidra <路径>。完整包默认离线安装；旧附件不会自动获得新安装器修复。使用 [最新源码 ZIP](https://github.com/Minglink/dsh-infinite-gen-5/archive/refs/heads/master.zip) 或 git clone 时，可在源码根目录运行 & .\install.ps1，安装器检查源码与 DSH profile 后下载固定资产，只补齐运行时和上游源码，保留当前代码。高级功能通过 /ig5 toolset full 展开。


<p align="center">
  <img src="assets/banner.png" alt="无限五代 IG5 · AI 驱动的专业逆向工作台" width="100%" />
</p>

<p align="center">
  <a href="#local-install">
    <img src="https://img.shields.io/badge/DeepSeek%20Harness-📦%20本地自包含安装-10B981?style=for-the-badge&logo=deepseek&logoColor=white" alt="本地自包含安装" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/开源协议-CC%20BY--NC--SA%204.0-brightgreen?style=for-the-badge" alt="CC BY-NC-SA 4.0 协议" />
  </a>
  <img src="https://img.shields.io/badge/项目性质-非盈利开源公益-blue?style=for-the-badge" alt="非盈利开源公益项目" />
</p>

> 🌐 **插件生态市场**：[DeepSeek Harness Hub - DeepSeek 官方与开源生态市场 | 插件发现与一键安装](https://deepseek.stream/)

> ## 💬 DeepSeek 交流群 & 社区
>
> ### 👉 **红队安全交流 9 群：`338431075`**
> ### 👉 **腾讯频道技术交流社区：`pd86424753`**
>
> 🔥 欢迎进群交流 AI 辅助逆向工程心得、二进制安全审计经验、软件漏洞分析基准与大模型逆向工具生态共建！

---

## 🚀 项目定位与五代革命性升级

**无限五代（dsh-infinite-gen-5 / IG5）** 是专为 **DeepSeek Harness (DSH)** 桌面客户端打造的高性能、无头**逆向分析插件与可视化工作台系统**。

与上一代以提示词注入为主的形态不同，五代彻底实现了从“脚本封装”向专业级全功能 Agent 逆向工作站的本质蜕变：
* **零提示词常驻占领**：不侵占全局系统提示词，彻底杜绝大模型在日常对话中的偏见与输出畸变；
* **38 项专业逆向工具面**：覆盖二进制侦察、CFG、符号与类型、真实 IR、受限仿真、原生调试、跨引擎修改计划，以及显式解密和报文解析；
* **双模式动态降噪**：默认仅加载 **Core 8 核心工具**，减少常驻工具描述开销；高级场景按需展开为 **Full 38 全景工具**；
* **人机协作安全审批门**：12 个写入或执行工具通过宿主公共审批服务请求一次批准，仅明确的 `allowed-once` 才交给后续工具策略；拒绝、缺少活跃 agent 或审批服务时不执行。自建操作日志覆盖部分数据库修改，具体 Undo 范围以各后端为准；
* **现代化交互式工作台**：原生注入 DSH 桌面端，包含富交互 SVG CFG（平移/缩放/双击汇编跳转）、局部变量切片高亮、在线 C 结构体声明草稿箱与真实审计时间线。

---

> ### ⚖️ 严正法律免责与合规使用声明（Strict Legal & Compliance Disclaimer）
>
> **【合规与合法使用严正申明】**：本项目坚决反对并严禁任何形式的违法犯罪行为！本项目开发者绝不支持、不鼓励、不协助任何未授权漏洞挖掘、黑灰产破解、非法获取计算机信息系统数据或破坏计算机信息系统的活动。
>
> 1. **合法受控范围限定**：本项目定位为面向安全研究员、逆向工程师、高校师生及企事业单位的**辅助逆向工程科研工具与防御性软件安全审计套件**。使用本工具必须严格遵守《中华人民共和国网络安全法》、《中华人民共和国数据安全法》、《中华人民共和国计算机软件保护条例》及相关司法解释。**严禁在未经软件著作权人或资产所有者合法书面授权的目标、商业软件或生产系统上运行本项目**。一切逆向与调试行为必须严格限制在自有软件、授权网络安全演练靶标、开源软件审计及合规教学科研环境中进行。
> 2. **严禁违法恶意用途**：使用者严禁利用本项目直接或间接从事：
>    - 破解侵犯正版软件版权、绕过数字版权管理（DRM）或商业授权验证机制；
>    - 分析、提取或利用漏洞编写武器化恶意载荷、病毒木马或勒索软件；
>    - 逆向分析特定受保护的关键信息基础设施系统并实施未授权入侵或窃密；
>    - 违反相关大模型提供商的《服务条款（Terms of Service）》与《滥用政策（Usage Policy）》。
> 3. **开源协议与严格非商用限制（CC BY-NC-SA 4.0）**：本项目依据 **CC BY-NC-SA 4.0（署名-非商业性使用-相同方式共享 4.0 国际开源协议）** 及严禁商用特别条款“按现状（AS-IS）”提供。**严禁任何个人、企业或第三方将本项目（或二次开发衍生版本）用于商业售卖、付费倒卖、商业培训封装或黑灰产牟利，二次开发商用属于严重违法违规行为**。使用者应对自身的所有下载、部署、运行、修改、传播行为以及由此产生的全部输入与输出后果承担独立、完全的法律责任。项目作者与贡献团队绝不承担任何因使用者滥用导致的直接、间接或连带责任。
> 4. **第三方独立性声明**：本项目属于完全独立的开源逆向辅助工具研究项目，与 DeepSeek 官方或其关联主体无任何隶属、商业合作或官方背书关系。

---

## 🧰 工具面与能力矩阵（24 只读 + 12 审批 + 2 配置）

五代提供 38 项逆向工具，并采用 **Core / Full 智能分级机制**：

| 类别 | 数量 | 工具清单 | 典型功能说明 |
| :--- | :---: | :--- | :--- |
| **只读分析面** | 24 | `ig5_doctor`, `ig5_open`, `ig5_status`, `ig5_funcs`, `ig5_strings`, `ig5_decompile`, `ig5_xrefs`, `ig5_calls`, `ig5_bytes`, `ig5_search`, `ig5_listing`, `ig5_scan`, `ig5_export_diff`, `ig5_cfg`, `ig5_slice`, `ig5_fingerprint`, `ig5_stack`, `ig5_switches`, `ig5_vtables`, `ig5_microcode`, `ig5_bindiff`, `ig5_ir`, `ig5_crypto`, `ig5_protocol` | 静态证据、启发式差异、显式参数数据变换、捕获文件解析与明确 schema 解码；分析产物单独保存，不修改原始输入或引擎数据库 |
| **写操作审批门** | 12 | `ig5_rename`, `ig5_patch_bytes`, `ig5_comment`, `ig5_analyze`, `ig5_set_type`, `ig5_undo`, `ig5_run_idapython`, `ig5_dbg`, `ig5_struct`, `ig5_switch_repair`, `ig5_emulate`, `ig5_sync` | 按工具名称请求公共 `approval.request`（含 sync preview）；仅 `allowed-once` 继续后续策略。拒绝、不可用、未知结果或请求异常均拒绝执行，取消保持取消；实际执行后登记审计 |
| **生命周期/配置** | 2 | `ig5_close`, `ig5_profile` | 会话安全关闭与工具集热切换（Core 8 ↔ Full 38） |

### 💡 Core 8 与 Full 38 动态降噪架构
* **Core 8 默认模式**：日常对话中仅注册 `ig5_doctor`、`ig5_open`、`ig5_status`、`ig5_funcs`、`ig5_strings`、`ig5_decompile`、`ig5_close`、`ig5_profile` 8 个工具，减少模型常驻工具上下文。
* **Full 38 展开模式**：需要高级分析时，模型可调用 `ig5_profile toolset=full`，或由用户在聊天框直接输入命令切换：
  ```text
  /ig5 toolset full   # 展开为全量 38 个专业工具
  /ig5 toolset core   # 恢复为轻量 8 工具省 Token 模式
  ```

支持 scoped API 的 DSH 全局保留 Core8，Full 只展开到当前智能体会话，其他会话不受影响；`ig5_profile` 返回 `toolsetScope=agent`。旧宿主保留插件实例模式并明确返回 `plugin-instance`。切换不持久化，重载按配置初始化；不会授予运行或写权限。

### 调查任务与单函数证据包

Core8 保持不变。`ig5_decompile style=dossier` 在同一静态会话与数据库修订下聚合反编译、CFG、调用者/被调函数和栈帧，逐章返回成功、截断、不支持或错误，整个证据包保留实际来源与分析 partial；正文按 UTF-8 字节和每个数组的项数限制输出，结果在同会话修订内缓存。响应预算不等于全部后端计算预算，宜围绕问题选取少量函数。

已打开目标可用 `ig5_profile target=... workspace={action:create,goal:...}` 建立持久调查任务，get/list 恢复进展，update 用返回的 `taskRevision` 作 `expected_task_revision` 防止覆盖并发修改。`ig5_decompile style=dossier task_id=...` 将系统快照与独立报告 hash/引用绑定任务；重开或修订变化会标记旧证据 stale。hypothesis/conclusion 与 status 是调用者陈述，保存不代表验证；任务不写 IDB、不授予样本执行权限。参数与恢复步骤见 [调查工作流](docs/INVESTIGATION_WORKFLOW.md)。

本轮已用本机实际安装的 **DSH `0.2.1-alpha.1`** SDK 验证工具 registry、两个 agent 的 Core/Full 隔离、七技能、命令、投影、审批拒绝及卸载。插件声明 `@deepseek-ai/dsh: >=0.2.0-rc.1 <0.3.0-0`，宿主按 `includePrerelease: true` 判断版本；这个范围接受 0.2 的相应预发布版，排除 0.3（含预发布版），不等于每个版本均已完成运行验收。用户所说的“0.2.1 re1”应以安装包实际 runtime 版本对账，详见 [兼容记录](docs/DSH_COMPATIBILITY.md)。

工具返回严格 JSON：可选对象字段的 `undefined` 被省略，`null` 保留；数字必须有限，零必须为正零，64 位地址使用十六进制字符串。常量样本的扫描熵返回 `0.0`，未读取到字节的熵仍为 `null`。无效数组项、BigInt、循环对象或非 JSON 值会明确拒绝，避免宿主在展示结果前校验失败。

---

## 🌟 核心技术亮点

### 1. 交互式 SVG 控制流图 (CFG) 与变量切片
* **富交互画布**：工作台内置高性能原生 SVG 渲染引擎，支持鼠标平移（Pan）、滚轮缩放（Zoom），清晰标明分支与回边。
* **双击汇编跳转**：在流程图上双击任意基本块，即可直接呼出该块的只读反汇编指令检视窗。
* **局部变量切片**：点击变量读取匹配代码行并高亮标识符；这是焦点行过滤，不代表完备的定义使用链或污点分析。

### 2. 轻量纯内存单函数仿真执行 (`ig5_emulate`)
* **内置 Unicorn 2.1.4 引擎**：无需安装庞大的外部依赖，零环境污染。
* **受限函数执行**：Reverse 与 Ghidra 通过公共内存映像提供器执行 x86/x64，Ghidra 另支持 ARM64 / AAPCS64；内存复制上限 64 MiB，可设置参数和指令/时间预算，捕获返回值、内存和 fault。无 OS/import/TLS 环境，不能外推真实进程行为。ARM64 样本在 Windows 宿主仿真通过，不代表 Android 原生运行包已完成。

### 3. Reverse Win32 与 x64dbg 原生调试车道 (`ig5_dbg`)
* Reverse native win32 与自建 x64dbg SDK/NamedPipe headless bridge 已分别验证真实 start、ASLR/RVA 断点、寄存器读写、step 与结构化异常；两条后端证据分别记录。Bochs 仍只有 load/bpt 通过。
* x64dbg 已分别验证 x64/x86 的真实 headless 闭环，其中 x64 中文路径 PE 覆盖受限 5 步 trace、控制 owner/takeover、过期 run/stop 拒绝、缓存读取与 stop/dispose；不使用 automate/ZeroMQ。load 不启动样本，执行需目标运行授权和审批。

### 4. C++ 虚函数表 (vtables) 与跳转表 (Switches) 恢复
* 支持 MSVC64 与 Itanium class/SI/VMI RTTI 布局检视；已验证生成 PE 夹具，未验证原生 Linux ELF 装载，调用解析要求显式表地址和偏移。
* 读取已识别跳转表的分支信息；修复默认 preview，应用需审批且不在 Reverse 操作日志的 Undo 范围。

### 5. 解密、配置提取与协议分析

* `ig5_crypto`：有界 hex/base64、本地文件、静态字节或 blob ref 输入；检查熵/编码/压缩头，执行 XOR、AES-CBC/CTR/GCM、gzip/zlib 及精确验证。`recover` 支持单字节 XOR 全空间、重复 XOR 统计/已知明文约束和 AES 候选材料检索；Latin、有效 UTF-8 CJK 和有限二进制格式头只影响候选评分，不保证任意中文编码或未知二进制。完整密钥以敏感 blob ref 复用，报告不展示原始密钥；随机 AES 全空间不在现实穷举能力内。
* `ig5_protocol`：解析已有 PCAP/PCAPNG 与受支持的 TCP/UDP 层，按方向保留连续片段、缺口与冲突。`infer` 提出有限整数长度、canonical varint 长度、TLV、固定长度及换行分帧候选和字段证据，支持独立 holdout；输出可传给 `decode`。TLV 不等于通用嵌套/BER 解析；没有实时抓包、通用协议语义/状态机自动恢复或 IP 分片重组。
* 两条数据车道在独立 Node worker 中执行，报告和输出单独保存到 analysis-data；后续调用使用 `result_id` 和 SHA-256 ref，避免重复大缓冲区。工作台只读查看结果，操作入口生成用户可审阅的 composer 草稿。动态取证和执行仍走原有审批门。
* 解密输入/输出最多 1 MiB，协议输入最多 8 MiB，完整报告与模型预览分别受预算控制。算法参数不写入保存的报告；输入/明文产物仍可能包含敏感内容，应按用户工程保管。纯数据层不依赖静态引擎，可供支持 Node worker 的宿主复用，但尚未通过 Android/iOS 真机验收，也不补足手机原生运行包。

具体参数、可重复使用的调用例子和验收边界见 [解密与协议工作流](docs/CRYPTO_PROTOCOL.md)。

---

<a id="local-install"></a>

## ⚡ 本地自包含安装

需要 Windows x64 和已安装的 DeepSeek Harness profile。完整 ZIP 包含插件、两套开源运行依赖和上游源码；GitHub **Source code ZIP / tar.gz** 或 `git clone` 提供插件维护源码。当前源码的 `install.ps1` 能为源码目录补齐资产：显示固定附件、大小和进度，流式下载并核验固定 ZIP 大小/SHA-256、校验文件、GitHub 资产摘要（如有）及逐文件清单，最后只补齐 `runtimes/` 与 `third_party/sources/`。固定供体由 `scripts/distribution.json` 锁定为已发布的 `IG5-1.0.0-Windows-x64-dsh021-full-20261010.zip`；它提供不变的引擎资产，不覆盖当前插件代码，也不表示旧 ZIP 已包含本次修复。

1. 完整解压下载的 ZIP，保留包内 `plugin/runtimes/`、`plugin/third_party/sources/` 与各清单文件，不单独复制安装脚本；
2. 打开 PowerShell，进入 ZIP 解压根目录；
3. 执行一键安装脚本：
   ```powershell
   & .\plugin\install.ps1
   ```
4. 脚本离线核验完整运行包，暂存插件及内置依赖，备份已有插件并配置 profile；缺件或校验失败时拒绝安装；
5. 重启 DeepSeek Harness；使用 `/ig5 engines` 或 `ig5_doctor` 检查实际引擎可用性。

源码安装默认首次联网获取完整资产，下载或校验失败不会更改 DSH profile。已下载原始固定 ZIP 的用户可完全离线复用，**在最新源码根目录**执行：

```powershell
& .\install.ps1 -DistributionArchive 'D:\IG5-1.0.0-Windows-x64-dsh021-full-20261010.zip' -Offline
```

`-DistributionArchive` 指向原始 ZIP 文件，并置于源码目录之外；安装器检查固定大小和整包 SHA-256，再在独立暂存目录提取、逐文件校验和安装。已确认完整的解压目录也可作为供体：

```powershell
& .\install.ps1 -DistributionRoot 'C:\已解压的完整发行包根目录' -Offline
```

`-DistributionRoot` 指向含 `manifest.json` 与 `plugin/` 的完整解压根目录，不能与 `-DistributionArchive` 同时使用。只传 `-Offline` 而未提供完整资产时，安装器给出对应发布页和可执行指引；需要下载固定供体时见 [已发布资产基线](https://github.com/Minglink/dsh-infinite-gen-5/releases/tag/v1.0.0-dsh021-20261010)。固定 ZIP 的 SHA-256 为 `a2459ddca1f19e5eec2d7918c504f133889809800a0b277e1e379d3ce1459b54`。

若完整包的 `runtimes/` 或 `third_party/sources/` 缺件、SHA-256 不符，当前安装器支持显式 `-RepairAssets`：先核验插件自身代码与完整外层清单一致，再以固定供体替换这两类资产并完整复验；核心代码被改动、外层清单缺失、资产版本或固定哈希不符仍拒绝。对于**包含此参数的新安装器完整包**，可在解压根目录执行：

```powershell
& .\plugin\install.ps1 -RepairAssets -DistributionArchive 'D:\IG5-1.0.0-Windows-x64-dsh021-full-20261010.zip' -Offline
```

SHA-256 不符时保留报错中的相对路径、Expected/Actual SHA-256 和文件大小，并核对原始 ZIP 哈希；当前证据不能确定其他用户文件变化的原因，不能直接归咎某种解压工具。不要改清单、跳过校验或只补空 JSON。安装成功后 profile 的 `node_modules/dsh-infinite-gen-5` 应指向 `.dsh/plugins/dsh-infinite-gen-5` 的完整目录；未完成安装而保留的普通 npm 源码副本没有运行时。完全退出并重启 DSH 后，以 `/ig5 engines` 和 `ig5_doctor engine=ghidra` 验证新副本。维护者资产重建步骤见 [BUILD](docs/BUILD.md)。

---


## 🧭 逆向工作台操作与常用指令

在对话框中可直接使用斜杠命令与模型工具调用：

### 1. 快捷斜杠命令（免模型 Token 消耗）
* `/ig5 status`：查看已打开引擎会话、样本身份、数据库修订与当前状态；
* `/ig5 engines`：检查三引擎配置和可用性；
* `/ig5 open --engine ghidra <样本路径>`：显式选静态后端；省略参数使用默认引擎，打开不启动样本；
* `/ig5 toolset full`：展开为 38 个全量逆向分析工具面；
* `/ig5 toolset core`：恢复为 8 工具轻量模式；
* `/ig5 export --engine ghidra <样本路径>`：导出指定数据库当前有效字节补丁副本与报告（尊重 Undo）；多目标时明确路径和来源。

### 2. 7 个原生工作流技能包（Runbooks）
系统预置 7 套分析流程，可在聊天中直接唤起：
* `/ig5-triage`：**新样本 10 分钟快速侦察流**（架构识别 → 熵与加密常量扫描 → 库函数过滤 → 提出关键假设）；
* `/ig5-deep-dive`：**核心算法攻坚流**（关键分支定位 → CFG 拓扑 → 变量切片 → 重建结构体与命名）；
* `/ig5-patch-and-sign`：**补丁实验与哈希签收流**（前置原字节安全校验 → 审批门提交 → 导出副本并校验 SHA-256）；
* `/ig5-diff`：**版本补丁差异比对流**（提取新旧二进制调用图与拓扑结构，定位 Patch 变更块）；
* `/ig5-debug-live`：**动态调试验证流**（断点设置 → 进程挂载 → 命中事件 → 寄存器回读）；
* `/ig5-crypto`：**解密与配置提取流**（定位处理路径 → 显式参数/捕获证据 → 数据变换 → 认证或已知明文对比 → 产物引用）；
* `/ig5-protocol`：**协议证据流**（导入捕获 → 检查方向/缺口/冲突 → 明确分帧与字段 → 多报文复核 → 保存解码配置与结果）。

---

## 📁 项目目录结构

```
dsh-infinite-gen-5/
├── 🖼️ assets/
│   ├── banner.png               # 无限五代高分辨率宽屏海报
│   └── community.jpg            # 官方社区与交流群二维码
├── 🚀 一键安装与维护套件
│   ├── install.ps1              # Windows 自动化一键部署脚本
│   └── uninstall.ps1            # 自动化卸载脚本
├── 🧩 核心插件装载面 (Cordis 架构)
│   ├── package.json             # 插件元数据（dsh-infinite-gen-5 v1.0.0）
│   ├── index.js                 # 宿主核心（38工具注册 + 审批门 + 三大 HTTP 诊断端点）
│   ├── client.js                # 工作台前端（SVG CFG + 变量切片 + 结构体草稿箱）
│   ├── advanced_tools.js        # 高阶工具扩展（栈帧 / 跳转表 / 虚表 / 微代码 / 差异比对）
│   ├── semantic_diff.js         # 多特征启发式匹配算法
│   ├── engine_runtime.js        # 独立运行包配置与引擎路由
│   ├── integration_tools.js     # Ghidra IR 与显式跨引擎 changeset
│   ├── analysis_tools.js        # 数据输入、任务与历史报告的工具组合
│   ├── source/                 # 身份/地址、纯数据分析、隔离 jobs 与 analysis artifacts
│   ├── adapters/               # Ghidra / x64dbg 独立工作进程
│   ├── runtimes/               # 随包 Ghidra/JDK/Python 与 x64dbg/Python/bridge
│   ├── third_party/sources/    # 上游源码、固定gitlinks与逐文件来源/hash清单
│   ├── workflow.js              # 原生命令与技能包生命周期管理器
│   ├── cordis.patch.yml         # 宿主加载补丁配置
│   └── HARNESS_PLUGIN.md        # 插件技术规范文档
├── 🧠 原生逆向技能包 (skills/)
│   ├── ig5-triage/SKILL.md      # 新样本快速首探 Runbook
│   ├── ig5-deep-dive/SKILL.md   # 单函数深挖 Runbook
│   ├── ig5-patch-and-sign/      # 补丁验证与导出 Runbook
│   ├── ig5-diff/SKILL.md        # 版本差异比对 Runbook
│   ├── ig5-debug-live/SKILL.md  # 动态调试交互 Runbook
│   ├── ig5-crypto/SKILL.md      # 解密与配置提取 Runbook
│   └── ig5-protocol/SKILL.md    # 捕获、分帧与字段证据 Runbook
├── 🐍 后端逆向工作进程 (worker/)
│   ├── ig5_worker.py            # JSON-RPC 核心通信进程（Reverse 引擎封装）
│   ├── advanced_analysis.py     # C++ 虚表/RTTI/微代码/跳转表分析实现
│   ├── execution_analysis.py    # Unicorn 仿真执行核心
│   └── vendor/unicorn/          # 插件内置 Vendored Unicorn 2.1.4 运行时
└── 🧪 自动化测试套件 (scripts/)
    ├── test_new_tools.mjs       # 真实样本基础工具烟测
    ├── test_advanced_runtime.mjs# Unicorn 仿真 / 微代码 / 虚表 / 跳转表回归测试
    ├── test_debug_runtime.mjs   # 原生 Win32 真实进程调试全流程闭环回归
    ├── test_client.mjs          # SVG CFG / 变量切片 / 竞态条件前端自动化测试 (含引擎切换与原生焦点回归)
    ├── test_workflow.mjs        # Core8/Full38、七技能注册/回滚/生命周期测试
    ├── test_crypto_analysis.mjs # 固定向量、认证与压缩/输出预算
    ├── test_protocol_analysis.mjs # 捕获、重组、分帧与字段边界
    └── test_patch_runtime.mjs   # 补丁审批与安全回滚测试
```

---

## 💬 官方交流社区

> 📌 **非盈利开源公益项目，严禁任何主体用于商业售卖、付费倒卖或黑灰产牟利，仅供技术研究交流。**

<p align="center">
  <img src="./assets/community.jpg" width="240" alt="DeepSeek 网安逆向技术交流社区" /><br>
  <sub><b>🌐 官方技术交流社区（腾讯频道号：pd86424753 · 红队安全交流 9 群：338431075）</b></sub>
</p>

---

## 📄 开源协议与非商用特别声明（License）

本项目采用 **[CC BY-NC-SA 4.0（署名-非商业性使用-相同方式共享 4.0 国际许可协议）](LICENSE)** 进行开源，并附加以下严格的法律与商业限制条款：

1. 🚫 **严禁直接商业使用**：禁止任何个人、企业或第三方将本项目自有代码、组件、前端界面及文档用于商业售卖、付费倒卖、付费社群、会员增值服务或黑灰产牟利。随包第三方源码、运行件和依赖继续适用各自上游许可，项目 NC 条款不覆盖它们。
2. 🚫 **严禁二次开发商业化**：任何基于本项目的 Fork、修改、重构、二次开发或作为组件嵌入其他软件时，**必须严格继承 CC BY-NC-SA 4.0 协议并完全开源，绝对禁止将任何二次开发或衍生作品用于商业营利**。二开商用属于严重侵权及违法违规行为。
3. ⚖️ **违规终止与法律追责**：任何违反非商业性条款或将本项目用于违法黑产活动的行为将导致开源授权自动且永久终止，原作者保留依法追究侵权方民事赔偿与法律责任的一切权利。
