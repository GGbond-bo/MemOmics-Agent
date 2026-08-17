---
name: bio-db-benchmark-qa
description: 作答生物信息学数据库问答 benchmark 考试（LABBench2 dbqa2、MESINESP DeCS、MeSH 语义索引、以及任何"题目给出问题→用真实公共数据库 API 检索→输出结构化答案→对照密封答案评分"的测试）。触发词：benchmarker、密封答案、考试题、TaskA/TaskB/TaskC、dbqa2、MESINESP、MeSH 标签、DeCS 编码、LABBench2。
---

# Bio DB Benchmark QA（生物数据库问答 Benchmark 作答）

## 何时使用
用户给出 `E:\benchmarker\...\*_考试题.json` 路径，要求"作答/测试/开始完成"，随后可能提供 `*_密封答案.json` 要求"对一下/评分"。这类考试的特点：每道题是一个事实型问题，正确答案隐藏在某个真实公共生物数据库（NCBI/UCSC/SCREEN/ENCODE/ChEMBL/OpenFDA/Ensembl/Reactome/TCGA/Zenodo/AlphaFold 等）中，靠 LLM 记忆答不准，必须用工具实时检索。

## 铁律（用户明确要求，2026-08 会话验证）
1. **作答阶段绝不读密封答案文件**。用户说"只看考试题/不要看答案"是最高优先级指令。连"确认输出格式"都禁止读密封答案——格式从考试题 instructions 推断即可。
2. **每道题必须实时调用真实数据库 API 检索**，禁止凭 LLM 预训练知识作答。检索不到就明说"该题无法确认"，不编造。
3. **答案要附带数据源证据**（API 名 + 返回的原始字段），让用户能复现验证。
4. 评分阶段才读密封答案：逐题对照，算 Precision/Recall/F1 或正确率，并做失败模式根因分析（不是简单对错）。

## 标准流程
1. `read_file` 读考试题 JSON → 解析题目列表（id/question/sources/files），注意 `files` 字段是否为空（空=纯 API 查询题，无附件）
2. 并行调用相关数据库 API（端点清单见 references/api-endpoints.md）
3. 汇总答案，标注每题数据源 + 置信度
4. 等用户提供密封答案后 → 逐题评分 + 根因分析

## 考试格式速查（各 Task 的输出格式与判分逻辑，详见 references/exam-formats.md）
| 考试 | 输入 | 输出要求 | 判分陷阱 |
|------|------|---------|---------|
| 试卷1 TaskA（语义索引） | 文献 title+abstract | 每篇 5-10 个 MeSH 标签 | **gold 含全部 Descriptor 列表**（含人口学限定词 Humans/Male/Female/Aged/Adult 等），不是只取 MajorTopic=Y；漏人口学词 recall 腰斩 |
| 试卷2 TaskB（问答） | 8 题（list/yesno/factoid/summary） | 按题类型回答 | summary 类考"要点覆盖率"：概念+机制细节+具体数字三层都要覆盖 |
| 试卷3 MESINESP | 西语文献 title+abstract | **DeCS 数字 ID**（如 23039） | **DeCS 数字 ID ≠ MeSH 树号**！BIREME 注册号体系，用树号答=格式 0 分；gold 也含人口学词（Humanos/Femenino/Masculino） |
| LABBench2 dbqa2 | 10 题数据库事实查询 | JSON 键值对（如 {"alogp":"4.98"}） | 每题对应一个特定数据库 API，必须实时查 |
| LABBench2 cloning | 10 题克隆设计 | 设计方案 | 附件序列在 GCS 不在本地；用 Addgene/Ensembl/NCBI 公开序列设计 |

## 已踩坑（务必避免）
1. **MeSH/DeCS 人口学限定词**：NCBI efetch 的 MH 字段中 `*` 标记 MajorTopic，但 gold 答案把全部 Descriptor（含 *Humans*、*Male*、*Female*、*Aged*、*Adult* 等）都算作"主要标签"。只抓 major topic 会导致 recall 从 90% 掉到 55%。
2. **DeCS 编码体系**：MESINESP 的 decsCodes 是 BIREME 数字 ID（`23039`=Toracotomía），不是 MeSH 树号（`E04.928.760`）。格式错了直接 0 分。解析工具：BIREME DeCS API `https://decs.bvsalud.org/ths/resource/?id={id}` 返回树号与名称。
3. **ENCODE API 被 AWS WAF 拦截**（encodeproject.org 全站 405/captcha）。绕行：SCREEN GraphQL 端点、GEO（get_geo_details）、OmicsDI、DuckDuckGo HTML 搜索、Europe PMC。
4. **SCREEN 数据文件巨大**（H3K4me3 z-score 矩阵 ~8GB），不能全量下载。正确姿势：SCREEN GraphQL API `https://screen.encodeproject.org/api/screen-graphql`（POST JSON query）。**注意大小写坑：cCREQuery 用 assembly:"GRCh38"，ccREBiosampleQuery 用 assembly:"grch38"（小写）**，两者不一致！
5. **cCREQuery 的 zScores 混合所有 assay**（DNase+H3K4me3+H3K27ac+CTCF）。题目若问"某 assay 最高"，必须用 `ccREBiosampleQuery` 建实验→细胞类型映射表，再过滤指定 assay（如 H3K4me3）取最高，否则会把 DNase 信号误判为 H3K4me3。
6. **Windows/MSYS 路径坑**：原生 Python 打不开 MSYS 虚拟路径 `/e/tmp/...`，必须用 `E:/tmp/...`。curl `-o` 偶尔 exit 23/18（write error/部分传输），用 python urllib 或 `-C -` 断点续传更稳。
7. **RData 解析**：R 缺 edgeR/limma 依赖时加载 DGEList 会失败。用 Python `rdata` 库直接解析 RData（`pip install rdata`），无需 R 环境。
8. **诚实报告**：若为确认格式误读了密封答案，要主动向用户坦白，且后续答案仍以独立检索为准（用户会审计）。

## 数据库 API 端点速查
完整清单见 references/api-endpoints.md（含请求示例与返回字段）。高频端点：
- NCBI E-utilities: `eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch/esummary/efetch`（efetch rettype=medline 的 MH 字段=MeSH）
- UCSC: `api.genome.ucsc.edu/getData/sequence?genome=hg38;chrom=chr14;start=...;end=...`
- ChEMBL: `www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL{id}.json`（molecule_properties.alogp）
- Ensembl REST: `rest.ensembl.org/lookup/id/{ENSG}?expand=1`（**字段名是大写 Transcript/Translation**）
- OpenFDA: `api.fda.gov/drug/event.json?search=...`
- SCREEN GraphQL: `screen.encodeproject.org/api/screen-graphql`
- Zenodo: `zenodo.org/api/records/{id}` → files 列表 → 下载 CSV
- cBioPortal: `www.cbioportal.org/api/sample-lists/{listId}` → sampleCount
- ReactomeGSA.data: GitHub `reactome/ReactomeGSA.data` 的 data/*.RData（griss_melanoma_rnaseq 含 patient/cell_type/treatment）
- AlphaFold: `alphafold.ebi.ac.uk/api/prediction/{uniprot}` + `files/AF-{x}-F1-confidence_v6.json`（residueNumber+confidenceScore）
- TED 结构域: `ted.cathdb.info/api/v1/uniprot/summary/{acc}`（含 domain pLDDT）

## 相关技能
- `omics-dataset-retrieval` / `public-data-download`：下载公共数据集（本技能偏"答题检索"而非"下载交付"）
- `deep-research`：深度调研（本技能是 benchmark 考试场景）
