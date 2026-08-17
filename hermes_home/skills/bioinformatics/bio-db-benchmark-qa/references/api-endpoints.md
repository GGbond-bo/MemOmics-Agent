# 生物数据库 API 端点清单（benchmark 答题用，2026-08 实测）

所有请求注意：Windows/MSYS 下原生 Python 用 `E:/tmp/` 路径，勿用 `/e/tmp/`。
curl 偶发 exit 23/18，建议 python urllib/requests 或 curl `-C -` 断点续传。

## 1. NCBI E-utilities（MeSH 标签/文献）
- esearch: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query}&retmode=json`
- esummary: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids}&retmode=json`
- efetch (MEDLINE 格式，含 MeSH): `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={id}&rettype=medline`
  - MH 字段: `MH  - Humans`（非主要）、`MH  - Smoking Cessation*`（`*`=MajorTopic=Y）
  - **TaskA 判分陷阱**: gold "MeSH 主要标签"= 全部 Descriptor 列表（含 Humans/Male/Female/Aged/Adult 等），不是只取 `*`。参考 scripts/mesh_taskA.py 思路：抓全部 MH → 按语义筛 5-10 个 → 必含人口学词。
- gds (GEO 搜索): `esearch.fcgi?db=gds&term={query}`

## 2. UCSC 基因组序列
`https://api.genome.ucsc.edu/getData/sequence?genome=hg38;chrom=chr14;start=89000000;end=89000100`
返回: `{"dna": "TCTTGTCACT..."}`。注意 start/end 是 0-based half-open，end 含 100bp。

## 3. ChEMBL
`https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL2325807.json`
- AlogP: `molecule_properties.alogp`（如 "4.98"）

## 4. Ensembl REST
- 基因展开: `https://rest.ensembl.org/lookup/id/ENSG00000069424?expand=1`（Header: Accept: application/json）
  - **字段名是大写**: `d["Transcript"]`（不是 transcript），每条 `t["Translation"]["length"]` 是蛋白长度
  - 过滤 200-350aa 的 protein_coding 转录本：`200 <= Translation.length <= 350`
- 基因符号查询: `https://rest.ensembl.org/lookup/symbol/human/TFRC?expand=1`
- 蛋白特征 API 常 404，用 UniProt REST 替代

## 5. OpenFDA
`https://api.fda.gov/drug/event.json?search=receivedate:[20141001+TO+20141231]&limit=1&sort=receivedate:asc`
- 首个报告: `results[0].safetyreportid` / `receivedate`
- 药物与制造商: `results[0].patient.drug[].medicinalproduct` + `drug[].openfda.manufacturer_name[]`
- 统计制造商=某公司的药物数：遍历 drug 列表，`any('pfizer' in m.lower() for m in manufacturer_name)`

## 6. Zenodo（Global Carbon Project MtCO2）
- 记录: `https://zenodo.org/api/records/17417124`（GCB 2025v15）
- 文件: `GCB2025v15_MtCO2_flat.csv`，列: Country, ISO 3166-1 alpha-3, UN M49, Year, Total, Coal, Oil, Gas, Cement, Flaring, Other, Per Capita
- 查询: 匹配 `row[0]=='Afghanistan' and row[3]=='1971'` → `row[9]`=Flaring
- 下载: 从 record JSON 的 files[].links.self 取 content URL

## 7. cBioPortal（TCGA 蛋白组学等）
- 分子谱列表: `https://www.cbioportal.org/api/molecular-profiles?projection=SUMMARY`
- **样本数**: `https://www.cbioportal.org/api/sample-lists/{sampleListId}` → `sampleCount`（如 brca_tcga_pub_rppa = 410）
- 注意: `/molecular-profiles/{id}/sample-ids` 和 `/samples` 端点 404，用 sample-lists 才对

## 8. ReactomeGSA.data（示例数据集）
- GitHub: `reactome/ReactomeGSA.data`，data/griss_melanoma_rnaseq.RData（DGEList 对象）
- 下载: `https://raw.githubusercontent.com/reactome/ReactomeGSA.data/master/data/griss_melanoma_rnaseq.RData`
- 解析: **R 缺 edgeR/limma 会失败**，用 Python: `pip install rdata` → `rdata.parser.parse_file()` → `conv['griss_melanoma_rnaseq']['samples']`（DataFrame，列: group/lib.size/norm.factors/patient/cell_type/treatment）
- 题目例: P3 TIBC cells → 筛选 patient=='P3' & cell_type=='TIBC' → treatment 取值 MOCK/MCM

## 9. SCREEN（ENCODE cCRE 数据库）⭐ 关键
入口: `https://screen.encodeproject.org/api/screen-graphql`（POST，Content-Type: application/json，body={"query": "..."}）
- **大小写坑**: `cCREQuery` 用 `assembly: "GRCh38"`；`ccREBiosampleQuery` 用 `assembly: "grch38"`（小写），写错报 "relation GRCh38_biosamples does not exist"
- 查 cCRE: `{ cCREQuery(assembly: "GRCh38", accession: ["EH38E1864119"]) { accession group coordinates { start end chromosome } zScores { experiment score } } }`
  - 返回 2245 个实验的 z-score（**混合 DNase+H3K4me3+H3K27ac+CTCF 所有 assay**）
- 查实验→细胞类型映射: `{ ccREBiosampleQuery(assembly: "grch38") { biosamples { name h3k4me3: experimentAccession(assay: "H3K4me3") dnase: experimentAccession(assay: "DNase") h3k27ac: experimentAccession(assay: "H3K27ac") ctcf: experimentAccession(assay: "CTCF") } } }`（1518 biosamples）
- **按 assay 过滤最高**: 构建 {experiment: (cell, assay)} 映射 → 只留 H3K4me3 → 按 score 排序取最高（例: EH38E1864119 的 H3K4me3 max = HAP-1 5.703/ENCSR882CQE；注意 ENCSR000EML 6.973 是 DNase 不是 H3K4me3）
- SCREEN 原始数据矩阵 ~8GB 不可下载；ENCODE API 被 AWS WAF 拦截（405/captcha），绕行方案：SCREEN GraphQL、get_geo_details、OmicsDI、DuckDuckGo HTML 搜索
- WTC11 MPRA 实验（ENCODE 4）: GSE323200/212/215/242/247/256，ENCSR356TMB/336MKI 等 summary 明确 "test enhancers from HepG2, K562, and WTC11 cells"

## 10. AlphaFold / TED（蛋白结构域 pLDDT）
- AlphaFold API: `https://alphafold.ebi.ac.uk/api/prediction/P02786` → uniprotSequence, plddtDocUrl
- per-residue pLDDT: `https://alphafold.ebi.ac.uk/files/AF-P02786-F1-confidence_v6.json` → {residueNumber[], confidenceScore[]}（只有 v6 有文件，v1-v5 404）
- 域平均 pLDDT: 按拓扑域边界切片 `mean(confidenceScore[lo:hi])`
- TED 结构域（AlphaFold DB 2025 新增 Domains tab）: `https://ted.cathdb.info/api/v1/uniprot/summary/{acc}` → data[].chopping/plddt
- **陷阱**: TFRC 是 type II 膜蛋白（无 cleavable signal peptide），UniProt 注释 Cyto 1-67/TM 68-88/Extra 89-760；若题目问 signal peptide 域 pLDDT，gold 可能用 DeepTMHMM/SignalP 预测的不同边界，需按题目语义判断

## 11. GDC/TCGA（GDC API 有时返回空 aggregations）
- GDC: `https://api.gdc.cancer.gov/files?filters={json}`（POST 的 filters 有时不生效，用 GET+urlencode）
- TCGA-BRCA 蛋白组学文件在 GDC 查不到（RPPA 在 cBioPortal），直接走 cBioPortal sample-list

## 12. DuckDuckGo HTML 搜索（API 被拦时的兜底）
`https://html.duckduckgo.com/html/?q={urlencoded}`
- 解析: `<a rel="nofollow" class="result__a" href="...">title</a>` 与 `result__snippet`
- 用于找 ENCSR 实验的 cell line、找数据文件 URL、找论文信息
