# ============================================================
# ArchR 注释写回模板（用户在自己集群上直接用）
# 适用：用户用 ArchR 跑完聚类，想把跨物种对齐注释写回 Project
# 输入: ArchR Project + markerList CSV（getMarkerFeatures 输出，含 Log2FC/FDR）
# 输出: Project cellColData 新增 anno_human 列 → saveArchRProject
# ============================================================
library(ArchR)

# 1. 加载 ArchR Project
proj <- loadArchRProject("你的ArchRProject路径")  # 改这里

# 2. 注释映射: cluster → 注释名
#    能对齐参考物种的用参考名；人脑独有按 marker 命名；低置信保留原文（不硬套）
anno_map <- c(
  # --- 对齐参考命名（依据: markerList top markers）---
  C1="OPC", C2="OPC", C3="OPC", C4="OPC", C5="OPC", C6="OPC",  # CSPG4/MYT1/SOX6
  C7="Astrocyte", C8="Astrocyte", C9="Astrocyte", C10="Astrocyte",
  C11="Astrocyte", C12="Astrocyte",                             # GFAP/AQP4/SLC1A2
  C14="MGE_SST_Inh", C15="MGE_PVALB_Inh", C16="CGE_Inh",       # DLX/LHX6+MGE; CNR1/LAMP5+CGE
  C20="Microglia", C22="Microglia", C23="Microglia_activated",  # CX3CR1/P2RY12; CXCL10 活化
  C21="Macrophage",                                             # CCL18/CCL3/CCL23 血管相关巨噬（勿标 VS）
  C30="ODC",                                                    # OPALIN/MAG/KLK6
  # --- 参考物种无精确对应的（marker 命名, ATAC 证据候选级加 * / like）---
  C17="CTX_deep_Ex",          # FEZF2/BCL11B 深层皮层
  C18="CA1_SUB_like_Ex",      # SSTR3+SATB2, WFS1/SORL1 未命中→候选
  C19="CA1_like_Ex",          # SSTR3/NRGN, WFS1/SORL1 未命中→候选
  # --- 低置信/噪声（保留原文, 不硬套）---
  C13="C13_artifact", C25="C25_noise", C26="C26_noise",
  C28="C28_lowconf", C29="C29_lowconf"
)

# 3. 取当前 cluster 列（ArchR 默认列名 "Clusters"，以实际 Project 为准）
cd <- getCellColData(proj)
stopifnot("Clusters" %in% colnames(cd))  # 列名不同就改这里

# 4. 校验：每个 cluster 都必须有映射（防漏注释）；映射里多余的 cluster 也警告
missing <- setdiff(unique(cd$Clusters), names(anno_map))
if (length(missing) > 0) stop("缺少映射的 cluster: ", paste(missing, collapse=", "))
extra <- setdiff(names(anno_map), unique(cd$Clusters))
if (length(extra) > 0) warning("映射中存在实际没有的 cluster: ", paste(extra, collapse=", "))

# 5. 写回 Project（关键：按 rownames 对齐 cells，force=TRUE 覆盖旧列）
proj <- addCellColData(proj, data=unname(anno_map[as.character(cd$Clusters)]),
                       name="anno_human", cells=rownames(cd), force=TRUE)
saveArchRProject(proj)

# 6. 输出注释分布核对
print(table(anno_map[as.character(cd$Clusters)]))
cat("\n完成: anno_human 已写入 Project 并保存\n")

# ============================================================
# 陷阱速查
# P1: ArchR 存 factor — as.character() 后再 map，map8[factor] 有整数索引 bug
# P6: 血管 marker (FOXC2/FOXF2/CLDN5) + CCL 趋化因子家族同时出现 → Macrophage 不是 VS
# P7: markerList 可能没有预期全部 cluster（human_40 实际 28 个，无 C24/C27）— 用 stopifnot 显式校验
# 关键: markerList CSV 本身就是 getMarkerFeatures 输出 — 注释不需要再跑 getMarkerFeatures
# ============================================================