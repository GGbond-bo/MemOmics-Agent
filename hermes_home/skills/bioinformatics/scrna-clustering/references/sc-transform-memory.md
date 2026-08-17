# SCTransform 内存调优指南

## 问题
SCTransform v2 在计算 corrected UMI count matrix 时需要大量内存。
~40,000 cells × ~40,000 genes → corrected UMI 全矩阵需 ~12 GB RAM。

## 症状
- R 报错: "无法分配大小为11.9 Gb的向量"
- 或长时间卡在 "Computing corrected count matrix" (>10 min)
- 或 exit code 3221225794 (OOM)

## 解决方案（按优先级）

### 1. 加载 glmGamPoi（必须）
```r
library(glmGamPoi)
```
SCTransform v2 的 NB 回归依赖 glmGamPoi。不加载会用慢速 MASS::glm.nb。

### 2. 内存设置
```r
library(future)
plan(multisession, workers=1)
options(future.globals.maxSize = 70 * 1024^3)  # 70 GB
```

### 3. 降级方案（推荐）
如果 SCTransform 仍然 OOM，直接用：
```r
seurat_obj <- NormalizeData(seurat_obj, normalization.method="LogNormalize", scale.factor=10000)
seurat_obj <- FindVariableFeatures(seurat_obj, selection.method="vst", nfeatures=3000)
seurat_obj <- ScaleData(seurat_obj, features=VariableFeatures(seurat_obj))
```
效果可靠，已验证通过 40K cells 人类骨骼肌 snRNA-seq 分析。

### 4. return.only.var.genes（部分缓解）
```r
SCTransform(seurat_obj, return.only.var.genes=TRUE, ...)
```
只减少最终输出大小，不减少 corrected UMI 计算量。单独使用效果有限。

### 5. 减少细胞数
如果必须用 SCTransform，subset 到 ≤20,000 cells。

## 已知成功配置
| 细胞数 | 基因数 | 方法 | 内存 | 结果 |
|--------|--------|------|------|------|
| 39,988 | 55,211 | NormalizeData+ScaleData | <4 GB | ✅ 14 clusters |
| 39,988 | 55,211 | SCTransform (glmGamPoi) | 需 12 GB | ❌ OOM |