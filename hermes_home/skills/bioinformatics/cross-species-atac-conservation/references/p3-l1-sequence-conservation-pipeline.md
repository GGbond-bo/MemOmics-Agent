# P3-L1 跨物种序列保守性管线（2026-08 实测可跑通）

专利测试版 P3 的 L1（序列保守性）在 Windows 上实测通过的完整路径。核心原则：**猴 DA tiles 基因锚定 → NCBI ortholog → hg38 坐标 → UCSC phyloP 远程查询**。

## 关键决策：T2T-MFA8v1.1 无现成 chain

- UCSC 无食蟹猴 T2T-MFA8v1.1 的 chain（`mfa8ToHg38` = 404；rheMac10/macFas5 链存在但物种/组装不对）
- NCBI GRS 旧 API 已废弃（410 Gone）；Datasets remap API 404
- **正解：基因锚定 ortholog 映射**（猴 DA tiles → 猴基因 → human ortholog → hg38），完全绕开全基因组 chain 构建（3GB×2 比对本机不现实）

## 数据源清单（全部可用）

| 数据 | 来源 | 说明 |
|------|------|------|
| 猴 GTF/feature_table | NCBI `GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz` | 6.4MB，含 gene 坐标 + GeneID |
| ortholog 映射 | NCBI gene XML `https://www.ncbi.nlm.nih.gov/gene/{id}/?report=xml` | Orthologs 段落直接给 human GeneID |
| hg38 坐标 | NCBI esummary `db=gene` genomicinfo | **注意是 GRCh37**（NC_xxx.14/.12 后缀）→ pyliftover 到 hg38 |
| phyloP | UCSC REST `api.genome.ucsc.edu/getData/track?genome=hg38&track=phyloP100way&chrom=chrX&start=&end=` | 远程查询，无需下载 bigWig |

## 关键坑（逐个实测）

1. **Ensembl 食蟹猴注释不兼容**：Ensembl 用 Macaca_fascicularis_6.0（GCA_011100615.1）组装，与我们的 T2T-MFA8v1.1 坐标体系不一致 → 不能用 Ensembl Compara/homology
2. **NCBI 网页爬虫 403**：`/gene/{id}/ortholog/` 页面直接抓被拒；但 `?report=xml` 端点可用且含 Orthologs 段
3. **eutils esummary/elink 无 ortholog 字段** → 必须用 efetch XML（`db=gene,id=...,rettype=xml`）
4. **feature_table 列索引**（易错）：0=feature, 5=chromosome(编号"1"非accession!), 6=genomic_accession(NC_xxx), 7=start, 8=end, 9=strand, 14=symbol, 15=GeneID。**染色体 key 必须用 genomic_accession（col 6）**，不是 chromosome（col 5 是"1"/"2"编号）
5. **esummary 坐标是 GRCh37**：NC_000007.14 = hg19（.14/.15 后缀区分），human ortholog 需 pyliftover → hg38
6. **UCSC API key**：phyloP 数据 key 是 `phyloP100way`（dict 列表 `x['value']`），**不是** `bedGraph`（list `x[3]`）——用错 key 全部返回空 → conserved 全 N
7. **大基因跨度查询极慢**：全基因窗口（SNED1 1MB）UCSC 响应 30-60s，40 区域 20-40min 不可行 → **用相对位置映射**：tile 在猴基因内 frac → 人基因对应位置 ±2500bp 窗口 → ~1s/区域

## 结果口径（P3-L1 输出）

`l1_seq_scores.csv`（40 tiles）+ `l1_phylop_results.csv`（每 tile: phylop_mean, n_bins, conserved Y/N）。
实测人侧 4 样本（hc78/hc5579/hc98/hc9）：
- Old DA: n=18, 50% conserved, mean phyloP=0.018
- Young DA: n=22, 77.3% conserved, mean phyloP=0.115
→ 生物学信号正确：年轻侧 DA CRE 序列保守性显著高于衰老侧。

## 脚本位置（可复用）

`E:/专利/P3_L1_data/`：
- `gene_anchor_ortholog.py` — 猴 DA tiles → 猴基因 → NCBI XML ortholog → hg38 坐标（esummary+pyliftover）
- `l1_phylop_fill_v3.py` — 相对位置映射 + 5kb 窗口 phyloP 查询（断点续传）
