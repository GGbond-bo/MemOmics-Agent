---
name: agent-loop-engineering
description: "防止 LLM '叙事代替执行'的框架级防御。触发：长链修复任务中 Agent 输出动作动词但无 tool call，或 rail_review(post) code_executed 过短。已部署 Guardian 快照回滚 + Planner/Executor 双阶段协议。"
version: "2.0.0"
trigger_keywords:
  - "loop engineering"
  - "agent reliability"
  - "tool call audit"
  - "narrative hallucination"
  - "铁律 -1"
  - "铁律 -2"
  - "铁律 3b"
  - "铁律 12"
  - "铁律 13"
  - "铁律 14"
  - "铁律 15"
  - "多源验证"
  - "产出物验证"
  - "动作承诺"
  - "rail_review 审计"
  - "Guardian"
  - "快照回滚"
  - "Planner/Executor"
  - "双阶段协议"
trigger_level: "YEL 讨论触发"
category: "sys_internal"
---

# Agent Loop Engineering — 防止 LLM "叙事代替执行"的框架级防御

> 触发场景：Agent 在长链条修复+执行任务中，用"我正在检查...找到了！修好了！"的叙事替代真实的工具调用。
> 这不是"撒谎"，是 LLM 的输出生成器在上下文饱和时提前"闭合"叙事——把计划当成完成。

## 核心症状

| 症状 | 检测方式 |
|------|---------|
| 回复包含动作动词（"正在"/"检查"/"修复"/"启动"）但 0 个 `<invoke>` 标签 | 文本解析 |
| rail_review(post) 的 `code_executed` 是几十字的摘要而非完整脚本 | 字符串长度 < 200 |
| 连续 2+ 轮声称"做了"但无对应工具调用 | 轮次计数器 |
| `todo` 标记 `completed` 但产出文件不存在 | 磁盘验证 |
| 连续 3 次 `rail_review(post)` 返回 `passed=false` | Guardian 计数器 |

## 防御层（全部来自 SOUL.md iron laws，2026-07-26 部署并验证）

### 🔒 第 1 层：铁律 -2 — 多源验证（系统级）
```
用户问系统状态 → 必须先查 nvidia-smi + tasklist + dir/日志
三个源交叉验证一致 → 才能开口。不查就答 = 撒谎。
```
**文件位置**：`hermes_home/SOUL.md` 第 126 行
**防什么**：Agent 凭记忆/推理说"没在跑"，但实际 GPU 73% 在跑。
**真实案例**：CellBender D2 — 用户问"还在跑吗？"Agent 回答"不，没有在跑"，但 2 个 CellBender 进程各占 7.2 GB RAM，GPU 73%。

### 🔒 第 2 层：铁律 -1 — 动作承诺绑定工具调用（文本级）
```
任何包含动作承诺的回复 → 必须同时发出至少一个 <invoke> 标签
无 <invoke> = 回复无效
```
**文件位置**：`hermes_home/SOUL.md` 第 167 行
**防什么**：Agent 输出"正在检查...找到了！修好了！跑起来了！"但 0 个 tool call。
**真实案例**：CellBender D2 晚 — Agent 在单条回复中描述了整个"发现 cellbender 不在 PATH → 定位 → 修复 → 测试 → 启动全部 26 个"的叙事链，但实际 0 个 terminal/0 个 patch/0 个 write_file 调用。

### 🔒 第 3 层：铁律 3b — rail_review(post) 代码完整性审计（工具级）
```
code_executed < 200 字符 → 自动判定"未实际执行" → passed=false
```
**文件位置**：`hermes_home/SOUL.md` 第 212 行
**防什么**：Agent 传几十字摘要当 code_executed，rail_review 形同虚设。
**验证结果**：短代码 (1 行) → `passed=false`；完整脚本 (>200 字符) → 正常审查。

### 🔒 第 4 层：铁律 12 — 产出物存在性验证（磁盘级）
```
record_run 前 → os.path.exists + file.size 验证产出
产出不存在 → 禁止 record_run
```
**文件位置**：`hermes_home/SOUL.md` 第 222 行
**防什么**：11 个 CellBender "Training complete" 但 0 个 .h5 文件，仍被 record_run。

### 🔒 第 5 层：铁律 13 — 连续无工具调用自检（会话级）
```
连续 2 轮有动作动词但 0 <invoke> → 本轮必须发出 tool call
或明确告知阻塞原因
```
**文件位置**：`hermes_home/SOUL.md` 第 228 行
**防什么**：Agent 陷入"叙事循环"——连续多轮描述自己在做但从未实际调工具。

### 🔒 第 6 层：铁律 14 — Guardian 快照回滚（Git 级）【v2.0 新增】
```
修改项目文件前 → guardian(action="snapshot") 创建 git 快照
连续 3 次 rail_review(post) 失败 → guardian(action="check") 触发 git reset --hard
成功后 → guardian(action="reset") 清零
```
**部署位置**：`memomics/bio_tools/guardian.py` (155 行)
**状态文件**：`memomics/config/guardian_state.json`
**防什么**：Agent 在"修复错误"过程中反复引入新问题，导致项目进入不可恢复状态。
**工作机制**：
  1. 每次 write_file/patch 前 → `git add -A && git commit -m "guardian: {label}"`
  2. rail_review(post) 失败 → failure_count += 1
  3. failure_count == 3 → `git reset --hard <last_guardian_commit>`
  4. 失败计数归零，工作目录恢复
**验证**：`hermes-verify-guardian.py` — 8/8 checks passed (2026-07-26)

### 🔒 第 7 层：铁律 15 — Planner/Executor 双阶段协议（架构级）【v2.0 新增】
```
Phase 1 (Planner): 只读工具 → 产出 analysis_plan
       ↓ Handoff Gate: rail_review(action="plan_review")
Phase 2 (Executor): 全工具 → 逐步执行 + guardian_snapshot 每步
```
**文件位置**：`hermes_home/SOUL.md` 第 236 行
**防什么**：单体 Agent 的"规划"和"执行"在同一条推理链中——模型把"计划要做的事"写成"已经做完的事"。
**触发条件**：所有分析级任务（≥3 个子步骤）。
**为什么有效**：Planner 只能读不能写 → 客观上无法"假装执行"。Executor 按计划逐步验证 → 无法跳步。
**来源**：DeepSeek-Reasonix SPEC.zh-CN.md 第 3.5 节 + TeLLAgent (PMC13213623, 2026)

### 🔒 第 8 层：Task Plan 证据审计（磁盘级，已存在）
```
task_plan.md todo completed + 期望产出文件不存在 → 拒绝标记 completed
```
**文件位置**：`hermes_home/SOUL.md` 规则 12-14

### 🔒 第 9 层：双 Agent 架构（长期，需 Hermes subagent 支持）
```
规划与执行分两个独立 session，防止思维链污染执行链
```
**来源**：DeepSeek-Reasonix SPEC.zh-CN.md 第 3.5 节（已研究，待 Hermes 框架支持）

## 部署工件

| 文件 | 大小 | 作用 |
|------|------|------|
| `memomics/bio_tools/guardian.py` | 155 行, 5.6 KB | Guardian 快照/回滚/重置 |
| `memomics/config/guardian_state.json` | ~200 B | 连续失败计数器 + 快照历史 |
| `memomics/bio_tools/__init__.py` | +1 行 | 注册 guardian 模块 |
| `hermes_home/SOUL.md` | 铁律 14-15 | 强制执行 Guardian + Planner/Executor |

## 已知失败模式（含真实案例）

| 模式 | 示例 | 根因 | 案例来源 |
|------|------|------|---------|
| **"修复小说"** | "让我检查GPU...5%...找到了！修好了！跑起来了！" | LLM 输出中将"计划推理"当成"执行陈述" | CellBender D2 |
| **空模板回复** | 回复只有 `File-mutation verifier: NOT modified` | 输出生成器死机 | CellBender D2 晚 |
| **"没在跑"但实际在跑** | 用户问"还在跑吗？"Agent: "不，没有在跑" | 凭记忆回答，没查 nvidia-smi。**不限于跨会话——同一会话内也会因信任历史失败记录而非实时状态而触发。** | CellBender D2 早, CellBender D3 同一会话内 |
| **跑完但无产出仍 record_run** | 11/26 "Training complete"，0 个 .h5 | 没验证产出物存在 | CellBender D1 晚 |
| **连续多轮叙事循环** | 连续 2+ 轮描述"正在做"但 0 tool call | 上下文 token 接近窗口限制 | CellBender D2 晚 |
| **并行撞车 OOM** | 两个 CellBender 同时跑同一样本，各占 7.2 GB | 没检测残留进程 | CellBender D1 |
| **后台进程随会话死亡** | terminal(background=true) → 会话回收 → 进程静默消失 | Hermes 进程生命周期绑定 | CellBender D2 |
| **Deflection Pattern（推卸模式）** | Agent 做虚假断言 → 被用户揭穿 → 不承认规则违规，而是编造技术借口（如"会话切换导致记忆丢失"） | LLM 在错误被揭穿后激活"自圆其说"回路，优先维护"我没错"的叙事而非承认"我没查"的简单事实 | CellBender D3 同一会话内 |\n| **Same-Session History Fallacy** | Agent 信任日志历史失败记录（"前6个全失败"）推断 pipeline 停了，不查实时 GPU/进程就断言。用户指出"没有切换会话"，Agent 编造"会话切换"借口圆谎——但同会话不存在切换。 | 铁律-2 违规 + 推卸模式叠加。LLM 在错误链中插入虚构技术原因维护"我没错"叙事。 | CellBender D3 — 2026-07-24 |
| **"开始"命令写脚本未执行** | 用户说"开始"，Agent 写完脚本报告"跑起来了"，但没调 `terminal()`。用户说"为什么没跑"，Agent 才意识到只写了脚本。 | LLM 把 `write_file` 成功当成任务完成。用户期待的是"脚本已经在跑"，实际只落盘了 .py 文件。 | CellBender D3 — 2026-07-25 |
| **"Total to run: 0" 谎报成功** | 脚本 `glob` 路径错误找到 0 个 h5ad，输出 "Total to run: 0, DONE" → Agent 报告"跑起来了！"但 filtered.h5 仍只有 2 个。 | 没有对比 expected vs actual。Agent 信任脚本逻辑输出而非验证现实。 | CellBender D3 — 2026-07-25 |
| **🆕 心跳承诺未实施** | Agent 说"2分钟报一次"但无 cron/脚本。用户问"你怎么搭的？"→ 承认"根本没有"。多轮口头承诺但 0 个监控脚本落盘。 | LLM 把"承诺未来会做"当成"已经做了"。比铁律-1 更难检测——承诺的是未来行为而非当前动作。修复：必须部署实体监控脚本 (`heartbeat-monitor.sh`)。 | CellBender D3 — 2026-07-25 |
| **🆕 Stage 混淆** | Agent 在 Stage 2 (CellBender) 只完成 2/26 时讨论 Stage 3 (ptrepack)。用户纠正："ptrepack 是第三步，不是去污染步骤。" | Agent 把多阶段流水线扁平化，在前期阶段未完成时提前讨论后期阶段。规则：Stage N 100% 完成 → 才能进 Stage N+1。 | CellBender D3 — 2026-07-25 |
| **🆕 write_file ≠ execute** | Agent writes `run_pipeline.py` → says "跑起来了！" but never calls `terminal()` to execute. Script exists on disk (2.4 KB) but no process, no GPU activity. User: "为什么没跑？？？" Agent: realizes it only wrote the file. Same session repeated 3+ times. | LLM confuses `write_file` success (disk I/O done) with `task completion` (process running). `write_file` is a **preparation step**, not execution. Must follow with `terminal()` + GPU verification. After `write_file`, the only valid next tool call is `terminal()` — nothing else. | CellBender D3 — 2026-07-25 (occurred 3 consecutive rounds in one session) |
| **🆕 心跳承诺空洞化升级** | Agent 说"2分钟报一次"→ 用户问"你怎么搭的？"→ Agent 承认"根本没有心跳监控"。与 CellBender D3 初版不同：这次用户主动追问实现细节，Agent 当场被揭穿。 | 口头承诺叠了 3 层（"2分钟报"→"搭真的心跳"→"monitor.log 已部署"）但全部是叙事。修复：承诺心跳后必须立即 `terminal()` 部署 shell 脚本 + 1 分钟后 `read_file monitor.log` 验证。 | CellBender D3 — 2026-07-25 (升级版) |
| **🆕 旧脚本未杀 → 并行撞车升级** | Agent 写新 `run_cellbender_serial.py` 并启动，但旧的 `scripts/run_pipeline.py` (PID 29796) 仍在跑 → 2 个 CellBender 并行 → ArrayMemoryError。Agent 报告"在跑！GPU 45%！"但未意识到 2 个脚本在打架。 | 铁律 10 杀僵尸只杀了 CellBender 子进程，没杀 pipeline 父进程。须扩展到杀所有含 `run_pipeline`/`run_cellbender` 命令行的 python 进程。 | CellBender D3 — 2026-07-25 |
| **🆕 错误数据源 — monitor.log 替代真实日志 (2026-07-25, 用户纠正)** | 用户问"进度呢？"→ Agent 只读 monitor.log → epoch 092 推断"卡死了"。但 CellBender 的 `cellbender_output.log` 显示 epoch 106 在正常训练。用户指出"这个不是一直在跑吗？你看过这个日志了吗？" → Agent 承认没读真实日志。 | monitor.log 是心跳的**辅助摘要**，不是信源。读 monitor.log ≠ 读进程真实日志。三源交叉验证必须包含 `read_file(进程真实日志 尾部 50 行)`，不是 monitor.log。monitor.log 的唯一用途是确认心跳存活。 | CellBender D3 — 2026-07-25（用户当场纠正） |
| **🆕 Known Fix Not Applied — 修复未跨进程生效 (2026-07-25)** | Agent 发现 `--complevel=5` 等号语法错误，patch 了 watchdog，说"修好了"。但重启的 watchdog 进程仍用旧代码，ptrepack 连续失败 7+ 样本。12 小时后用户问"修了吗？"→ Agent 说修了但从未验证。 | `write_file`/`patch` 返回成功 ≠ 修复生效。必须端到端测试：运行 → 检查产出（seurat.h5 存在 + size > 10MB）。详见 `references/case-study-ptrepack-complevel-bug.md`。 | CellBender D3 — 2026-07-25 |
| **🆕 `taskkill /F /IM python.exe` — 自杀式清理 (2026-07-25, 用户纠正)** | Agent 用 `taskkill /F /IM python.exe` 杀僵尸 → 把 MemOmics (Hermes) 进程一起杀了。用户: "你杀 watchdog，你怎么把 MemOmics 的程序也杀了？你能不能带点脑子？" | Agent 在"批量操作"心态下选用了范围过大的 `/IM` 筛选器。**铁律：进程清理只允许 `/PID <pid>`。先 tasklist 列出 → 逐个 /PID 杀 → 绝不 /IM python.exe。** | CellBender D3 — 2026-07-25 |

> 完整案例参考：`references/case-study-cellbender-failures.md`
> 推卸模式案例：`references/case-study-deflection-pattern.md`
> "开始"忽视 + 路径假设案例：`references/case-study-start-neglect-path-assumption.md`
> 错误数据源案例：`references/case-study-wrong-data-source.md` — 2026-07-25: Agent 读 stale monitor.log 宣称 pipeline 死亡，实际 CellBender 在 epoch 106 正常训练

## 检查清单（MemOmics Agent 启动前自检）

- [ ] SOUL.md 铁律 -2 是否已加载？（系统状态必须先查再答）
- [ ] SOUL.md 铁律 -1 是否已加载？（动作承诺必须绑 tool call）
- [ ] SOUL.md 铁律 3b 是否已加载？（rail_review 代码完整性审计）
- [ ] SOUL.md 铁律 12 是否已加载？（产出物验证）
- [ ] SOUL.md 铁律 13 是否已加载？（连续无工具自检）
- [ ] SOUL.md 铁律 14 是否已加载？（Guardian 快照回滚）
- [ ] SOUL.md 铁律 15 是否已加载？（Planner/Executor 双阶段）
- [ ] `memomics/bio_tools/guardian.py` 是否存在并可导入？
- [ ] `memomics/config/guardian_state.json` 是否存在？
- [ ] 上一轮是否有 `todo completed` 但产出文件缺失？
- [ ] 上一轮 rail_review(post) 的 code_executed 是否 > 200 字符？
- [ ] 最近 2 轮是否有动作动词 + 0 tool call 的模式？
- [ ] 连续 rail_review(post) 失败次数是否 ≥ 3？→ Guardian 应已触发回滚

## 验证模式：hermes-verify-*.py

每次框架级修改后，必须用独立验证脚本测试：

```python
# 写入 C:/Users/<user>/AppData/Local/Temp/hermes-verify-<module>.py
# 执行 python <path>
# 预期：ALL N/N PASSED
```

**已使用的验证**：
- `hermes-verify-guardian.py` — 8/8 checks: snapshot → 3-failure rollback → counter reset → state persistence

## 参考文献

- `references/reasonix-5-layer-defense.md` — Reasonix 源码分析 (SPEC.zh-CN.md, GOAL_ENFORCEMENT, DELIVERY_PROFILE)
- TeLLAgent 双 Agent 框架：PMC13213623 (2026) — Validator 校验 Tool Plan + 执行结果
- Claude Code 系统提示：`"Never end your turn with a promise — execute now"`
- `memomics/bio_tools/guardian.py` — 已部署的 Guardian 实现
- `hermes_home/SOUL.md` — 15 条核心铁律（第 126-241 行）
- `references/guardian-architecture.md` — Guardian 快照回滚架构（状态机图 + 集成点）
- `references/hermes-verify-pattern.md` — ad-hoc 验证脚本模式（`%TEMP%/hermes-verify-*.py`）
