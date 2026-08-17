# CellChat v2: human skeletal muscle aging — session 2026-07-04

## Proven workflow

```r
# 1. Check age column type — numeric needs binning
unique(seu$age)  # if numeric, bin with ifelse

# 2. Merge subclusters into main types
seu$celltype_main <- case_when(
  grepl("^Type_I", seu$annotation) ~ "Type_I_Fiber",
  grepl("^Type_II", seu$annotation) ~ "Type_II_Fiber",
  ...
)

# 3. Use SCT assay (not RNA) after SCTransform
DefaultAssay(seu) <- "SCT"
data.input <- GetAssayData(seu, assay = "SCT", layer = "data")

# 4. Run CellChat per condition
cellchat <- createCellChat(object = data.input, meta = meta, group.by = "celltype")
cellchat@DB <- CellChatDB.human
cellchat <- subsetData(cellchat)
cellchat <- identifyOverExpressedGenes(cellchat)
cellchat <- identifyOverExpressedInteractions(cellchat)
cellchat <- computeCommunProb(cellchat, type = "triMean")
cellchat <- filterCommunication(cellchat, min.cells = 10)
cellchat <- computeCommunProbPathway(cellchat)
cellchat <- aggregateNet(cellchat)

# 5. Merge and compare
cc_list <- list(Young = cc_young, Old = cc_old)
cellchat_merged <- mergeCellChat(cc_list, add.names = names(cc_list))

# 6. Visualize (skip diffInteraction if cell types mismatch)
compareInteractions(cellchat_merged)
netVisual_chord_gene(cc_young, slot.name = "netP")
netVisual_circle(cc_young@net$count)
netAnalysis_computeCentrality(cc_young, slot.name = "netP")  # REQUIRED before heatmap
netAnalysis_signalingRole_heatmap(cc_young, pattern = "outgoing")
rankNet(cellchat_merged, mode = "comparison")
```

## Errors & fixes

| Error | Fix |
|-------|-----|
| `No cells found` subsetting by `age == "Young"` | age was numeric (15-99); used `ifelse(age_numeric <= 34, "Young", "Old")` |
| `Layer 'data' is empty` | Default assay was SCT; changed to `assay = "SCT"` |
| `netVisual_diffInteraction` parameter length zero | Cell types differ between groups; skip diff plot |
| `netAnalysis_signalingRole_heatmap` fails | Must call `netAnalysis_computeCentrality` first |