# 批量 AI/科研智能体文献 → 独立知识库域 + 横向合读（2026-10-11 实测，9 篇一次跑通）

> 配套 SKILL.md **模式 I**。本文件是这次任务的**事实底稿**（身份 / 逐字数字 / 谱系 / benchmark /
> 评测范式 / 原文矛盾表），再次遇到这 9 篇或同类批量任务时**直接取用，不必重读全文**。
> 源目录：`E:/文献/AI/agent/literature/`（用户放 AI agent 类文献的固定位置）。

---

## 1. 任务形态与双交付

用户一次丢 **9 个 PDF 路径**，要求：「整理到知识库，**创建 AI 的单独分类**，主要看看他们的**研究思路**、
解决什么问题、工作量与内容、怎么测试、用什么 **benchmark**，**先整理到知识库，然后帮我解读**」。

双交付 = ① 逐篇入知识库（结构化 YAML）② 横向合读解读（给人读的 Markdown）。
两条**同时**要，⛔ 不要只做入库或只做解读。

**规模实测**：9 篇 → 全文提取 **84.6 万字符**（落 `data/lit_text/*.txt`）→ 逐篇结构化提取 →
知识库 **12 条**（9 篇 + 3 条横向综合）→ 解读稿 **228 行 / 20,900 B**。

---

## 2. 入库域的决策（本模式最容易被做错的一步）

这 9 篇**没有物种/组织维度**（它们是方法/系统论文，不是组学数据论文）。塞进
`Homo_sapiens/<组织>/<方向>/...` 五级目录会让目录语义失效、也检索不出来。

⇒ 新建独立域 `memomics/knowledge_base/ai_agent/`，**子类固定五档**：

```
memomics/knowledge_base/ai_agent/
├── 00_INDEX.md        收录清单 + 子类约定 + 使用建议 + 同期交付物指针
├── frameworks/    (7) 系统与框架架构
├── agent_design/  (2) 设计范式与自改进
├── benchmarks/    (1) 基准与数据集      ← 横向综合
├── evaluation/    (1) 评测方法          ← 横向综合
└── overview/      (1) 横向综合（谱系）
```

**每条 YAML 固定 11 字段**：定位 / 研究思路 / 解决的问题 / 工作量 / 测试方式 / benchmark 细节 /
关键数字 / 局限 / **原文矛盾标注** / **可复用点** / 元信息（DOI·代码·许可），并带 `evidence` 溯源字段。

⚠️ 入库通道：`save_knowledge(domain="ai", direction="<子类>", ...)`。若工具报 domain 非法，
说明**运行中的 server 还持旧模块**（改了代码但进程没重启）——处置见
`platform-execution-pitfalls`「打了补丁的模块 ≠ 在跑的进程」。

---

## 3. 三条横向综合条目（批级入库的真增量形状）

逐篇条目只回答「这篇是什么」；批级价值全在横向格子上。三条条目的可复用形状：

| 条目 | 内容骨架 |
|---|---|
| `overview/ai_agent_research_paradigms_9papers` | **研究思路谱系**：N 篇归到 3–5 条谱系 + 3 条设计公理 + 「发现 vs 执行」分野句 |
| `benchmarks/ai_benchmark_inventory_9papers` | 公开基准复用表 + 9 篇自建基准表 + 对抗测试 + 湿实验 + **选型建议** |
| `evaluation/ai_agent_evaluation_paradigms_9papers` | 评测范式卡（专家盲评 rubric / LLM-as-judge / Elo 自对弈 / 分层准确率 / 消融 / 真实闭环）+ 坑 + 检查清单 |

每条末尾写「**可复用点**」与「**原文矛盾**」两小节——用户引用规模数字前会先看这两节。

---

## 4. 九篇身份与判别列

| # | 系统 | 出处（DOI） | 一句话定位 | 训练模型？ | 开源？ |
|---|---|---|---|---|---|
| 1 | **Biomni** | Stanford 等 11 单位，预印本 2025 | 通用生物医学 agent：150 工具 + 105 软件包 + 59 库 + CodeAct | ❌ Sonnet 3.7 | ✅ 全开源 + prompt |
| 2 | **Co-Scientist** | *Nature* 655 (2026)，10.1038/s41586-026-10644-y | 7 类 agent，**Elo 自对弈锦标赛**演化新假设 | ❌（test-time scaling） | ❌ 代码不公开 |
| 3 | **DeepRare** | *Nature* 651 (2026)，10.1038/s41586-025-10097-9 | 罕见病诊断：三层 MCP + 可溯源推理链 | ❌ DeepSeek-V3 | ✅ |
| 4 | **ChemGraph** | *Commun Chem* (2025)，10.1038/s42004-025-01776-9 | LangGraph/ReAct 编排 ASE/xTB/MACE/DFT | ❌ Qwen2.5-14B/GPT-4o | ✅ |
| 5 | **BioMaster** | *Bioinformatics* (2025)，10.1101/2025.01.23.634608 | Plan/Task/Debug/**Check** 四角色 + 双 RAG | ❌ GPT-4/4o | ✅ |
| 6 | **Paper2Agent** | *Nature* (2026)，10.1038/s41586-026-11044-y | 论文→MCP agent（tools+resources+prompts） | ❌ Sonnet 4 | ✅ + HF Spaces |
| 7 | **CASSIA** | *Nat Commun* (2025)，10.1038/s41467-025-67084-x | 细胞注释多 agent：**质量分 + 共识分 CS** | ❌ GPT-4o/Claude3.5 | ✅ MIT |
| 8 | **ChemCrow** | *Nat Mach Intell* 6:525 (2024)，10.1038/s42256-024-00832-8 | 18 工具 + ReAct 的**最早范式**，接 RoboRXN | ❌ GPT-4 | ✅ 12/18 工具 |
| 9 | **ScienceBuddy** | arXiv:2609.17523v1 (2026) | **recursive-in-recursive**：内层进化 harness、外层 GRPO | ✅ **唯一训练** | 代码公开 |

**判别列是重点**：通读后数一遍「是否训模型 / 是否产出新假设」就得到分野句（见 §5）。

---

## 5. 五条研究思路谱系（模式 I 的主体，可复用分型）

- **A 环境/动作空间派** —— Biomni：通用性来自**动作空间覆盖度 + 以代码为通用接口**，不来自模型本身。
  动作发现智能体读 **2,500 篇** bioRxiv（25 学科 × 100 篇）→ 150 工具 + 105 软件包 + 59 库；CodeAct；
  prompt-based 双 LLM 检索器（一个选工具、一个主推理）。
- **B 论文/代码即 agent 载体** —— Paper2Agent（**工具先验证后锁定**：tutorial 输出做 ground truth，
  数值容差 3% + 图像感知哈希 Hamming < 20，反复失败剔除；作者自陈 benchmark 度量的是**忠实执行**，
  不是分析有效性）；ChemCrow 是这条路线的**起点**（2024，18 工具 + ReAct，接真实机器人）。
- **C 领域专用** —— DeepRare（self-reflective diagnosis + reference link verification 后处理剔除无效 URL）；
  CASSIA（生成者/评估者分离、0–100 质量分、共识分 CS、75% 阈值触发精化）；ChemGraph（planner→executor(s)
  →aggregator，**多 agent 拆分让中小模型准确率翻倍**）。
- **D 防误差传播** —— BioMaster：长链真正的敌人是**累积误差与「假完成」**；Check Agent 每步校验
  （存在/非空/命名符合计划/格式一致）；消融证明**移除 Check Agent 长流程严重受损**；
  **Hi-C 完整预处理只有它跑通**（AutoBA 与 ChatGPT 均失败）。
- **E 自我改进（模型与流程双轨）** —— ScienceBuddy：可编辑 harness（instructions/skills/context）与
  不可变基础设施解耦；内层**有界编辑 + 同 seed/同预算/冻结 rubric 成对评估，Δ>0 才接受**；
  外层 GRPO 训模型 + 动态校准环境难度。Co-Scientist 是**不训权重**的另一条：
  generate → debate → evolve → **Meta-review（无梯度反馈回路）**，主张随 test-time compute 持续上升未见饱和。

**分野句（直接复用）**：*这 9 篇不是「9 个更好的聊天机器人」，而是在回答同一个问题：大模型怎么从
「会聊天」变成「能真正做完科研」。其中只有 2 篇在做**新知识**（Co-Scientist、ScienceBuddy），
其余 7 篇本质是**忠实执行 / 可靠复现**。*

**三条设计公理**：① 不训练也能强 → 先把「动作/工具」做对（8/9 不训）；② **反幻觉 = 结构，而非说辞**；
③ 可溯源/可审计是刚需（回答「凭什么信它」）。

---

## 6. 工作量与规模对照（跨家归一表，逐字数字）

| 系统 | 工具/模块 | 数据/语料 | 评测规模 | 成本/耗时 |
|---|---|---|---|---|
| Biomni | 150 工具 + 105 软件 + 59 库 | 2,500 篇（25×100） | DbQA 315 题 / SeqQA 12.5% / HLE 52 题 + 8 自建 | — |
| Co-Scientist | 7 类 agent | 2,300 已批准药物 × 34 癌型 | 203 目标 / 15 策展 / 11 盲评 | AML prompt <1h 专家时间 |
| DeepRare | >40 工具 | 2,919 病 / 14 专科；9 数据集 6,401 例 | 6,401 例 + 240 人机一致 + 180 推理链 + 163 医师对照 | 5 阶段 Web 应用 |
| ChemGraph | 6 工具 | 13 任务 | 360 次独立评测 | LLM <1 min/实例 |
| BioMaster | 4 角色 + 双 RAG | 6 类流程 / 20 experiment | 20（**原文未报告百分比**） | 48 核+8GB / i9+94GB |
| Paper2Agent | 5 类子 agent | 100 篇 + 26 + 10 | 74 篇 agent 化 / 599 工具（593 通过） | 单篇 ~45 min · **US$14**；查询 $0.20/1.6 min |
| CASSIA | 5 核心 + 4 可选 | 970 细胞类型；MOCA ~200 万细胞 | >500 质量分 / 2,670 marker 扫描 | ~30 s/细胞类型/核 · **$0.02/注释** |
| ChemCrow | 18 工具 | — | 14 use cases；人类 n=56 / EvaluatorGPT n=14 | 真实机器人合成 |
| ScienceBuddy | 224 工具 / 22 模块 | 895 任务 / 16 子主题 | 288 段对话 / 24 次 harness 更新 | RL ~2 小时 |

**三条读表结论**：① **工具数量 ≠ 质量**（6 工具的 ChemGraph 靠多 agent 拆分把 GPT-4o 拉到 100%）；
② **成本已低到可落地**（$14/篇、$0.02/注释——这是 2025–2026 相比早期 agent 工作的最大变化）；
③ **开源程度差别极大**（仅 Co-Scientist 代码完全不公开，只给伪代码与 prompt）。

---

## 7. Benchmark 清单（用户明确问的部分）

**公开基准（复用率高）**：`LAB-Bench (DbQA/SeqQA/LitQA2/ProtocolQA)` · `HLE 生物医学` ·
`GPQA diamond` · `Biomni-Eval1` · `RareBench (MME/LIRICAL/RAMEDIS/HMS)` · `MyGene2` · `DDD` ·
`MIMIC-IV-Rare` · `GTEx / Tabula Sapiens / HCL / MCA / Azimuth` · `1000 Genomes` · `4DN GM12878` ·
`10X PBMC` · `Open Targets / DepMap / CellxGene`

**自建基准 —— 9 篇里 8 篇都自建，本组最大共性**：

| 论文 | 自建基准 | 规模 |
|---|---|---|
| Biomni | 8 个真实世界基准 | 含 CRISPR 筛选 18,939 候选基因 |
| Co-Scientist | 203 目标 / 15 策展 / 11 盲评 | Elo + novelty/impact |
| Paper2Agent | AlphaGenome 三档 + 大规模三语料 | 15/15/30/300/100/42 |
| ChemGraph | 13 任务 | 360 次独立评测 |
| ChemCrow | 14 use cases | 人工 n=56 |
| DeepRare | RareBench 体系 + 2 自建中心 | 6,401 例 |
| CASSIA | 5 数据集 + 专门场景 | 970 细胞类型 |
| ScienceBuddy | 895 任务 | 16 子主题 |

⚠️ **Co-Scientist 全文未出现 LAB-Bench**（虽生物医学 agent 普遍用它）——对比时不要假设「同一 benchmark」。

---

## 8. 评测范式三档 + 三个坑（实证）

**第一档（最硬）真实世界闭环**：Biomni B2M guide RNA → 克隆 → miniprep → **Sanger 完美比对**；
ChemCrow **RoboRXN 4/4 合成成功** + 新发色团（目标 369 nm / 实测 336 nm）；
Co-Scientist AML IC50 + Chou-Talalay/HSA/Bliss（n=3）+ 肝类器官；CASSIA **NCT03398694** 脑转移瘤。

**第二档 专家盲评 + rubric**：Paper2Agent 两名独立专家，**评分者间一致性 96.7%**；
DeepRare **10 名副高/主任医师**审 180 例 + **5 名 10 年以上经验医师**对照 163 例；
Co-Scientist 7 名专家策展 15 个高难目标 + 各自 best-guess 同场竞技；Biomni 克隆盲评 1–5 分。

**第三档 自动指标**：DbQA/SeqQA/HLE；Recall@1/@3/@5；CASSIA **三级分层准确率**
（完全 1 / 部分 0.5 / 错 0，按 Cell Ontology 树距离）；ScienceBuddy validation / first-response /
single-attempt acc / **pass@4**。

**三个坑（写进任何 agent 评测设计）**：
1. 🔴 **LLM-as-judge 偏好「流畅」而非「正确」**（ChemCrow 实证）：**EvaluatorGPT 倾向纯 GPT-4**
   （回答更流畅完整），而**专家评估偏向 ChemCrow**（化学事实性/推理更准）⇒ 事实性关键领域不可只靠 LLM judge。
2. 🔴 **只有 1 篇做了系统性对抗测试**：Paper2Agent 12 个 repo-drift 配置（缺失依赖/损坏路径/拼写错误/
   弃用 API）+ 置换 paper–question 测越界拒答（**正确拒答率 100%**）+ 硬编码/shortcut 扫描；
   其余 8 篇**无对等设计** ⇒ 这是「可靠 agent」与「demo」的分水岭。
3. 🔴 **7/9 篇存在原文数字自相矛盾**，集中在**自建 benchmark 的规模统计**上（见 §9）。

---

## 9. 原文矛盾汇总表（照录，不圆场）

| 论文 | 矛盾处 |
|---|---|
| Biomni | 克隆基准题数 正文/图注 **10** vs Methods **20**；可穿戴温度文件 **458** vs Methods **485**；动作发现文献量「2,500 篇」vs 摘要「tens of thousands」 |
| ChemCrow | 工具数 正文 **18** vs Methods 枚举 **19**；工具分类 Fig.1b **5 类** vs Methods **3 类** |
| CASSIA | CS 评测 正文 **95** vs 图注 **n=100**；质量分评测 **500/530/586** 三口径；癌细胞检出 正文 72.5%/20% vs 图注 57–100%/0–40%；穿山甲 正文 **75.9%** vs 图注「>85%」；Zenodo DOI 两个编号 |
| ScienceBuddy | §4.2 标题「Two-Cycle」vs 正文/图注 **three** cycles；第 2 轮起点 正文 34.4% vs 图注无此值 |
| DeepRare | Fig.2 图注 MME **70.0%** / RAMEDIS 72.6% vs 正文 **78%**；数据集计数摘要「nine」vs 后文「eight」 |
| Paper2Agent | Scanpy 数据集数量 正文先 **four** 后 **seven**（Methods 3+4=7） |
| BioMaster | 基座 正文 **GPT-4** vs 评测章节统一 **GPT-4o** |
| Co-Scientist / ChemGraph | 未发现硬矛盾（Co-Scientist 代码不公开 ⇒ 复现性受限） |

> 正文口径：**这不是挑刺**——所以「多源验证 + 不编造」的价值就在这。做综述时这类数字必须**并列照录**，
> 否则会把自己的综述建立在错误的规模数字上。**最隐蔽的一类是「正文 vs 图注」**（同一指标三源逐处对照）。

---

## 10. 对 MemOmics 的 7 条可落地启示（本次产出，可直接复用）

1. **每步 Check**（BioMaster）→ 把 rail_review(post) 强化为「产物存在性 + 非空 + 命名一致性」硬校验；
2. **工具先验证后锁定**（Paper2Agent）→ 对应 skill 的 proven scripts + `record_run` 机制；
3. **输出带可核验引用 + 链接有效性后处理**（DeepRare reference link verification）→ 对应 `save_reference` / `evidence_write`；
4. **给结论配定量置信度**（CASSIA 质量分 + CS + 阈值）→ 比「有/无结论」更可用；
5. **多角色独立评审 + 裁判，不微调即反馈**（Co-Scientist Meta-review）→ 与 `debate_analysis` 同构；
6. **诚实边界声明**（ScienceBuddy 承认 reflector 固定）→ 不宣称机制变强；
7. **对抗测试应成为标配**（12 配置 + 越界拒答 + 硬编码探测）。

---

## 11. 路径与复现

| 产出 | 路径 |
|---|---|
| 合读解读（228 行 / 20,900 B） | `results/<sid>/results/AI_agent_前沿工作解读.md` |
| 知识库域 + 索引 | `memomics/knowledge_base/ai_agent/00_INDEX.md` |
| 逐篇结构化摘要 | `results/<sid>/data/AI摘要_*.md`、`Biomni_结构化摘要.md` |
| 全文纯文本（84.6 万字符） | `results/<sid>/data/lit_text/*.txt` |

**检索已验证**：`search_knowledge("AI agent 科研智能体 benchmark 评测")` →
命中 `ai_agent/frameworks/biomni_general_biomedical_agent.yaml` 排第一（score 180.95，total 136 条）。
入库后**务必跑一次检索验证**——索引不到 = 分类没生效。