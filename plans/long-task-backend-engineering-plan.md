# MemOmics 长任务后台运行 · 工程规划（基于 LoopX 调研 + MemOmics 现状）

> 目标：长任务后台可跑、报错可纠、任务不误重启、两会话不互踩。
> 原则：**增量不重构**——每步新增独立小模块 + 现有文件只加调用点（≤20 行）+ env 开关默认关闭。不动 hermes 底座主循环、不动 state.db schema。

## ✅ 实施状态（2026-08-06 晚）
| 项 | 状态 | 产出 |
|---|---|---|
| LoopX vendor | ✅ 完成 | `memomics/vendor/loopx/`（267 文件 3.6MB，MIT，v0.4.1，独立 import 验证） |
| LoopX bridge | ✅ 完成 | `memomics/loopx_bridge.py`（goal 注册/quota 决策/心跳/轮询/交接/事件溯源，全 API 测试通过） |
| P1-A 完成闸门 | ✅ 完成 | `webui/runtime/run_gate.py` + server.py 三处接入（env `MEMOMICS_RUN_GATE=1` 启用） |
| P1-B 结构化纠错 | ✅ 模块完成 | `webui/runtime/retry_backoff.py`（接入点待灰度：terminal 失败处注入，P2） |
| P1-C 会话单飞锁 | ✅ 模块完成 | `webui/runtime/session_locks.py`（server 层已有 TaskSupervisor 兜底同会话单飞） |
| 回归测试 | ✅ 24/24 PASS | `webui/runtime/test_gates.py`（python 直接跑，勿 `-m` 触发 webui/__init__） |
| 端到端模拟 | ✅ 8/8 PASS | 完成→不重启 / 用户新消息→重置 / 中断优先 / 新会话不受影响 |
| ② P1-B 接入 terminal | ✅ 完成 | `hermes-agent/tools/structured_failure.py` + terminal_tool.py 失败点注入（连续失败计数 3 次上限 + 换方案提示；grep=1 等语义退出码不注入） |
| ③ 闸门开关开启 | ✅ 完成 | start.bat / start.sh 加 `MEMOMICS_RUN_GATE=1`（出问题删/注释该行即回退） |
| ① 失活检测增强 | ✅ 完成 | stall watchdog：`MEMOMICS_STALL_TIMEOUT` 可配（默认 300s）+ 活跃后台进程（process_registry.has_active_processes）豁免"合法长静默" |
| ④ 模型配置会话隔离 | ✅ 完成 | switch_model：运行中的会话豁免覆盖（长任务不被打断），空闲会话照常同步 |
| ⑤ 取消标记 + plan 防污染 | ✅ 完成 | run_gate 加 `cancelled` 状态（用户放弃=退役，自动唤醒不再恢复）；WS cancel / cancel_task 文本两条路径确定性落盘；`_build_task_plan_context` 注入前三闸（退役状态 / 文本取消标记 / sid 归属校验）；自动建 plan 带 `<!-- sid: -->` 标记 |

---

## 0. 现状关键事实（与部分记忆不符，以代码为准）

调研日期 2026-08-06，以 `E:\MemOmics-Agent` 实际代码为准（`webui/server.py` 6588 行 + `memomics/hermes-agent/`）：

| 记忆中的说法 | 实际现状 | 影响 |
|---|---|---|
| max_iterations 按任务分级 20/40/80 | **全局统一 300**（`webui/server.py:2632`），无分级 | 长任务够用，但"分级"是幻觉 |
| LoopEngine / loop_progress / observation_compressor 已集成 | **当前项目不存在**（grep 0 匹配，属另一项目 E:\MemOmics，已清空） | 心跳进度推送其实靠 server.py 自己的 watchdog + task_plan |
| 任务完成后不会重启 | **存在 self-check 自唤醒看门狗**（`_schedule_self_check` `server.py:538-641`），finally 里**无条件**触发（`:6427`），靠 task_plan.md 文本标记判定，会"误重启" | 这是你担心"老任务被重启"的**真实根因** |
| 错误纠正有结构化流程 | 很薄：terminal 报错→LLM 自己看 traceback；API 层有 3 次重试+fallback；rail_review 只警告不硬阻断 | 报错纠正主要靠 LLM 自觉 |
| 两会话隔离良好 | results_dir 按 sid+短ID 隔离 ✅；但 `_current_model` **全局共享**、共享 analysis_dir 时心跳标记文件会串 | 基本隔离，有边角风险 |

**中断链路（已完整）**：WS cancel → `TaskSupervisor.cancel` + `agent.interrupt()`（`_interrupt_requested` 置位 + 线程信号 + 子agent传播，`run_agent.py:2642`）→ conversation_loop 多点轮询 break → webui clear + 广播 stopped。**这是协作式中断，已可用，不动它。**

**失活检测阈值（分散）**：MemOmics stall watchdog 5min（`server.py:125-151`）/ cron 10min / gateway 30min。**风险：无心跳的合法长静默（阻塞子进程、非流式长响应）会被 5min watchdog 误杀。**

---

## 0.5 LoopX 结合方案（照搬式）⭐ 2026-08-06 已实测验证

### 调研结论（全部实测，非纸面）
- **LoopX v0.4.1 = MIT 协议 + 零依赖（`dependencies=[]`）+ 纯标准库**，要求 Python ≥3.11（本机 3.12 ✓）→ **法律与技术上均可整段照搬**。
- 核心 API 是**纯函数**，可进程内 `import` 直接调用（不需要跑它的 CLI）：
  `build_quota_should_run`（quota.py）/ `collect_status`（status.py）/ `build_heartbeat_prompt`（heartbeat_prompt.py）/ `AppendOnlyStateEventStore`（event_sourced_state.py）/ `build_scheduler_hint`（control_plane/scheduler/scheduler_hint.py）。
- 已 vendor 到 `memomics/vendor/loopx/`：按**运行时闭包裁剪**（267 个 py 文件 / 3.6MB，非整包 18MB），保留 LICENSE，独立 import 验证通过。
- 实测冒烟链路：最小 registry.json → `collect_status` → `build_quota_should_run` 全链路跑通，返回 `operator_gate`（LoopX 默认假设**无人值守**场景）。
- 实测坑（照搬时已踩）：`scan_roots` 必须传 `pathlib.Path` 对象（传 str 报 `AttributeError: 'str' object has no attribute 'resolve'`）。

### 结合架构（三明治：vendor 层 / bridge 层 / 集成点）
```
memomics/vendor/loopx/            ← vendor 层：原样复制（MIT），一行不改，便于日后整包升级
memomics/loopx_bridge.py          ← bridge 层：新文件 ~280 行，MemOmics 会话 ↔ LoopX 控制平面状态映射
webui/runtime/run_gate.py 等      ← 集成点：只加调用点（≤20 行/处），不动底座
```

### 状态映射（bridge 层核心设计）
| MemOmics | LoopX | 说明 |
|---|---|---|
| 会话 sid | `goal_id` | registry.json 的 `goal.id = sid` |
| `results_dir/.loopx/` | runtime root | **每会话独立目录 → 两会话控制平面天然隔离**（兼治 P1-C 串标记） |
| `session["task_state"]` | ACTIVE_GOAL_STATE.md | 双写：显式状态机为准 + loopx 状态文件，过渡期后废弃文本判定 |
| 用户在线（WS 活跃/刚发消息） | `operator_gate` | **bridge 裁决：用户在场 → gate 通过**（交互式 vs LoopX 无人值守的根本差异点） |
| 工具结果/心跳点 | attention queue | `waiting_on` 值域 `user_or_controller/controller/codex/external_evidence/monitor` |

### 照搬清单（直接调用 vendor 纯函数，非"借鉴思想"）
1. **quota should-run 状态机**（`build_quota_should_run`，状态序 `blocked_health→operator_gate→focus_wait→eligible→waiting→throttled→paused`）→ P1-A run_gate 的**判定核心**（替代自写逻辑）。
2. **心跳提示词四档**（`build_heartbeat_prompt`：full/compact/brief/thin，按 interface budget 选档）→ 心跳推送内容从"进度条"升级为结构化汇报。
3. **scheduler hint 退避表**（`build_scheduler_hint`：`run_now(3/10min)/backoff(30/60/120/240min)/checkpoint` 等 cadence_class）→ `_schedule_self_check` 下次轮询间隔由它驱动（治固定间隔空转）。
4. **handoff budget**（`handoff_budget.py`：≤16 行 / ≤1800 字符）→ P2-B 交接摘要的硬约束。
5. **事件溯源**（`AppendOnlyStateEventStore`：幂等 append + checkpoint + rebuild）→ goal 生命周期事件落 `.loopx/events.jsonl`，与 state.db **职责分离**（控制平面 vs 会话消息），不动 schema。

### 适配决策（bridge 层做，vendor 层一行不改）
- `operator_gate` → 用户在场裁决：交互式会话中用户刚发消息/WS 活跃 = 在场 → 放行并记录原因。
- 不搬（单 agent 交互式场景无意义）：claim/lease 租约、goal_frontier replan、agent_scope、supervisor 多代理、capability_bridge、workspace_guard、benchmark 全家。

---

## 1. 问题→根因→方案映射

| 你的诉求 | 根因（代码证据） | 方案 |
|---|---|---|
| 长任务后台跑 | 已有 asyncio + executor 混合模型（`server.py:6290`），基本可用 | 增强：失活检测区分"真静默"与"合法长静默" |
| 报错及时纠正修复 | 无结构化纠错，全靠 LLM 看 traceback | **P1-B**：工具失败结构化注入 + 秒级指数退避 |
| 结束后新任务会不会重启老任务 | **self-check 自唤醒**误判（task_plan.md 文本标记不可靠） | **P1-A**：确定性"任务完成"闸门 |
| 两会话长任务互不干扰 | results_dir 隔离 OK；`_current_model` 全局共享 + 共享 analysis_dir 串标记 | **P1-C**：会话级单飞锁 + 标记文件带 sid |

---

## 2. 分期规划

### P1 — 解决三个最痛问题（预计各 <120 行，1 周内）

#### P1-A：任务完成闸门（治"老任务被重启"）⭐ 最高优先
- **新增** `webui/runtime/run_gate.py`（~70 行）：每轮 `run_conversation` 开始前过一次闸，返回 `run / stop / ask_user`。判定三件事：① 会话是否已标记 `done`（确定性状态，非文本）；② `_interrupt_requested` 是否置位；③ 迭代预算是否耗尽。
- **改造** `_schedule_self_check`（`server.py:538-641`）：把"靠 task_plan.md 文本词判定完成"改为**读 `session["task_state"]` 显式状态机**（`pending/running/done/blocked`）。完成判定从"文本含'completed/完成'"改为"`task_state == 'done'`"，由 agent 调一个轻量 `mark_task_done` 工具显式置位，不再靠猜文本。
- **接入点**：`run_agent()` 入口（`server.py:6266` 前）加 `run_gate` 检查（~10 行）。
- **env 开关**：`MEMOMICS_RUN_GATE=1`（默认 0，灰度）。
- **风险**：`task_state` 初版与 task_plan.md 双写，跑 2-3 个真实任务确认一致后再废弃文本判定。**不删** `_urgent_wakeup`（6396-6402）和空响应重试（6405-6410）这两个看门狗，只让它们也过闸。

#### P1-B：工具失败结构化纠错（治"报错没人管"）
- **新增** `webui/runtime/retry_backoff.py`（~65 行）：工具连续失败按 2s/5s/15s/45s 指数退避（**分段 sleep 且每段检查 `_interrupt_requested`**，否则点停止会卡）；连续 3 次失败后停止硬重试，把结构化错误（命令、exit_code、traceback 摘要、已试次数）作为一条 observation 消息注入上下文，让 LLM **换方案**而非死磕。
- **接入点**：`tool_executor.py` 的工具结果返回处（~15 行），不改主循环。
- **env 开关**：`MEMOMICS_RETRY_BACKOFF=1`。
- **风险**：退避只用于"可重试错误"（参考 `error_classifier.py` 的 `retryable` 标记复用），auth/格式错误不重试。先 shadow 模式（只记录不退避）校准。

#### P1-C：会话级单飞锁（治"会话互踩"）
- **新增** `webui/runtime/session_locks.py`（~80 行）：`threading.Lock` + holder 元数据（哪个 sid 持有）+ 超时即失败（≤5s，不死等）。锁住两处：`results_dir` 的写入入口、`execute_r`/结果落盘处。
- **治理 `_current_model` 全局共享**：`server.py:811` 改为"新会话默认继承，已运行会话不受影响"——已缓存的 `session["agent"]` 不动（现状已对），只需文档化"切模型只影响新会话"。
- **共享 analysis_dir 串标记**：心跳/标记文件（`.heartbeat_stop/PROGRESS.md/alerts.json`）写入时强制带 sid 前缀（`_marker_belongs_to_session` 已有归因逻辑 `server.py:516-535`，把"缓解"升级为"写入即隔离"）。
- **env 开关**：`MEMOMICS_SESSION_LOCK=1`。
- **风险**：纯进程内锁防不住多进程部署，但当前单进程够用，注释标注未来换文件锁。

### P2 — 长任务质量增强（P1 稳定后）

#### P2-A：薄进度/实质进度节奏检测（借鉴 LoopX cadence）
- **新增** `webui/runtime/cadence_detector.py`（~120 行）：每轮记录 `{wrote_file, ran_cmd}` 到内存 deque；连续 ≥8 轮无实质产出→注入"widen-step"提示（**只提示不打断**，可关闭）。
- **接入点**：`conversation_loop.py` 每轮结束（~20 行）。
- **借鉴自**：`loopx/long_task_cadence.py`（190 行纯函数，只搬判定逻辑）。
- **风险**：阈值保守（≥8 轮），"读文件探索"不算假忙。

#### P2-B：结构化交接摘要（跨会话恢复）
- **新增** `webui/runtime/handoff_note.py`（~120 行）：任务暂停/中断/完成时生成 ≤16 行 markdown 摘要（当前进度/下一步/阻塞项/产物路径），**规则模板生成**（非 LLM，省一次调用），作为特殊 role 消息写入 state.db 现有消息表（**不改 schema**）。新消息进会话若检测到有未完成长任务，注入该摘要。
- **借鉴自**：`loopx/handoff_budget.py`（28 行预算约束思想）。
- **风险**：与现有 task_plan.md 双轨一段时间，摘要更结构化后逐步替代。

### P3 — 上下文预算（可选，P2 后按需）
- **新增** `webui/runtime/context_budget.py`（~85 行）：每轮统计注入工具结果总字符，超预算（如 30k）触发压缩。先 shadow 模式校准阈值。
- **借鉴自**：`loopx/interface_budget.py`。

---

## 3. 明确**不做**的（LoopX 机制不适用 MemOmics 单 agent 交互式）

| LoopX 机制 | 不落地原因 |
|---|---|
| todo 认领+租约（claim/lease 45min） | 前提是多 worker 竞争，MemOmics 单 agent 无竞争者 |
| goal_frontier replan / agent_scope / supervisor / worker_bridge | 多代理编排专属，单 agent 用不上 |
| capability_bridge / workspace_guard / benchmark 全家 | 属于 LoopX 自身执行面，非控制平面，搬来即重复建设 |
| spend ledger 24h 花销账本 | 单 agent 用户实时看着，现有 max_iterations=300/超时已够约束 |

> **已翻案**（旧版曾列为不做，实测后改为做）：事件溯源（控制平面事件落 `.loopx/`，与 state.db 职责分离）、operator gate（改为"用户在场裁决"适配）、心跳双向指令（recommendation 驱动 self-check 间隔）。详见 §0.5。

---

## 4. 风险与"不修坏东西"保障

1. **每步独立开关**：所有新功能 env 开关默认关，灰度验证后再开。
2. **不动底座**：不改 `conversation_loop.py` 主循环结构、不改 `state.db` schema、不改中断链路（已完整）。
3. **双轨过渡**：`task_state` 与 task_plan.md 并存一段时间，确认一致再废弃旧文本判定。
4. **每步可回滚**：新模块独立文件，出问题删文件+关开关即恢复原状。
5. **先做 P1-A**：它直接治你最担心的"误重启"，且改动最小、风险最低。

## 5. 验收标准

- **P1-A**：起一个长任务跑到完成 → 发新消息 → 老任务**不**自动重启；未完成任务的 self-check 仍能正常唤醒。
- **P1-B**：构造一个会失败的 terminal 命令 → 观察到指数退避 + 3 次后注入结构化错误 → LLM 换方案而非死循环。
- **P1-C**：两个会话同时跑长任务 → results_dir 不撞、标记文件不串、互不死锁。
