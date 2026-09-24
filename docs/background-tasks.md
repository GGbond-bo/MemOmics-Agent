# 后台任务面板（⏱ 任务）

> 目标：用户随时能回答「现在在跑什么、在哪跑、什么环境、PID 多少、跑到哪一步、产物在哪、日志怎么说、能不能停」。
> 契约由任务自己写（wrapper / 脚本打点），服务端只读取 + 核对存活；面板只显示，不猜。

## 1. 面板（webui/index.html）

- 左侧导航 `⏱ 任务`（`id="nav-tasks"`）→ 面板 `id="panel-tasks"`；
- 列表：状态图标 + 标题 + 类型 + 会话 + PID + 阶段 `阶段 2/4：出图` + 进度条 + 耗时 + 环境行；
- 详情抽屉：状态/进度/阶段时间线（每段耗时）/关键参数/实际命令/脚本内容/产物（存在与否 + 字节数）/日志尾部（可 grep）/取消按钮；
- 进视图订阅 WS 推送（服务端只在契约变化时推），切走即退订；没订阅上才退回 2000 ms 轮询
  （订阅成功则把轮询降到 8000 ms 兜底）。轮询只在任务视图里跑，不打扰别的页面。
- 活任务还能看到**还要多久**：列表状态后面 ` · 还要 4m5s`，详情多一行「预计还要」+ 出处 + 可信度（见 2.2）。
- 面板**顶部一条资源队列**：`CPU 8/8 核 · 内存 6/16 GB · 运行中 1 · ⏳ 排队 2`，
  下面逐行列出排队的人（`#1 跑 ATAC · memomics-811918 · 已等 4m5s · 需 2 核/2 GB`），在跑的带 `▶`（见 2.3）。
- 失败的任务（`failed` / `interrupted`）详情里有**一键重试**：`🔁 重试（第 2 次 · 5s 后启动）`，
  重试出来的任务名字带 `（重试 2/3）`、参数里写清 `重试来源 / 重试根 / 第几次重试`（见 2.4）。

## 2. 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/tasks?refresh=1&limit=100&states=running` | 列表；`refresh=1` 用 PID + 进程创建时间核对存活，进程没了就把活任务收敛成 `interrupted` |
| GET | `/api/tasks/{id}?tail=200&script=1` | 详情：**`{ok, task:{...}}`**（注意是嵌套的），含 stages/outputs/params/log_tail/script_text/env/proc |
| GET | `/api/tasks/{id}/log?tail=200&grep=WARN` | 日志尾部（seek 读，不整读几百 MB），`grep` 是不区分大小写的子串过滤，结果在 `text` |
| POST | `/api/tasks/{id}/cancel` | 需要 `X-Task-Token`（从 `/api/tasks` 的 `api_token` 拿），返回 wait/escalated/killed/kill_wrapper/marks |
| POST | `/api/tasks/{id}/retry` | 同一把 `X-Task-Token`；按 retry_backoff 的退避重跑契约里的命令，返回 `scheduled/attempt/delay_sec/spawned`；不能重试时 409 + 中文理由（见 2.4） |
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

### 2.2 还要多久（ETA，来自阶段历史）

`memomics/bio_tools/task_eta.py` 按「同一类型 + 同一脚本」把**真跑完过**的任务聚成历史，
算出每段平均耗时，再减掉活任务已经跑掉的部分 —— 只用真数据，不猜：

| 字段 | 含义 |
| --- | --- |
| `eta_sec` / `eta_text` | 预计还要多少秒（无依据时为 `null` / 空串） |
| `eta_source` | `history`（阶段历史）/ `progress`（按进度外推）/ `""`（不给数） |
| `eta_basis` | 人话出处，例如「按 3 次同类型历史」 |
| `eta_confidence` | `高`（≥3 次历史）/ `中`（历史不全，用均值兜底）/ `低`（按进度外推） |

边界：历史只算**真终态且有阶段耗时**的任务（跑挂的、中断的、没打过点的都不算）；
已经跑过的阶段按实际值扣，扣成负数就钳到 0（面板上不会出现「还要 -3s」）；
没历史又没进度就**不给数**（宁可不显示，也不编一个）；任务结束后 ETA 一律为空。
时间戳全部按 UTC 解析（契约写的是 `+00:00`）。

### 2.3 排队视图（谁在跑 / 谁在排 / 排第几）

`webui/runtime/resources.py` 的 `ResourceScheduler` 是唯一裁判（协作式 FIFO：每轮对话开始时拿租约、结束归还）。
`GET /api/resources` 现在把队列讲清楚（**老字段一个没动，全是新增**）：

| 字段 | 含义 |
| --- | --- |
| `queue.active` / `queue.waiting` | 在跑几个 / 排了几个 |
| `queue.head_wait_sec` / `queue.max_wait_sec` | 队首等了多久 / 最久等了多久（秒；面板上超 30s 会标黄提醒容量不够） |
| `active[].label` / `held_sec` / `acquired_at` | 谁在跑（会话标题，没有就退回最近一句用户话）、占了多久、什么时候拿到的 |
| `waiting[].position` | 排第几（从 1 数起；严格 FIFO，所以就是真实位次） |
| `waiting[].label` / `enqueued_at` / `waited_sec` | 谁在排、什么时候开始排、已经等了多久 |

等待/占用时长用**单调时钟**算（改系统时间不影响），时间戳一律 UTC ISO。
队首不满足就**整队等着**（后到的小请求不插队）—— 这是有意的：面板上「排第几」才可信；
代价是一个超大请求会挡住后面的人（`test_resources_queue.py::test_d1` 把这个行为钉住了，改策略前先看它）。

要复现排队，把容量压小即可：`MEMOMICS_CPU_CORES=1`、`MEMOMICS_MEMORY_GB=2`（GPU 走 `MEMOMICS_GPU_SLOTS`）；
不给覆盖就按机器自动探测（CPU = 核数-1，内存 = 可用内存×0.8）。
### 2.4 失败任务一键重试（retry_backoff）

失败任务（`failed` / `interrupted`）详情里多一个 `🔁 重试（第 N 次 · 5s 后启动）`。
按钮亮不亮**由后端算好**：列表卡片/详情都带 `retry_allowed / retry_attempt / retry_delay_sec /
retry_reason / retry_used / retry_max / retry_root`，面板只负责画，不自己猜。

| 关键点 | 约定 |
| --- | --- |
| 重跑什么 | **只重跑契约里已经记下的命令**（`cmd` + `type/title/stages/script/params/session_dir/session_id` 原样搬），服务端不自己发明参数 |
| 命令怎么还原 | 契约里 `cmd` 是给人看的**字符串**，重跑要拆回 token：只认双引号包裹，**不解释 shell 语法** —— 管道、`&&`、重定向一律当普通参数；宁可跑出来报错，也不偷偷换个意思执行 |
| 隔多久 | 用 `webui/runtime/retry_backoff.py` 的 `RetryBackoff`：2s / 5s / 15s（表尾 45s），第 N 次重试取第 N 个间隔 |
| 还能几次 | 同一条链最多 3 次（`MAX_FAILURES=3`：连续失败 3 次后不再硬重试） |
| 什么时候不给 | 任务没失败（done/running…）、契约里没记命令、**上一次重试还在跑**（含"已排定、还在等退避"的那几秒 —— 连点两下不会排出两次）、已经用满 3 次 —— 一律 409 + 中文理由 |
| 溯源 | 重试任务的参数里写死 `重试来源`（直接上一级）、`重试根`（最初的 task_id）、`第几次重试`；`重试根` 相同即同一条重试链，上限按链上最大次数算 |
| 退避等待放哪 | 服务端 `asyncio` 后台等，请求立刻返回 `scheduled=true` + `delay_sec`（面板不用吊在 15s 的请求上）；退避为 0 时同步拉起 |

说清楚三条边界（别当成 bug）：
- 重试**不占资源租约** —— 后台任务本来就不走 `ResourceScheduler`（那是「每轮对话」的租约），重试沿用同一约定；
- 重试进程的 cwd 依次取 原任务 `cwd` → 会话目录 → 仓库根；
- 重试**没有幂等保证**：命令再跑一遍，产物可能被覆盖或追加，动手前先看日志和产物。

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

### T10 阶段历史推 ETA（真机 8899，2026-09-24）

`E:\release\_t10\eta_verify.py`（真起 5 个任务：3 次建历史 + 1 次预测 + 1 次新脚本）13 项断言全过：

| 断言 | 实测 |
| --- | --- |
| 历史样本 | 同类型同脚本真跑 3 次，全部 `done`、退出码 0 |
| 运行中就有数 | 第 4 次跑到一半：`eta_sec=12.5`，`eta_source=history` |
| 出处 + 可信度 | `按 3 次同类型历史` / `高` |
| 文本自洽 | `eta_text=12s` 与 `eta_sec=12.5` 是同一个数（先取整再格式化） |
| 预测 vs 实际 | 预测还要 12.5 s，实测还要 12.9 s，**差 0.4 s**（任务总时长 14.1 s） |
| 结束后清零 | `done` 的任务 `eta_sec=None`、`eta_text=""` |
| 新脚本不冒充历史 | 换一个没跑过的脚本：`eta_source=progress`、`eta_sec=7.4`、进度 50% |
| 低可信度标注 | 同上 `eta_confidence=低`（按进度外推，不假装有历史） |
| 详情接口字段齐 | `eta_sec/eta_text/eta_basis/eta_source/eta_confidence` 全在 |

单测：`webui/tests/test_task_eta.py`（12 项：格式化与契约逐值对齐、UTC 解析、历史分组均值、
兜底、负数钳位、无依据不给数）+ `test_task_routes.py::test_i1..i4`（历史汇总先于状态过滤、
详情与列表一致、没历史不撒谎、超时不为负）+ 面板 JS 真跑断言 ETA 显示与缺失。


### T11 资源队列真机实测（8899 + 临时 8898 限 1 核，2026-09-24）

`E:\release\_t11\queue_verify.py` 14 项断言全过（`T11_QUEUE_RC=0`）：8899 查结构 + 真下发页面；
排队用临时实例 8898（`MEMOMICS_CPU_CORES=1`、`MEMOMICS_MEMORY_GB=2`）压出来 —— 三个**真会话、真模型轮次**先后发同一句指令。

| 断言 | 实测 |
| --- | --- |
| 8899 快照带队列汇总 | `queue{admission,active,waiting,head_wait_sec,max_wait_sec}`，容量 19 核 / 20.8 GB / 1 GPU |
| 8899 页面真的有队列条 | 实际下发的 HTML（735 631 字节）里有 `id="task-queue"` + `renderResources` + `/api/resources` |
| 真排队 | 93 个采样点里 77 个 `waiting>0`，最多同时 2 个排队 |
| 位次与名字 | `#1 只回复：B收到`（memomics-bc06085d）· `#2 只回复：C收到`（memomics-81191800） |
| 等待在真涨 | 同一会话 `waited_sec` 0.7 → 26.0 s（另一路 0.0 → 31.5 s） |
| 占用时长 | `active[].held_sec` 最大 27.6 s |
| 容量没被突破 | 全程 `max(active)==1`（1 核容量） |
| 排队的真进来了 | 收尾样本 `active=0 waiting=0`（三个会话全部跑完） |
| 临时会话清理 | 三个 `results/memomics-*` 跑完即删，8898 临时实例已退出 |

单测：`webui/tests/test_resources_queue.py`（10 项：env 覆盖容量、位次/名字/等待时长、取消排队不留幽灵、
取消队首不卡死、严格 FIFO 不插队、超容量不留队列、GPU 排队、老字段不丢）
+ `test_task_panel_ui.py::test_render_resources_shows_queue_positions`（node 假 DOM 真跑渲染：
`#1/#2`、`已等 41s`、`队首已等超 30s`、会话标题转义）。
回归：全量 `scripts/check_skills_gate.py` 774 例通过 / 跳过 2。

回归测试：`webui/tests/test_task_ws.py`（订阅协议 / 退订摘连接 / 指纹 / 失败不撒谎）+
`test_task_routes.py::test_h1`（穿越三路由）、`test_h2`（越界脚本不读）。

### T12 失败任务一键重试真机实测（8899，2026-09-24）

`E:\release\_t12\retry_verify.py` 24 项断言全过（`T12_RETRY_RC=0`，37.4 s）：
先真起一次 wrapper 造出**真失败**的任务（`qc-20260924-121142-88c6`，`failed / exit=3`，真跑了 3.7 s），
然后全程走 HTTP 点重试。

| 断言 | 实测 |
| --- | --- |
| 鉴权与 404 | 坏 token → 401；不存在的任务 → 404；done 任务 → 409「任务没失败（done），不用重试」 |
| 第一次重试排定 | `200 {scheduled:true, delay_sec:2.0, attempt:1}`（请求不吊在退避上） |
| **连点第二下** | 409「上一次重试还在跑（已排定（等退避）），等它结束」 |
| 重试任务落地 | `qc-20260924-121149-720b`：参数 `{重试来源, 重试根, 第几次重试=1}`、标题 `（重试 1/3）`、`type=qc` 与脚本/阶段原样搬过去 |
| 命令真被执行 | 重试任务 `exit=3`，子进程留下的痕迹 2 个（原任务 1 + 重试 1） |
| 重试「重试」 | 第 2 次：`attempt=2, delay_sec=5.0`，`重试根` 仍是最初那个 → `qc-20260924-121159-5a39` |
| 第三次 | `attempt=3, delay_sec=15.0` → `qc-20260924-121220-5b12`，退避 15s 也没耽误落地 |
| 没有多跑 | 三次重试后子进程痕迹**正好 4 个**（原任务 + 3 次重试），连点没排出重复 |
| 用满 3 次 | 409「已经连着重试 3 次（上限 3 次），先看日志再动手」；卡片 `retry_used=3 / retry_max=3 / retry_allowed=false` |
| 路由清单 | `/api/middleware/audit?routes=1` → `added=[] removed=[] total=132` |
| 前端就位 | 8899 真下发的页面（737 229 字节）里有 `task-retry-btn` / `function retryTask(id)` / `'/retry'` |

**修之前真的会连点排出两次**（12:08 那一轮，旧代码）：同一秒里出现 `qc-20260924-120841-58f8` 与
`qc-20260924-120841-a32c` 两份重试契约、两份日志各 126 字节 —— 才补的 `_RETRY_INFLIGHT`
（"已排定、还在等退避"也占名额），改完第二下就是 409。

测试工具自己也踩了一个坑：子进程并发「读-改-写」同一个计数文件会丢更新（三个进程只留下两三行），
改成**每次跑写一个独立文件**再计数，才数得准 —— 这条是验证脚本的坑，写在这里免得下次再踩。

单测：`test_task_routes.py::test_j1..j8`（8 项：token/404、只对 failed 且记了命令的开重试、
上一次还在跑就拒、退避上限、卡片计划字段、命令拆分只认引号不解释 shell、**真起进程真跑完的端到端重试**、
连点名额守卫）+ `test_task_panel_ui.py::test_render_detail_retry_button_and_grey_reason`
（node 假 DOM 真跑渲染：按钮文案"第 1 次 · 2s 后启动"、点击已接线、用满后按钮消失只剩理由）。
回归：全量 `scripts/check_skills_gate.py` **783 例通过 / 跳过 2**（79.8 s）。

