# ☁️ DCS 云连接器（华大 DCS Cloud / GenPilot）

> 2026-10-07 接入。一句话：MemOmics 通过**官方 PAT（个人访问令牌）+ 官方 `dcs` CLI** 操作用户**自己**的
> DCS Cloud（www.dcs.cloud）项目 —— 看项目/数据、上下传文件、在云上在线容器里跑命令、查离线任务与日志。
> 这条链路也是 GenPilot「智能分析」用的同一套云端体系（OpenSandbox 容器），所以它同时是「让 MemOmics 上云算」的地基。

## 用户怎么用（三步）

| 步骤 | 做什么 | 在哪做 |
|------|--------|--------|
| ① 装 CLI（一次性） | `powershell -ExecutionPolicy Bypass -File scripts\install_dcs_cli.ps1`（官方 CDN 下载 + SHA256 校验，装到 `%LOCALAPPDATA%\MemOmics\tools\dcs\`） | 本机终端 |
| ② 绑账号 | 「☁️ DCS 云」→ ⚙️ 设置 → 粘贴 PAT（DCS → 个人中心 → **访问令牌** → 创建，最长 1 年）→ 🔗 绑定 | WebUI 左侧导航 |
| ③ 用 | 面板点「📁 项目 / 🗂 数据 / 📋 任务」；或直接在对话里说（模型调 `dcs_cloud` 工具，和面板共用同一套后端） | WebUI / 对话 |

首次绑定后建议顺序：`projects` → `use_project` → `ls`。真机上如果 CLI 没装，面板/工具都会明确提示去跑安装脚本，不会静默失败。

## 面板/工具动作（18 个）

| 动作 | 作用 | 备注 |
|------|------|------|
| `status` | 绑定状态 / CLI 版本 / 当前会话 | 未绑定时也会给"去哪儿绑"的指引 |
| `bind` / `unbind` | 绑定 / 解绑 PAT | 绑定会跑一次真实 `dcs auth login` 校验令牌 |
| `context` | **开工前确认上下文（只读）**：会话 / 候选项目（含欠费旗标）/ 数据根 / 默认下载目录 + 必问清单 | 用户说"在云上跑 / 投递任务"时**第一步**调它 |
| `projects` / `use_project` / `current` | 项目列表 / 切换 / 当前 | 切项目后容器会话失效，需重开 |
| `ls` / `find` / `info` | 浏览 Files / 搜索 / 元数据 | `find` 支持名字、类型、大小、时间、样本等过滤 |
| `download` / `upload` | 云 → 本机 / 本机 → 云 | 小文件 `web`（上 ≤100MB，下 ≤200MB）；大文件用 `raw` 切 `oss`/`raysync` |
| `container_open` / `container_exec` / `container_close` | 在线容器开关 + 容器内执行 | 打开后等 3–5 秒再 exec（平台返回 83007）；用完关掉释放资源 |
| `tasks` / `task_logs` | 离线（个性化分析）任务列表 / 日志 | WDL 流程投递暂走 `raw` |
| `raw` | 白名单原生命令（project/data/table/terminal/analysis/workflow/image/billing/region/history） | 凭据类子命令（auth/login/logout/config）**不允许**走 raw |

## 安全与合规

- **不保存账号密码**：DCS 有双因子，且中国站点用密码登录还要手机验证；不少用户是微信扫码/短信注册，根本没有密码。只托管 PAT。
- PAT 只落 `hermes_home/dcs_cloud.json`（写入时尽力收窄权限 0600）；工具输出里只出现掩码（`dcs_pat_9f2a…abcd`）；不进日志、不进安装包。
- 一人一 PAT、不做共享账号（平台明确"API Key 仅供账号本人使用"）；用户在 DCS 侧删掉令牌即刻失效。
- 写操作（上传 / 开容器 / 投递）会改动云端数据并计费：工具描述要求模型先跟用户确认；面板对 upload 有二次确认；`allow_write: false` 可一键只读。
- 平台业务码已翻译成可操作指引：`41201/60003` → 重新绑定 PAT；`83003` → 先选项目；`83006/83007` → 容器没开/刚开。

## 配置（`hermes_home/config.yaml`）

```yaml
dcs_cloud:
  enabled: true              # 总开关；false 时工具对模型不可见
  cli_path: ''               # 留空 = 自动探测（PATH → %LOCALAPPDATA%\MemOmics\tools\dcs → 仓库 tools/dcs）；别写死本机路径（打包要求）
  base_url: https://www.dcs.cloud
  region: ''                 # 片区代码，留空用站点默认
  default_project: ''        # 留空 = 用 CLI 当前项目
  timeout: 120               # 单条命令超时秒
  max_output_chars: 20000
  allow_write: true          # false = 只读模式
```

环境变量覆盖：`MEMOMICS_DCS_ENABLED / _CLI / _BASE_URL / _REGION / _PROJECT / _TIMEOUT / _ALLOW_WRITE`。

## 代码结构与改动面

| 文件 | 角色 |
|------|------|
| `memomics/connectors/dcs_cloud.py` | 连接器核心：配置加载、PAT 凭据库、CLI 执行器（强制 `--output json --no-history`）、错误翻译、17 个动作 |
| `memomics/bio_tools/cloud_connector.py` | agent 工具壳 `dcs_cloud`（schema + `check_fn=enabled`），转调同一个 handler |
| `memomics/bio_tools/__init__.py` | 导入新模块（不导入 = 模型看不到，见 `test_bio_tools_registry_complete.py` 的事故说明） |
| `webui/server.py` | 薄路由：`/api/dcs/status|bind|unbind|config|exec|pick` + 下载队列 `/api/dcs/dl/{start,list,cancel,retry,clear,reveal}`（worker 在连接器里） |
| `webui/index.html` | 左侧「☁️ DCS 云」面板（数据/队列/日志三个标签）；远端集群的 `cc-*` 样式改为 `.cc-console` 类，两个面板共用 |
| `scripts/install_dcs_cli.ps1` | 官方 CLI 安装器：官方 CDN + SHA256 校验，校验不过就删文件、绝不执行 |
| `webui/tests/test_dcs_cloud_connector.py` | 33 项离线回归（假 CLI / 假下载器 + 临时 HERMES_HOME，不用真 PAT、不联网） |
| `webui/middleware_routes.json` | 路由清单已用 `python webui/entry_middleware.py --snapshot` 同步 |

## 验证记录（2026-10-07）

- `pytest webui/tests/test_dcs_cloud_connector.py webui/tests/test_bio_tools_registry_complete.py` → 25 passed；
  `pytest webui/tests/test_p2_1_middleware.py` → 54 passed（路由清单一致性）。
- `scripts/install_dcs_cli.ps1` 实跑：从官方 CDN 下到 v1.2.0，SHA256 与官方 `SHA256SUMS` 一致
  （`5cd97323…4a228`），装到 `%LOCALAPPDATA%\MemOmics\tools\dcs\dcs.exe`。
- 9000 端口测试实例：`GET /api/dcs/status` 返回 enabled=true / bound=false / cli_found=true；
  `POST /api/dcs/exec {"action":"projects"}` 返回"未绑定 → 去面板绑定"的可操作指引；
  假 PAT `POST /api/dcs/bind` 返回平台原始错误（business_code 60003）且**未落盘任何凭据**；
  首页包含新面板（`id="dcs-console"` 面板 + `openDcsConsole`）。
- **尚未验证**：真实 PAT 下的项目/数据/容器/任务全链路（需要用户自己的令牌），以及 `upload/download/container_*`
  的带上游行为 —— 绑上真令牌后第一次跑 `status` → `projects` → `ls` 即可确认。

## 🧭 面板结构（入口各归各位，别重复）

顶部一行：`📁 项目` · `🗂 数据` · `🧾 日志` · `⬇ 队列` 四个**视图标签** + `📋 任务` · `⬆ 上传` · `⚙️ 设置` · `✕ 关闭` 四个**动作按钮**。

| 入口 | 是什么 | 不是 |
|------|--------|------|
| `📁 项目` 标签（最左） | **项目清单**：当前项目 / 欠费 / 片区，点进去可切项目（`use_project`）。**点开面板默认就停在这里** | 不是文件浏览 |
| `🗂 数据` 标签 | 云上 **`/Files` 文件浏览**：点这个标签**总是**回到数据视图（记住上次浏览的目录），不会停在项目/任务列表上 | 不是项目列表 |
| `🧾 日志` 标签 | CLI 调用日志（`/api/dcs/exec` 的原始输出） | — |
| `⬇ 队列` 标签 | 下载队列（见下一节），带 `2⏳ / ✓3` 徽章 | — |
| `📋 任务` 按钮 | 离线任务列表 → 任务详情与日志 | — |

> 2026-10-07 修（一）：此前 `openDcsConsole` 把**项目列表**渲染在「浏览」标签里，旁边又有一个「数据」按钮 —— 三个入口看起来在做同一件事（用户原话："浏览和项目这两栏岂不是重复的？"）。项目归项目、数据入口只剩标签一个（`_dcsLastPath` 记住路径 + `dcsTabData()` 保证点击确定性）；未绑定时首屏直接给"去 ⚙️ 设置 绑 PAT"的指引。

> 2026-10-07 修（二，用户要求）：`📁 项目` 挪到工具行**最左**并升级为视图标签，**点「☁️ DCS 云」默认展示项目信息**（`openDcsConsole` 里 `_dcsOpenDefault = true` → `dcsLoad()` 默认分支改 `dcsShowProjects(1)`）；标签高亮改由 `dcsMarkTabs()` 按 `_dcsState.kind` 决定 —— 数据 / 项目 / 任务 共用同一个容器，不会再出现"停在项目列表上、亮的却是数据标签"。

## ⬇️ 下载队列（进度 / 完成态 / 多文件）

用户原话：「下载文件的时候，没有进度表，没有完成显示，我要下载多个文件，没有队列展示」。

| 环节 | 做法 |
|------|------|
| 入队 | 「🗂 数据」里勾选文件（行首复选框）→「⬇ 下载选中（N）」；或文件行「⬇ 加队列」；或文件详情「⬇ 下载到本机」（可先挑目录，用原生选择框） |
| 看队列 | 「⬇ 队列」标签（标签带 `2⏳ / ✓3` 徽章）：每行有进度条 + 状态徽章 + 用时 + 落盘路径 + 操作 |
| 进度 | 官方 CLI 不吐百分比 → 后端每 0.5s **盯本机落盘字节**，对照云上 `size` 算百分比；目录/未知大小给"不确定"动画条 + 已落盘字节数；CLI 用临时名（`name.part`）也认得出 |
| 串行 | 云盘吞吐有限，一次只跑一个（单 worker 线程）；「排队中」明确写在行里 |
| 完成 | 绿色「✓ 完成」+ 完整本地路径 +「📂 打开所在文件夹」；失败 = 红色 + 平台业务码翻译后的指引（83003 → 先选项目）；取消 = 真杀下载进程 + 保留已落盘字节（可「🔁 重试」重新入队） |
| 刷新页面不丢 | 任务登记在**服务进程内存**（`dcs_cloud._DL_JOBS`），页面重新 `dl/list` 即恢复；**重启服务才清空**（在跑的会被中断） |
| 默认目录 | 「⚙️ 设置」的 `download_dir`；留空时用真实生效目录（仓库 `results/dcs`），队列页顶部直接显示"下载到：…"并可「📂 换目录」 |

验证记录（真账号、真文件，2026-10-07）：入队 3 个真文件（260 B / 13 MB / 17 MB）→ 中间进度 **22 → 32 → 36 → 53 → 70 → 100%**，最大并发 1，落盘字节与云上 `size` 逐一相等（合计 30,455,553 B）；真取消在 12% 时变成 `cancelled`（已落盘 11,392,148 B）；离线回归 `pytest webui/tests/test_dcs_cloud_connector.py -k dl_`（假下载器 `webui/tests/fixtures/fake_dcs_download.py`：真进程、真落盘、分块写）。

## 🗣️ 「在云平台跑分析」怎么走：开工前确认协议

用户说「帮我在云平台跑分析 / 投递任务」时，**不问清不动手**（对齐仓库铁律 27 / 28 / 35）：

1. `dcs_cloud(action="context")` —— 只读一次拿齐：当前用户 / 当前项目 / 全部候选项目（含欠费旗标）/ 数据根 /
   默认下载目录 / 写开关。
2. `ask_user(kind="intent")` 一次问清五件事：**哪个项目**（当前项目只是候选 —— 用户有很多项目）、
   **数据在哪**（本机路径 / 云上 `/Files` / 容器内 `/work`，三套文件系统不互通）、**跑什么 + 参数**、
   **结果回哪**、**费用**（欠费项目会被平台拦，先充值）。
3. 用户勾选确认后才执行；upload / 开容器 / 投递都算高代价写操作，参数变了要重问。

**「是不是就用当前项目？」** —— 默认**不假定**：只有用户明说「就用当前项目」或 config 配了
`dcs_cloud.default_project` 才直接用，否则把候选列出来让他选（实测某账号 12 个项目、3 个欠费）。
切项目会让云容器会话失效（需 `container_close` 后重开）。

## 📂 本地路径：原生选择框（不再手打）

下载/上传点一下就走表单：「⬇ 下载」→ 目标目录输入框 + **「📂 选择文件夹」**（宿主进程弹 Windows 原生选择框：
tkinter 优先，缺失时自动退到 PowerShell `System.Windows.Forms`），选完自动填回；输入框旁边还有
「📌 设为默认」写进 `dcs_cloud.download_dir`。上传同理有「📄 选择文件」+ 云上目标目录。
接口：`POST /api/dcs/pick`（`{"kind":"dir|file","initial":"..."}`；带 `{"dry_run":true}` 只回默认目录、不弹窗）。

## 🧠 技能：dcs-cloud（RED 必触发）

`hermes_home/skills/bioinformatics/dcs-cloud/`：16 个触发词（云平台 / DCS / DCS Cloud / GenPilot / 华大云 /
云上跑 / 在云上 / 云上分析 / 投递任务 / 云端任务 / 云容器 / 云平台项目 / 上传到云 / 云上数据 …），
已登记进 `SKILLS_INDEX.md`（09_内置 · RED）与 `SOUL.md` 必触发表。技能内写死：铁律、触发场景（含"不该触发"
的反例：本机小分析不要上云）、确认协议五问、项目定位规则、四套配方（取数 / 云上算 / 看任务 / 投递）、坑表。

## 限制与后续

- **没有**采用"网页会话自动化（`cld:token`）"方案：那是未公开接口，脆弱且违反稳定性预期；连接器只走官方 CLI。
- `analysis run`（投递离线任务）与 `workflow submit_task`（WDL 投递）目前走 `raw` 逃生舱，参数模板与计费确认后
  再升级成专用动作（`analysis_submit` / `workflow_submit`）。
- 可加：`terminal ls_resource`（容器规格列表）、PAT 到期提醒（`status` 已回 `expires_at`）、把云路径纳入
  `remote_cluster locate` 式的"数据在哪"判定（本地 / 集群 / DCS 云三选一）。