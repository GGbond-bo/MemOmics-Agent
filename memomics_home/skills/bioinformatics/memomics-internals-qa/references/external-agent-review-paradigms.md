# 外部科研 Agent 的审查范式 vs MemOmics 辩论机制（知识银行）

> 首次整理：2026-10-23 ｜ 来源：CellVoyager（Zou group, bioRxiv 2025.06.03.657517）逐篇精读 +
> MemOmics 源码取证 ｜ 完整交付版：`results/memomics-802973c9/results/cellvoyager_vs_memomics_debate.md`
> 用途：被问「我们的辩论机制跟 XX agent 有什么不同」「对比一下 CellVoyager / Biomni / AI 科学家」时，
> 直接用本文件的事实与 file:line，不必重新取证。**两侧都必须是实证口径**（对外侧引原文页码，对内侧引 file:line）。

## 0. 先定对象层级（最容易答错的地方）

| | CellVoyager | MemOmics |
|---|---|---|
| 审查对象 | **下一步做什么**（探索蓝图 / 分析计划 π） | **这个结论/参数对不对**（结论与参数裁决） |
| 审查形态 | single-agent **自省**（self-critique） | multi-role **对抗**（物理隔离的多角色辩论） |
| 审查产物 | 修订后的计划 → 继续跑 | verdict + 五维评分 + `decision/next_actions/fallback/reopen_condition/missing` → 落成待办/硬拦 |
| 回答的问题 | "**接下来干什么**" | "**这么说算不算数**" |

一句话差异（对外汇报可直接用）：**CellVoyager 把审查做成探索循环里的一个固定步骤；MemOmics 把审查做成一道带门控和强制力的事故防线。**

## 1. 13 轴对照（facts，含取证位置）

| # | 轴 | CellVoyager（原文取证） | MemOmics（源码取证） |
|---|---|---|---|
| 1 | 触发 | 主循环每步固定 `REFLECT`（Algorithm 1 第 4 行，p.18）；无门控 | `webui/enforcement.py:447-521` 三级门控：L0 八条跳过判据（chat/lightweight、只读、线性执行、事实查询、同议题已辩过、活选项<2、设计类、图类）；硬信号（高影响 / 重试≥2 / 冲突）→ **L2 强制不降级**；2026-10-18 起风险分级降时延（小任务直接 L0） |
| 2 | 主体 | 1 个 LLM 扮批评者 | **7 席**：`pro/con × {biology, statistics, bioinformatics}` + `con_history` + `judge`（`memomics/bio_tools/debate_analysis.py:1774-1776`）；赛前场景预判按问题类型换裁判口径（`:1244`） |
| 3 | 隔离 | 无（同一条上下文自问自答） | 代码层物理切断：每角色一次独立 HTTP 调用，只带自己那份 prompt，返回 `isolation_verified: True` + `messages_count: 1` 可断言凭证（`:1573-1710`，`:2243`） |
| 4 | 证据 | 无外部证据契约（靠模型内嵌知识 + notebook 输出） | v2 证据契约（`:726-752`）：`P（PMID/DOI）/ C（实验记录）/ I（纯推理）`；无证据须标 `[仅是推理]` 且**不计分**；须给 `evidence_chain` 的 `step/anchor/counter`；KB 按物种+组织+方向自动注入（`:3014`） |
| 5 | 裁判 | 无独立裁判，agent 自当裁判（REPLAN） | 独立 judge：judge digest 整理（`:1078`）→ rubrics 五维（证据质量/效应量/混杂/先验文献/可重复性，`:896`）→ `judge_count>1` 多裁判投票（`:1472`） |
| 6 | 裁决落地 | 裁决 = 改计划 | `decision + next_actions(owner/why/expected/blocks) + fallback + reopen_condition + missing` 必填（`:681-711`, `:865-870`）；`owner=ai` → 会话待办；带 `blocks` 未完成 → 高影响工具（入库/报告）**被硬拦**（`enforcement.py` `debate_enforce_blocks=True`）；verdict 回流 `record_verdict` → skill.json（`:2775-2828`, `:3606`） |
| 7 | 错误处理 | `FIXCODE` 最多 F 次 → 修不好 `REPLAN`；**报错被定义为"改道信号"而非终点**（Algorithm 1 8-14 行） | `failed_retries≥2` / `last_error` → 强 L2；`rail_review(post)` 未过 → 强 L2；连续 3 次 rail 失败 → Guardian 快照回滚 |
| 8 | 防重复 | `past_analyses` 回灌提示词（p.19 S058：分析摘要追加进历史列表） | `debated_topics` 同题只辩一次 + 会话隔离（铁律 -5）+ KB / `run_log.json` 复用 |
| 9 | 人在回路 | **事后**：原作者按 rubric 打分（创造力 2.8/3.4/2.4），一句反馈可触发重做 | **事前硬门禁**：高代价任务开工前意图确认表单（未答复时执行类/产物类工具被拦）；方案前 `grill-me` 五攻击面；缺包先问用户 |
| 10 | 长期资产 | 仅会话内历史列表，跨论文不共享 | KB 五级目录 + 三道证据铁轨（`verified=unverified` 拒 / `data_driven` 无 evidence 拒） → 下次复用 → 辩论时再引为论据；技能 `record_run/record_error` 沉淀 |
| 11 | 成本时延 | **顺序执行、每项分析约 30 分钟**、未报 token（p.20 Limitations） | 铁律 -6 **禁并发调 LLM（串行）**；L1 实测整场 303.6s（`debate_analysis.py:307`）；`_deadline_budget` + `_judge_reserve` 秒级护栏；长任务走 `task_run.py` 面板可见可取消 |
| 12 | 可证伪性 | **有公开基准**：CellBench 50 篇/483 项；CellVoyager(GPT-4o) 65.89/68.74% vs GPT-4o 49.89/49.41%（+16.00/+19.33 个百分点，p<0.01 / p<0.001） | **无公开基准**（短板）；`rail_review` 只做形式校验，**验不出统计口径选错** |
| 13 | 折扣项（读原文要打的折扣） | 为公平只跑"想法生成"阶段且**提示词被改成"预测最可能的 held-out 分析"**（基线用通用提示词）；真值由 LLM 抽取、判定由 LLM judge，人工一致性只在 47 条上校验（89%/85%）；案例评估是**择优**（8 条轨迹取成功率最高 5 条 + 单一作者非盲评分）；核心卖点"不重复既往分析"**无独立消融** | 同模型多角色 ≠ 真异构，抓不到同源偏差 |

## 2. 可互相借鉴（写对比时别只说好话）

1. **"结果与预期不符 → 重规划"值得做成显式信号**：CellVoyager 把它当主循环输入；MemOmics 侧只有被动的
   `looks_absurd()` / `deviation` 信号进 `debate_gate` → 可要求每个 Phase 收尾必产出 expectation vs actual 对照，作为 L2 一级触发源。
2. **MemOmics 缺语义读图环**：CellVoyager 每步用 VLM 读图并据此改计划；MemOmics 的 `vision_describe` 是纯本地管道（OCR + 亮度图 + 几何检测，**不调视觉模型**）——能判"图是不是空的"，读不出"这张 UMAP 说明了什么"。**真实代差项**。
3. `past_analyses`（分析摘要级）与 `debated_topics`（议题级）是同一防重复思路的两种粒度 → 可把 KB 里"已做过的分析"也做成显式清单。

## 3. 反向诚实提醒（用于回答"这类 agent 靠得住吗"）

CellVoyager 正文自我披露：COVID-19 焦亡分析**首版直接对细胞做 Mann–Whitney U（典型伪重复）**，是原作者指出后才补 pseudobulk 的 → 单角色"自我批判"抓不住统计单元错误；MemOmics 的多角色辩论**也不见得抓得住**（同模型），真正兜底仍是人类评审 + `statistical-design-review`。

## 4. 用法纪律（与 SKILL.md §五一致，别搞混）

| 场景 | 要求 |
|---|---|
| 对外汇报页 / 对比他人方案 | 用户明确要求"不要说缺点，说优点"→ 只列设计初衷/解法/工作量 |
| 被问"你自己的边界" | **必须给诚实边界**（No benchmark、形式校验≠科学校验、同模型偏差） |

⛔ 不要把「对比页只说优点」泛化成「审自己也不说缺点」。

## 5. 交付形态

- 用户要"逐项对比"时的落地形态：**对话内完整可读成品（Markdown 管道表格，抗截断）+ 主文件落盘 md**
  （用户的横向合读偏好：不能只回"已落盘，路径是 X"）。
- 机制对比/介绍类 deck：常要 **`.pptx` + `.html` 双版本**（见 `interactive-html-deliverables` §七）。
- 两根审查回路并排的 mermaid 图（单角色自省 vs 门控+对抗+落地）在完整交付版 md 里，可直接复用。