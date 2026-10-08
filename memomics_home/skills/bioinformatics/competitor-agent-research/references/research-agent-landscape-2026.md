# 科研 AI Agent 赛道知识库（调研于 2026-09-16）

全部事实来自原文（期刊摘要 / arXiv / 官方站点），DOI/PMID 可直接核验。
用途：写行业综述、竞品展示页、定位判断时的**事实底座**——不要在没查证的情况下改动这些数字。

## 0. 一句话时间线（可直接用作叙事骨架）

AlphaFold 2（2020–21，AI 当"预测器"）→ Coscientist/ChemCrow（2023，自主操控实验设备）
→ The AI Scientist v1 + PaperQA2（2024，端到端写论文 / 超人类文献检索）
→ Co-Scientist + AlphaEvolve（2025，多智能体假设生成 / 进化式编码 agent 发现新算法）
→ 平台化与商业化（2025 下半，FutureHouse 平台、Edison 分拆、Lila 自主实验室）
→ **Co-Scientist 与 The AI Scientist 同登 Nature、Biomni 登 Science、BAISBench 给出标尺（2026）**。

## 1. 分型框架（比名单更值得记）

| 路线 | 产出 | 代表 | 不做什么 |
|------|------|------|---------|
| **A 假设生成型** | 值得验证的新假设 | Co-Scientist | 不跑分析流水线 |
| **B 端到端自动化** | 想法→论文全包 | The AI Scientist | 不做湿实验 |
| **C 工具/环境型** | 可组合的领域执行环境 | Biomni | 10 分钟超时，无长任务 |
| **D 实验室闭环型** | AI 驱动硬件做实验 | Lila、FutureHouse/Edison | 重资产，非纯软件 |

## 2. 竞品事实卡

**Biomni** — Stanford CS + Genentech + Arc Institute｜Science 2026｜DOI 10.1126/science.adz4351｜PMID 40501924
- 两组件：Biomni-E1 环境（150 专业工具 / 105 预装软件包 / 59 数据库 / ~11GB data lake）+ Biomni-A1 agent（LangGraph：generate→execute→self_critic）
- **代码为中心规划**（每步写成可执行代码块，非静态 function calling）；检索增强工具选择
- 基准：LAB-Bench DbQA **74.4%**（人类专家 74.7%）· SeqQA **81.9%**（人类 78.8%）· HLE 52 题 17.3%（base LLM 6.0%）
- 消融：相对 ReAct **+20.4%**；真实任务相对 base LLM **+402.3%**
- 软肋：工具统一 **10 分钟超时**（CellBender 级任务直接超时）；架构赌"动态组合"，深度场景工程可靠性弱

**Co-Scientist** — Google DeepMind｜Nature 2026｜DOI 10.1038/s41586-026-10644-y｜PMID 42156544
- 基于 Gemini 的**多智能体**科学思维系统：智能体持续生成/批判/精炼假设
- 两大设计：① 多智能体 + **异步任务执行框架**（算力弹性扩展）② **锦标赛式演化**让假设自我改进；随测试时算力增长质量持续提升
- 真实验证：**急性髓系白血病**药物重定位候选与协同联合方案（**体外实验验证**）、新靶点发现、抗菌药耐药机制解释
- 取向：假设生成，不跑分析流水线

**The AI Scientist** — Sakana AI 等｜Nature 2026｜DOI 10.1038/s41586-026-10265-5｜PMID 41882133
- 端到端：提出想法 → 写代码 → 跑实验 → 画图分析 → 写完整论文 → **自己做同行评审**
- 两种模式：聚焦模式（人类给代码模板脚手架）/ 无模板开放式（agentic search）
- 里程碑：生成的论文**通过某顶级 ML 会议 workshop 首轮评审**（该 workshop 录取率 70%）
- 原文自陈风险：**加重评审系统负担、给文献引入噪声**

**AlphaEvolve** — Google DeepMind｜arXiv 2506.13131（2025）
- 进化式编码 agent：LLM 集群直接改写代码 + 评估器反馈迭代
- 成果：4×4 复矩阵乘法 **48 次**标量乘法（**56 年来首次改进 Strassen**）；数据中心调度优化；加速器电路等价简化；**加速其自身底层模型训练**

**FutureHouse → Edison Scientific** — 非营利 → 商业分拆（2025-11）｜futurehouse.org
- PaperQA2（2024-09，超人类科学文献检索）· ether0（2025-06，化学推理模型）· 平台（2025-05）· **Robin**（2026-05，多智能体端到端科学发现）
- 另有 "AI-for-Science 独立博士后" 计划（把 AI 工具配给早期研究者）

**Lila Sciences** — Flagship 系｜lilasciences.com
- 定位 "Scientific Superintelligence"：**AI 模型当大脑 + 自主实验室（AI Science Factory™）当身体**
- 覆盖材料/治疗/化学/能源等；重资产路线（真实验室），不是纯软件 agent

**Isomorphic Labs** — DeepMind 派生｜isomorphiclabs.com
- 在 AlphaFold 基础上做预测 + 生成式药物设计引擎；已完成 Series B
- 垂直整合药物发现公司（模型 + 自有管线），非通用科研 agent

**BAISBench** — Bioinformatics 2026｜DOI 10.1093/bioinformatics/btag227｜PMID 42412809
- 首个面向**真实单细胞数据**的 AI 科学家基准：15 个专家标注数据集细胞类型注释 + **193 道**选择题（来自 **41 篇**已发表单细胞研究的生物学结论）
- 人类基线：**5 位研究生级生信人员**
- 结论：现有 AI 科学家**尚未达到完全自主的生物学发现**，但在支撑数据驱动研究上已具实质潜力

**Closing the Empirical Loop** — Advanced Science 2026｜DOI 10.1002/advs.76675｜PMID 42734488
- 领域无关 agentic AI Scientist 独立走完科研全流程：自主设计并执行 **3 项心理学研究**（视觉工作记忆 / 心理旋转 / 想象生动性），在线招募 **288 名真人被试**，单次连续编码 **8 小时以上**，产出完整手稿
- 结论：理论推理与方法严谨性**可比有经验研究者**；局限在**概念细腻度与理论解释**

**其他 2026 信号（可选引用）**
- 《Building MCP-native hierarchical AI scientist ecosystems》Front Artif Intell 2026｜DOI 10.3389/frai.2026.1820375 — 层级化多 agent 科研生态
- 《The Virtual Biotech: A Multi-Agent AI Framework for Therapeutic Discovery》bioRxiv 2026｜DOI 10.64898/2026.02.23.707551

## 3. 赛道级判断（写"总结"时用）

1. **瓶颈迁移**：生成能力已过剩，稀缺的是**可验证 / 可复现 / 可追溯**。下一阶段的竞争在"能不能验"，不在"能不能生"。
2. **评测成为分水岭**：BAISBench 这类标尺出现后，"没有公开基准成绩"的系统会越来越难被信任——这既是行业进步，也是自查压力。
3. **闭环 ≠ 可复现**：多次独立运行的稳定性、输入版本追溯、结论可复核，是没捷径的工程问题。
4. **人机分工重构**：人负责提问、判断价值、承担伦理与署名；agent 负责执行、记录、自查。
5. **自主科研 ≠ 无人科研**：短期最有效形态是"人定方向 + agent 跑闭环 + 人做终审"。

## 4. MemOmics 的定位结论（2026-09-16 调研口径）

- 属**路线 C 的深化版**，重心不同：竞品拉"通用能力上限"，本家抬"**落地可靠性下限**"。
- 本家强项（对竞品可验证的差异点）：小时–天级长任务（后台 + 心跳 + 三源验证）、单输入→全产物可复现 + 数字溯源、
  发表级出图（矢量+位图+源数据）、7 角色对抗辩论 + 流程硬阻断、跨会话自进化（运行日志 + 错误库）。
- 本家短板（**必须如实写进交付**）：无公开基准成绩；工具/数据库广度远低于 Biomni；无湿实验闭环；
  假设生成能力弱于 Co-Scientist；更慢更贵更吃硬件。
- 一句话差异表述：「他赢在广度和可验证，我赢在深度和落地」。
