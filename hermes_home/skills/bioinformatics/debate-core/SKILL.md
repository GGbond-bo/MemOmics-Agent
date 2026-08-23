---
name: debate-core
description: >-
  MemOmics 辩论核心技能（P0-P3，2026-08-10）。何时该辩论（三级门控
  L0/L1/L2 + 五类触发信号）、怎么辩论（mode 四架构 / rounds / role_model_map，
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

**预算护栏**：单会话辩论次数 ≥ config `debate.budget`（默认 3）后，
非强制 L2 自动降 L1。**topic 级去重**：同一主题只辩一次
（`debated_topics` 集合，替代旧的 debate_done 布尔）。

**L2 裁判 confidence=low 且要入库** → 自动升级重辩（不可用低置信结论入库）。

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

## 3. 辩论结果怎么用（裁决回流）

辩论成功后**自动**（无需 agent 手动）：
1. 结果缓存到 `_debates/{fingerprint}.json`（72h TTL，失败结果不缓存）
2. 归档到 `results/<session>/log/debate_{ts}_{hash}.json`
3. **裁决回流**：`skill_evolution(action="record_verdict")` →
   - `skill.json` 的 `debate_verdicts` 数组（topic 去重，带 evidence）
   - `results/.../log/run_record_*_verdict.json` 归档
   - 前置条件：无 error 且 confidence ≠ low；`reflow_skill` 配置了
     skill 名才写 skill.json（缺省只归档）

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
