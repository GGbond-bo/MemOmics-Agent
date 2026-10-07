#!/usr/bin/env Rscript
# audit_r_package_api.R — 「版本 + 签名」审计探针
# 用途：写分析脚本【之前】跑一次，避免照 skill/文档假定的版本硬写（实装版本常与文档不同，
#       如 skill 名 cellchat-v2 但机器上实装 CellChat 1.6.1）。
#       一次调用打印全部结论 —— 不要一个函数一次调用地逐个探（会触发循环检测形态）。
#
# 用法（用目标库所在那个 R 小版本的 Rscript 绝对路径跑）：
#   Rscript audit_r_package_api.R CellChat
#   Rscript audit_r_package_api.R CellChat createCellChat computeCommunProb filterCommunication
#   Rscript audit_r_package_api.R Seurat DefaultAssay GetAssayData
#
# 输出：R 版本 / .libPaths / 包版本与所在库 / library() 实测加载结果 / 逐函数 args() 实测签名

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("用法: Rscript audit_r_package_api.R <pkg> [func1 func2 ...]")
pkg <- args[1]
fns <- if (length(args) > 1) args[-1] else NULL

cat("== ", R.version.string, " ==\n", sep = "")
cat(".libPaths():\n")
cat("  ", .libPaths(), "\n", sep = "")
cat("\n")

loc <- tryCatch(find.package(pkg, quiet = TRUE), error = function(e) NA_character_)
if (is.na(loc)) {
  cat(sprintf("[X] 包 '%s' 不在当前 .libPaths() 中。\n", pkg))
  cat("    包可能装在【另一个 R 小版本的库】里 —— 先扫盘定位，再用那个版本的 Rscript 重跑：\n")
  cat(sprintf("    find \"E:/R-libs\" \"C:/Users/<user>/AppData/Local/R\" \"C:/Program Files/R\" -maxdepth 3 -iname \"%s\" -type d\n", pkg))
  quit(status = 2)
}

cat(sprintf("[OK] %s %s  @ %s\n\n", pkg, as.character(packageVersion(pkg)), loc))

# 只读 DESCRIPTION 的 requireNamespace() 会漏报坏 DLL —— 一律用 library() 实测加载
loaded <- suppressWarnings(suppressMessages(
  tryCatch({ library(pkg, character.only = TRUE); TRUE },
           error = function(e) { cat("!! library() 加载失败:", conditionMessage(e), "\n"); FALSE })
))
if (!loaded) {
  cat("   -> 缺依赖/跨小版本 DLL 不匹配。先补齐报错点名的那个包，或改用该包所属 R 小版本的库。\n")
  quit(status = 1)
}

ns <- asNamespace(pkg)
if (is.null(fns)) {
  cat("(未指定函数名 -> 列出该 namespace 全部对象，最多 200 个)\n")
  fns <- utils::head(sort(ls(ns)), 200)
}

for (f in fns) {
  cat("\n### ", f, "\n", sep = "")
  obj <- tryCatch(get(f, envir = ns), error = function(e) NULL)
  if (is.null(obj)) {
    cat("  (该 namespace 中不存在)\n")
  } else if (is.function(obj)) {
    print(args(obj))
  } else {
    cat("  (非函数) ")
    print(utils::str(obj, max.level = 1))
  }
}

cat("\n== 审计完成：以上均为实测值；与 skill / 官方文档不一致时【以实测为准】 ==\n")
cat("== 提醒：数量级类基线也顺手核一下（如 CellChatDB.human = 1939 互作对 / 41787 geneInfo） ==\n")