# Benchmark 考试格式与判分逻辑（2026-08 实测汇总）

## 试卷1_语义索引 TaskA（MeSH 标签）
- 输入: 5 篇文献（title + abstract），如 PMID 23479819/23483174-77
- 输出: 每篇 5-10 个 MeSH 主要标签（英文）
- 正确做法: efetch MEDLINE 拿全部 MH 字段 → 按"疾病主体>干预>机制>结局>人群"优先级筛 5-10 个
- **判分陷阱（实测 F1=69% 的根因）**: gold 的 "MeSH 主要标签" = 该文献**全部 Descriptor 列表**，含 *Humans*、*Male*、*Female*、*Aged*、*Middle Aged*、*Adult* 等人口学限定词。只抓 MajorTopic(`*`) 会 precision 高(91%) 但 recall 腰斩(56%)。正确策略: 语义主体词必选 + 人口学词必补，若超 10 个按优先级截断。
- 额外教训: 不要从 abstract 推断 Publication Type 词（如 "Randomized Controlled Trial" 是 PT 不是 MeSH，gold 里没有）。

## 试卷2_问答 TaskB（list/yesno/factoid/summary）
- 8 题混合类型。list/factoid 考精确答案（如 Qsymia=phentermine+topiramate；MethPed R 包），yesno 考判断（sonidegib 对 BCC 有效=yes），summary 考要点覆盖率。
- **判分陷阱**: summary 类（如 CAMUR/TCGA、lncRNA 功能、外泌体功能）考"gold 要点覆盖率"。答案要"概念+机制细节+具体数字"三层覆盖，漏机制细节（CAMUR 的基因幂集迭代、外泌体的多泡内体融合释放）就扣分。硬指标完全命中 6/8=75%，加权 ~87.5%。

## 试卷3_多语言检索 MESINESP（DeCS 编码）⭐ 最容易 0 分
- 输入: 4 篇西班牙语文献（title+abstract）
- 输出: 每篇 7-11 个 **DeCS 数字 ID**（decsCodes）
- **判分陷阱（实测 F1=28%）**:
  1. **格式**: DeCS 数字 ID 是 BIREME 注册号（如 `23039`=Toracotomía、`9562`=Neoplasias），**不是 MeSH 树号**（`E04.928.760`）。用树号作答按严格格式判=0 分。解析工具: BIREME DeCS API `https://decs.bvsalud.org/ths/resource/?id={id}`（返回树号+名称）。
  2. **人口学词**: gold 必含 Humanos/Femenino/Masculino/Anciano/Mediana Edad/Adulto 等（与 TaskA 同款陷阱）。
  3. **官方标引 vs 主题推断**: gold 是文献在 LILACS/BIREME 的官方索引（含 Enfermedades del Ciego、Placa Hemolítica、Ictericia 等难以从摘要推断的词）。纯摘要推断词命中率极低。
- 正确策略: 格式用数字 ID；先从官方标引/数据库拉取，再补人口学词，宁多勿少。

## LABBench2 dbqa2（10 题数据库事实查询）
- 每道题对应一个特定数据库（Reactome/NCBI Genomes/SCREEN/ChEMBL/ENCODE/OpenFDA/TCGA/Zenodo/AlphaFold/Ensembl）
- 输出: JSON 键值对，如 `{"alogp":"4.98"}`、`{"reference_sequence":"..."}`、`{"cell_lines":"HepG2, K562, WTC11"}`
- 答案格式从密封答案的 ideal 字段看是带键名的 JSON（如 `{"cell_type_highest_h3k4me3":"HCT116"}`）——但**作答阶段不能读密封答案**，键名按题目语义合理命名即可
- files 字段全空（纯 API 题），无需附件

## LABBench2 cloning（10 题克隆设计）
- 附件序列文件在 GCS（`labbench2-data-public` bucket 的 validation/ 前缀），本地目录只有试题+密封答案
- 密封答案**可能是空模板**（ideal=""、ground_truth=false）——此时无法评分，如实告知用户"答案文件未填充"，不编造分数
- 作答基于 Addgene 质粒公开结构 + Ensembl/NCBI 转录本（实时查询验证）

## 通用评分报告格式
每轮评分输出: 逐题对比表（我的答案 vs gold / 命中点 / 漏掉点）→ 总分指标（Precision/Recall/F1 或正确率）→ **失败模式根因分析**（为什么错、对应哪个判分陷阱）→ 改进方案（下次怎么跑）。用户期待这种"结论先行+证据链"的交付。
