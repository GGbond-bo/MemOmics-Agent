# 9 篇科研 AI Agent 横向合读 · 事实底座（2026-10-11）

来源：`E:/文献/AI/agent/literature/` 下 9 个 PDF → 全文提取（84.6 万字符）→ 逐篇结构化提取
（所有数字回溯原文；原文未报告者标「原文未报告」；原文自相矛盾者并列照录）。
主合读成品：`results/<sid>/results/AI_agent_前沿工作解读.md`（228 行）。
知识库落点：`memomics/knowledge_base/ai_agent/`（12 条）。

> ⚠️ 与 `research-agent-landscape-2026.md` 是**两个不同批次**：那份是赛道全景（AlphaFold2/AI Scientist/
> AlphaEvolve/FutureHouse/Lila/BAISBench/Closing-the-Empirical-Loop…），本份是**结构化提取批**
> （Biomni/Co-Scientist/DeepRare/ChemGraph/BioMaster/Paper2Agent/CASSIA/ChemCrow/ScienceBuddy）。
> 只有 Biomni / Co-Scientist / ChemCrow 三篇重叠。

## 0. 一句话分野尺（本篇最有复用价值的一句）

> 这 9 篇不是"9 个更好的聊天机器人"，而是**在回答同一个问题的不同侧面：大模型怎么从"会聊天"变成"能真正做完科研"**。
> 其中 **只有 2 篇在做"新知识"**（Co-Scientist、ScienceBuddy），**其余 7 篇本质是"忠实执行 / 可靠复现"**。

## 1. 身份表

| # | 系统 | 出处 | 一句话定位 | 训练模型? |
|---|---|---|---|---|
| 1 | Biomni | Stanford 等 11 单位（预印本 2025） | 先映射领域**动作空间**，再用 CodeAct 自由组合 | ❌ Sonnet 3.7 |
| 2 | Co-Scientist | Google Cloud AI / DeepMind，*Nature* 655 (2026) | 「结构化科学思考引擎」，**Elo 自对弈锦标赛**演化假设 | ❌ Gemini 2.0 |
| 3 | DeepRare | 上海交大 / 新华医院 / 哈佛，*Nature* 651 (2026) | 罕见病鉴别诊断，**三层 MCP + 推理链可溯源** | ❌ DeepSeek-V3 |
| 4 | ChemGraph | Argonne 国家实验室，*Commun Chem* (2025) | LangGraph/ReAct 编排 ASE/xTB/MACE/DFT 工作流 | ❌ Qwen2.5-14B / GPT-4o |
| 5 | BioMaster | HKUST-GZ，*Bioinformatics* (2025) | Plan/Task/Debug/**Check** 四角色 + 双 RAG | ❌ GPT-4 / GPT-4o |
| 6 | Paper2Agent | Stanford，*Nature* (2026)，DOI 10.1038/s41586-026-11044-y | 把**任意论文**自动变成可交互 MCP agent | ❌ Sonnet 4 |
| 7 | CASSIA | 威斯康星，*Nat Commun* (2025)，DOI 10.1038/s41467-025-67084-x | 首个细胞注释多 agent：**质量分 + 共识分**制衡幻觉 | ❌ GPT-4o / Claude 3.5 / LLaMA3.2 |
| 8 | ChemCrow | EPFL / Rochester / FutureHouse / IBM，*Nat Mach Intell* 6:525 (2024)，DOI 10.1038/s42256-024-00832-8 | 本组**最早范式**：18 工具 + ReAct，接真实机器人 | ❌ GPT-4 |
| 9 | ScienceBuddy | PhAI Labs / 复旦等，arXiv:2609.17523v1 (2026) | **recursive-in-recursive 自改进**：内层进化 harness、外层训模型 | ✅ **唯一训练**（GRPO） |

## 2. 五谱系（研究思路，可直接复用作分型框架）

- **A 环境 / 动作空间派**：Biomni。洞察不是"换更强模型"，而是**先把领域动作空间系统化映射出来**——
  读 2,500 篇 bioRxiv（25 学科 × 100）抽 task/software/database 三类可执行洞见 → 150 工具 + 105 软件包 + 59 数据库；
  用 **code-as-action**（代码当通用动作接口，而非 function-calling 固定签名）；prompt-based 双 LLM 检索器。
  > 金句：通用性来自**动作空间覆盖度 + 以代码为接口**，不来自模型本身。
- **B 论文 / 工具即 agent**：Paper2Agent（MCP 三件套 tools/resources/prompts；**工具先验证后锁定**：
  用论文 tutorial 输出做 ground truth，数值容差 3% + 图像感知哈希 Hamming < 20，失败者剔除）+ ChemCrow（该路线起点，
  证明"通用 LLM + 工具外挂"走得通，且首接真实机器人 RoboRXN）。
  > 作者自陈：开放式任务上 benchmark 度量的是**忠实执行**，不是分析有效性。
- **C 领域专用系统**：DeepRare（三层 MCP：central host + 6 agent server + 异构数据源；self-reflective diagnosis；
  **reference link verification** 后处理剔无效 URL 抑制幻觉）· CASSIA（生成者/评估者分离、0–100 质量分、
  共识分 CS、75% 阈值触发精化、Annotation Boost）· ChemGraph（planner → executor(s) → aggregator；
  ASE calculator 抽象成可换后端，**多 agent 拆分让中小模型准确率翻倍**）。
- **D 长流程可靠性**：BioMaster。直指要害——**长链真正的敌人不是单步出错，而是累积误差与"假完成"**；
  Check Agent 每步校验输出文件（存在/非空/命名符合计划/格式一致）；消融证明**移除 Check，短任务影响小、长流程严重受损**；
  **Hi-C 完整预处理只有它跑通**（AutoBA 与 ChatGPT 均失败）。
- **E 自我改进**：ScienceBuddy（harness 可编辑 / 科学基础设施不可变解耦；内层成对评估 Δ>0 才接受；
  外层 GRPO 训模型 + 动态校准环境难度；42.2% → 73.3%）· Co-Scientist（**完全不训权重**：
  generate → debate → evolve + **meta-review 无梯度反馈回路**；随 test-time compute 缩放未见饱和）。

## 3. 评测：三档可信度分层

| 档 | 手段 | 代表数字 |
|---|---|---|
| 最硬：真实世界闭环 | 湿实验 / 机器人 / 临床样本 | Biomni B2M 克隆 → Sanger 完美比对；ChemCrow **RoboRXN 4/4 合成成功**（目标 369 nm / 实测 336 nm）；CASSIA 临床试验 NCT03398694 |
| 次硬：人类盲评 + rubric | 专家打分 / 医师对照 | Paper2Agent 两名独立专家、**评分者间一致性 96.7%**；DeepRare 10 名医师审 180 例 + 5 名 10 年以上经验医师对照 163 例 |
| 自动指标 | 准确率 / Recall@k / pass@k | CASSIA 三级分层准确率（按 Cell Ontology 树分类学距离）；DeepRare R@1 **57.18%**；ScienceBuddy pass@4 **48.3%→67.8%** |

公开基准：`LAB-Bench (DbQA/SeqQA/LitQA2/ProtocolQA)` · `HLE 生物医学` · `GPQA diamond` · `Bomni-Eval1` ·
`RareBench` · `GTEx/TS/HCL/MCA/Azimuth` · `1000 Genomes` · `4DN GM12878` · `10X PBMC` …
**自建基准是本组最大共性：9 篇里 8 篇都自建了**（Biomni 8 个真实基准含 CRISPR 18,939 候选基因；
Co-Scientist 203 目标；ChemGraph 13 任务 × 360 次独立评测；CASSIA 970 细胞类型；ScienceBuddy 895 任务）。

⚠️ 反例提醒：**Co-Scientist 全文未出现 LAB-Bench** —— 对比时不要假设"大家用同一 benchmark"。

**评测设计上的三个坑**：
1. LLM-as-judge 偏好"流畅"而非"正确"（ChemCrow 实证：EvaluatorGPT 偏好纯 GPT-4，专家偏好 ChemCrow）。
2. **只有 Paper2Agent 做了系统性对抗测试**（12 配置 repo-drift + 置换 paper–question 测越界拒答 **100%** + 硬编码扫描）——
   其余 8 篇无对等设计，这是"可靠 agent"与"demo"的分水岭。
3. 7/9 篇存在原文数字自相矛盾（见下节），集中在自建 benchmark 的规模统计。

## 4. 横向对比速览

| 维度 | Biomni | Co-Scientist | DeepRare | ChemGraph | BioMaster | Paper2Agent | CASSIA | ChemCrow | ScienceBuddy |
|---|---|---|---|---|---|---|---|---|---|
| 类型 | 通用 agent | 假设生成 | 领域诊断 | 领域工作流 | 流程工程 | 论文→agent | 领域注释 | 工具+ReAct | 自改进 |
| 开源 | ✅ 含 prompt | ❌ 不公开代码 | ✅ | ✅ | ✅ | ✅ | ✅ MIT | ✅ 12/18 工具 | 代码公开 |
| 反幻觉 | retriever + 执行 | Reflection 搜索校验 | **链接有效性校验** | — | **每步 Check** | **验证后锁定** | **质量分 + 共识分** | 安全硬门 | rubric 冻结 |
| 关键数字 | DbQA 74.4%（人 74.7%） | Elo 未见饱和 | R@1 57.18% | 多 agent GPT-4o **100%** | Hi-C 仅它跑通 | 300 题 **91.2%** | 完全正确 **+12–41%** | **4/4** 合成 | 42.2%→**73.3%** |
| 主要短板 | 未达专家级全科 | 代码不公开、样本小 | 未做湿实验 | 首版、小模型弱 | **未报百分比** | 部分 repo 无法 agent 化 | **无功效分析/未盲法** | judge 不可靠 | reflector 固定 |

## 5. 🔴 原文矛盾照录表（7/9 篇）——本批最有复用价值的一节

| 论文 | 矛盾处 |
|---|---|
| Biomni | 克隆基准题数 正文/图注 **10** vs Methods **20**；可穿戴温度文件 案例 **458** vs Methods **485**；动作发现文献量 "2,500 篇" vs 摘要 "tens of thousands" |
| ChemCrow | 工具数 正文 **18** vs Methods 枚举 **19**；工具分类 Fig.1b **5 类** vs Methods **3 类** |
| CASSIA | CS 评测 正文 **95** vs 图注 **n=100**；质量分评测 **500 / 530 / 586** 三口径；癌细胞检出 正文 72.5%/20% vs 图注 57–100%/0–40%；穿山甲 正文 **75.9%** vs 图注 ">85%"（矛盾）；Zenodo DOI 两个编号 |
| ScienceBuddy | §4.2 标题 "Two-Cycle" vs 正文/Fig.8 **three** cycles（k=0,1,2）；第 2 轮起点 正文 34.4% vs 图注序列无此值 |
| DeepRare | Fig.2 图注 MME 70.0% / RAMEDIS 72.6% vs 正文 78% |
| Paper2Agent | Scanpy 数据集数 正文先 **four** 后 **seven**，Methods 3+4=7 |
| BioMaster | 基座 正文 **GPT-4** vs 评测章节统一 **GPT-4o** |
| Co-Scientist / ChemGraph | 未发现硬矛盾（前者**代码不公开**，复现性受限；后者 Table 1/2 明细在提取文本中缺失） |

> 汇报口径（照抄）：这不是挑刺——**恰恰是"多源验证 + 不编造"的价值**。综述时这类数字必须并列照录，
> 否则会把自己的综述建立在错误的规模数字上。

## 6. 对本家（MemOmics）的 7 条启示

1. **每步 Check**（BioMaster）→ 强化 rail_review(post) 为「产物存在性 + 非空 + 命名一致性」硬校验。
2. **工具先验证后锁定**（Paper2Agent）→ 对应 skill 的 proven scripts + record_run 机制。
3. **输出带可核验引用 + 链接有效性后处理**（DeepRare）→ 对应 save_reference / evidence_write 的溯源要求。
4. **给结论配定量置信度**（CASSIA 质量分 + CS + 阈值）→ 比"有/无结论"更可用。
5. **多角色独立评审 + 裁判，且不微调即反馈**（Co-Scientist Meta-review）→ 与 debate_analysis 同构。
6. **诚实边界声明**（ScienceBuddy：reflector 固定 → 不宣称机制变强）。
7. **对抗测试应成为标配**（Paper2Agent 的 12 配置 + 越界拒答 + 硬编码探测）。

## 7. 两处「任务书标题 ≠ 原文标题」更正（交付时必须主动列出）

- **Paper2Agent**：任务书给《paper2Agent: Automatic generation of AI agents from research papers》，
  原文实际标题是 **_Reimagining research papers as interactive and reliable AI agents_**（Nature 2026）。
  第一作者 Jiacheng Miao（共同通讯），共同通讯 James Zou；代码 github.com/jmiao24/Paper2Agent；
  agent 地址 HF Spaces（alphagenome_agent / scanpy_mcp / tissue_mcp）。
- **arXiv 2609.17523v1**：任务书未给准确标题，原文为
  **_ScienceBuddy: Recursive-in-Recursive Self-Improvement for Interactive Scientific Agents_**（2026-09-15, cs.AI）；
  通讯 Zhenfei Yin / Yingcheng Wu / Ling Yang（PhAI Labs 等），代码 Gen-Verse/ScienceBuddy。

## 8. 数字底稿（逐字，可直接引用）

**Paper2Agent**：100 篇计算生物学论文 → **74 篇 agent 化 / 599 tools（593 通过验证）**；
AlphaGenome 22 tools / ~45 min / $14；Scanpy 7 tools / $13；
AlphaGenome tutorial **98.7 ± 1.3%**、novel **100 ± 0%**、开放式 **82.7 ± 2.4%**
（vs Claude+Repo 82.7 / 78.7 / 56.7%，**Biomni 37.3 / 56.0 / 72.2%**）；
大规模 300 题 **91.2 ± 1.6%**（P<0.0001）；非生物 42 题 **98.1 ± 0.8%**；数据/发现 100 题 **89.0 ± 3.1%**；
越界拒答 **100%**；查询成本 **$0.20 / 1.6 min** vs **$0.38 / 4.3 min**；
发现用例 GPR137（quantile 0.997；Spearman 0.613/0.630，FDR<0.05）、SORT1（0.99983，eQTL P=1.1×10⁻⁶⁵）。

**CASSIA**：**970 细胞类型**、5 数据集（GTEx/TS/HCL/MCA/Azimuth）；>500 质量注释；**2,670 次 marker 扫描**；
完全正确 **+12–41%**、组合正确 **+9–20%**；模型 0.92 / 0.88 / 0.82；混合群 90% / 80%；
RAG **+7–13%**；MOCA 0.53 vs 0.15；质量分阈值 75%（KW p=2.56×10⁻⁸）；Boost 纠错 **24/27（89%）**；
MOCA ~200 万细胞；**~30 s / 细胞类型 / 核**；**$0.02 / 注释**（GPT-4o）。

**ChemCrow**：18 工具（开源 **12**）、GPT-4（temp **0.1**）、ReAct；
**4 个真实合成成功**（DEET + 3 个硫脲催化剂）；发色团 目标 369 nm / 实测 336 nm / RMSE 37 nm；
专家 n=4、人工样本 56、EvaluatorGPT 14；**专家偏好 ChemCrow，LLM judge 偏好 GPT-4**。

**ScienceBuddy**：**224 工具 / 22 模块**；**895 任务 / 16 子主题**（LitQA2 96 + DbQA 511 + ProtocolQA 108 + GWAS 180，
来自 LAB-Bench + Biomni-Eval1）；Qwen3.5-4B 任务模型 / Qwen3.8-27B 辅助 / GPT-6 Astra 编辑；
测试准确率 **42.2% → 73.3%**；harness 验证 **31.1% → 51.1%（+20pp）**；pass@4 **48.3% → 67.8%（+19.5pp）**；RL ~2 小时。

**其余**：Co-Scientist 7 类 agent、2,300 已批准药物 × 34 癌型、203 目标 / 15 专家策展 / 11 盲评、
AML 初始 prompt <1h 专家时间 · 评审约 3h；DeepRare **>40 工具**（含 Exomiser 14.1.0）、
覆盖 **2,919 病 / 14 专科**、**9 数据集 / 6,401 例**、240 例人机一致性、180 例推理链专家评审、163 例医师对照；
ChemGraph 6 工具、13 任务 / **360 次独立评测**、LLM 开销 <1 min/实例；
Biomni 150 工具 + 105 软件包 + 59 库、2,500 篇文献、DbQA 315 题 / SeqQA 12.5% / HLE 52 题；
BioMaster 4 角色 + 双 RAG、6 类流程 / 20 个 experiment（**原文未报告百分比**）。