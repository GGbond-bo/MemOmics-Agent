# DA Volcano Plot — Base R 极速方案

## 问题

`markerPlot(plotAs="volcano")` 对 TileMatrix SE（>100 万 tile）：
- 600s 超时（PDF 矢量路径太多）
- ArchR 1.0.3 明确警告 `markerPlot不再有用，请用'plotMarkers'`

## 解决方案：直接从 SummarizedExperiment assay 提取 + base R plot()

```r
# === 加载 ===
.libPaths(c("USER_R_LIBS/R-4.5.3", .libPaths()))
suppressMessages(library(SummarizedExperiment))
markers <- readRDS("markers_age_tiles.rds")

# === 提取数据 ===
comp_name <- colnames(assay(markers, "Log2FC"))[1]  # 第一组比较名
log2fc <- assay(markers, "Log2FC")[, comp_name]
fdr   <- assay(markers, "FDR")[, comp_name]
negLog10FDR <- -log10(fdr + 1e-300)

# === 分类 ===
sig <- rep(rgb(0.7, 0.7, 0.7, 0.4), length(log2fc))  # NS = grey
sig[fdr < 0.05 & log2fc >  0.5] <- rgb(0.9, 0.2, 0.2, 0.6)  # Up = red
sig[fdr < 0.05 & log2fc < -0.5] <- rgb(0.2, 0.3, 0.9, 0.6)  # Down = blue

n_up   <- sum(fdr < 0.05 & log2fc >  0.5)
n_down <- sum(fdr < 0.05 & log2fc < -0.5)

# === PNG (for HTML report) ===
png("Volcano_DA.png", width=1600, height=1400, res=200)
par(mar=c(5,5,4,2))
plot(log2fc, negLog10FDR, col=sig, pch=16, cex=0.4,
     xlab="Log2 Fold Change", ylab="-log10(FDR)",
     main=paste0("Differential Accessibility: ", comp_name))
abline(h=-log10(0.05), lty=2, col="grey40")
abline(v=c(-0.5, 0.5), lty=2, col="grey40")
legend("topright",
  c(paste0("Up: ", n_up), paste0("Down: ", n_down)),
  fill=c("red", "blue"), border=NA, cex=0.8, bg="white")
dev.off()

# === PDF ===
pdf("Volcano_DA.pdf", width=10, height=8)
par(mar=c(5,5,4,2))
plot(log2fc, negLog10FDR, col=sig, pch=16, cex=0.2,
     xlab="Log2 Fold Change", ylab="-log10(FDR)",
     main=paste0("Differential Accessibility: ", comp_name))
abline(h=-log10(0.05), lty=2, col="grey40")
abline(v=c(-0.5, 0.5), lty=2, col="grey40")
legend("topright",
  c(paste0("Up: ", n_up), paste0("Down: ", n_down)),
  fill=c("red", "blue"), border=NA, cex=0.8)
dev.off()
```

## 性能

| N tiles | 耗时 | 对比 markerPlot |
|---------|------|-----------------|
| 6M | <5s | >600s（超时） |
| 1M | <1s | ~60s |

## 备注

- 2026-07-29 猕猴 scATAC 验证：6,085,841 tiles → base R 5s 产出 PNG+PDF
- 若需要 MA plot：x 轴用 `assay(markers, "Mean")[, comp_name]`, y 轴用 log2fc
- `assay(se, "AUC")` 可提取 AUC 分数用于排序 top hits
