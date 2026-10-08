# Biomni 知识库（2026-08-05 调研）

调研来源: Science 论文全文 PDF (88页, biomni.stanford.edu/paper.pdf) + GitHub snap-stanford/Biomni 源码 (231文件) + PubMed 40501924。

## 身份
- **Biomni**: Stanford CS (Huang Kexin, Jure Leskovec) + Genentech (Aviv Regev) + Arc Institute
- Science 2026《Autonomous biomedical research with an artificial intelligence agent》(DOI 10.1126/science.adz4351)
- bioRxiv 2025.05.30 (10.1101/2025.05.30.656746v1), PubMed 40501924
- GitHub snap-stanford/Biomni: 3.6K stars, Apache-2.0, Python, 231 files, 2025-03 创建
- 商业化 spinout = Phylo (phylo.bio)
- 用户口述 "biomini" = Biomni（音译歧义，必须先确认身份）

## 架构: 两组件

### Biomni-E1（环境）
- **Action Discovery Agent**: 从 bioRxiv 25 类 × 100 篇最近论文（2500篇）挖掘工具/数据库/软件 → 人工专家验证 → 入库
- 产物: **150 个专业工具 + 105 个预装软件包(Py/R/Bash) + 59 个数据库**(~11GB data lake, 自动下载)
- 数据库两类: ① web API 型 (PDB/OpenTarget/ClinVar) → 每库一个统一函数，内部 LLM 解析 schema 动态生成查询；② 无 API 型 → 下载到本地 data lake 转 pandas DataFrame

### Biomni-A1（agent）
- LangGraph StateGraph: generate→execute→(self_critic)→end; MemorySaver checkpointer
- **检索增强规划**: ToolRetriever 按 query 选工具/数据/软件 → LLM 生成计划 → **code-based planning**（每步写成 `<execute>` 代码块，支持 Py/R/Bash）——不是静态 function calling
- **self-critic 循环**: 每轮 LLM 对历史执行生成批判反馈再改进（test_time_scale_round 轮）
- 工具统一 10 分钟 multiprocessing 超时; 输出截断 10K 字符
- 支持 MCP 工具接入 + 自定义工具/数据/软件注册（add_tool/add_mcp/add_data/add_software）

## 基准成绩（Science 原文数字）
| 基准 | Biomni | 对比 |
|------|--------|------|
| LAB-Bench DbQA (315题) | 74.4% | 人类专家 74.7%; ReAct+Code 40.8% |
| LAB-Bench SeqQA | 81.9% | 人类 78.8% |
| HLE 52题 (14 子领域) | 17.3% | base LLM 6.0%, coding agent 12.8%, literature agent 12.2% |
| 8 个真实任务 | — | vs base LLM 相对 +402.3%; vs coding agent +43.0%; vs 自身 ReAct 消融 +20.4% |

- 每任务平均执行 6-24 步，组合 0-4 工具 + 1-8 软件包 + 0-3 data lake 条目
- 三个 case study: ① 458 个可穿戴传感器文件联合分析 ② 大规模 scRNA-seq & ATAC-seq 分析 ③ 湿实验克隆协议设计(经湿实验验证)
- 消融实验证明 "代码为中心规划" 是性能核心（Biomni-ReAct 消融 +20.4% 差距）

## 常见误解澄清：2500 篇论文 ≠ Biomni 的 "skill"（2026-10-04 实测）

**用户会这样问**（他本人用过 Biomni，带着强直觉来确认，且会拿它对照 MemOmics 的设计）：

> 「2500 篇论文整理出来的东西，是不是就是它的 **skill** 呢？我用过 biomni，它就是典型的
> 触发对应的 skill，然后调用里面的工具，然后完成任务。是不是？」

**答案：不完全是——Biomni 恰恰是反着设计的。**

1. **被榨出来的是「能力」，不是「流程」**：AI 驱动 discovery agent 从论文里逐块抽
   **tasks / software / databases** 三类 actionable insights（Methods · *Action Discovery from Literature*），
   人工专家再去冗、**剔除 "trivial or easily implementable through simple code" 的条目**
   （≈1,900 个 recurring tasks 收敛到 150 个专用工具）。落进环境的是
   **150 专用工具 + 105 软件 + 59 数据库 = 314 个资源**，单位是**工具/数据库**，不是打包好的 skill。
2. **论文里 "skill" 只出现 1 次**，且是 Discussion 的 "coding **skills**"（编程技能）——
   88 页全文命中探针：`skill(s)` **1** / `action space` 9 / `retriev*` 27 / `2,500` 1。
   ⇒ 它**不是** Biomni 的架构概念。
3. **论文自己的白纸黑字**（Abstract）：
   > "enabling it to dynamically compose and carry out complex biomedical workflows –
   > **entirely without relying on predefined templates or rigid task flows**."
4. **用户直觉对的那半步**：确实有一层「触发」——Methods · *Biomni-A1*：Biomni 建在 **CodeAct**
   框架上，先让 LLM 出编号计划，再用 **prompt-based retriever（另一个独立 LLM 当路由器）**
   从 314 个资源里挑最相关的 functions / datasets / software libraries（目的是避免长上下文），
   然后**现场写代码**在容器里执行并回灌 observation 迭代收敛。
   ⇒ **被检索出的单位是单个工具，不是流程。** 上面「架构」节的 ToolRetriever 即此层（源码佐证）。
5. **口径提醒（引用时必须自报）**：正文/图 1 图注 = **2,500 篇 bioRxiv（25 亚领域）**；
   Methods 写初始迭代 = **2024 年 100 篇** → ~1,900 recurring tasks。两者不矛盾（小样本起步扩量），
   但表述口径不同，别只挑一个数字当唯一事实。

**一句话定位（可直接复用）**：Biomni 把论文榨成**工具箱**，把「怎么用」交给 LLM 每次现想；
MemOmics 把经验榨成**菜谱**（流程 + 参数规范 + 审查标准）。他赢泛化，我们赢可复现——
他 Discussion 自认的局限之一恰是 "risks overlooking foundational concepts and techniques
that have faded from current discourse despite their enduring relevance"。

> 核验规程（用户带心智模型来求确认时怎么核原文、命中探针脚本）见
> `bioinformatics-fact-retrieval` §2.7 + `scripts/pdf_probe.py`。

## 与 MemOmics 对比结论

### Biomni 有我没有
- 湿实验协议设计（CRISPR 克隆/sgRNA/AAV 库）——MemOmics 只做数据分析
- 跨 25 子领域广度（生化/生物工程/生物物理/免疫/病理/药理/生理）——MemOmics 聚焦组学
- 统一 59 数据库检索（数量级 10 倍差）
- 可验证的基准成绩（Science 三级基准 + 消融实验）
- 论文驱动的工具发现（Action Discovery）——MemOmics 技能靠实战+人工沉淀

### 我有 Biomni 没有/没提
- 数小时-数天 GPU 长任务（Biomni 工具统一 10min 超时，CellBender 级任务直接超时）
- 发表级出图（nature-figure SVG/PDF/TIFF）+ HTML 报告 + PPT/Word
- 自进化（skill_evolution record_run/record_error 跨会话沉淀）——Biomni 只有 conversation history
- 7 角色多辩论（debate_analysis）——Biomni 只有单 LLM self-critic
- rail_review 流程门禁、session 隔离、多源验证铁律

### 架构分水岭
- Biomni 赌 **code-based planning 动态性**（不靠模板，现场写代码组合 150 工具，消融证明 +20.4%）
- MemOmics 赌 **skill 模板 + 铁律门禁可靠性**（预设步骤 + 审查辩论防跑偏）
- 我缺: 泛化到未见任务时的现场组合能力；他有缺: 深度场景的工程可靠性

### 追赶优先级
1. Action Discovery（论文挖掘→自动生成 skill 条目）——方法论代差，最值得学
2. 代码为中心规划（从"选模板执行"演进到"模板+现场动态组合"）
3. 自建 benchmark（用真实项目：骨骼肌 MF、猴海马 ATAC 固化评估集）
4. self-critic 迭代（把 debate 从结论裁决扩展到执行中自我批判）
