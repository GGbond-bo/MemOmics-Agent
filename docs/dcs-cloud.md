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

## 面板/工具动作（17 个）

| 动作 | 作用 | 备注 |
|------|------|------|
| `status` | 绑定状态 / CLI 版本 / 当前会话 | 未绑定时也会给"去哪儿绑"的指引 |
| `bind` / `unbind` | 绑定 / 解绑 PAT | 绑定会跑一次真实 `dcs auth login` 校验令牌 |
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
| `webui/server.py` | `/api/dcs/status|bind|unbind|config|exec` 五条薄路由（与 `/api/cluster/*` 同款） |
| `webui/index.html` | 左侧「☁️ DCS 云」面板；远端集群的 `cc-*` 样式改为 `.cc-console` 类，两个面板共用 |
| `scripts/install_dcs_cli.ps1` | 官方 CLI 安装器：官方 CDN + SHA256 校验，校验不过就删文件、绝不执行 |
| `webui/tests/test_dcs_cloud_connector.py` | 25 项离线回归（假 CLI + 临时 HERMES_HOME，不用真 PAT、不联网） |
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

## 限制与后续

- **没有**采用"网页会话自动化（`cld:token`）"方案：那是未公开接口，脆弱且违反稳定性预期；连接器只走官方 CLI。
- `analysis run`（投递离线任务）与 `workflow submit_task`（WDL 投递）目前走 `raw` 逃生舱，参数模板与计费确认后
  再升级成专用动作（`analysis_submit` / `workflow_submit`）。
- 可加：`terminal ls_resource`（容器规格列表）、PAT 到期提醒（`status` 已回 `expires_at`）、把云路径纳入
  `remote_cluster locate` 式的"数据在哪"判定（本地 / 集群 / DCS 云三选一）。