# MemOmics 中途引导（Steering）调查与设计

> 2026-10-19 · 「引导」= **agent 运行中用户插话**（steer / 中途引导）。
> 对照系：DSH（DeepSeek Harness）的 steer/queue 机制。

---

## 1. 直接回答

**Q：agent 在思考/跑工具，我插一条信息进去，能不能顺利引导？**
能，链路是通的（前端自动识别运行中→走 steer 通道），但**生效时机是「下一个 LLM 调用边界」**：
- agent 正在等模型流式返回 → 插话**进不去本次调用**，本次回答完、下次调用前才被读走（pre-API drain）
- agent 正在跑长工具（如 terminal 跑 10 分钟）→ 插话**等工具跑完**才附在工具结果里送达（steer 设计上不中断当前工具）
- 要**立刻停**只有「⏹ 停止」按钮（interrupt），steer 做不到打断

**Q：连发几条会怎样？**
不丢、不乱序：多条插话在 `_pending_steer` 槽里按到达顺序 "\n" 拼接，下个消费点**合并成一块**一起送达模型。（但有两个静默丢失的坑，见 §4。）

**Q：能不能被正确读取并修改/完善任务？**
能读到且权威够：插话被包成 `[OUT-OF-BAND USER MESSAGE — a direct message from the user, delivered mid-turn; not tool output]` 标记附在工具结果尾部，系统提示里的 STEER_CHANNEL_NOTE 明确告诉模型「这是真用户、与原始请求同等权威、按它调整方向、只信这个标记（防注入）」。模型读到后会按它改方向、修任务。
**但**：读完之后「引导 → 任务」没有硬联动——模型口头上答应了方向调整，task_plan/待办不会自动跟着改，全靠模型自觉。

---

## 2. 现状链路（代码级）

```
用户输入 → 前端 send()（index.html:3320）
  │ agentRunning ? → WS {type:"steer"}      （空闲 → 普通 chat；steer 落空则自动转新消息）
  ▼
server.py:21481  msg_type=="steer"
  │ session["running_agent"].steer(text)     → 回 steer_sent 事件（仅表示"写进槽"）
  ▼
run_agent.py:2900  steer(text)
  │ _pending_steer 槽（threading.Lock，多条 "\n" 累加）
  ▼ 三个消费点：
  ① conversation_loop.py:794  pre-API drain：下次 LLM 调用前读出，
  │   附到最后一条 tool 消息尾部（format_steer_marker 包装）；
  │   还没有 tool 消息 → 放回去等下一轮
  ② agent_runtime_helpers.py:3336  post-tool drain：工具批次结果落地时附上去
  │   （tool_executor.py 有 6 个调用点）
  ③ turn_finalizer.py:560  回合结束 leftover → result["pending_steer"] 交还调用方
  ▼
模型看到：工具结果尾部 [OUT-OF-BAND USER MESSAGE]…[/OUT-OF-BAND USER MESSAGE]
权威来源：STEER_CHANNEL_NOTE（stable 系统提示，prompt_builder.py:640）
```

同槽生产者还有两处**系统干预**：`_loop_inject_steer`（循环检测强制收尾，server.py:14003）与 enforcement 的 require 提示（enforcement.py:862）。它们与用户插话共用 `_pending_steer`。

---

## 3. 对照：DSH 的 steer 好在哪里

| 维度 | DSH | MemOmics 现状 |
|---|---|---|
| 插话载体 | **持久 inbox 消息**（有 MessageId，进 transcript） | `_pending_steer` 内存字符串槽 |
| 生效时机 | 下一个 step 边界，原子领取 | 下一个 LLM 调用边界（pre-API / post-tool drain） |
| 多条插话 | 批量原子领取，逐条是独立消息 | "\n" 合并成一块（不丢但无结构） |
| 送达回执 | `agent/inbox/claimed` 通知 + 前端气泡无缝交接（pending→正式 user 气泡） | 只有 `steer_sent`（=写进槽，不代表模型读到） |
| 排队能力 | next-turn FIFO 队列：可见、可编辑、可删、可逐条 steer；空草稿 Ctrl+Enter 整队插话 | 运行中 chat 直接拒绝（"该会话已有任务在运行"），只能 steer |
| 窗口关闭兜底 | best-effort：转下一条 queue 轮次，不丢 | hermes 把 leftover 放进 `result["pending_steer"]` 交还——**webui 没接** |
| 历史可见 | steering 是 transcript 里的真实 user 消息，刷新/回放都在 | 附在 tool 结果里，前端只本地显示，**刷新即消失**，消息 API 里没有 |

---

## 4. 实测发现的坑（按严重度）

| # | 坑 | 证据 | 后果 |
|---|---|---|---|
| K1 🔴 | **回合尾巴上的插话静默丢失**：steer 在最后一个工具批次之后到达 → hermes 交还在 `result["pending_steer"]` → webui `_do_run` 只取 `final_response`（server.py:21050） | server.py:21045-21050 vs turn_finalizer.py:560-562 | 用户看到「已发送引导」，模型永远没看到 |
| K2 🔴 | **新回合清空残留 steer**：每个新 chat 回合开始清 `_pending_steer`（为防系统干预串扰而设计），会把没来得及被读的**用户插话**一起清掉 | server.py:19702-19713 | 插话晚到一步 + 用户再发一条正常消息 → 上条插话消失 |
| K3 🟡 | **插话不进会话历史**：steer 附在 tool 结果里，不写 `session["messages"]`（微信通道都写了，steer 反而没写） | server.py:21481-21501 无 append；14188 微信有 append | 刷新后用户插过的话消失；`/api/sessions/{sid}/messages` 没有；事后审计查不到 |
| K4 🟡 | **无排队队列**：运行中发普通消息被拒，多条 steer 只能合并，不能逐条管理/撤回 | server.py:21312 | 连发几条想改其中一条 → 做不到 |
| K5 🟡 | **无送达回执**：`steer_sent` 只表示写进槽 | server.py:21488 | 用户无法区分「模型已读」和「还在等工具跑完」 |
| K6 🟢 | 系统干预与用户插话同槽 | server.py:14003、enforcement.py:862 | 本身能共存送达，但 K2 的清空逻辑是为系统干预写的，误伤用户插话 |

---

## 5. 改进设计

### P0 修坑（改动小，纯补漏）—— ✅ 已实现（2026-10-19）

1. **接住 leftover**：分两层。根修在 `hermes-agent/agent/conversation_loop.py`（text_response 出口前 drain steer，有预算就追加为真实 user 消息延续当前轮，kanban nudge 同款模式；预算将尽则不取，留在槽里交兜底）；兜底在 `webui/server.py` `_do_run`（捕获 `result["pending_steer"]` → 回合末落历史 + emit 告知，下一条用户消息在入口拼入本轮处理）。
2. **清空前兜底**：chat 入口处清 `_pending_steer` 前先经新增的 `_salvage_steer_text()` 抢救——系统干预段（【系统循环检测·强制干预】/【系统强制提示】）作废，用户插话段拼进本轮 `_run_text` 前面 + 落历史（含 state.db）+ emit info。
3. **插话落历史**：steer 成功即 `session["messages"].append(source="steer")` + `SessionDB.append_message()` 持久化 → 刷新可见、审计可查。
4. **顺手修了一个隐藏 bug**：steer 落空时原来的 `_internal_chat` 浏览器回弹在前端根本没有处理器（静默丢失）；改为入口处 steer→chat 归一化（会话空闲即转普通消息走 chat 通道，对齐 DSH best-effort 语义）。

回归测试：`webui/tests/test_steer_delivery.py`（抢救/拼接语义）+ `hermes-agent/tests/run_agent/test_steer_exit_continuation.py`（回路级：插话延续当前轮 / 预算将尽走 leftover 兜底）。

### P1 对齐 DSH（体验层）

4. **送达回执**：在两个 drain 点（pre-API / post-tool）消费用户插话后回调 server → emit `steer_delivered`；前端把「↳ 已发送引导」更新为「✓ 模型已读」。实现上给 agent 挂一个轻量 steer 消费回调（或 server 侧轮询槽清空的 ts——推荐回调，agent_runtime_helpers.conversation_loop 各加一行）。
5. **轻量排队队列**：运行中 chat 不再直接拒绝 → 进 per-session FIFO（内存 + state.db kv 持久化），回合结束按序自动开新轮；前端显示排队列表（可删可撤回）。这把 DSH 的 queue/steer 双通道补齐：急事 steer（下个边界到）、缓事 queue（下轮跑）。
6. **引导→任务联动**：steer 送达后若语义是「改方向/停某步/换参数」，由模型自觉没错，但可加一条铁轨：steer 被消费时 enforcement 记 `last_steer_ts`，回合末自检比对 task_plan 是否反映了插话（轻量提示，不硬拦）。

### 不做的事

- 不让 steer 打断正在执行的工具/正在流的 API 调用——那需要可取消的执行器（interrupt 已经是这条路），steer 的定位就是「不中断的方向调整」。

---

## 6. 验证清单（改完怎么测）

自动化已覆盖（2026-10-19）：K1 根修与兜底（test_steer_exit_continuation.py：插话延续当前轮 / 预算将尽走 leftover）、K2 抢救语义与多条拼接顺序（test_steer_delivery.py）。

人工验收（重启 server 后）：
- [ ] 长工具（如 sleep 60）运行中发 steer，等工具结束 → 模型回复里体现了插话内容
- [ ] 插话后刷新页面 → 引导消息仍在对话流里（K3）
- [ ] 空闲会话误发引导 → 自动按普通新消息处理（不再静默丢失）
- [ ] 回归：`pytest -m "not external and not network and not live_llm"` 全绿
