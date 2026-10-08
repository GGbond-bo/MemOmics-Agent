# 模式 C9 — 深度卡 10 字段 schema + 「薄卡 → 深度卡升级」变体

来源：2026-10-07 会话（n=4,5,6,7,8 五篇「科研 AI agent」论文精读，把竞品卡从薄卡升级为深度卡）。

## 1. 任务变体：薄卡 → 深度卡升级

- 用户已有**一批薄卡**（旧 schema，字段少/信息浅），要求「精读全文，把竞品卡从薄卡升级为深度卡」。
- 输入形态：**不一定给 `cards_source.json` manifest**。本次只给了论文编号 `n = 4,5,6,7,8`，
  全文在 `results/<sid>/data/text/PMC*.txt`；调用方**只指定编号**，文件靠自行定位。
- 输出形态：**「只输出我要的 JSON 字段」**——严格只给 JSON 对象（`{"<n>": {…}}`），
  **不加前言、不加字段说明、不加未要求的额外字段**。要总结等用户问再加。
  （与既有偏好一致：解说类交付压到核心，只给被点名要的东西。）

## 2. 深度卡 10 字段 schema（本次用户认的形状）

| 字段 | 要求 |
|---|---|
| `architecture` | **400–800 中文字**。必含：**模块名 / agent 角色名 / 工具名 / 超参数 / 失败模式 / 通信机制（黑板 or 消息传递）/ 记忆机制 / 人在回路位置**。只报「多 agent」不报模块名=不合格 |
| `inputs` | 输入数据类型、必填项、可选增强（外部库/协议） |
| `outputs` | 交付物清单（脚本/模型/报告/文件格式） |
| `models` | **各 agent ↔ 模型的映射**、有无微调、嵌入模型、成本口径（$/M token、€/运行） |
| `benchmark` | 逐字数字 + 口径（独立测试集 / best-of-N / 均值±SEM） |
| `validation` | 数据来源、**是否有湿实验/盲评/用户研究/消融**；作者自陈局限与「我读出的未声明局限」**分开写** |
| `key_claim` | 一句话主张 |
| `novelty` | 相对同类的机制差异点 |
| `limitations` | **两段**：①作者自陈 ②我读出的未声明局限（⛔ 不可混为一段） |
| `evidence_quote` | ≤200 字符、**连续逐字**原文片段，交付前 `t.count(q) == 1` 机械校验 |

## 3. 执行配方（本次实测）

1. 定位全文文件（`results/<sid>/data/text/PMC*.txt`），`wc -c` 看体积（本次 53–126KB，`wc -l` 只显示 5 行 → 单行长文本）。
2. **逐篇 `execute_python` 按字符区间 `print(t[a:b])` 读**（每段 ~11–13k 字符，因 stdout 约 10k 上限而分段）。
   本次 5 篇共约 29 次 tool call（每篇 5–7 段），**一篇一调用**（可接受，未撞迭代上限）。
3. 落卡前对每条 `evidence_quote` 跑 `t.count(q) == 1`（原文唯一可查）。本次 5 条全部 =1 才交卡。
4. **输出长度是隐形约束**：本次 5 张**富卡**（architecture 各 400–800 字）单条回复放不下，
   被输出长度上限截断后接续输出。见 SKILL.md C6。对策：先落盘 `*.json` 再分段贴，或压缩 architecture 到 ~400 字。

## 4. 本次 4 篇新竞品事实底稿（逐字已核）

> BioMaster（n=5）已有独立知识库 `biomaster-knowledge-bank.md`，此处只补本次新抽的数字。

| n | 名称 | 出处 | 架构一句话 | 关键数字（逐字） | 模型 | 成本 |
|---|---|---|---|---|---|---|
| 4 | **Agentomics** | Bioinformatics 2026, `10.1093/bioinformatics/btag250`, PMC13340167 | 七步**固定流水线**（Data Exploration→…→Prediction Exploration）+ 每步一个**独立干净上下文** Agent + Experiment Design 总结器；6 工具；Docker 只读挂载；测试集对 Agent 永久隐藏；指标由确定性代码算 | 20 数据集；对人工 leaderboard 平均分位 Protein 75.92±8.00 / Drug 34.29±5.33 / Reg 60.15±10.94（超 AIDE/MLAgentBench/STELLA/Biomni/Zero-Shot）；11/20 超人类 SoTA（Protein 6/6、Drug 2/9、Reg 4/5）；val-test corr 中位 0.964；成功率 100%（60 runs） | GPT-5.1-Codex-Max（统一骨干） | 9.4±5.0 USD/8h；0.45±0.09 USD/iteration；~30min/iteration |
| 6 | **ChemGraph** | Communications Chemistry 2026, `10.1038/s42004-025-01776-9`, PMC12824235 | **LangGraph + ReAct**；单 agent（工具循环 + 常规/结构化双出口）与多 agent（planner / executor / aggregator + loop controller）；6 工具；AtomsData 容器；ASE calculator 接 xTB/MACE/DFT | 自研 13 实验 360 实例；多 agent 显著提升：react2enthalpy GPT-4o-mini 40%→87%、Claude 67%→87%（超单 agent GPT-4o 的 83%）；react2gibbs 49%→87% / 69%→93%；GPT-4o 多 agent=100% | GPT-4o / GPT-4o-mini / Claude-3.5-haiku / Qwen-2.5-14B（开源，ALCF Globus Compute） | LLM 额外开销 <1 min/实例 |
| 7 | **CASSIA** | Nature Communications 2025, `10.1038/s41467-025-67084-x`, PMC12796229 | **五 agent 链**（Annotator→Validator→Formatting→Quality Scoring→Reporter）+ 可选 Boost/Subclustering/CS/RAG；零样本 CoT + 自验证循环（验证最多 3 轮）；选择性记忆访问 | 970 细胞类型，完全正确注释比次优 +12–41%；质量分 0–100（阈值 75%，Kruskal-Wallis p=2.56e-8）；Annotation Boost 修正 24/27(89%)；癌症识别 72.5% vs GPTCelltype 20%（加 prompt 后 88–100%）；RAG +7–13% | GPT-4o（默认）/ Claude 3.5 Sonnet（最准 0.92）/ LLaMA-3.2-90B（开源 0.82） | GPT-4o ~$0.02/注释；Claude $0.03；LLaMA $0.003 |
| 8 | **SPARK** | Nature Medicine 2026, `10.1038/s41591-026-04357-y`, PMC13278948 | **crewAI** 上四模块（idea generation / refinement / coding / verification）串行，每步输出即下步输入；8 个 agent（IGA / Idea-Review / IDDA / Refinement / ICA / Code-Review / List-Formatting / Idea-Formulation）；**agentic memory 全程关闭**（自陈无益且贵）；工具实现在管线代码里（extra-agentic） | 18 队列 5 癌 >5400 患者；500 唯一想法（单轮×4，121–128/轮）；99.2% 编译成代码；去冗余后 1,115 参数；AUROC MSI 0.933 / BRCA 亚型 0.898 / ER 0.863 / HPV 0.828（HER2 最高 0.725；LUSC PD-L1 最高 0.719）；>70% 侵袭性特征属晚期 | 分工：生成=o1(full)，审/查重=o3-mini，编码=Claude Sonnet 3.5；开源替代 gpt-oss-120b/20b、DeepSeekR1-Llama3-70b、Qwen3-32b、Meditron-70b、MedGemma-27b、BioMistral-7b | 开发+实现总 ~4,000 €（o1: 15€/M in, 60€/M out） |

BioMaster（n=5）本次新抽的数字（补进 `biomaster-knowledge-bank.md` 可沿用）：
49 任务成功 47（95.9%）vs SingleAgent 24(49.0%)/AutoBA 13(26.5%)/ChatGPT 12(24.5%)；
多评分器 ICC(3,5)=0.70–0.92；默认 o1-2024-12-17；LangChain + Chroma + mem0 式摘要记忆；
Hi-CRep SCC>0.99、loop 图 Pearson r=1.00/Spearman 0.999、APA=2.31、ANOSIM R 0.405 vs 0.423。

## 5. 五条 evidence_quote（本次已 count==1 校验）

- n=4：`Each step is implemented by a separate LLM Agent with a clean context that is prompted with`
- n=5：`It comprises four specialized agents—plan, task, debug, and check—that operate in an iterative loop`
- n=6：`the multi-agent ChemGraph system comprises three main LLM agents: a planner agent, executor agent(s), and an aggregator agent`
- n=7：`CASSIA is a multi-agent LLM framework consisting of five interconnected LLMs for annotation, validation, formatting, quality scoring, and reporting`
- n=8：`We developed SPARK as a modular agentic workflow, where the output of each step serves as the input for subsequent steps`

## 6. 范式定位（可并入 F5 五范式矩阵）

本次 5 篇的失败模式正交轴：
**Agentomics** = 防「Agent 自报指标 / 不可复用代码」（验证闸门 + 测试集隔离）；
**BioMaster** = 防「长流程跑不完」（每步校验 + debug agent）；
**ChemGraph** = 防「上下文拥挤导致工具调用/结果抽取出错」（多 agent 分解 + 小模型）；
**CASSIA** = 防「LLM 注释幻觉」（自验证 + 质量分 + 共识不确定度）；
**SPARK** = 防「病理学假设无法规模化生成与可解释实现」（想法生成/精修/编码/验证闭环）。