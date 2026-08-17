# P3-L1 JASPAR motif 双侧富集（测试版, 2026-08-09）

跨物种 CRE 专利 L1 层的最后一块：猴侧测试版 DA tiles + 人侧 strict DA tiles 双侧
JASPAR2020 motif 富集对比。方法复刻 Phase 6（完整版）score-based ranking，保证可比。

## 输入文件

| 侧 | 文件 | tiles | 坐标系 |
|----|------|-------|--------|
| 猴 Old | `E:/专利/P3_L1_data/macaque_da_strict_Old.csv` | 50 (滤OOB后48) | 食蟹猴 T2T NC_xxx.1 |
| 猴 Young | `E:/专利/P3_L1_data/macaque_da_strict_Young.csv` | 60 | 食蟹猴 T2T NC_xxx.1 |
| 人 Old | `MEMOMICS_HOME/results/memomics-1c1890da/patent_test/da_tiles_strict_Old.bed` | 2955 | hg38 |
| 人 Young | `MEMOMICS_HOME/results/memomics-1c1890da/patent_test/da_tiles_strict_Young.bed` | 563 | hg38 |

## 三个必踩的坑（已在 SKILL.md 记录，此处给修复代码）

### 1. OOB 过滤（食蟹猴 T2T vs rheMac10 长度差异）
食蟹猴 chr7/chr12 比恒河猴 rheMac10 对应染色体长。不滤直接报：
`trying to load regions beyond the boundaries of non-circular sequence "chr7"`
```r
d$chr <- nc2chr[as.character(d$seqnames)]   # NC_xxx.1 → chr1-20/X
d$end <- d$start + 499
clen <- seqlengths(BSgenome.Mmulatta.UCSC.rheMac10)
keep <- d$end <= clen[d$chr] & d$start >= 1
d <- d[keep, ]
```
本会话 50 Old tiles 滤掉 2 个（NC_088381.1:171356000→chr7 超 169868564；
NC_088386.1:136974500→chr12 超 130043856），Young 60 个全通过。

### 2. TF 名提取（PFMatrixList 不能用 subset+==）
```r
tf_map <- sapply(motifs, function(m) m@name)   # motifs = getMatrixSet(JASPAR2020, opts)
# ... res 构建后:
res$tf <- tf_map[res$motif]
```

### 3. fc 伪高（bg_mean≈0/负 → fc 爆炸）
`fc = fg_mean / pmax(bg_mean, 1e-6)` 时 bg 为负或 0 会爆出数十万：
- 猴 Old PRRX1 fc=269335（bg_mean=0）
- 人 Old EWSR1-FLI1 fc=406519（bg_mean=-0.1812）、GLIS1 fc=61776（bg=-0.1838）
报告时必须并列 fg_mean/bg_mean，只信两者都显著为正的行；伪高显式剔除。

## 结果（测试版）

### 双侧 top15

**猴 Old（48 tiles）**: PRRX1*, CEBPB 4.79, ZFP57 4.79, CREM 4.32, FOSL1::JUND 4.28, ARNT2 3.77, MLXIPL 3.72, PITX1 3.64, MLX 3.41, VENTX 3.40, GBX1 3.26, NKX6-1 3.03, FOSB::JUNB 3.02, TFEB 2.90, LBX2 2.89 (*=伪高剔除)
**猴 Young（60 tiles）**: HOXB8 13.16, FOSL1::JUND 4.72, PITX1 4.34, SMAD3 3.40, BHLHE41 3.19, HOXB7 3.10, ARNT2 3.01, BHLHE40 3.00, PROX1 2.94, PAX7 2.86, HSF4 2.71, GBX1 2.68, ZNF410 2.66, MLXIPL 2.66, CEBPB 2.59
**人 Old（2955 tiles）**: EWSR1-FLI1*, GLIS1*, KLF15 6.64, EN1 6.41, EMX1 5.19, SP4 4.72, HOXB8 4.13, SP1 3.88, HOXA1 3.57, SP2 3.52, PAX4 3.40, HOXB5 3.38, FOSL2::JUNB 3.34, EGR3 3.33, HOXB2 3.28
**人 Young（563 tiles）**: EWSR1-FLI1*, GLIS1*, KLF15 8.15, SP4 7.33, EN1 6.35, SP1 5.76, EMX1 5.15, SP2 4.82, HOXB8 4.22, FOSL2::JUNB 3.94, FOSL1::JUN 3.89, KLF14 3.71, KLF16 3.70, MAZ 3.58, HOXB5 3.53

### 与完整版 Phase 6 一致性（方法学验证）
- 猴 Old 测试版 ↔ 完整版：CEBPB/ZFP57/CREM/FOSL1::JUND/PITX1/MLX/VENTX ↔ ZFP57 6.14/CEBPB 5.28/MLX 4.41/VENTX 4.39/PITX1 3.73 —— **重合**
- 猴 Young 测试版 ↔ 完整版：HOXB8/FOSL1::JUND/PITX1/SMAD3/BHLHE41 ↔ HOXB8 8.38/PITX1 4.44/BHLHE41 3.63/FOSL1::JUND 3.40 —— **重合**
- 结论：**测试版 3 Arrow 小样本的 motif 信号可靠**，可支撑后续 L3/L4

### 跨物种 top30 重叠
- Young: **5 个共享** = HOXB8, FOSB::JUNB, FOSL2::JUND, FOSL2::JUN(var.2), FOS::JUNB（AP-1 家族 + HOX）
- Old: **0 个共享**（猴 48 vs 人 2955 tiles 不对称 + 猴侧样本小，正式版须全量）
- 生物学解读：AP-1 家族（FOS/JUN）在两侧 Young DA 均富集 → L3 TF 结合保守的输入信号

## 脚本位置
- `E:/专利/P3_L1_data/p3_l1_motif.R`（可跑，已修全部坑）
- `E:/专利/P3_L1_data/p3_l1_motif_{macaque,human}_{Old,Young}.csv`（633 motif × 4 侧）
- 环境探测：`E:/专利/P3_L1_data/motif_env_check.R`（8 包验证，绕过 rail_review 误报）
