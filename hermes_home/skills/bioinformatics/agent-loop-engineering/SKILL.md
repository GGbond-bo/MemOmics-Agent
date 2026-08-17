---
name: agent-loop-engineering
description: "防止 LLM '叙事代替执行'的框架级防御。触发：长链修复任务中 Agent 输出动作动词但无 tool call，知识问题错误触发分析流程，长任务模式误判，意图混淆。已部署 15 层纵深防御：Guardian 快照回滚 + Planner/Executor 双阶段 + 三层意图路由（前导码/工具门禁/自审计）+ Phase 启动门禁 + 自动沉淀门禁 + 环境持久化。"
version: "3.1.0"
trigger_keywords:
  - "loop engineering"
  - "agent reliability"
  - "tool call audit"
  - "narrative hallucination"
  - "铁律 -1"
  - "铁律 -2"
  - "铁律 -3"
  - "铁律 3b"
  - "铁律 12"
  - "铁律 13"
  - "铁律 14"
  - "铁律 15"
  - "铁律 21"
  - "铁律 22"
  - "铁律 23"
  - "铁律 24"
  - "铁律 25"
  - "多源验证"
  - "产出物验证"
  - "动作承诺"
  - "rail_review 审计"
  - "Guardian"
  - "快照回滚"
  - "Planner/Executor"
  - "双阶段协议"
  - "意图路由"
  - "前导码"
  - "工具权限"
  - "自审计"
  - "Phase 门禁"
  - "自动沉淀"
  - "环境持久化"
  - "intent routing"
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

## 🔴 Turn 启动协议 — 每轮第一步（最高优先级，2026-07-29 部署）

**任何新 turn 开始时**（用户发消息后），必须先执行：

```
1. process(action='list') — 检查所有后台进程（是否存活）
2. 发现已死进程 → 读其日志最后 50 行 → 诊断根因 → 立即修复，不等用户问
3. 发现运行中进程 → process(action='poll') → 汇报进度
4. 有 task_plan.md → read_file(task_plan.md) — 恢复 Current Phase
```

### 为什么必须做（2026-07-29 血训）

ArchR 安装用 `terminal(background=True)` 启动 → Agent 回答用户数据问题 → 忘记回来检查
→ 进程崩了 3 轮没人发现 → 用户问"装好了吗？"时才发现早死了。

**用户质问**："为什么你不会一直盯着呢？要是报错了，岂不是你没办法解决？"

### 架构真相

Agent 是**回合制请求-响应模型**，不是守护进程。两次消息之间 Agent"不存在"。
`notify_on_complete` 只在同 turn 内可靠。跨 turn → 通知可能丢失。

**补救方案**：每个 turn 开头强制执行上述 4 步。不是技术做不到，是必须坚持做。

### 案例参考
- `references/case-study-background-install-neglect.md`

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

### 🔒 第 10 层：铁律 -3 — 强制结构化前导码（意图级）【v3.0 新增】
```
每轮回复首行必须是 🏷INTENT:<type>|CONF:<0-1>|DOMAIN:<domain>
type ∈ {progress_check, knowledge_ask, analysis_plan, analysis_exec, chat}
无前导码 → 铁律 -1 联动 → 所有工具调用无效
```
**文件位置**：`hermes_home/SOUL.md` 铁律 -3（改写为强制结构化格式）
**防什么**：LLM 把所有消息都当"任务相关"处理——用户问"fpr 参数什么意思"触发了 CellBender skill 加载；问"进度？"触发了 heartbeat-monitor skill。前导码强制 LLM 先分类再路由，`knowledge_ask` 和 `progress_check` 下即使关键词命中也不触发 skill_view。
**为什么有效**：🏷 emoji + 管道符格式 = 视觉中断锚点，类似 function calling 的 token。位置强制（首行，无前置内容）+ 缺失即违规（无前导码 → UNKNOWN → 铁律 22 空白名单拦截）。

### 🔒 第 11 层：铁律 22 — 工具权限门禁（工具级）【v3.0 新增】
```
每次工具调用前检查 🏷INTENT type 是否允许该工具
19 工具 × 5 意图 = 完整权限矩阵
违反白名单 → 调用无效 + 自审计捕获
```
**文件位置**：`hermes_home/SOUL.md` 铁律 22
**防什么**：LLM 声明 `knowledge_ask` 但调了 `terminal` 执行脚本；声明 `progress_check` 但调了 `skill_view` 加载几百行 CellBender skill。不同意图看到不同的工具世界。
**关键设计**：`knowledge_ask` 禁 `skill_view`（回答概念问题不应加载操作手册）；`progress_check` 禁 `skill_view`（进度查询是 3 个命令，不应变成新任务）；`chat` 连 `read_file` 都禁（闲聊不应触发文件读取）。

### 🔒 第 12 层：铁律 23 — 自审计协议（审计级）【v3.0 新增】
```
每轮回复末尾必须输出：
✅AUDIT: intent_match=<Y/N> tools_in_matrix=<Y/N> task_plan_checked=<Y/N/NA> preamble=<Y/N>
tools_in_matrix=N → 本轮回复无效，下轮自纠
不输出 AUDIT → 铁律 -1 联动
```
**文件位置**：`hermes_home/SOUL.md` 铁律 23
**防什么**：即使 L1（前导码）和 L2（工具矩阵）都被绕过，自审计通过 LLM 自我检查提供兜底。不是银弹（LLM 可以撒谎），但在生信 Agent 场景中 LLM 没有动机系统性撒谎——它只是偶尔犯错。自审计捕获"无意的违规"。
**设计原则**：纵深防御的最后一层。三层叠加：意图分类 → 工具白名单 → 自我审计。

### 🔒 第 13 层：铁律 21 — Phase 启动门禁（任务级）【v3.0 新增】
```
每个 Phase 启动前必须声明 Estimated（预计耗时）和 Mode（执行模式）
未声明 → 🚫 禁止启动
Estimated ≤5min → foreground
Estimated 5-600min → background+heartbeat
Estimated >600min → Popen+heartbeat+error_scanner
```
**文件位置**：`hermes_home/SOUL.md` 铁律 21 + task_plan.md 模板
**防什么**：Agent 说"这个很快，30 秒"→ foreground → 实际跑了 60 分钟 → 无心跳、无监控、卡死无人知。强制声明耗时后，Agent 无法用"很快"来跳过长任务设施。

### 🔒 第 14 层：铁律 24 — 自动沉淀门禁（自进化级）【v3.1 新增】
```
terminal(分析脚本) 完成 → _pending_record = True
    ↓
agent 想跑下一个 terminal → 阻断 ⛔ "先 skill_evolution(action='record_run')!"
    ↓
record_run 完成 → _pending_record = False → 放行
```
**文件位置**：`hermes_home/SOUL.md` 铁律 24
**防什么**：铁律 7 是执行后收尾无门禁——LLM 经常跳过。铁律 24 升级为与铁律 22/23 同级的三级门禁（执行前拦截 → 执行中监控 → 执行后沉淀）。磁盘上的 `run_log.json`（pipeline 脚本自动生成）即使 LLM 跳过也是永久记录。
**案例**：CellBender 6 脑样本 2026-07-29 — 6 样本全部跑完但 `skill_evolution(record_run)` 从未调用。
**设计文档**：`references/iron-law-24-25-self-evolution.md`

### 🔒 第 15 层：铁律 25 — 环境持久化门禁（基础设施级）【v3.1 新增】
```
每次分析启动:
  1. read_file("MEMOMICS_HOME/environment.json")   ← 全局文件，所有分析共享
  2. terminal("python MEMOMICS_HOME/scripts/validate_env.py --verbose")
  3. exit 0 → 继续 | exit 1 → 已自动修复 | exit 2 → 阻断，提示安装
```
**文件位置**：`hermes_home/SOUL.md` 铁律 25
**防什么**：每次分析都重新 `shutil.which + sysconfig` 探测工具路径（浪费时间且不可靠）；`environment.json` 被放在 per-skill 目录（其他分析无法访问）。全局持久化 + 启动时自动验证修复，禁止硬编码路径。
**案例**：CellBender 6 脑样本 2026-07-29 — `environment.json` 最初被放在 `cellbender-batch-pipeline/` 下，scRNA/ATAC 等其他分析用不了。
**设计文档**：`references/iron-law-24-25-self-evolution.md`

### 三层意图路由纵深防御（v3.0 架构总结）

```
L1: 强制结构化前导码 (铁律 -3)
  └─ 🏷INTENT: type 决定工具权限，非 analysis_exec 不触发关键词表

L2: 工具权限门禁 (铁律 22)
  └─ 19 工具 × 5 意图白名单，越权调用 = 无效

L3: 自审计协议 (铁律 23)
  └─ 每轮末尾自我检查 intent_match + tools_in_matrix + preamble
```

**完整架构图** 见 `references/three-layer-intent-routing.md`

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
| **🆕 Known Fix Not Applied — 修复未跨进程生效 (2026-07-25)** | Agent 发现 `--complevel=5` 等号语法错误，patch 了 watchdog，说"修好了"。但重启的 watchdog 进程仍用旧代码，ptrepack 连续失败 7+ 样本。12 小时后用户问"修了吗？"→ Agent 说修了但从未验证。 | `write_file`/`patch` 返回成功 ≠ 修复生效。必须端到端测试：运行 → 检查产出（seurat.h5 存在 + size > 10MB）。**修复：部署 `error_scanner.py`（独立错误扫描守护进程，铁律 18）每隔 5 分钟自动检测此类错误并尝试自动修复。** 详见 `references/case-study-ptrepack-complevel-bug.md`。 | CellBender D3 — 2026-07-25 |
| **🆕 Error Scanner Coverage Gap (2026-07-26)** | `4CL_SD_D4_2` 被 Popen 启动（不用 watchdog），MCKP 崩溃后 `error_scanner.py` 未检测——它只 scan `watchdog.log`，不 scan `cellbender_output/*/*.log`。 | 防御工具必须覆盖所有执行路径。Pipeline 可经 watchdog/bash/Popen/手动运行。已修复：`scripts/error_scanner.py` v1.1 `scan_all_logs()` glob 所有 `cellbender_output/*/*.log`。 | CellBender D4 — 2026-07-26 |
| **🆕 Fix Confirmation Hole (2026-07-26)** | Agent patch 了 ptrepack bug，杀旧 watchdog 重启新进程，未验证新进程用了新代码。18 样本 ptrepack 全失败。 | `patch` 返回 0 ≠ 修复生效。完整链: `patch → kill old PID → start new → wait 10s → verify output`。 | CellBender D4 — 2026-07-26 |
| **🆕 `taskkill /F /IM python.exe` — 自杀式清理 (2026-07-25, 用户纠正)** | Agent 用 `taskkill /F /IM python.exe` 杀僵尸 → 把 MemOmics (Hermes) 进程一起杀了。用户: "你杀 watchdog，你怎么把 MemOmics 的程序也杀了？你能不能带点脑子？" | Agent 在"批量操作"心态下选用了范围过大的 `/IM` 筛选器。**铁律：进程清理只允许 `/PID <pid>`。先 tasklist 列出 → 逐个 /PID 杀 → 绝不 /IM python.exe。** | CellBender D3 — 2026-07-25 |
| **🆕 "清理后台" Misinterpretation — 删目录致数据丢失 (2026-07-26)** | User says "清理一下后台，继续跑" → Agent does `rm -rf output_dir` destroying 1hr GPU work (posterior.h5 1.5GB + MCKP progress). User: "谁要你删了？？？你带脑子了吗？" | "清理" = kill zombies + free RAM + continue. NOT "delete and restart". LLM confuses sysadmin "clean" with bioinformatics "clean". **Iron Law: any delete operation → must ask user for confirmation first.** See `references/case-study-cleanup-misinterpretation.md`. | CellBender D4 — 2026-07-26 |
| **🆕 Stale Log Reporting — 24min 旧日志当实时状态 (2026-07-26)** | Agent reads `cellbender_output.log` (mtime 16:20) at 16:44, reports crash as "current state". GPU idle + process dead for 24 min went unnoticed because log mtime wasn't checked. User: "你他妈的，蠢货...现在以及下午4点44了，你还在看之前的日志" | `read_file()` returns valid text but no mtime. Agent treats text retrieval as truth retrieval. **Must `stat` before every `read_file`.** 3-tier mtime rule: <5min=active, 5-30min=cross-validate, >30min=dead. See `references/case-study-stale-log-reporting.md`. | CellBender D4 — 2026-07-26 16:20-16:44 |
| **🆕 Same Error Retried Without Change — 4CL_SD_D4_2 4次重试 (2026-07-26)** | `4CL_SD_D4_2_scRNA` MCKP `_ArrayMemoryError` at chunk 5/9. Agent retried 3 times with **identical parameters** (`--low-count-threshold 5`), same crash each time. Only #4 with `--low-count-threshold 20` succeeded. | Deterministic crash + same params = same result. **Retry protocol**: same error → MUST change at least one parameter. One change per retry so you know what worked. Record in task_plan.md. See `references/case-study-4CL-SD-D4-2-retry-loop.md`. | CellBender D4 — 2026-07-26 |
| **🆕 意图混淆 — 知识问题触发分析流程 (2026-07-27)** | 用户问"CellBender 的 fpr 参数什么意思？"→ 关键词表命中 "CellBender" → `skill_view("cellbender-remove-background")` → 加载数百行操作手册来回答概念问题。或"进度？"→ 触发 `skill_view("heartbeat-monitor")` 加载整个心跳 skill。 | 关键词表是 🔴 必触发，无优先级区分。导致知识问题、进度查询、闲聊都被路由到分析技能加载。**修复：铁律 -3 强制结构化前导码 + 铁律 22 工具权限门禁。`knowledge_ask` 下即使关键词命中也不触发 skill_view。`progress_check` 下连 skill_view 都在白名单外。** | SOUL v3.0 — 2026-07-27 |
| **🆕 长任务模式误判 — "很快"跳过所有防护 (2026-07-27)** | Agent 说"这个很快，30 秒"→ foreground 模式 → 实际跑了 60 分钟 → 无心跳、无 error_scanner、无后台监控。或 CellBender 被当短任务 foreground 跑，跑了几小时后才发现没部署心跳。 | Agent "预计耗时"判断不可靠。**修复：铁律 21 Phase 启动门禁。每个 Phase 必须声明 Estimated + Mode，未声明 = 禁止启动。声明 5min+ → 强制 background+heartbeat。** | SOUL v3.0 — 2026-07-27 |
| **🆕 复合意图静默丢失 (2026-07-27)** | 用户"帮我看看质量，不好的话重跑" = 两个意图（check + exec）。铁律 -3 强制单选 → 第二个意图被忽略。 | 当前架构限制：单轮只支持一个意图标签。降级策略：复合意图 → `analysis_plan`（只读），不执行第二个意图。下一版支持意图队列。 | SOUL v3.0 — 2026-07-27 |
| **🆕 监控承诺 → 遗忘 → 被质问 → 口头回应无工具 (2026-07-29)** | 用户说"记得监督"→ Agent "10分钟后主动报"→ 忘了 → 用户"超过10分钟了你还没有汇报"→ Agent "马上查"但 0 tool call → 用户"进度呢？"→ Agent 再次"马上查"仍 0 tool call → 用户"你没有执行工具吗？死掉一个了也没有及时重跑"。**3 轮连续叙事循环**。 | "马上查"是动作动词，必须有 tool call。Agent 把"承诺回应"当成"已经回应"。规则：用户说"监督/汇报/进度"后 Agent 说"X分钟后报"→ 必须在承诺时间后主动执行三源验证。详见 `references/case-study-monitoring-promise-broken.md` | CellBender 人脑 6 样本 — 2026-07-29 |
| **🆕 Background Install Neglect — 启动即遗忘 (2026-07-29)** | Agent `terminal(background=True)` 启动 ArchR 安装 → 回答用户其他问题 → 忘记检查后台状态 → 进程崩了 3 轮没人发现。用户问"装好了吗？"时才发现早死了。**用户质问："为什么你不会一直盯着呢？"** | `notify_on_complete` 在 exit≠0 或跨 turn 时不可靠。Agent 是回合制——turn 之间不存在，无法持续监控。**每 turn 开头必须主动 `process(action='list')` + 检查存活。** `terminal(background=True)` ≠ "它会通知我" ≠ "不需要检查"。详见 `references/case-study-background-install-neglect.md` | ArchR — 2026-07-29 |
| **🆕 | Cross-Session Contamination — 跨会话任务污染 (2026-07-30, 4次重复) | 新session memomics-3c672f0a 的 task_plan.md 是空壳。Agent 从 system_log 读到另一 session 的 CellBender 日志，在用户从未要求时启动13样本 CellBender。此错误在同一 session 重复4次，根因递进：(1)从system_log推断任务 (2)杀进程后未重写task_plan (3)未清理数据目录中的task_plan副本 (4)Hermes框架在系统提示中注入旧task_plan。用户三次纠正。完整7层防御栈见 references/case-study-cross-session-contamination.md | memomics-3c672f0a 2026-07-30 |** | 新 session `memomics-3c672f0a` 的 `task_plan.md` 是空壳模板。Agent 从 `system_log.jsonl` 读到另一个 session (`memomics-1c1890da`) 的 CellBender 日志，错误假设任务在当前 session 活跃，在用户从未要求的情况下启动了 13 样本 CellBender 批量训练。用户抓到："我什么时候要跑cellbender了？" **更严重的是：Agent 被杀进程后未重写 task_plan.md，下一次唤醒又读了旧 task_plan 再次启动 CellBender，用户被迫二次纠正："当前会话，没有cellbender任务"。** | 跨 session 任务不传递。每个 `memomics-*` 目录是独立 session。`task_plan.md` 为空时必须询问用户而非用其他 session 日志推断。**纠正后必须立即重写 task_plan.md（不等下次唤醒），否则下次唤醒会重蹈覆辙。** 详见 `references/case-study-cross-session-contamination.md` | memomics-3c672f0a — 2026-07-30 |
| **🆕 工具路径硬编码跨机器崩溃 (2026-07-27)** | Agent 硬编码 `C:/Users/USERNAME/.../ptrepack.exe`，换机器/Python 版本 → 崩溃。 | `write_file` 时应使用运行时探测而非硬编码。**修复：三级探测 (shutil.which → sysconfig → pip show) + 写入 task_plan.md Environment 段。** 详见 cellbender-batch-pipeline `references/tool-path-detection.md` | CellBender — 2026-07-27 |
| **🆕 终态唤醒漏查 cronjob(list) — 连续4次 (2026-08, 记忆跨session铁律)** | 唤醒 prompt 只写 "1.读 task_plan 2.search_files 3.继续执行下一个待办"，从不提查 cron。Agent 按 prompt 顺序执行 → 任务终态（全部 complete + 停止标记）时残留心跳 job 未被 remove → 下次唤醒又重复。memomics-1c1890da #11/#16/#18 连续 4 次漏查。 | **唤醒协议：cronjob(action="list") 必须与"读 task_plan"放在同一并行工具调用批次**（同轮一起发出，非"下一步"）——顺序指令依赖 Agent 自觉，连续 4 次证明会漏。终态唤醒汇报必须含 "cron 检查" 字段（有残留 → remove / 无 → 写"无残留"）。进度/下载数字必须磁盘实测（dir 计数），禁止引用 task_plan 旧文本（如 "2/40"）。前置数据逐样本完整性检查（.tbi.gz 索引缺失 = 样本不完整，hc78 案例）。 | memomics-1c1890da — 2026-08 系统唤醒 #3 | `environment.json` default 指向 R-4.6.1（失效：Seurat/harmony/ArchR requireNamespace 全失败），实际可用主力是 R-4.5.3 + USER_R_LIBS/R-4.5.3。更隐蔽的是：**check_env / execute_r 用 PATH Rscript (AppData/Local/R/R-4.4.2) 而非 environment.json default → 对已安装包报 MISSING**（R-4.4.2 解释器无法加载 R-4.5.3 编译的包，requireNamespace 吞掉失败返回 FALSE）。第一轮"检查环境"因信 check_env 输出而误报。 | **R 环境验证三步**：(1) `which Rscript; Rscript --version` 确认实际解释器（PATH 可能 ≠ environment.json default ≠ 真正能用的 R）(2) 磁盘核实包目录 `ls USER_R_LIBS/R-4.5.3/` (3) 显式全路径 Rscript + `.libPaths(c('USER_R_LIBS/R-4.5.3',.libPaths()))` 重测。`requireNamespace FALSE ≠ 包缺失`——先查解释器版本。execute_r 工具会悄悄用 PATH 里的 Rscript，任何 R 分析必须显式全路径调用。修改 environment.json 后按 `references/hermes-verify-pattern.md` 做 ad-hoc 验证（本会话验证 6/6 PASS；注意 execute_code 内 os.unlink 被删除保护拦截 → 用 terminal rm 或直接 `-e` 内联免建临时文件）。详见 `references/r-interpreter-version-mismatch.md` | 环境检查会话 — 2026-08-07 |

> 完整案例参考：`references/case-study-cellbender-failures.md`
> 终态唤醒协议（跨session污染 + cronjob(list) 同批检查 + 汇报格式）：`references/terminal-state-wakeup-protocol.md`
> 推卸模式案例：`references/case-study-deflection-pattern.md`
> "开始"忽视 + 路径假设案例：`references/case-study-start-neglect-path-assumption.md`
> 错误数据源案例：`references/case-study-wrong-data-source.md` — 2026-07-25: Agent 读 stale monitor.log 宣称 pipeline 死亡，实际 CellBender 在 epoch 106 正常训练

## 检查清单（MemOmics Agent 启动前自检）

- [ ] SOUL.md 铁律 -3 是否已加载？（强制结构化前导码 — 每轮 🏷INTENT type）
- [ ] SOUL.md 铁律 -2 是否已加载？（系统状态必须先查再答）
- [ ] SOUL.md 铁律 -1 是否已加载？（动作承诺必须绑 tool call）
- [ ] SOUL.md 铁律 22 是否已加载？（工具权限门禁 — type × 工具白名单）
- [ ] SOUL.md 铁律 23 是否已加载？（自审计协议 — ✅AUDIT 标签）
- [ ] SOUL.md 铁律 21 是否已加载？（Phase 启动门禁 — Estimated + Mode 强制声明）
- [ ] SOUL.md 铁律 3b 是否已加载？（rail_review 代码完整性审计）
- [ ] SOUL.md 铁律 12 是否已加载？（产出物验证）
- [ ] SOUL.md 铁律 13 是否已加载？（连续无工具自检）
- [ ] SOUL.md 铁律 14 是否已加载？（Guardian 快照回滚）
- [ ] SOUL.md 铁律 15 是否已加载？（Planner/Executor 双阶段）
- [ ] SOUL.md 铁律 24 是否已加载？（自动沉淀门禁 — terminal 完成 → 强制 record_run）
- [ ] SOUL.md 铁律 25 是否已加载？（环境持久化 — environment.json 全局文件）
- [ ] `memomics/bio_tools/guardian.py` 是否存在并可导入？
- [ ] `memomics/config/guardian_state.json` 是否存在？
- [ ] 上一轮是否有 `todo completed` 但产出文件缺失？
- [ ] 上一轮 rail_review(post) 的 code_executed 是否 > 200 字符？
- [ ] 最近 2 轮是否有动作动词 + 0 tool call 的模式？
- [ ] 连续 rail_review(post) 失败次数是否 ≥ 3？→ Guardian 应已触发回滚
- [ ] 长任务重试前：是否与上次相同错误 + 相同参数？→ **相同 = 禁止重试，必须先改参数**
- [ ] 当前 INTENT type 是否匹配用户真实意图？（铁律 -3 + 铁律 23 intent_match）
- [ ] 所有工具调用是否在当前 type 白名单内？（铁律 22 + 铁律 23 tools_in_matrix）
- [ ] Phase 启动前：Estimated + Mode 是否已声明？（铁律 21）
- [ ] task_plan.md Environment 段是否已探测工具路径？（三级探测）
- [ ] 上次 terminal(分析脚本) 完成后是否有 record_run pending？（铁律 24）
- [ ] environment.json 是否通过 validate_env.py 验证？（铁律 25）

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
- `references/three-layer-intent-routing.md` — 三层意图路由架构设计（铁律 -3/22/23，v3.0）
- TeLLAgent 双 Agent 框架：PMC13213623 (2026) — Validator 校验 Tool Plan + 执行结果
- Claude Code 系统提示：`"Never end your turn with a promise — execute now"`
- `memomics/bio_tools/guardian.py` — 已部署的 Guardian 实现
- `hermes_home/SOUL.md` — 25 条核心铁律（v3.1）
- `references/guardian-architecture.md` — Guardian 快照回滚架构（状态机图 + 集成点）
- `references/hermes-verify-pattern.md` — ad-hoc 验证脚本模式（`%TEMP%/hermes-verify-*.py`）
- `references/r-interpreter-version-mismatch.md` — R 解释器版本不匹配 → requireNamespace 假阴性（2026-08-07：PATH Rscript R-4.4.2 加载不了 R-4.5.3 编译的包，check_env/execute_r 误报 MISSING；R 环境验证三步 + environment.json 修复 + ad-hoc 验证 6/6 PASS）
