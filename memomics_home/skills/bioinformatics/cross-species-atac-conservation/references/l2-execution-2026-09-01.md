# L2 执行实测配方（2026-09-01 · 峰对齐→归一化→rho 初探）

## 输入数据（已就位 E:/专利/P3_L1_data/file/）

| 文件 | 结构 | 说明 |
|------|------|------|
| human_GroupSE_byindividual.rds | 525,137 peaks × 40 个体 | hg38 坐标，colData 含 TSSEnrichment/nFrags/FRIP/Age/nCells 等 18 列 |
| monkey_GroupSE_byIndividual.rds | 538,420 peaks × 21 个体 | T2T-MFA8 坐标（NC_088375.1 等） |
| monkey_peaks_hg38_map.csv | 289,523 唯一行 | monkey_chr/start/end + macaque_gene/human_gene + hg38_chr/start/end（L1 基因锚定产物） |
| human/monkey_meta.csv | 40/63 行 | individual/Age/Sex/age_group 等 |

## 已保存脚本（会话 scripts/ 目录）

- `l2_1_peak_alignment.R` — 峰坐标构建 + 映射 + RBH 正交化 + M4 剔除
- `l2_2_activity_normalize.R` — RBH 矩阵提取 + CPM + log1p + Spearman + sig_cons
- `l2_3_gene_level_summary.R` — 基因对聚合 + 基因级 Spearman

## 中间产物（E:/专利/P3_L2_data/）

- `l2_alignment_prep.rds` — rd_m2/rd_h/shared/ov/ov_1to1/ov_rbh/gr_monkey/gr_human/keep_m/human_se/monkey_se
- `l2_activity_normalized.rds` — rbh/cpm_m/cpm_h/log_m/log_h/mean_m/mean_h/z_m/z_h/sig_cons/rho/keep_m/colData 两侧
- `l2_gene_level.rds` — agg（macaque_gene/human_gene/n_peaks/mean_m/mean_h/sig_cons_mean）

## 关键坑位（全部实测）

### 1. 峰字符串匹配 = 0 共有峰（归零陷阱）
```r
# ❌ 错误：坐标字符串精确匹配
shared <- intersect(mapped$hkey, rd_h$hkey)   # = 0！！
# 原因①：人 seqnames="chr1"，映射表 hg38_chr="1"（无 chr 前缀）
# 原因②（根因）：人猴峰是各自 call 的，边界不逐碱基相等，字符串相等几乎不可能
```

```r
# ✅ 正确：GenomicRanges 区间重叠
library(GenomicRanges)
gr_monkey <- GRanges(seqnames=paste0("chr", mapped$hg38_chr),
                     ranges=IRanges(start=as.integer(mapped$hg38_start),
                                    end=as.integer(mapped$hg38_end)))
gr_human <- GRanges(seqnames=as.character(rd_h$seqnames),
                    ranges=IRanges(start=as.integer(rd_h$start), end=as.integer(rd_h$end)))
ov <- findOverlaps(gr_monkey, gr_human, minoverlap=200)   # 777,279 对
```

### 2. 严格 1:1 正交化 = 信息自杀 → RBH
```r
# ❌ 严格 1:1：只留 12,600 对（丢 95%，统计功效崩）
multi_q <- names(which(table(q) > 1)); multi_s <- names(which(table(s) > 1))
keep <- !(q %in% as.integer(multi_q)) & !(s %in% as.integer(multi_s))

# ✅ RBH（reciprocal best hit）：136,654 对，重叠宽度中位 501bp
dt <- data.table(mi=q, hi=s, w=ov_width)     # ov_width = pmin(end)-pmax(start)+1
setorder(dt, mi, -w); best_m <- dt[!duplicated(mi)]
setorder(best_m, hi, -w); rbh <- best_m[!duplicated(hi)]
```

### 3. CPM 深度归一化（divideN 不等于跨物种可比）
```r
lib_m <- colSums(mh); lib_h <- colSums(mh_h)          # libsize 差 1.8 倍
cpm_m <- sweep(mh, 2, lib_m, "/") * 1e6
log_m <- log1p(cpm_m)
```

### 4. 基因级聚合索引对齐（NA 污染）
```r
# ❌ d$mean_h[hi] — hi 是 52.5 万级 SE 索引，d$mean_h 是 13.6 万 RBH 行序 → 越界 NA
# ✅ 加 row_id 按 RBH 行序取
gene_dt[, row_id := seq_len(nrow(gene_dt))]
gene_dt[, mean_h_g := d$mean_h[row_id]]
```

### 5. R 内核跑 R 脚本用 source()
```r
# ❌ exec(open('x.R').read()) → unexpected symbol（Python 语法）
# ✅ source('path', encoding='utf-8')
```

## 核心结果（2026-09-01）

| 指标 | 值 |
|------|-----|
| 猴峰映射 hg38 成功 | 289,523 / 538,420 |
| 全量区间重叠对 | 777,279（猴 230,210 / 人 227,814 覆盖） |
| 严格 1:1 对 | 12,600 |
| **RBH 正交对** | **136,654**（重叠中位 501bp，≥300bp 99.5%） |
| 跨峰 Spearman ρ | **-0.0039** |
| 基因对 | 7,456（中位 5 峰/基因对） |
| 基因级 Spearman ρ | **0.0085** |

**解读（重要）**：峰级/基因级 ρ≈0 不是技术 bug——零膨胀低、CPM 后分布接近（猴 0.63-2.67 / 人 0.87-2.66）排除深度差 → 是生物学事实（峰级可及性哺乳动物间发散快，Andrews 2023）。**L2 专利价值在 species×age 交互，不依赖总体 ρ**。ρ≈0 只能作为"峰级活性高度物种特异"的背景陈述；核心结论必须从"哪些峰衰老轨迹跨物种同向/分歧"（混合效应交互项）里出。

## 下一步（承接）

1. species×age 交互混合效应模型：pseudobulk 个体级 → 直接 `lm`/`limma`（无需随机效应，个体已是独立样本）
2. 猴 20 个体（剔 M4）4 组 / 人 40 个体 Age 连续 → 按 stage 标签（age-group-unification.md）对齐
3. S_acc 合成 → CRECS（权重 0.3，S_seq 来自 L1 v4）