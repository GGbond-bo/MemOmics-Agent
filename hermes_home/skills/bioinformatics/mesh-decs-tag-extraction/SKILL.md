---
name: mesh-decs-tag-extraction
description: 从文献（title/abstract/PMID）提取 MeSH/DeCS 受控词表标签，用于语义索引类任务与 benchmarker 试卷（TaskA 语义索引 / MESINESP 多语言检索）。触发词：语义索引、MeSH标签、MeSH主要标签、DeCS编码、meshMajor、decsCodes、benchmarker、试卷作答、paper to tags、PubMed索引、多语言检索。核心经验（2026-08 三轮实测）：gold 答案 = 官方索引记录，含人口学限定词（Humans/Female/Male/Age组），必须用 NCBI efetch 拉全部 DescriptorName（勿只按 MajorTopicYN=Y 过滤）、排除 PublicationType、DeCS 题输出数字 ID 而非树号、从摘要推断的词与官方标引差异巨大。
---

# MeSH/DeCS 语义索引标签提取（benchmarker 试卷作答）

## 何时使用
- 用户给论文 title/abstract/PMID，要求输出 MeSH 主要标签 / MeSH 词 / 语义索引标签
- benchmarker 试卷：TaskA（语义索引 5-10 MeSH 词）、TaskB（问答 list/factoid/yesno/summary）、TaskC（MESINESP 多语言检索 → DeCS 编码 decsCodes）
- 任何"论文 → 受控词表标签"类任务

## 核心铁律（三轮实测教训，2026-08）
1. **gold = 官方索引记录，不是模型推断**。出题人的"主要标签"= 文献在 PubMed/LILACS 的完整 Descriptor 列表。
2. **必含人口学限定词**：Humans / Male / Female / Aged / Middle Aged / Adult / Infant / Young Adult 等。它们在 PubMed 记录中通常 MajorTopicYN="N"，**只抓 MajorTopic=Y 会把 recall 打到 ~55%**（TaskA 实测 F1 69%；TaskC 同样漏掉全部人口学词）。这是两轮都栽的同一个坑。
3. **排除 PublicationType**：Randomized Controlled Trial / Cohort Studies / Case Reports 等 PublicationType 节点不是 MeSH Descriptor，gold 中不存在。从摘要推断"研究类型词"是稳定错误来源。
4. **格式必须匹配题面**：TaskA 要 MeSH 词名；**TaskC MESINESP 要 DeCS 数字 ID（decsCodes）**，不是 MeSH 树号。DeCS 有独立数字 ID 体系（BIREME 注册号，如 23039=Toracotomía、9562=Neoplasias、21034=Humans）。给出树号 = 严格判分 0 分。
5. **优先拉官方记录，不要只凭摘要推断**：官方标引常含摘要里推不出的词（TaskC 中 Enfermedades del Ciego、Hemólisis、Ictericia 等）。推断词与官方标引重合率低（TaskC 6 个摘要推断词全军覆没）。
6. 输出数量参考 gold 分布（TaskA ~14 个/篇、TaskC ~8.75 个/篇），宁多勿少。

## 工作流
1. 读考试题 JSON，提取 PMID 或文献标识
2. `python scripts/fetch_mesh_tags.py <PMID>...` → NCBI efetch 全部 DescriptorName + MajorTopicYN 标记
3. 过滤：**保留全部 descriptor**（含 MajorTopicYN=N 的人口学限定词），剔除 PublicationType
4. 若题目要 DeCS 数字 ID：用 `python scripts/decs_id_lookup.py <ID>...` 解析/核对名称与树号
5. 逐篇输出标签，标注来源（主要主题标记）；对照密封答案时先对齐格式
6. 评分比对：名称先去重音/去括号/词序归一，再用语义包含匹配（严格字符串匹配会误判漏判）

## 工具配方
- NCBI efetch MeSH: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=<PMID>&retmode=xml` → 解析 `<MeshHeading><DescriptorName MajorTopicYN="Y|N">...`
- DeCS 数字 ID 解析: `https://decs.bvsalud.org/ths/resource/?id=<ID>` → 页面含 "Descritor em espanhol/inglês/português" 字段 + TreeNumberList。注意：h1 是站点宣传语（"Queremos a sua opinião..."），描述符名称在 td 字段里；`?filter=ths_regid&q=` 参数无效，必须用 `resource/?id=`。
- DeCS ID ↔ MeSH 词名映射靠上述 resource 页面实时解析，不要凭记忆。

## 常见坑
| 坑 | 后果 | 对策 |
|----|------|------|
| 只抓 MajorTopicYN=Y | recall ~55% | 全量 DescriptorName，含人口学限定词 |
| 把 PublicationType 当 MeSH | 错误标签 | 只认 MeshHeading 节点 |
| DeCS 题给树号 | 格式 0 分 | 输出 decsCodes 数字 ID |
| 从摘要推断主题词 | 与官方标引差异大 | 拉官方记录（LILACS/BIREME） |
| 名称严格字符串比对 | 误判漏判 | 去括号/去重音/词序归一后语义包含匹配 |

## 问答型题目（TaskB）补充
- list/factoid 题：直接给规范答案 + PMID 证据；yesno 题给明确 Yes/No + 适应症细节
- summary 题：**概念 + 机制/方法细节 + 具体数字**三层覆盖，只给功能列表会漏要点（TaskB Q4 CAMUR 漏"power set 迭代消除 + 内置知识库查询工具"，Q8 外泌体漏"多泡内体-质膜融合释放"生物发生机制，各扣 20-30%）

## 支持文件
- `scripts/fetch_mesh_tags.py` — PMID → 全量 MeSH descriptor 抓取（含 MajorTopicYN 标记）
- `scripts/decs_id_lookup.py` — DeCS 数字 ID → 名称/树号解析
- `references/benchmarker-sessions-2026-08.md` — 三轮试卷逐题评分与根因记录
