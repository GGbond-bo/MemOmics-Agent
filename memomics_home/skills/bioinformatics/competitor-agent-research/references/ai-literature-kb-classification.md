# 非生物学文献的知识库落法（AI / 方法 / 工具类，2026-10-11 实测）

> 适用范围：竞品调研（模式 B/C/H）里那批**科研 AI Agent 论文**入库。
> 本文件是 `kb-evidence-extraction`（手工撰写、禁止自动改）的**补充配方**——那条技能的五级目录是为生物学文献设计的，
> 直接套用会把这类文献塞错位置。（原始落库脚本：`kb_write_ai_entries.py` / `deliver_ai_agent_report`。）

## 0. 判据：这篇文献有没有 物种 / 组织 / 方向 维度？

**没有 ⇒ 不要硬塞进五级目录。**

五级目录 `<物种>/<组织>/<方向>/<类别>/<assay>/` 的价值是**防止跨组织串味**（肌肉 snRNA MT%<5% 不能套海马）。
科研 AI Agent 论文**无物种无组织**，硬套等于两条损失：
① 串味风险凭空制造；② 丢掉这类文献真正的价值维度——**横向可比性**
（一批 agent 互相打分、范式互补、同一 benchmark 上的差距）。

⛔ 不要为了把条目塞进五级目录而**编造**物种/组织字段。宁可另建分类根。

## 1. 独立分类根（内容型子目录，不是物种型）

```
memomics/knowledge_base/ai_agent/
├── frameworks/     (7)  Biomni · DeepRare · ChemGraph · BioMaster · Paper2Agent · CASSIA · ChemCrow
├── agent_design/   (2)  Co-Scientist · ScienceBuddy
├── overview/       (1)  研究思路谱系合读（不是单篇，是批次级综合）
├── benchmarks/     (1)  全部 benchmark 清单（跨篇汇总）
└── evaluation/     (1)  评测范式与坑
```

要点：
- 子目录按**内容型**切（框架 / 设计思想 / 总览 / 基准 / 评测），不按物种组织。
- **批次级综合**（overview / benchmarks / evaluation 三条）与单篇条目**同等重要**——横向合读的结论
  本身就是可复用知识，不要只存单篇。
- 12 条 = 9 篇论文 + 3 条横向综合（本批实际落库数）。

## 2. 每条固定 11 个字段（工程属性，不是生物学属性）

定位 / 研究思路 / 解决的问题 / 工作量 / 测试方式 / benchmark 细节 / 关键数字 / 局限 /
**原文矛盾标注** / 可复用点 / 元信息（DOI · 代码仓库 · 许可），并带 `evidence` 溯源字段。

**与生物学条目的差别**：生物学走「结论 + L0-L3 证据链 + validation/locator」；
这类文献走**工程属性**——它要回答的是"这系统是什么形状 / 靠什么跑 / 数字是多少 / 凭什么可信 / 谁做的"。

🔴 **`原文矛盾标注` 是必备字段**：AI/agent 论文里"同一量两处两个数"极常见
（本批 **7/9 篇**有硬矛盾，集中在**自建 benchmark 的规模统计**）。
知识库若不记录，下游 AI 引用时会拿到一个**未标注冲突的数字**——比"缺数据"更危险。
（与模式 H 的「主动标注原文自相矛盾」同一纪律，落到 KB 字段层。）

## 3. 入库后必须实测检索（否则等于没注册）

```python
search_knowledge("AI agent 科研智能体 benchmark 评测")
```

期望：新条目命中并排在**前列**（本批实测 `ai_agent/frameworks/biomni_general_biomedical_agent.yaml`
排第一，score **180.95**，总命中 136 条）。
⛔ **检索不到 = 注册未生效**，不要凭"文件已写入"就汇报完成。

## 4. 跨会话去重（同类文献会跨批次重叠）

新一批 AI 文献入库前先 `ls memomics/knowledge_base/ai_agent/frameworks/`（及各子目录）看是否已有同一系统。
本批 9 篇里 **Biomni / Co-Scientist / ChemCrow 与既有批次重叠**——
处理方式：以**新提取的数字为准做字段级更新**（保留旧条目独有字段），而不是新建一张重名条目。
（与 `kb-evidence-extraction` 的 `save_knowledge` 铁轨并不冲突：仍须 evidence 必填、unverified 拒收。）

## 5. 汇报口径

入库完成后向用户报三件事：① **落在哪个分类根**（含"为什么不进五级目录"一句理由）；
② **条数与子目录分布**；③ **检索实测命中**（证明真的可被下游检索到）。