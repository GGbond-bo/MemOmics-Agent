# ============ 海马 ATAC 8大群注释（集群版） ============
# 输入: ArchRProject rds（含 GeneScoreMatrix 的 Arrow）
# 输出: <proj>_annotated8.rds + 控制台打印 cluster→cellType8 表
# 用法: ① 改 readRDS 路径为集群路径 ② 跑完把打印的映射表贴回对话核对
# 变体: 若 rds 已有注释列（如猴侧 predictedAnno），可直接 map 到 8 大类，免 GeneScore 计算
library(ArchR)

proj <- readRDS("your_project.rds")   # ← 改成你的集群路径

# 8 大类 marker（海马 ATAC GeneScore 版，按需替换）
markers8 <- list(
  ExN   = c("SLC17A7","NEUROD2","NRGN","CAMK2A"),
  InN   = c("GAD1","GAD2","SLC32A1","DLX1"),
  Astro = c("GFAP","AQP4","SLC1A2","S100B"),
  Micro = c("P2RY12","CX3CR1","C1QB","TMEM119"),
  OPC   = c("PDGFRA","CSPG4","OLIG2"),
  ODC   = c("MBP","PLP1","MOBP"),
  VS    = c("FLT1","PECAM1","RGS5","CLDN5"),
  ChP   = c("TTR","CLIC6","IGFBP7")
)

# GeneScoreMatrix 打分（createArrowFiles 默认已生成；缺失时先 addGeneScoreMatrix）
mat <- assays(getMatrixFromProject(proj, useMatrix = "GeneScoreMatrix"))[[1]]

# cell 级每类平均 GeneScore → argmax 注释
score <- sapply(markers8, function(gs) {
  g <- gs[gs %in% rownames(mat)]
  if (length(g) == 0) return(rep(0, ncol(mat)))
  colMeans(mat[g, , drop = FALSE])
})
cell8 <- colnames(score)[apply(score, 1, which.max)]

proj <- addCellColData(proj, data = cell8, cells = rownames(getCellColData(proj)),
                       name = "cellType8", force = TRUE)

# 打印 cluster→cellType8 映射表（贴回来核对，勿自动下结论）
print(table(proj$Clusters, proj$cellType8))
saveRDS(proj, "your_project_annotated8.rds")   # ← 改成输出名

# 变体：rds 已有注释列（猴侧 predictedAnno 等）→ 直接命名向量映射，无需 GeneScore
# map8 <- c("DG Ex"="ExN","CA1_SUB s_f_Ex"="ExN",...,"Astrocyte"="Astro",...)
# proj$cellType8 <- unname(map8[as.character(proj$predictedAnno)])   # ⚠️ 必须 as.character（factor 索引坑）