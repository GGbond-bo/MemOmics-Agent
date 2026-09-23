# 后台任务面板（⏱ 任务）

> 目标：用户随时能回答「现在在跑什么、在哪跑、什么环境、PID 多少、跑到哪一步、产物在哪、日志怎么说、能不能停」。
> 契约由任务自己写（wrapper / 脚本打点），服务端只读取 + 核对存活；面板只显示，不猜。

## 1. 面板（webui/index.html）

- 左侧导航 `⏱ 任务`（`id="nav-tasks"`）→ 面板 `id="panel-tasks"`；
- 列表：状态图标 + 标题 + 类型 + 会话 + PID + 阶段 `阶段 2/4：出图` + 进度条 + 耗时 + 环境行；
- 详情抽屉：状态/进度/阶段时间线（每段耗时）/关键参数/实际命令/脚本内容/产物（存在与否 + 字节数）/日志尾部（可 grep）/取消按钮；
- 进视图订阅 WS 推送（服务端只在契约变化时推），切走即退订；没订阅上才退回 2000 ms 轮询
  （订阅成功则把轮询降到 8000 ms 兜底）。轮询只在任务视图里跑，不打扰别的页面。

## 2. 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/tasks?refresh=1&limit=100&states=running` | 列表；`refresh=1` 用 PID + 进程创建时间核对存活，进程没了就把活任务收敛成 `interrupted` |
| GET | `/api/tasks/{id}?tail=200&script=1` | 详情：**`{ok, task:{...}}`**（注意是嵌套的），含 stages/outputs/params/log_tail/script_text/env/proc |
| GET | `/api/tasks/{id}/log?tail=200&grep=WARN` | 日志尾部（seek 读，不整读几百 MB），`grep` 是不区分大小写的子串过滤，结果在 `text` |
| POST | `/api/tasks/{id}/cancel` | 需要 `X-Task-Token`（从 `/api/tasks` 的 `api_token` 拿），返回 wait/escalated/killed/kill_wrapper/marks |
| GET | `/api/middleware/audit?routes=1` | 路由清单漂移（`added`/`removed` 是**列表**，空列表=没漂移） |

### 2.1 实时推送（复用已有的 `/ws`，不新开端口也不新增路由）

面板订阅走聊天那条 WebSocket（`ws://<host>/ws`），消息类型两种：

| 方向 | 消息 | 说明 |
| --- | --- | --- |
| 面板 → 服务端 | `{"type":"task_subscribe"}` | 订阅后**当场**回一份快照（首屏不空） |
| 面板 → 服务端 | `{"type":"task_unsubscribe"}` | 退订（切走视图、离开页面） |
| 服务端 → 面板 | `{"type":"tasks", ...}` | 与 `GET /api/tasks` **同一个载荷**（同一个函数生成的，字段不会漂） |

推送策略：订阅期间服务端每 1.5 s 比一次「任务目录指纹」（契约条数 + 最新 mtime + 总字节），
**指纹变了才推**整份列表；没人订阅扫描循环自己退出（不占 CPU）。断线/退订即摘连接，
不往死连接推。多开几个标签也只算一份扫描。

## 3. 契约（memomics/bio_tools/task_run.py）

字段：`task_id/title/type/status/session_id/session_dir/log/pid/started_at/finished_at/duration_sec/
exit_code/error/summary/progress{value,text}/params{}/outputs[]/stages[{name,status,sec}]/stage_index/stage_total/
env{}/proc{}/wrapper{}/cancel_requested/cancel_by/cwd`。

脚本打点（四个标记，全部可选，缺了也能跑）：

```text
#TASK:STAGE 读入数据      → 阶段（stage_index 自增，上一段自动收尾计时）
#TASK:PROGRESS 0.42 过滤中 → 进度 0~1 + 说明
#TASK:PARAM 样本数=12      → 关键参数（面板「关键参数」区）
#TASK:OUTPUT results/x.csv → 产物（绝对路径最稳；相对路径见下）
```

启动方式（**长任务一律走它**，别用 `start /b` 或 `Popen` 一扔了事）：

```bat
python memomics\bio_tools\task_run.py --type qc --title "QC 过滤" --stages "读入,过滤,出图" ^
  --param 样本数=12 --script D:\work\qc.R --session-dir <会话目录> -- <真正的命令>
```

## 4. 两条边界（都踩过）

- **相对产物路径**：子进程以 wrapper 的工作目录为 cwd 跑，脚本却常把文件写到 `<会话>/results/`。
  服务端解析顺序：绝对路径 → 会话目录 → 会话/results → 任务 cwd → 仓库；解析结果回在 `outputs[].abs`。
  （历史 bug：只按会话目录拼一次，于是文件明明在、面板说「文件不存在」。）
- **脚本正文**：只读会话目录/仓库内的脚本（防止面板变成任意文件读取）。够不着时返回
  `script_note`（"脚本在会话目录/仓库之外，面板不读（安全策略）：<路径>"），不会静默空白。

## 5. 实测记录

T5 极端场景实测（真实 R 分析 / 4 组表格 / Europe PMC 文献下载 5/5 全文 / 6 段长任务中途取消 /
4 路并发 / 8 MB 脏字节日志 / 失败传播 / 路由漂移）共 40 项断言，驱动脚本与证据在仓库外的
`E:\release\_t5\`。面板 JS 用 node 假 DOM 真跑（`webui/tests/test_task_panel_ui.py`），
接口契约用 FastAPI TestClient 真跑（`webui/tests/test_task_routes.py`）。

### T9 实时推送 + 越界补测（真机 8899，2026-09-24）

`E:\release\_t9\ws_verify.py`（真 WS 客户端 + 真起任务）11 项断言全过：

| 断言 | 实测 |
| --- | --- |
| 订阅当场回快照 | `type=tasks`、`ok=true`、带 `api_token` 与 `tasks_dir` |
| 推送与 HTTP 同源 | counts 与字段集完全一致（同一函数生成） |
| 任务一跑就推 | 12 s 的任务收到 6 条推送：running/读入 → 读入 → 读入 → 计算 50% → done |
| 收尾推送 | `done` + 自动小结「完成 · 2/2 段 · 12s · 1 个产物」 |
| 空闲不推 | 静止 6 s 收到 0 条（指纹没变就不推） |
| 退订即停 | 退订后再起一个任务，12 s 收到 0 条 |
| 路径穿越 | `../`、`..\\`、绝对路径、`....//`、`%00`、`.json` 共 10 种 × 详情/日志 = 20 个请求全 404 |
| 不泄漏内容 | 仓库根放金丝雀 `CANARY_T9.txt`，20 个请求里一个字节都没带出来（跑完即删） |

回归测试：`webui/tests/test_task_ws.py`（订阅协议 / 退订摘连接 / 指纹 / 失败不撒谎）+
`test_task_routes.py::test_h1`（穿越三路由）、`test_h2`（越界脚本不读）。
