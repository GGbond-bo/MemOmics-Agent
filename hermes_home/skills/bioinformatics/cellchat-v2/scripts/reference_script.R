
# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", script_name="本脚本名",
#      species="物种", tissue="组织", direction="方向")
#      → 查同类运行日志，有则参考已有参数和经验，无则按原脚本执行
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
#   2. 如果通过 → skill_evolution(action="record_run",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", params_used="参数JSON", result_summary="结果",
#      quality_score=8, notes="经验总结")
#      → 记录成功运行日志，供后续同类型分析参考
#   3. 如果失败 → skill_evolution(action="record_error",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", error_message="报错", root_cause="根因",
#      fix_applied="修复方案")
#      → 记录错误日志，修正后重跑
#
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
#   ★ 强制: 图片空白/NA/过小 → 重新出图 | 图片不够 → 补图 | 代码未分段 → 重写
#   ★ 强制: 有参数有结论 → debate_analysis 辩论
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================


# =============================================================================
# Cell-Cell Communication Analysis — Core CellChat Pipeline
# =============================================================================
# Runs the complete CellChat v2 analysis: ligand-receptor identification,
# communication probability inference, pathway aggregation, and centrality.
# =============================================================================

suppressPackageStartupMessages({
    library(CellChat)
    library(Seurat)
})

#' Run complete CellChat analysis pipeline
#'
#' @param seurat_obj Annotated Seurat object
#' @param species "human" or "mouse"
#' @param group.by Metadata column with cell type annotations
#' @param db_category Which interaction categories to use:
#'   "all" (default), "Secreted Signaling", "ECM-Receptor", "Cell-Cell Contact"
#' @param min.cells Minimum cells per group for communication inference
#' @return CellChat object with all analyses computed
run_cellchat_analysis <- function(seurat_obj,
                                  species = "human",
                                  group.by = "celltype",
                                  db_category = "all",
                                  min.cells = 10) {

    cat("\n=== Running CellChat Analysis ===\n\n")

    # -------------------------------------------------------------------------
    # 1. Create CellChat object
    # -------------------------------------------------------------------------
    cat("Step 1/6: Creating CellChat object...\n")
    cellchat <- createCellChat(object = seurat_obj, group.by = group.by)
    cat("   Created CellChat object with", length(levels(cellchat@idents)),
        "cell groups\n")

    # -------------------------------------------------------------------------
    # 2. Set ligand-receptor database
    # -------------------------------------------------------------------------
    cat("Step 2/6: Setting CellChat database...\n")
    if (tolower(species) == "human") {
        CellChatDB <- CellChatDB.human
        cat("   Using CellChatDB.human\n")
    } else if (tolower(species) == "mouse") {
        CellChatDB <- CellChatDB.mouse
        cat("   Using CellChatDB.mouse\n")
    } else {
        stop("Species must be 'human' or 'mouse'. Got: ", species)
    }

    # Optionally filter to specific signaling category
    if (db_category != "all") {
        valid_cats <- unique(CellChatDB$interaction$annotation)
        if (!db_category %in% valid_cats) {
            stop("Invalid db_category '", db_category, "'. Valid options: ",
                 paste(valid_cats, collapse = ", "))
        }
        CellChatDB_use <- subsetDB(CellChatDB, search = db_category)
        cat("   Filtered to:", db_category, "\n")
    } else {
        CellChatDB_use <- CellChatDB
        cat("   Using all signaling categories\n")
    }

    cellchat@DB <- CellChatDB_use
    n_interactions <- nrow(CellChatDB_use$interaction)
    cat("   Database contains", n_interactions, "ligand-receptor interactions\n")

    # -------------------------------------------------------------------------
    # 3. Identify overexpressed genes and interactions
    # -------------------------------------------------------------------------
    cat("Step 3/6: Identifying overexpressed signaling genes...\n")
    cellchat <- subsetData(cellchat)

    # Use presto for fast Wilcoxon if available, otherwise standard
    has_presto <- requireNamespace("presto", quietly = TRUE)
    if (!has_presto) {
        cat("   (presto not installed — using standard Wilcoxon test, slower)\n")
    }
    cellchat <- identifyOverExpressedGenes(cellchat,
                                            do.fast = has_presto)
    cellchat <- identifyOverExpressedInteractions(cellchat)
    n_LR <- nrow(cellchat@LR$LRsig)
    cat("   Identified", n_LR, "overexpressed ligand-receptor pairs\n")

    # -------------------------------------------------------------------------
    # 4. Compute communication probabilities
    # -------------------------------------------------------------------------
    cat("Step 4/6: Computing communication probabilities...\n")
    cat("   (This may take 1-3 minutes depending on dataset size)\n")
    cellchat <- computeCommunProb(cellchat, type = "triMean")
    cellchat <- filterCommunication(cellchat, min.cells = min.cells)

    # Count significant interactions
    df_net <- subsetCommunication(cellchat)
    n_sig <- nrow(df_net)
    cat("   Found", n_sig, "significant cell-cell interactions\n")

    # -------------------------------------------------------------------------
    # 5. Pathway-level aggregation
    # -------------------------------------------------------------------------
    cat("Step 5/6: Aggregating at pathway level...\n")
    cellchat <- computeCommunProbPathway(cellchat)
    cellchat <- aggregateNet(cellchat)

    # Count active pathways
    pathways <- cellchat@netP$pathways
    n_pathways <- length(pathways)
    cat("   Aggregated into", n_pathways, "signaling pathways\n")

    # Print top pathways by overall information flow
    if (n_pathways > 0) {
        cat("\n   Top signaling pathways:\n")
        # Get pathway contribution
        pathway_prob <- cellchat@netP$prob
        if (!is.null(pathway_prob) && length(dim(pathway_prob)) == 3) {
            pathway_strength <- apply(pathway_prob, 3, sum)
            pathway_strength <- sort(pathway_strength, decreasing = TRUE)
            top_n <- min(10, length(pathway_strength))
            for (i in seq_len(top_n)) {
                cat(sprintf("     %2d. %-20s (strength: %.4f)\n",
                    i, names(pathway_strength)[i], pathway_strength[i]))
            }
        }
    }

    # -------------------------------------------------------------------------
    # 6. Compute network centrality
    # -------------------------------------------------------------------------
    cat("\nStep 6/6: Computing network centrality scores...\n")
    cellchat <- netAnalysis_computeCentrality(cellchat)
    cat("   Computed sender, receiver, mediator, and influencer roles\n")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    cat("\n--- Analysis Summary ---\n")
    cat("   Species:", species, "\n")
    cat("   Cell types:", length(levels(cellchat@idents)), "\n")
    cat("   L-R pairs tested:", n_LR, "\n")
    cat("   Significant interactions:", n_sig, "\n")
    cat("   Active pathways:", n_pathways, "\n")

    cat("\n✓ CellChat analysis completed!", n_sig,
        "significant interactions across", n_pathways, "pathways\n\n")

    return(cellchat)
}
