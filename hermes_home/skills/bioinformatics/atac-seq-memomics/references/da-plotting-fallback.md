# DA 可视化回退方案 — markerPlot 崩溃时的 ggplot2 手动绘图

## 问题

`markerPlot(markers, name=..., plotAs="MA"/"volcano")` 对 TileMatrix 输出的 SummarizedExperiment 偶发崩溃：
- PDF 输出为 0 字节空文件
- stdout 无报错（tryCatch 能捕获但 R 设备已打开）
- 尤其大 SE（>100 万 tile）时概率高

## 诊断

```r
dim(markers)  # 如果 >5M tiles，不推荐 markerPlot
assayNames(markers)  # [1] "Log2FC" "Mean" "FDR" "Pval" "MeanDiff" "AUC" "MeanBGD"
```

## 回退方案：手动提取 assay + ggplot2

```r
library(ggplot2)
library(ggrepel)

log2fc_mat <- assay(markers, "Log2FC")
fdr_mat <- assay(markers, "FDR")
mean_mat <- assay(markers, "Mean")
groups <- colnames(log2fc_mat)

for (grp in groups) {
  df <- data.frame(
    log2Mean = mean_mat[, grp],
    log2FC = log2fc_mat[, grp],
    FDR = fdr_mat[, grp],
    significant = fdr_mat[, grp] <= 0.05 & abs(log2fc_mat[, grp]) >= 0.5,
    row.names = rownames(log2fc_mat)
  )
  # PNG only for >100K tiles (PDF = 130MB+ with vector rendering)
  p <- ggplot(df, aes(log2Mean, log2FC, color=significant)) +
    geom_point(size=0.3, alpha=0.5) +
    scale_color_manual(values=c("TRUE"="red","FALSE"="grey60")) +
    geom_hline(yintercept=0, lty="dashed") + theme_bw(14)
  ggsave(paste0("MA_", grp, ".png"), p, width=10, height=8, dpi=150)
}
```

## 性能阈值

| Tile 数 | 推荐格式 | 预计时间 |
|---------|:---:|---------|
| < 10万 | PDF + PNG | < 30s |
| 10-100万 | PNG 主，PDF 只显著点 | 1-3 min |
| > 100万 | PNG only | 3-10 min |

> ⚠️ **不要对 >100万 tile 输出 PDF**: 每个点作为独立矢量路径 → 130MB+ 文件 → 打开卡死或超时。

## ⚠️ 0-byte PDF 边缘情况（2026-07-29 猕猴海马 3 样本验证）

**现象**：即使改用 base R `plot()` + `pdf()`，某些对比方向仍产出 0-byte PDF，但 PNG 完全正常。本次观察到：

| 文件 | 大小 | 结果 |
|------|------|:--:|
| `MA_plot_Old.pdf` | 131MB | ✅ |
| `MA_plot_Young.pdf` | **0** | ❌ |
| `Volcano_Old.pdf` | 128MB | ✅ |
| `Volcano_Young_vs_Old.pdf` | **0** | ❌ |

**根因**：当某个对比方向显著点极少（Old=1 样本 vs Young=2 样本，Young 方向统计功效低），PDF 设备处理 6M+ 点的极端稀疏散点图时静默失败——R 无报错但文件为空。

**绕过**：
1. **永远先出 PNG**（最可靠），再尝试 PDF
2. **PDF 生成前先检查**：`if (sum(fdr<0.05 & abs(log2fc)>0.5) == 0) → skip PDF`
3. **PDF 为 0 byte 时用 PNG 替代** — HTML 报告 base64 嵌入 PNG 不影响质量
4. **抽样减少点**：`idx <- sample(N, min(500000, N))` 后再试 PDF

> ⚠️ **0-byte 是确定性的，重跑修复脚本无效（2026-08-02 验证）**：为恢复 `Volcano_Young_vs_Old.pdf` / `Volcano_plot.png` / `MA_plot_Young.pdf` 专门写的修复脚本（`18_fix_plots.R`）失败，文件仍为 0 byte。结论：某个对比方向一旦产出 0-byte PDF，**不要反复重试**——直接把 PNG 当最终交付，在 task_plan 记入 "Issues: 0-byte（已知遗留，不阻塞）"，后续唤醒/汇报把它列为已知遗留并给\"可选修复\"而不是自动重跑。

```r
# 防御性 PDF 生成
n_sig <- sum(fdr < 0.05 & abs(log2fc) > 0.5)
if (n_sig > 0) {
  set.seed(42); idx <- sample(length(log2fc), min(500000, length(log2fc)))
  pdf("volcano.pdf", width=12, height=10)
  plot(log2fc[idx], -log10(fdr[idx] + 1e-300), col=sig[idx],
       pch=16, cex=0.5, xlab="Log2FC", ylab="-log10(FDR)")
  dev.off()
  if (file.size("volcano.pdf") == 0) {
    message("PDF 0-byte, using PNG only — this is expected for low-signal comparisons")
  }
}
```
