# 模式 C11 小批深读卡事实底稿 — n=1,2,14,15,16,17（2026-10-08）

任务：精读 6 篇「科研 AI agent」论文全文，把 `data/cards.json` 的薄卡升级为深读卡（10 中文字段），
结果**写盘**到 `data/deep_cards_round2_t0.json`（「不要只回传内容」）。
路径：`E:/MemOmics-Agent/results/memomics-be17649b/data/text/<PMCID>.txt`（均单行长文本）。

> ⚠️ 本轮**未完成落盘**（迭代耗在读取+起草上，见 SKILL C11-d）。以下是已完成的事实底稿，可直接续用。

## 新增工具坑（本轮各实测一次）

1. **`execute_python` 用 Windows 原生路径**：在 MSYS bash 里 `E:/…` 有效，但 kernel 里的 Python 是
   Windows 原生 —— 传 `/e/MemOmics-Agent/...` 会 `FileNotFoundError`。**一律写 `E:/…` 原生盘符路径**
   （与「工具陷阱」表里 `execute_python 的 /tmp ≠ bash 的 /tmp` 同源：kernel 不认 MSYS 虚拟路径）。
2. **单篇正文远超 stdout 上限**：`execute_python` 的 stdout 约 10000 字符 → 每篇按 ≤9000 字符切片
   `print(t[a:b])` 逐段读；6 篇合计 ~446KB ≈ 50+ 次 print。**这是本类任务的头号预算黑洞**（→ C11-d）。

## 已校验的 6 条逐字 evidence_quote（`q in t` 全 True）

| n | PMCID | evidence_quote |
|---|---|---|
| 1 | PMC13346116 | `By integrating literature search agents with data analysis agents, Robin can generate hypotheses, propose experiments, interpret experimental results and generate updated hypotheses` |
| 2 | PMC13573717 | `The system autonomously designed and executed three psychological studies on visual working memory, mental rotation, and imagery vividness, executed online data collection with 288 participants, developed analysis pipelines through 8h+ continuous coding sessions, and produced completed manuscripts.` |
| 14 | PMC12954778 | `By merging verified data, interpretable models, human-inspired reasoning, and standardized automation, the community can move from knowledge accumulation to autonomous scientific discovery` |
| 15 | PMC12667065 | `Humans remain central: researchers set objectives and priors, approve high-impact actions, and adjudicate new chemical insights.` |
| 16 | PMC12647001 | `It currently lacks rigorous, quantitative empirical validation comparing its performance (e.g., success rates, efficiency) against traditional data discovery methods.` |
| 17 | PMC13369662 | `PGxAI-Recommender achieved the highest average expert score (mean 9.0), compared to baseline models with mean scores ranging from 6.2 to 7.8` |

被否决的 n=2 候选（U+2010 连字符导致 MISS，见 SKILL C11-e）：
`each agent functions as an autonomous entity … domain‐specific reasoning …`、
`this is the first demonstration of autonomous, end‑to‑end experimental research with human participants.`

## 事实底稿（关键数字，均逐字来自正文）

### n=1 · Robin (Nature 2026, 10.1038/s41586-026-10652-y) — 假设生成 / lab-in-the-loop
- 架构：Jupyter notebook + Aviary 框架。Crow（简洁检索）/ Falcon（深度检索）基于 PaperQA2；
  Finch（Jupyter 原生、ReAct、仅 `edit_cell` + `submit_answer` 两工具、跑 `BixBench-env:v1.0` Docker）。
  8 条 Finch 轨迹 + meta-analysis 共识；LLM judge pairwise + Bradley–Terry–Luce 排序（>25 假设取 300 对）。
- models：o4-mini（合成文献/假设）；Claude 3.7 Sonnet（judge）；Gemini 2.5 Pro Preview（生成 judge prompt）。
- benchmark：Finch 在 BixBench 药物发现子集 **170 题 22.8±1.7%** vs 裸 Claude 3.7 Sonnet **1.6±1.2%**（n=3）；
  统计学子集 47.9±1.5% / 生信子集 15.3±2.0%；rubric 依从 RNA-seq 86±0%、flow cytometry 100±0%。
  成本 Crow $0.0963 / Falcon $0.2142（n=52），典型 run $10.76；551 篇文献 30 min vs 人类 294 h（~200×）。
  消融：Falcon 或 Crow+Falcon 消融→幻觉引用↑（o4-mini 44.5±6.37%，n=15）；judge↔专家 top10 重合 7.25/10，judge 一致性 88% vs 人 61%。
- validation：真实湿实验 ARPE-19 + 老年供体 RPE-SC；ripasudil 吞噬 ↑1.89×（人分析 1.75×）；ABCA1 ↑3×（adj P=2.13×10⁻⁸³）；
  对照 OpenAI Deep Research 17 候选无一命中且未提 ROCK 机制。
- 作者自陈局限：不出可执行 protocol；Finch 依赖专家 prompt engineering；依赖 2025 初前沿 LLM。

### n=2 · Closing the Empirical Loop (Advanced Science 2026, 10.1002/advs.76675) — 端到端自动化
- 架构：层级多 agent，>50 agents；master agent → 二级 orchestrator（method/data analysis/visuals/manuscript）→ specialist
  （coding/troubleshooting/review/inspection/archivist/pre-registration/power analysis/LaTeX/Word/document/caption）。
  九段流水线（hypothesis→protocol(OSF 预注册)→implementation→analysis→re-evaluation→visualization→manuscript→'peer' review→document）。
  四认知算子 abstraction/metacognition/decomposition/autonomy；d-RAG 动态记忆 + archivist 多级 search engine；Mixture of Agents；Aider 式代码编辑。
- models：Claude 4 Sonnet、o3-mini、o1、Grok-3、Pixtral Large、Gemini 2.5 Pro（全公开，无私有微调）。
- benchmark：无标准 benchmark；~17 h/研究、32.5M tokens、~$114/项目（不含 ~$4,500 被试费）；分析 agent 连续 8h32m、7696 行代码、72 循环。
- validation：d-RAG 消融（最新年份 2019 vs 2025、幻觉引用 6 vs 0）；去 review agent 四阶段各 3 次 1 次全失；
  同研究重跑 5 次同结论；288 名真实被试（Prolific+Pavlovia，Bellberry HREC EC00455）；专家结构化评审。
- 🔴 **`limitations` 截断恢复（C10 曾记为 `"作者自陈：物理能"` 8 字）**：完整作者自陈见 Discussion §4.2 ——
  ①实验实现是根本瓶颈（物理能力受限于已有工具/接口的在线实验）②并非不会出错、仍受益于人工监督；
  ③可视化偶有图形瑕疵（轴标签重叠/错位/轴范围）且难自主检测；④长链数千步跨 12h，推理模型长链退化；
  ⑤对早期阶段准确性敏感（anchoring 偏置，错误前提难逆转）；⑥训练语料偏置（幻觉引用，用引用核验缓解）；
  ⑦架构非最优、不声称排他/优越；⑧缺验证自主科研质量的多维基准；⑨发表受期刊 GenAI 政策所限。
  另 §3.2 专家负面项：理论误述与过度外推、方法学断言不一致、统计遗漏、呈现问题、内部矛盾。

### n=14 · Digital materials ecosystem (Chem Sci 2026, 10.1039/d5sc09229a) — 综述与观点
- 架构：Perspective，五层生态（数据库 / 物理模型 / 机器智能 / LLM-based AI agent / 闭环自动化实验）。
  agent 实例：DIVE（三步式图解抽取）、Eunomia（全文→ML-ready 数据集）、Odobesku（多 agent 多模态抽取）、DigHyd（设计-预测-优化）；
  平台 DigCat/DigMat/DigBat（原 DDSE：~3000 实验材料/25996 电导测量/863 计算条目）。
- models：本 Perspective 未指定统一 LLM；盘点对象 DIVE/Eunomia/DigHyd 均 LLM 驱动但未点名版本。
- benchmark：无量化评测（观点文）；转述 DigHyd ML 回归 R²=0.87、CaMgFe2 2.64 wt%、Mg2Fe 4.13 wt%、Mg2Fe0.6Co0.2Mn0.2 4.19 wt%（未见任何数据库）。
- validation：非本研究湿实验；转述 ScNiSb zT ~0.5@925K、Er2Te2.7Bi0.3 zT ~1.0@973K、RbSbWO6 闭环验证回灌 DigCat。
- 作者自陈局限（§7）：数据可靠性/模型可解释性/数字-物理集成三瓶颈；agent 揭示机制仍早期、需标准化可解释工作流；
  需共享 schema 与语义对齐。

### n=15 · The agentic age of predictive chemical kinetics (Chem Sci 2026, 10.1039/d5sc07692g) — 综述与观点
- 架构：Perspective，双车道 S1（自动化骨架：RMG/Genesys/EStokTP/AutoTST/ChemTraYzer/KinBot/AutoMech/ARC/T3/Cantera）
  + S2（agentic 车道）。S2 具名 agent：**Planning / Tool / Literature / Data / X-Design / Lab Interface / Revision / Reporting**。
  六步决策循环；RAG + persistent memory；HITL 门设在昂贵算力与湿实验；budget envelope + 端到端 provenance 构造性要求。
- models：未披露具体 LLM（概念性 Perspective）。
- benchmark：无量化评测；倡议 community-agreed Mechanism Development Benchmark（offline replay + shadow mode，
  评分板加权 predictive accuracy / UQ calibration / provenance completeness / cost / latency / HITL approvals）。
- validation：无实验；倡议 offline replay + shadow mode。
- 作者自陈局限：LLM 黑箱推理链、误差级联、资源争用、加 agent 反增噪、缺形式化验证、对抗威胁（prompt injection/投毒/工具操纵）、
  幻觉反应路径 / emergence agency、问责模糊。

### n=16 · PANGAEA GPT (Front AI 2025, 10.3389/frai.2025.1674927) — 基础设施与框架
- 架构：MAS，LangChain + LangGraph，开源 `github.com/CliDyn/pangaeaGPT`。集中式 supervisor（command-and-control）动态派生
  领域子 agent（oceanography/geology/climatology/ecology）。工具：Memory Extractor / Report Checker / Task Planner / Visualizer /
  Analytic/Modeller / Writer / Search / Articles Manager + PANGAEA Search + 引用管理。多层记忆（短期上下文 + 长期可检索向量库）。
  可靠性 = Tool-Augmented Generation + Reflection/Validation（统计校验 + VQA 查图，如海洋深度轴是否反转）。
- models：未披露（仅称 LLM 驱动）。
- benchmark：无量化评测（作者明言 proof-of-concept）。
- validation：人在回路专家评估为主 + Reflection/Validation 模块，无定量对比。
- 作者自陈局限：proof-of-concept、缺严格定量实证；地学缺领域基准、无 imaging benchmark；多语言/多绘图习惯使通用校验器失效；
  多 agent 计算开销大、对资源有限机构构成可及性障碍。

### n=17 · PGxAI-Recommender (npj Digital Medicine 2026, 10.1038/s41746-026-02590-w) — 领域专用 agent
- 架构：模块化流水线 + 轻量 agentic controller（perceive–reason–act）。各模块暴露为可调用工具：文献检索 → LLM 注释 →
  FDA 标签解析 → 跨研究证据聚合 → 推荐生成。controller 维护每 case 持久状态表（extract/annotate/fda/recs 的 pending/completed/需重跑）。
  五阶段：Entrez 检索 PubMed(1966–2025)（优先 PMC XML，否则 PDF，再 OCR）→ LLM 注释 → 证据聚合（按 allele 聚类 + High/Moderate/Weak 分级）→
  FDA label 抽取剂量/药理遗传学考量/禁忌/警告 → 推荐生成（严格 JSON，含推荐强度 Strong/Moderate/No recommendation）。支持 de novo/updater 模式，每周增量重跑。
- models：**GPT-4.1（OpenAI API, temperature=1e-5）** 用于注释/FDA 抽取/推荐生成；基线对比 GPT-4.1、GPT-4o-mini、GPT-5、GPT-o3、Claude Opus 4、Grok 4（均 inference-only、无联网）。
- benchmark：自建评测 22 篇全文 × 35 二值字段 × 3 标注者 = 2310 判断，抽取总体准确率 **91.9%**（多数专家共识 94.7%）；
  24 条随机推荐盲评，PGxAI-Recommender 均分 **9.0**（基线 6.2–7.8），配对 CPIC 一致性胜率 0.83，Friedman χ²=46.71 p<0.001。
- validation：3 位独立标注者（含 PGx 训练审稿人）；1 位临床药理学家（MD,PhD）0–10 盲评 24 条；CPIC 参考配对排序。无湿实验。
- 作者自陈局限：评测规模小（22 篇/24 条，仅可行性评估）；付费墙文献不可得→覆盖缺口/倾向于开放获取；未纳入 BioMedLM/BioGPT/Me-LLaMA 等领域模型；
  未建模药物相互作用/phenoconversion/既往治疗/多基因/年龄/共病；panel 式指南开发仍是金标准。我读出：代码因专利不公开、难复现；
  专家一致性偏低（Cohen's κ 0.19–0.52，Fleiss' κ 0.26）使 91.9% 的含义需谨慎解读。

## 交付落盘约定（用户指定，照抄）
`json.dump({"cards": {"1": {…10 字段…}, "2": {…}, "14": {…}, …}}, f, ensure_ascii=False, indent=2)`
→ 落盘 `E:/MemOmics-Agent/results/memomics-be17649b/data/deep_cards_round2_t0.json`；
回复给出 `os.path.getsize` 字节数 + `json.load` 回读 OK；**不动 `data/cards.json`（list[dict]）**。

## ✅ 第二次尝试完成（2026-10-08 同日重做，n=15/16/17 → `deep_cards_round2_t0b.json`）

上一轮失败后，用户就同一批下达修复指令：**「每写完一张立即 json.dump 落盘——不要攒到最后写」**。
照做，N=3 一次跑通（见 SKILL C11-g）。本轮**只做 15/16/17 三张**（1/2/14 已由前序完成）：

- 落盘文件 `E:/MemOmics-Agent/results/memomics-be17649b/data/deep_cards_round2_t0b.json`，**19,286 字节**；
  容器 `{"cards":{"15":…,"16":…,"17":…}}`，10 字段/卡；**3 次独立 `json.dump`**（每卡完成即写）。
- 字段长度：n=15 arch **1431** / lim **469**；n=16 arch **1297** / lim **333**；n=17 arch **1510** / lim **407**。
- 回读校验：`json.load` OK；三卡 `set(keys)==10 字段` 全 True；`evidence_quote in 全文` 三卡全 True（与上表逐字一致）。
- 🔴 **基准样卡容器形状坑**：`data/deep_cards_deleg_15d8b24b.json` 是**扁平 dict 以 n 为键**（非 `{"cards":{...}}`）——
  按 C11-b 读它校准密度时别照抄其形状，读前先 `print(type(obj), list(obj)[:5])`。
- 读法：`execute_python` 按字符区间切片 `print(t[a:b])`（每段 ≤10000，40–55KB 正文各 4–6 段）足够，未用 `fold`。

## ⚠️ 第三次尝试（同日，**扇出 2 子代理**）→ 全批 interrupted；主代理才是正解（2026-10-08）

同一条「每写完一张立即 `json.dump` 落盘 / 不要攒到最后写」的指令第三次出现，这次被**扇出**执行：
`delegate_task` 两个子代理 × 每人 3 篇（task-0 = n=1,2,14 → `deep_cards_round2_t0a.json`；
task-1 = n=15,16,17 → `deep_cards_round2_t0b.json`）→ 回执 `deleg_96407a20`：
**两任务全 `status=interrupted`（0s；整批 295.12 s）、无 summary**，
原文 `no summary — status=interrupted: Parent agent interrupted — child did not finish in time`。

同一任务、同一 6 篇、同一落盘要求下的三次对照：

| 执行者 | 粒度 | 结果 |
|---|---|---|
| 主代理（见 SKILL C11-g） | n=15/16/17，每卡一 dump | ✅ 跑通（`t0b`，19,286 B，3 次独立 dump） |
| 主代理（见 SKILL C11-h） | n=1/2/14，每卡一 dump | ✅ 跑通（`t0a`，21,729 B，3 次独立 dump） |
| **扇出 2 子代理 × 每 3 篇（本轮）** | 3 篇/人 | ❌ **两任务全 interrupted、零 summary** |

⇒ **默认执行者结论：N ≤ 6 且要求「落盘 + 全批字段口径统一」时，主代理串行做（每卡一 dump），⛔ 不要扇出。**
扇出的唯一红利是并行读长文——3 篇短文本并行几乎不省时间，却多担一层「父会话中断连带杀死在跑的子代理」的风险
（本轮即该风险成真）。扇出只在 **N ≥ 8 或单篇 30–580 KB 长文** 时才划算，且**必须同时要求增量落盘到各自独立文件**。

⇒ 收到 `interrupted` 回执的动作顺序（与 `delegation-orchestration` §一 一致）：
① **先 `ls` 该批的落盘路径**——brief 里已含增量 dump 契约 ⇒ 磁盘上**可能已有 1–2 张完整卡**，
**⛔ 重派前必须先查**（重派会把已完成的卡再做一遍、白烧一轮）；
② `tail cache/delegation/live/deleg_96407a20/task-*.log` 判停点（日志停在半途 = 被切断，不是完成）；
③ 确无落盘件 ⇒ 再重派，并**优先改为「主代理自己做」**（见上表）。
⇒ 编排协议与三源判死法见 `delegation-orchestration` §一 / §一-b / Common Issues。