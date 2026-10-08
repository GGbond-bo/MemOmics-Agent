# Paper2Agent 竞品知识库（Nature 2026）

> 用途：用户精读/对比科研 AI Agent 论文时的**逐字事实底稿**。所有数字均从 PDF 原文提取（写结论只引用本文件里可回源的数字）。
> 本文件是 `references/research-agent-landscape-2026.md` 的**待并入竞品卡**（下次更新赛道全景时合并进去）。

## 0. 身份卡

| 字段 | 值 |
|---|---|
| 标题 | Reimagining research papers as interactive and reliable AI agents |
| 团队 | **Jiacheng Miao**¹²✉, Joe R. Davis¹, Yaohui Zhang³, **Jonathan K. Pritchard**¹⁴, **James Zou**²³⁵✉ — Stanford（遗传系 / 生物医学数据科学 / 电气工程 / 生物 / CS） |
| 载体 | **Nature**（正刊）· DOI `10.1038/s41586-026-11044-y` · 收稿 2025-10-13 / 接收 2026-08-14 |
| 路线分型 | **工具-环境型 / 论文资产化型**（与 Biomni 同为 Stanford 系，但方向不同，见 §5） |
| 代码 | https://github.com/jmiao24/Paper2Agent ｜ AlphaGenome agent 已上线 Hugging Face Spaces |
| 本会话 PDF | `E:/文献/AI/agent/literature/paper2Agent.pdf`（18 页，含 Methods + Extended Data Fig.1–2；**无 Supplementary Note**） |
| 全文落盘 | `data/paper2Agent_fulltext.txt`（82,778 字符） |

## 1. 一句话定位

> **Biomni 把「整个领域」做成工具箱；Paper2Agent 把「单篇论文」做成一个可执行、可对话、经过验证的 Agent。**
> 作者自命的角色是论文的 **"virtual corresponding author"（虚拟通讯作者）**——不再"读"方法学论文，而是直接对话让方法跑在你的数据上。

解决的问题原文口径：论文是 **passive objects**；已有努力（可执行论文 / Papers with Code / Binder / CodeOcean / paper-to-code）改善的是**可复现性**，"理解、定制、迁移到新项目"这一关**没解决**。

## 2. 技术核心：论文 → MCP server → agent

选型是 **MCP（Model Context Protocol）**，把论文封装成 MCP server，挂给 LLM agent。MCP server 三件套：

| 组件 | 内容 | 论文举例 |
|---|---|---|
| **MCP tools** | **可执行函数**，封装方法学贡献 | `score_variant_effect()` / `visualize_variant_effects()` / `quality_control_basic_filtering()` |
| **MCP resources** | 静态资产：手稿 + 代码库 + 补充材料/表/图/数据 | AlphaGenome MCP 里指向训练数据的链接 |
| **MCP prompts** | **多步工作流指令**，从论文/代码推断，**无需人工编写** | Scanpy 的 QC→归一化→HVG→降维→建图→聚类→注释 **正确顺序** |

### 六步管线（Claude Code Agent SDK；编排器 + 5 个专职子 agent）

```
① 定位并下载代码库（自动识别 / 用户指定）→ 输出 clone 仓库 + 语言
② 环境搭建（environment manager）→ 隔离虚拟环境 + 测试配置
③ tutorial 发现（tutorial scanner）→ 候选清单 JSON（分类文件索引）
④ tutorial 全量执行与审计（tutorial executor）→ 跑出 gold-standard 输出/图 + 逐 tutorial 执行报告，并记录必须显式化的隐含假设
⑤ 工具提取 + 测试精修（两个子 agent 串行）
     tool extractor-implementor：tutorial → 可复用单职责函数；硬编码值（路径/阈值/列名）参数化；强制基于文件的 I/O
     test verifier-improver：用 tutorial 自带示例数据当 ground truth 造测试
⑥ 组装 MCP server（manifest + 版本 + 安全默认）→ 部署远程（Hugging Face Spaces）
```

**验证判据（硬标准，不是模型自觉）**：
- 期望文件生成；
- 数值与 tutorial 输出一致，**浮点 3% 容差**；
- 图**感知哈希比对，Hamming 距离 < 20**；
- 每个函数**最多 6 次**尝试；反复失败 → **摘掉 MCP 装饰器**、加失败注释、**不进最终 server**。
- 每个 tool 内嵌**指回原始源码的可追溯链接**。

**成本**：AlphaGenome 一次生成 **22 个工具全通过，约 45 分钟，US$14**（Scanpy 约 US$13），个人笔记本、无人工干预，**一次性投入可复用**。

## 3. 核心结果（全部来自正文原文）

### 3.1 AlphaGenome 任务：与人类/基线/竞品对比（双专家打分，评分者一致性 **96.7%**）

| 任务类型 | Paper2Agent | Claude + Repo | **Biomni** |
|---|---|---|---|
| 15 个 tutorial 派生问题 | **98.7 ± 1.3%** | 82.7 ± 3.4% | **37.3 ± 4.0%** |
| 15 个新问题（novel） | **100.0 ± 0.0%** | 78.7 ± 4.4% | **56.0 ± 3.4%** |
| 30 个开放式研究式问题（多步工具组合 + 生物学综合） | **82.7 ± 2.4%** | 56.7 ± 2.3% | **72.2 ± 2.2%** |

> ⚠️ **这是本会话最有价值的一条**：竞品之间**互相 benchmark**，且 Biomni 在这里**输得很明显**（因为它没有 AlphaGenome 的专用经验证接口，只能现场拼代码）。开放式问题上两者收窄（82.7 vs 72.2），说明 Biomni 的通用推理有价值。
> 作者自陈：**"We did not include Biomni in this benchmark [100 篇计算生物学] owing to its high cost."**

### 3.2 规模化（三套语料，全自动、无人工清理/改码/干预）

| 语料 | 结果 |
|---|---|
| **100 篇计算生物学论文**（bioRxiv bioinformatics 类，从 2025-12 倒序取，不筛文档/仓库质量） | **74 篇成功 agent 化**；提出 **599** 个工具、**593 通过验证**；300 道 tutorial 题 **91.2 ± 1.6%**（Claude+Repo Sonnet4 80.3 ± 2.3%、Sonnet4.6 86.3 ± 1.1%，均 **P < 0.0001**）；**$0.20 / 1.6 min per query**（对照 $0.38 / 4.3 min） |
| **10 篇非生物学计算论文**（grf / SAELens / Binoculars / SAM2 / TabPFN / GenericML / CausalImpact / Nashpy / emcee / conformal-selection） | 42 个执行任务 **98.1 ± 0.8%**（跨领域泛化） |
| **26 篇数据/发现型论文**（13 bioRxiv + 13 Nature, 2025，无可执行代码） | 退化为 **resource layer**；100 道综合题 **89.0 ± 3.1%**（Claude browser-use 基线 82.0 ± 3.8%，**P = 0.03**），**便宜 34×、快 15×** |

**失败模式**（74/100 未成功的 26 篇）：缺可执行代码 / 缺数据或模型产物 / 环境依赖失败 / 脚本不可泛化。

**鲁棒性**：
- 越界问题（随机置换 paper–question 对）：**正确拒答率 100%**（有/无显式拒答指令两种条件）；
- 对抗仓库漂移：**12 种配置**（缺依赖 / 断路径 / 拼写错 / 废弃 API × AlphaGenome + POP-TOOLS + mlearner）= **全部恢复出可用 MCP**；
- 无 tutorial 也能建：从 POP-TOOLS 删掉全部可执行 tutorial（留 README + 源码）仍生成可用 MCP → **tutorial 有益但非必需**；
- 无 shortcut learning 系统证据（人工检查 + 自动化 reviewer agent 扫硬编码常量/固定路径/缓存输出）。

### 3.3 多 agent 协作发现（最有说服力的案例）

三 agent = AlphaGenome + MPRA 耦合 scCRISPRi + CD4⁺ T 细胞 Perturb-seq → 定银屑病位点 **rs887314** 的因果基因：

- AlphaGenome 预测 **GPR137** 为首（RNA-seq quantile score **0.997**），高于邻近其他基因；
- agent 自主提议 **10 个候选验证策略**，人类从中选 **signature-correlation analysis**；
- 结果：**只有 GPR137** 敲低与 CRE 扰动特征显著一致 —— Stim8hr **ρ = 0.613, P = 3.79×10⁻³**；Stim48hr **ρ = 0.630, P = 4.71×10⁻³**（**FDR < 0.05**）；BAD 及另三个候选基因任何条件下均不显著；
- **仅刺激条件下显著、静息不显著**（Rest: ρ = 0.29, P = 0.21）→ 解释为**激活依赖**（与 Perturb-seq 原文"调控因子随刺激条件大幅变化"及活化 CD4⁺ T 细胞在银屑病中的作用一致）；
- 作者明确声明：**"This cross-screen, cross-modality signature-correlation procedure is not proposed in the source papers"** —— 方法本身是 agent 提出的（新的数据整合手法）。

## 4. 🔴 用户反复追问的"skill"问题：本论文给出的直接证据

用户此前问过 **"Biomni 里 2500 篇论文整理出来的是不是就是它的 skill？"**（Biomni 讨论见 `references/biomni-knowledge-bank.md` 澄清节）。Paper2Agent 把这一区分讲得更清楚：

- **MCP prompts = 我们说的 "skill"**（从论文/代码推断出的可复现步骤序列，如 Scanpy 管线顺序，**无需人工编策**）；
- **MCP tools = "可执行工具"**（真正跑代码的函数）；
- 作者**专门做了消融**：**"Markdown skill files variant"** —— 用 Claude Code 的 **Markdown skill 文件**替换可执行的 MCP tools，用来检验**"技能文档 vs 可执行工具"**到底哪个重要。

> ⛔ **该消融的具体数字在 Supplementary Note 里，本 PDF（18 页）不含补充材料** —— Extended Data 只到 Fig. 2，且正文仅写 "Ablations further showed that automated validation and the multi-agent design contribute to performance (Supplementary Note)"。
> **不要编这个数字**（与模式 C2 同规矩）；正确动作是：如实告知并主动提出"要不要我去把 Supplementary Note 找来"。
> 其余消融变体（Methods 有描述、数字同样缺）：monolithic 单 agent（单 200k context，不拆子 agent）/ non-parallel multi-agent（强制串行）/ no test verifier-improver（不验证直接部署）/ alternative scaffolding（OpenCode 替换 Claude Code）。全部用 `claude-sonnet-4-20250514`。

## 5. 范式对比（本会话交付用表）

| 维度 | **Biomni**（Science 393, eadz4351, 2026） | **Paper2Agent**（Nature, 2026） | **MemOmics（本家）** |
|---|---|---|---|
| 沉淀单位 | 314 个**通用资源**（150 工具 + 105 软件 + 59 数据库），来自 2500 篇论文挖掘 | 每篇论文一个**专属 MCP**（tools + resources + prompts） | **skill**（流程 + 参数规范 + 审查标准 + 自进化日志） |
| 广度 vs 深度 | 广度优先（全领域跨学科） | 深度优先（绑定单篇，含方法级验证） | 深度优先 + 触发/级别/注册表 |
| 工作流 | **不预设模板**，agent 每次现场用代码拼 | **MCP prompts 固化论文标准流程** | 预封装，触发后按步骤跑 |
| 质量保证 | 工具人机协同实现 + 带测试用例 | **每个 tool 用论文自身数据回测**（3% 数值 + 感知哈希比图），不通过剔除 | rail_review + 多角色辩论门控 |
| 成本 | 一次建库极贵（对方论文因成本过高未纳入 benchmark） | 每篇 ~45 min / US$14，一次性 | 无建库成本（skill 为经验沉淀） |
| 失败模式 | 广而不深：对具体方法无专用验证 → AlphaGenome 任务 37.3/56.0% | 依赖代码质量：100 篇只有 **74 篇**可 agent 化 | 覆盖不到的场景没有对应 skill |

**一句话意义（用户原问"还是跟 biomni 意义"）**：
> Biomni 回答"**一个 AI 能懂多少生物医学**"；Paper2Agent 回答"**一篇论文能不能活过来**"。
> 前者是知识广度，后者是**可信执行的深度** —— 且它把"**能否被 agent 化**"反向当成了**论文可复现性的度量**（最具洞见的论点）。

## 6. 作者自陈局限（引用时必须带上）

- **相当一部分仓库仍无法 agent 化**（代码不完整 / 文档缺失 / 环境配不通）；反向推论：**agent 化的难易本身就构成可复现性的实用度量**；
- 开放式科学推理（假设生成、机制解释）**仍 human-in-the-loop**；定位为"增强工具"，**不是自主或权威的科学结论来源**；
- **benchmark 性质声明**：开放式任务上**多个答案都成立**，与单一参考答案的一致率**主要衡量"忠实执行"而非"分析有效性"**；
- **前瞻提议**：像"数据/代码可用性声明"一样，未来应出现 **"agent availability" 章节**，把 agent-native artefacts 当作与代码仓库、示例 notebook 同级的发表物并持续维护；
- 致谢/资助：NIH R01HG014005；J.Z. 受 Chan-Zuckerberg Biohub 与 Stanford Center for Digital Health 资助；**无利益冲突声明**。

## 7. 方法学可复用细节

- **基准构造**：tutorial 题 ground truth = **执行原始代码并对照 tutorial 输出**；综合题要求跨正文与补充材料整合（含重解题，例："论文用 Pearson，请用 Spearman 重做结论"）；
- **统计口径**：mean accuracy ± **s.e.m.**，bootstrap；tutorial 基准用**配对 t 检验**，100 篇大规模用 **bootstrap 假设检验（10,000 次重采样）+ 95% CI**；
- **成本口径**：MCP 构建 = 全部子 agent API 调用总和 + 从启动到 server 生成的时间；查询期 = 提交到最终答案；
- **基线设计**：Claude + Repo = 给完整仓库 + 论文，**不给 MCP tools/resources/prompts**；数据/发现型论文基线 = **Claude browser-use + 论文 URL**（代表强人机协同 LLM 配置）。