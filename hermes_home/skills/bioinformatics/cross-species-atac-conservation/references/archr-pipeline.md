# ArchR 跨物种 ATAC 分析 Pipeline

## 环境要求

- R 4.6.1 (Windows, 独立安装到 C:/Program Files/R/R-4.6.1/)
- 库路径: C:/Users/USERNAME/R/R-4.6.1-library/
- ArchR 1.0.2+
- 参考基因组: BSgenome.Hsapiens.UCSC.hg38 + BSgenome.Mmulatta.UCSC.rheMac10
- 调用方式: `"C:/Program Files/R/R-4.6.1/bin/Rscript.exe" script.R`

> ⚠️ R 4.4.2 (默认) 不能装 ArchR——ArchR 需要 R≥4.5.0。两个版本并存，通过 Rscript 路径切换。

## 标准 Pipeline（每个物种独立运行）

### Step 1: 创建 Arrow 文件

```r
library(ArchR)
addArchRGenome("hg38")  # 或 "rheMac10"

ArrowFiles <- createArrowFiles(
  inputFiles = "fragments.tsv.gz",
  sampleNames = "hippocampus_human",
  minTSS = 4,
  minFrags = 1000,
  addTileMat = TRUE,
  addGeneScoreMat = TRUE
)
```

### Step 2: 质控与过滤

```r
proj <- ArchRProject(
  ArrowFiles = ArrowFiles,
  outputDirectory = "archr_output",
  copyArrows = TRUE
)

# 过滤低质量细胞
proj <- filterDoublets(proj)
proj <- proj[proj$TSSEnrichment > 4 & proj$nFrags > 1000, ]
```

### Step 3: 降维与聚类

```r
proj <- addIterativeLSI(proj, useMatrix = "TileMatrix", name = "IterativeLSI")
proj <- addClusters(proj, reducedDims = "IterativeLSI")
proj <- addUMAP(proj, reducedDims = "IterativeLSI")
```

### Step 4: Call Peaks（细胞类型特异）

```r
proj <- addGroupCoverages(proj, groupBy = "Clusters")
proj <- addReproduciblePeakSet(proj, groupBy = "Clusters")
proj <- addPeakMatrix(proj)
```

### Step 5: 差异可及性（年龄组比较）

```r
# 年龄作为连续变量
markers_age <- getMarkerFeatures(
  proj, useMatrix = "PeakMatrix",
  groupBy = "age_group",
  contrast = c("old", "young")
)
```

## 跨物种比较 Pipeline

### 1. liftover (rheMac10 → hg38)

```bash
# UCSC liftOver 工具
./liftOver monkey_peaks.bed rheMac10ToHg38.over.chain monkey_peaks_hg38.bed unmapped.bed
```

### 2. peak overlap

```r
# 计算 Jaccard 指数
human_peaks <- read.table("human_peaks.bed")
monkey_peaks_lifted <- read.table("monkey_peaks_hg38.bed")

human_gr <- GRanges(human_peaks$V1, IRanges(human_peaks$V2, human_peaks$V3))
monkey_gr <- GRanges(monkey_peaks_lifted$V1, 
                      IRanges(monkey_peaks_lifted$V2, monkey_peaks_lifted$V3))

overlap <- findOverlaps(human_gr, monkey_gr)
jaccard <- length(unique(queryHits(overlap))) / 
           (length(human_gr) + length(monkey_gr) - length(unique(queryHits(overlap))))
```

### 3. 信号强度相关性

```r
# 对重叠的 peak 比较信号强度
shared_peaks <- human_gr[unique(queryHits(overlap))]
human_signal <- getGroupSE(proj_human, groupBy="Clusters")[shared_peaks, ]
monkey_signal <- getGroupSE(proj_monkey, groupBy="Clusters")[shared_peaks, ]
spearman_rho <- cor(human_signal, monkey_signal, method="spearman")
```

### 4. 衰老动态: mixed model

```r
# lme4: accessibility ~ species + age + species:age + (1|individual)
model <- lmer(accessibility ~ species * age + (1|individual), data=combined_df)
species_age_interaction <- summary(model)$coefficients["speciesmonkey:age", "Pr(>|t|)"]
```

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| ArchR 装不上 | R<4.5.0 | 必须 R 4.6.1 |
| BiocManager 版本错 | R 4.6 需要 Bioc 3.23 | `BiocManager::install(version="3.23")` |
| liftOver 失败 | 链文件版本不对 | 从 UCSC 下载正确版本 |
| 内存溢出 | 细胞数太多 | subset 或迭代处理 |
