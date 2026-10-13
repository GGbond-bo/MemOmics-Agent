#!/usr/bin/env Rscript
# =============================================================================
# diagnose_masking.R -- 确诊 R 命名空间遮蔽 / S4 泛型劫持
#
# 用法:
#   Rscript diagnose_masking.R <函数名> <原包名> [验证对象表达式]
#   Rscript diagnose_masking.R cpm edgeR
#   Rscript diagnose_masking.R cpm edgeR 'DGEList(matrix(1:12, nrow=3))'
#
# 输出四项事实：
#   ① find()       搜索路径上谁在提供这个名字
#   ② isGeneric()  是否 S4 泛型（TRUE = 可能被泛型劫持）
#   ③ conflicts()  原包是否被遮蔽
#   ④ 显式命名空间 vs 裸调用的可调用性对比
#
# 判读: ④「显式正常 + 裸调用报错」 ⇒ 确诊遮蔽。
#       修法 = 调用点写成 <原包>::<函数>()，不要卸包/装包/换环境/换 R 版本。
# =============================================================================

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  cat("用法: Rscript diagnose_masking.R <函数名> <原包名> [验证对象表达式]\n")
  cat("例:   Rscript diagnose_masking.R cpm edgeR\n")
  quit(status = 1)
}
fn  <- args[1]
pkg <- args[2]

cat("=== R 版本 / 库路径（多版本机器先看这里）===\n")
cat("R.version :", R.version.string, "\n")
cat(".libPaths :", paste(.libPaths(), collapse = " | "), "\n\n")

cat(sprintf("=== ① find(\"%s\") -- 谁在提供这个名字 ===\n", fn))
print(find(fn))

cat(sprintf("\n=== ② methods::isGeneric(\"%s\") -- 是否 S4 泛型 ===\n", fn))
cat(methods::isGeneric(fn),
    "  (TRUE = 裸调用走 S4 dispatch，缺少对应类的方法就会报 inherited method 错)\n")

cat(sprintf("\n=== ③ conflicts() -- 原包 %s 是否被遮蔽 ===\n", pkg))
cd <- tryCatch(conflicts(detail = TRUE), error = function(e) NULL)
hit <- FALSE
if (!is.null(cd)) {
  for (nm in names(cd)) {
    if (fn %in% cd[[nm]]) { cat("  暴露处:", nm, "\n"); hit <- TRUE }
  }
}
if (!hit) cat("  （conflicts 未命中；S4 泛型劫持常常不出现于 conflicts，靠 ② 判）\n")

cat("\n=== ④ 显式命名空间 vs 裸调用 ===\n")
fq <- tryCatch(getExportedValue(pkg, fn), error = function(e) NULL)
if (is.null(fq)) {
  cat(sprintf("  %s::%s 取不到（包未载入或未导出）-- 先 library(%s)\n", pkg, fn, pkg))
} else {
  cat(sprintf("  %s::%s 可取到: TRUE\n", pkg, fn))
}

if (length(args) >= 3) {
  obj <- tryCatch(eval(parse(text = args[3])), error = function(e) {
    cat("  验证对象构造失败:", conditionMessage(e), "\n"); NULL })
  if (!is.null(obj) && !is.null(fq)) {
    ok_fq <- tryCatch({ fq(obj); TRUE },
                      error = function(e) { cat("  显式调用失败:", conditionMessage(e), "\n"); FALSE })
    ok_bare <- tryCatch({ get(fn)(obj); TRUE },
                        error = function(e) { cat("  裸调用失败  :", conditionMessage(e), "\n"); FALSE })
    cat(sprintf("\n  ===> 显式=%s  裸=%s\n", ok_fq, ok_bare))
    if (ok_fq && !ok_bare)
      cat(sprintf("  ===> 确诊【命名空间遮蔽】: 把调用点写成 %s::%s(...)；逻辑零变化，不要卸包/换环境\n",
                  pkg, fn))
    if (!ok_fq && !ok_bare)
      cat("  ===> 两者都失败 ⇒ 不是遮蔽问题，另查参数/对象类型/包版本\n")
    if (ok_fq && ok_bare)
      cat("  ===> 两者都成功 ⇒ 当前无遮蔽（注意 library() 顺序不同可能改变结论）\n")
  }
} else {
  cat("  （未给验证对象；补一个该函数应接受的类实例即可拿到确定性判定）\n")
}

cat("\n=== 附: library() 的 masked 提示不要忽略 ===\n")
cat(sprintf("若见过 \"The following object is masked from 'package:%s': %s\"，\n", pkg, fn))
cat(sprintf("修法同上 —— 调用点改成 %s::%s()。\n", pkg, fn))