# =============================================================================
# batch_coverage_preflight.R —— 协变量可用性预检（只读，不写分析结果）
#
# 用途：在把用户提供的外部表（batch / 用药 / 处理组）加进 DEG 模型之前，
#       先算清「能不能加」。三道门：命名对得上 → 覆盖够 → 不与设计共线。
#
# 为什么需要：用户给表 ≠ 表能进模型。实测踩过——用户表的编号在不同组间复用
#   （Old_2/4/5/10/13/17/23 = OD 组；Old_1C..Old_10C 带 C 后缀才是 O 组），
#   结果最需要批次校正的两个正交比较一个样本都拿不到，而脚本照样跑完出表。
#
# 用法（集群）：
#   Rscript --vanilla batch_coverage_preflight.R > batch_probe.log 2>&1
# 输出：stdout 报告 + 5 张 csv 到 OUT 目录
#
# ⚠️ 本脚本本身也是踩过坑改写来的，注意两处注释标记 [坑]
# =============================================================================
suppressPackageStartupMessages({ library(Seurat); library(Matrix) })

## ======================== 参数（改为你的数据） ==============================
RDS     <- "/path/to/object.rds"     # Seurat 对象
OUT     <- "/path/to/outdir/batch_probe"
LIB_COL <- "library"                 # 文库列（若不存在则退化为 samplename）
SMP_COL <- "samplename"              # 样本列（Pre/Post 级）
IND_COL <- "individual"              # 个体列（生物学重复）
GRP_COL <- "type"                    # 分组列
ANN_COL <- "annotation_L3"           # 亚群列（仅用于打印，不参与判定）

## 用户提供的协变量表：两列 (id, value)。id 必须能与 LIB_COL/SMP_COL 对上。
## ⚠️ 用户常写成连字符（Y16-1-1），对象里是下划线（Y16_1_1）——下面统一归一化。
COVARIATE <- data.frame(
  id = c("Y16-1-1", "Y16-2-1"),      # ← 替换成用户的完整清单
  value = c(1, 1),
  stringsAsFactors = FALSE
)

## 比较组定义（两侧均为分组列的取值）
COMPARISONS <- list(
  A_vs_B = c("Y_Pre", "O_Pre")
)

## ========================= 工具 =============================================
CAT <- function(...) cat(..., "\n")
norm_id <- function(x) gsub("[-. ]", "_", tolower(as.character(x)))

## ========================= 0. 读入 ==========================================
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)
obj <- readRDS(RDS)
md  <- obj@meta.data
CAT("[dim]", nrow(obj), "genes x", ncol(obj), "cells")

need <- c(LIB_COL, SMP_COL, IND_COL, GRP_COL)
for (n in need) CAT(sprintf("  %-12s exists=%s", n, n %in% colnames(md)))
missing <- setdiff(need, colnames(md))
if (length(missing)) stop("缺列：", paste(missing, collapse = ", "))

## ============ 1. 三层嵌套核对（individual → samplename → library）===========
smp <- unique(md[, need])
for (cl in need) smp[[cl]] <- as.character(smp[[cl]])
CAT(sprintf("\n[结构] library=%d | samplename=%d | individual=%d | group=%d",
            length(unique(smp[[LIB_COL]])), length(unique(smp[[SMP_COL]])),
            length(unique(smp[[IND_COL]])), length(unique(smp[[GRP_COL]]))))

chk1 <- tapply(smp[[SMP_COL]], smp[[LIB_COL]], function(x) length(unique(x)))
chk2 <- tapply(smp[[IND_COL]], smp[[SMP_COL]], function(x) length(unique(x)))
CAT("[嵌套] 每 library 对应 samplename 数:", paste(sort(unique(chk1)), collapse = ","),
    "（全 1 = 严格嵌套）")
CAT("[嵌套] 每 samplename 对应 individual 数:", paste(sort(unique(chk2)), collapse = ","))

## ============ 2. 匹配用户表（门 1：命名）====================================
COVARIATE$id_n <- norm_id(COVARIATE$id)
smp$id_n <- norm_id(smp[[LIB_COL]])
smp$cov  <- COVARIATE$value[match(smp$id_n, COVARIATE$id_n)]

# 若 library 级对不上，再试 samplename 级
if (all(is.na(smp$cov))) {
  CAT("\n[匹配] library 级 0 命中 → 回退 samplename 级")
  smp$id_n <- norm_id(smp[[SMP_COL]])
  smp$cov  <- COVARIATE$value[match(smp$id_n, COVARIATE$id_n)]
}

CAT(sprintf("\n[匹配] 上层对象 %d 个中命中 %d | 未命中 %d",
            nrow(smp), sum(!is.na(smp$cov)), sum(is.na(smp$cov))))

## [硬规则] 未命中必须列出具体 ID + 模糊候选，否则用户无法判断是"少给了"还是"名字写错"
unhit <- unique(smp[[LIB_COL]][is.na(smp$cov)])
if (length(unhit)) {
  CAT("\n[未命中] 前 20 个：", paste(head(unhit, 20), collapse = ", "))
  all_ids <- unique(smp[[LIB_COL]])
  CAT("\n[模糊候选]（供判断是否只是命名差异）：")
  for (u in head(unhit, 10)) {
    cand <- agrep(u, all_ids, max.distance = 0.2, value = TRUE)
    if (length(cand)) CAT(sprintf("  %-14s -> %s", u, paste(head(cand, 3), collapse = " | ")))
  }
  # 用户表里有、对象里没有的条目 = 名字写错了或对象不含该样本
  orph <- setdiff(COVARIATE$id, unique(smp[[LIB_COL]]))
  if (length(orph)) {
    CAT("\n[用户表里对象中不存在] ", paste(head(orph, 20), collapse = ", "))
    for (o in head(orph, 10)) {
      cand <- agrep(o, all_ids, max.distance = 0.3, value = TRUE)
      if (length(cand)) CAT(sprintf("  %-14s -> %s", o, paste(head(cand, 3), collapse = " | ")))
    }
  }
}

## [坑] aggregate() 默认 na.action = na.omit 会把协变量为 NA 的整行吃掉，
##      导致汇总表行数少于 samplename 数、覆盖率被低报。必须 na.action = na.pass。
smpsum <- aggregate(cov ~ ., data = smp[, c(SMP_COL, IND_COL, GRP_COL, "cov")],
                    FUN = function(x) if (all(is.na(x))) NA else unique(na.omit(x)),
                    na.action = na.pass)
stopifnot(nrow(smpsum) == length(unique(smp[[SMP_COL]])))   # 吃掉行就当场炸
write.csv(smpsum, file.path(OUT, "cov_by_samplename.csv"), row.names = FALSE)

## ============ 3. 每个分组下完整个体名单（门 1 的核心证据）==================
CAT("\n===== 每个分组下的个体名单 + 协变量值 =====")
for (g in sort(unique(smpsum[[GRP_COL]]))) {
  sub <- smpsum[smpsum[[GRP_COL]] == g, ]
  CAT(sprintf("\n=== %s (%d samplename) ===", g, nrow(sub)))
  for (i in seq_len(nrow(sub)))
    CAT(sprintf("   %-18s %-16s cov=%s", sub[[SMP_COL]][i],
                sub[[IND_COL]][i], ifelse(is.na(sub$cov[i]), "NA", sub$cov[i])))
}

## ============ 4. 共线性：全局 + 组内（门 3）=================================
ind <- unique(smpsum[, c(IND_COL, GRP_COL, "cov")])
ok  <- ind[!is.na(ind$cov), ]
if (nrow(ok) > 4 && length(unique(ok$cov)) > 1) {
  ct <- table(ok[[GRP_COL]], ok$cov)
  suppressWarnings(cs <- tryCatch(chisq.test(ct), error = function(e) NULL))
  if (!is.null(cs)) {
    v <- sqrt(as.numeric(cs$statistic) / (sum(ct) * (min(dim(ct)) - 1)))
    CAT(sprintf("\n[共线] 全局 Cramer's V = %.3f (p = %.4g)；V>0.8 = 强共线", v, cs$p.value))
  }
  CAT("\n⚠️ 全局 V 会骗人 —— 必须看组内分布：")
  print(ct)
  CAT("\n[共线] 组内是否有空单元格（某组完全没有某个协变量水平 = 该组内不可分离）：")
  print(ct == 0)
}

## ============ 5. per-comparison 覆盖率（门 2）==============================
CAT("\n===== 每个比较组两侧的协变量覆盖（samplename 级）=====")
res <- do.call(rbind, lapply(names(COMPARISONS), function(nm) {
  g <- COMPARISONS[[nm]]
  s1 <- smpsum[smpsum[[GRP_COL]] == g[1], ]
  s2 <- smpsum[smpsum[[GRP_COL]] == g[2], ]
  n1 <- sum(!is.na(s1$cov)); n2 <- sum(!is.na(s2$cov))
  data.frame(comparison = nm,
             side1 = g[1], n1_total = nrow(s1), n1_cov = n1,
             side2 = g[2], n2_total = nrow(s2), n2_cov = n2,
             # 判定与 DEG 脚本保持一致：两侧均 >=2 才可用
             cov_usable = (n1 >= 2 && n2 >= 2),
             stringsAsFactors = FALSE)
}))
print(res, row.names = FALSE)
write.csv(res, file.path(OUT, "cov_coverage_by_comparison.csv"), row.names = FALSE)

## ============ 6. 嵌套判定：能否加进配对模型（门 3）=========================
# 每个 individual 内协变量是否唯一 → 唯一 = 完全嵌套于 individual
# = 配对比较里会被 (1|individual) 吸收，再加就秩亏
nv <- tapply(ind$cov, ind[[IND_COL]], function(x) length(unique(na.omit(x))))
CAT(sprintf("\n[嵌套] 每个 individual 内协变量水平数: %s  （全 1 = 完全嵌套于 individual）",
            paste(sort(unique(nv)), collapse = ",")))
if (all(nv <= 1, na.rm = TRUE))
  CAT("  ⇒ 配对比较不要加它（RE 已吸收）；只在独立比较里加")

write.csv(smp, file.path(OUT, "row_level_full.csv"), row.names = FALSE)
CAT("\n[done] 诊断表已写入", OUT)
CAT("\n下一步：覆盖率不足的组先回报用户补数据，⛔ 不要直接写模型代码")