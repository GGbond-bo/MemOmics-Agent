---
name: debate-core
description: >-
  MemOmics 辩论核心技能（P0-P3，2026-08-10；P1/P0/P2 补丁 2026-09-22）。
  什么时候**不值得**辩（P1 分情况矩阵：只读/事实查询/线性执行/重复议题/活选项<2 → L0）、
  何时该辩论（三级门控 L0/L1/L2 + 五类触发信号）、裁决必须能落地（P0：decision/
  next_actions/fallback/reopen_condition/missing，禁止"证据不足先补数据"式空结论）、
  裁决怎么驱动下一步（P2：next_actions→待办，blocks→高影响工具硬拦）、
  怎么辩论（mode 四架构 / rounds / role_model_map，
  配置在 config.yaml debate 段）、裁决回流（record_verdict → skill.json
  debate_verdicts）、以及 8/8 失败排障。所有分析结论、参数选择、入库/报告
  前的裁决都走它。multi-role-debate 保留为排障手册，本技能是总纲。
category: Core Mechanism
tags: [debate, gating, verdict, quality, self-evolution]
when_to_use: >-
  任何涉及结论/参数裁决的时刻：rail_review(post) 后、结论合成前、入库/报告前、
  参数候选≥2 或结果冲突/重试失败时。SOUL.md 铁律 #5 强制场景。
---

# Debate Core: 何时辩、怎么辩、怎么回流

辩论是 MemOmics 的质量内核：结论、参数、可入库知识都必须过辩论。
但**不是每次都辩**——全量辩论有害（iMAD, AAAI 2026 Oral：选择性触发省
92% token 且准确率反升 13.5%）。用门控决定何时辩。

## 1. 什么时候该辩论（debate_gate 三级门控）

enforcement.py 的 `debate_gate(es, stage, signals)` 自动判定，返回
`(level, reasons, force)`：

| 级别 | 含义 | 成本 |
|---|---|---|
| L0 | 跳过（chat/lightweight 级，无分析对象） | 0 |
| L1 | 轻量（单对正反+裁判 / 3 采样投票） | ≈1/4 |
| L2 | 完整 8 角色（正方3+反方4+裁判） | 全量 |

**五类触发信号**（命中即升级）：
1. **高影响**（high_impact）：入库/报告/结论产物工具（generate_report、
   save_knowledge、add_figure 等）→ **强制 L2，不可降级**
2. **失败**（failed_retries≥2 或 last_error）：同命令重试≥2 次 → L2
3. **冲突**（conflict）：rail_review(post) 未通过 / 与上次结果差异大 → L2
4. **不确定性**（uncertainty）：候选参数≥2、措辞犹豫、自评低置信 → 结论前 L2
5. **阶段**（stage）：analysis 级结论合成前默认 L2；脚本设计/执行后默认 L1

**级别默认值**：chat/lightweight → L0（不辩）；statistical → L1；
analysis → 结论前 L2、其余 L1。

### 1.1 P1 分情况矩阵：什么时候**不值得**辩（2026-09-22，反"为辩论而辩论"）

辩论的准绳只有一条：**辩完必须能改变下一步动作**。改变不了 → 不辩（系统会打印
`执行前不辩论：<原因>`，这是正常的跳过，不是失败）。`_debate_worthiness(signals)`
在门控前先过一层"值不值"，命中的跳过原因：

| 跳过原因 | 判据 | 为什么不懂 |
|---|---|---|
| `no_debate` | 调用方显式 `debate=False` | 用户/引擎说不用辩 |
| `n_options<2` | 活选项 < 2（只有一个可行路径） | 没有分歧点，辩不出东西 |
| `fact_lookup` | 事实查询（版本号/包名/路径/是什么） | 事实问题查文档，不靠投票 |
| `readonly` | 只读操作（ls/cat/head/status/jobs/logs…） | 读一眼就知道结果 |
| `repeat_topic` | 本会话已辩过同一 topic | 重复辩论 = 烧 token |
| `linear` | 线性命令执行（单行 shell、无参数选择） | 没有可选方案 |

**但硬信号优先于跳过**（`high_impact` / `failed_retries≥2` / `last_error` / `conflict`
四条一出，跳过规则全部让路，按强制 L2 处理）——因为这些场景里"不辩"的代价更高。

**分级判据（分情况，不要一刀切）**：

| 场景 | 级别 | 判据 |
|---|---|---|
| 只读 / 事实查询 / 线性执行 / 重复议题 / 活选项<2 | **L0** | 辩了也改不了动作 |
| 脚本设计（首次，且脚本含可争议参数：resolution、阈值、分组列、方法选择） | **L1** | 有选择但影响面小 |
| 结论合成有 ≥2 个**活选项**或存在不确定性 | **L2** | 结论会进报告/知识库，错了代价大 |
| 结论合成无分歧（数据已指向唯一解释） | **L1** | 走个证据校验 |
| 高影响（入库/报告/产物）/ 失败重试≥2 / rail_review(post) 未通过 | **L2 强制，不可降级** | 硬信号 |

**预算护栏**：单会话辩论次数 ≥ config `debate.budget`（默认 3）后，
非强制 L2 自动降 L1。**topic 级去重**：同一主题只辩一次
（`debated_topics` 集合，替代旧的 debate_done 布尔）。

**L2 裁判 confidence=low 且要入库** → 自动升级重辩（不可用低置信结论入库）。

> **与本矩阵正交的另一条铁律**：本矩阵管"辩不辩"，铁律 35 管"开工前问清楚没"——
> 高代价任务（分析/集群投递/入库/报告）如果目标、交付物、关键参数还没跟用户对齐，
> 系统会**预置执行门禁**（`enforcement.arm_intent_confirm`），要求先用 `ask_user` 弹
> 确认表单勾选，用户答复前执行/产物类工具全被拦。两者不冲突：先对齐意图，再决定辩不辩。

## 2. 怎么辩论（引擎参数化，config.yaml `debate:` 段）

`debate_analysis(topic, context, mode=?, rounds=?, role_model_map=?)`：
不传参数时全部从 config 读，config 无 debate 段 = 现状行为（兼容）。

| mode | 含义 | 适用 |
|---|---|---|
| homogeneous | 单模型 8 角色（默认/现状） | 日常 L1/L2 |
| adversarial | 正/反/判三组异构模型 | 实验、高争议 |
| multi_model | 每个角色独立模型 | 实验、多样性最大 |
| temperature | 同模型多温度采样 | 对照实验 |

- `rounds`：轮数，>1 时第 2 轮起向正反方注入上一轮裁判摘要
  （角色依然看不到彼此原始论点——隔离不破坏）
- `role_model_map`：角色级模型覆盖，优先级最高
  （角色名：pro_biology/pro_statistics/pro_bioinformatics/
  con_biology/con_statistics/con_bioinformatics/con_history/judge）
- **缓存指纹**：缓存 key = md5(topic+context+mode指纹)。不同架构
  永不共享缓存结果。改 mode/rounds/role_model_map 必然是新辩论。
- 模型解析优先级：role_model_map[label] → mode 分组
  （adversarial 的 judge/pro/con；multi_model 按角色哈希从 provider_keys
  分配）→ 环境变量（_sync_debate_env 注入的 _current_model）
- 无环境 key 时回退 provider_keys.json：跳过失效 dcs-cloud，优先 deepseek
  官方（deepseek-v4-flash），其余兜底

**v2（2026-08-27）新增参数**（config 的 debate 段或工具参数）：
- prompt_version: 2（默认）：v2 证据契约 + 结构化论据 + 裁判 rubrics；
  MEMOMICS_DEBATE_LEGACY_PROMPTS=1 一键回退 v1 提示词
- evidence_cards：外部证据卡（JSON 数组或文本，含 PMID/DOI/effect/n/source_file），
  注入所有角色与裁判；内容变化 → 指纹变化 → 不复用缓存
- role_preset: core7 | core9：core9 增加**实验设计评审**与**可重复性评审**两个中立角色 → 10 角色/轮
- judge_count: 1 | 3：多裁判温度采样 + 简单多数投票（judge_consensus 字段）；
  >1 时成本 ×2-3，预算护栏按调用次数计
- rounds_max: 5：rounds 上限护栏（默认 5）
- max_tokens: {judge:8192, role:2048, l1_role:2048, l1_judge:8192}
  —— 推理模型（deepseek-v4-pro）若上限过低会被 reasoning 吃满，content 为空 → 裁决恒低
- 并发说明（2026-08-14 修正）：受控并发 max_workers=3（MEMOMICS_DEBATE_MAX_WORKERS），
  不再全串行（会卡死）也不全并发（会触发配额 8/8 失败）；隔离性不受影响

## 3. 辩论结果怎么用（裁决回流）

辩论成功后**自动**（无需 agent 手动）：
1. 结果缓存到 `_debates/{fingerprint}.json`（72h TTL，失败结果不缓存）
2. 归档到 `results/<session>/log/debate_{ts}_{hash}.json`
3. **裁决回流**：`skill_evolution(action="record_verdict")` →
   - `skill.json` 的 `debate_verdicts` 数组（topic 去重，带 evidence）
   - `results/.../log/run_record_*_verdict.json` 归档
   - 前置条件：无 error 且 confidence ≠ low；`reflow_skill` 配置了
     skill 名才写 skill.json（缺省只归档）

### 3.1 P0：裁决必须**能落地**（2026-09-22，反"证据不足先补数据"式空结论）

裁决 JSON 必须带这五个字段（裁判提示词已强制要求；引擎在裁判漏字段时会从正文回填，
并标 `decision_source = "judge" | "engine_backfill"` + `decision_warnings`——回填是兜底，
不是常态）：

| 字段 | 含义 | 示例 |
|---|---|---|
| `decision` | 一句话结论（**必须有方向**） | "用 resolution=0.8 继续，不重聚类" |
| `next_actions[{action,owner,why,expected,cost,blocks}]` | 下一步动作，owner=ai/user | owner=ai → 自动写成会话待办 |
| `fallback{path,confidence,risk,label}` | 主路径失败时的退路 | "若 silhouette<0.3 → 改 1.0" |
| `reopen_condition` | 什么条件下重开这个议题 | "新数据/新文献推翻结论时" |
| `missing` | 缺什么证据（`verdict=need_more_info` 时**必须非空**） | "缺 marker 热图" |

**一致性硬检查**：`verdict=need_more_info` 但 `missing` 为空 → hard issue
（等于"没结论又不说缺什么"，是最没用的裁决形态）。

### 3.2 P2：裁决 → 下一步动作的自动闭环

1. `next_actions[owner=ai]` → 写入本会话待办（Hermes TodoStore，`{id,content,status}`，
   merge 写入），前端待办面板直接可见；裁决里出现 `debate_todos` 时同样落盘。
2. 带 `blocks` 的动作**未完成时** → 高影响工具（入库/报告/产物）被**硬拦**，
   返回"裁决行动未完成"。解除路径三条：完成该待办 / 重跑 `debate_analysis` / 标记 cancelled。
3. 配置：`debate.budget`（单会话辩论上限，默认 3）、`debate.enforce_blocks`（默认 true，
   关掉就只写待办不拦工具）。**永远不会死锁**——三种解除路径都可用。

## 4. 排障（8/8 失败排查顺序，详见 multi-role-debate）

1. 查注入的 provider（`_sync_debate_env`：_current_model → deepseek → dcs）
2. 单角色 httpx 直测（200=注入正常；401=provider 错；超时=配额）
3. deepseek-v4-flash 答案在 `reasoning_content`，content 常空（已有 fallback）
4. 串行执行是默认（并发 8 路曾触发配额 7 次全失败）；串行不破坏隔离
5. 全部失败 → 不缓存不归档（P0-1 守卫），agent 应重试或检查 key

## 5. 与其它机制的关系

- **rail_review(post) → debate**：rail 通过后门控决定要不要辩
  （不是必须辩！L1/L2 按信号）
- **skill_evolution record_run**：辩论前的 record_run 是另一回事；
  record_verdict 只沉淀裁决本身
- **KB 验证铁轨**：入库知识必须带 evidence；辩论裁决的 evidence
  （call_ids/scores/kb_used）就是溯源链的一环
- 论文实验（P4+）：mode 参数化即实验开关，日常任务自动积累
  4×2×2 因子矩阵数据（详见 docs/debate-core-design.md）
