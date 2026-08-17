# P3-L1 基因锚定 ortholog 映射通道实测（2026-08-08）

## 问题
猴 DA tiles（T2T-MFA8v1.1 坐标）需要映射到人 hg38 坐标做 phyloP/JASPAR 比较。
原计划：猴 DA → 猴基因（feature_table）→ NCBI ortholog → hg38 → phyloP/motif。
关键依赖 = 猴 GeneID → 人 GeneID 的 ortholog 映射。

## 已排除的死路（不要重试）

| 通道 | 结果 | 根因 |
|------|------|------|
| NCBI datasets API `/gene/orthologs/{id}` | 404 | 该端点不存在（v1/v2alpha 全试过，openapi 无法获取） |
| NCBI datasets gene/report | 404 | 同上 |
| Ensembl Compara homology API | 空 data | **食蟹猴 Ensembl 注释用 Macaca_fascicularis_6.0 组装，与 T2T-MFA8v1.1 坐标不兼容**；ENSMFAG ID 能 lookup 到（biotype=protein_coding）但 homology 返回 0 条 |
| NCBI 网页 `/gene/{id}/ortholog/` | 403 | NCBI 反爬虫（正常 UA 也被拒） |
| NCBI 网页 `/gene/{id}` 抓 HTML | 403 | 同上 |
| **NCBI 网页 `/gene/{id}/?report=xml`** | ⚠️ 曾可用 → **2026-08-08 实测 500（被限流）** | 勿再依赖网页端，改用 efetch API（见下） |
| eutils esummary | 无 ortholog 字段 | 只给 name/description/organism |
| eutils elink `gene_gene_ortholog` | 无此 linkname | 只有 gene_gene_neighbors（同源邻居，非 ortholog） |
| mygene.info homologene | 不含食蟹猴 | **homologene 只有恒河猴 9544，没有食蟹猴 9541** |
| gene_orthologs.gz 全量下载 | 128MB 需 ~7h | 300KB/分钟，不可行；且按 tax_id 排序，9541 在文件后部，无法部分下载 |
| UCSC REST `api.genome.ucsc.edu/liftOver` POST | 非 JSON 响应 | 网络受限，不可依赖（改用 pyliftover 本地） |

## ✅ 可用通道（本会话验证）

### 1. 猴基因符号/ID 解析
- **feature_table.txt.gz**（NCBI FTP，6.4MB）：
  `https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/037/993/035/GCF_037993035.2_T2T-MFA8v1.1/GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz`
  - 断点续传必须循环（`curl -C -` + gzip -t 校验），单次 curl 常 rc=28 超时
  - 格式：tab 分隔，`feat==gene` 行含染色体/start/end/GeneID/symbol
  - **列索引（本会话两次踩坑）**：`0=#feature 5=chromosome 6=genomic_accession(NC_xxx.1) 7=start 8=end 9=strand 13=name 14=symbol 15=GeneID 16=locus_tag`
  - **染色体 key 必须用 col6 genomic_accession**（NC_088375.1）匹配 DA tiles 的 seqnames；col5 chromosome 是 "1"/"2" 编号，匹配不上
- mygene.info 可解析 symbol → Ensembl ID（taxid=9541 食蟹猴 BNIP3 → ENSMFAG00000036887），但只用于确认，不能拿 ortholog

### 2. 猴 GeneID → 人 ortholog（核心通道，唯一可靠）
**NCBI eutils efetch XML**：
```
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=gene&id={GeneID}&retmode=xml&tool=MemOmics&email=xxx
```
- XML 含 `<Gene-commentary_heading>Orthologs from Annotation Pipeline</...>` 段落
- 其中 `Other-source_anchor>human` + `Object-id_id>人GeneID` + `Other-source_pre-text>人symbol`
- 实测：食蟹猴 BNIP3（GeneID 102116967）→ human GeneID 664 ✅
- 解析正则（efetch 返回**原始 XML**，无 HTML 实体转义，直接 `<` 标签）：
  ```
  <Dbtag_db>GeneID</Dbtag_db>\s*<Dbtag_tag>\s*<Object-id>\s*<Object-id_id>(\d+)</Object-id_id>\s*</Object-id>\s*</Dbtag_tag>.*?<Other-source_pre-text>([^<]+)</Other-source_pre-text>\s*<Other-source_anchor>([^<]+)</Other-source_anchor>
  ```
- 批量查询：110 个 DA tiles 涉及基因有限，逐基因 URL 查询 + 0.3-0.4s 限速 sleep 即可；每 10 个打印进度
- 网页端 `?report=xml` 曾可用但 2026-08-08 起 500 → **一律用 efetch API**

### 3. human GeneID → hg38 坐标
- **eutils esummary 的 genomicinfo 是 GRCh37**（`chraccver` = `NC_000007.14` / `NC_000002.12`，.14/.12 后缀 = hg19）
- 必须 liftover 到 hg38：`pip install pyliftover` → `pyliftover.LiftOver('hg19','hg38').convert_coordinate(f'chr{chrom}', start, '+')`
  - 实测：DLD hg19 chr7:107891106 → hg38 chr7:108250662 ✅
- 参考：NCBI efetch gene XML 无 GenomicInfoType 坐标段（不含坐标），必须走 esummary

### 4. phyloP100way 远程查询（UCSC REST）
```
GET https://api.genome.ucsc.edu/getData/track?genome=hg38;track=phyloP100way;chrom=chrX;start=S;end=E
→ JSON key 是 "phyloP100way"（不是 "bedGraph"），值是 dict 列表 p['value']（不是 list x[3]）
```
- 正确解析：`vals = [float(p['value']) for p in data['phyloP100way']]`
- 必须 3 次重试 + sleep（UCSC 偶发超时）；数千区域 → 后台跑 + notify_on_complete（单区域 300s 前台会超时）

## 已有代码
`E:/专利/P3_L1_data/`（2026-08-08 编写，全部已修复可用）：
- `gene_anchor_ortholog.py`：DA tile ±2kb → feature_table 基因体 overlap → 猴 GeneID → NCBI efetch XML 逐基因查 human ortholog
- `fetch_hg38_coords_v3.py`：esummary (hg19) + pyliftover → hg38 坐标
- `l1_seq_scores.py`：生成可评估 tile 表
- `l1_phylop_fill.py`：UCSC phyloP 填充（已修 phyloP100way key + dict 解析 + 重试）
- `query_phylop.py`：批量 phyloP 查询（人侧 DA 3,518 区域，已验证）

## 数据现状（2026-08-08 23:50）
- 猴 DA tiles: strict Old 50 / Young 60
- 基因锚定: 71/119 tiles → 21 基因 → 8 human ortholog（TTC29/SNED1/GSTM5/ULK4/CAMK1D/DLD/MYOM2/FAM156A）
- hg38 坐标: 8/8 liftOver 完成 → 40 个 tile 可评估（l1_seq_scores.csv）
- 人侧 DA phyloP: Old 2,955 / Young 563（human_da_*_phylop.tsv）
- L1 评分表: l1_seq_scores.csv（40 行）+ l1_phylop_results.csv（填充中）

## 教训
1. **不要先下载全量 ortholog 文件**（128MB）——先评估涉及基因数量（DA tiles 只有 110 个 → 定向查询即可）
2. **Ensembl 对食蟹猴不可用于 ortholog**（组装版本不兼容），但 NCBI GeneID 通道可靠
3. **网页端 `?report=xml` 会 500 被限流 → 一律用 eutils efetch API**
4. **esummary 坐标是 GRCh37（.14/.12 后缀），必须 pyliftover 到 hg38**
5. **UCSC phyloP API key 是 `phyloP100way`（dict 格式 p['value']），不是 bedGraph**
6. **feature_table 染色体 key 用 col6 genomic_accession（NC_xxx.1），symbol=col14、GeneID=col15**
7. 大文件下载必须断点续传循环 + gzip -t 校验（单次 curl -m 60 必超时）
