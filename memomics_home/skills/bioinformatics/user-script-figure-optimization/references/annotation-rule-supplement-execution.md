# 标注规则「补标」执行协议 + R 脚本静默失败定位

配套：`references/volcano-label-rule-audit.md`（那一份讲**审计**：为什么这个点没标）。
本份讲**用户勾选「② 只补标该基因」之后怎么执行**，以及执行中撞到的两个 R 坑。

实测背景：人骨骼肌 5 对比 × 8 MF 亚群火山图（用户 notebook 原稿样式，脚本 `42_volcano5_8sub_FINAL.R`）。
用户先问「标记标准是什么 / 为什么 TMSB4X 没标」，审计完给他 A/B/C/D 勾选，**用户选 B = 只补标 TMSB4X 一处**。

---

## 1. 为什么用白名单，而不是改门槛

| 做法 | 后果 |
|---|---|
| 改全局门槛（如 `filter(fdr <= 0.001)` → 放宽） | **连带改动该图全部标签**：本例另有 31 个中等显著行会被放进池、Aging 还会冒出 `\|coef\|=2.500` 的 RSS 点 → **超出「只改指定项」授权** |
| 白名单单点补标 | 0 副作用，可溯源，其余标签一个不动 |

⇒ 用户偏好「只改指定项」时，**默认走白名单**；把 C（改门槛）的**波及范围**写进选项说明里再让他选。

## 2. 白名单补标实现（`sheet/celltype/group/gene` 四元组）

```r
# ── 顶层：白名单（四元组唯一确定一行；写成可扩展的表，不是散落的 if）────────
EXTRA_LABELS <- data.frame(
  sheet    = "O_Pre_vs_OD_Pre",   # 对比（xlsx sheet 名，不是组别名）
  celltype = "OTUD1+(I)",
  group    = "up",
  gene     = "TMSB4X",
  stringsAsFactors = FALSE)

# ── 循环内、top_genes 算完、画图之前 ────────────────────────────────────
top_genes$source <- "top5"                                   # 溯源列
top_genes <- as.data.frame(top_genes, stringsAsFactors = FALSE)
ex <- EXTRA_LABELS[EXTRA_LABELS$sheet == cs$sheet, , drop = FALSE]
if (nrow(ex) > 0) for (i in seq_len(nrow(ex))) {
  hit <- which(aging$gene == ex$gene[i] &
               as.character(aging$celltype) == ex$celltype[i] &
               aging$group == ex$group[i])
  stopifnot(length(hit) == 1)                                # 硬校验：必须精确命中 1 行
  supp <- data.frame(gene = aging$gene[hit], celltype = aging$celltype[hit],
                     coef = aging$coef[hit], fdr = aging$fdr[hit],   # 从数据取，不写死
                     group = aging$group[hit], source = "manual_supplement",
                     stringsAsFactors = FALSE)
  cat("#TASK:PARAM 补标=", ex$gene[i], " | coef=", round(aging$coef[hit],4),
      " | fdr=", signif(aging$fdr[hit],3), " (规则外补标)\n", sep = "")
  top_genes <- dplyr::bind_rows(top_genes, supp)              # 不要用 base::rbind，见 §4
}
```

要点：
- **coef/fdr 从数据里取，不写死数值** —— 写死等于在脚本里埋一个会过期的复制品
- `stopifnot(length(hit) == 1)`：命中 0 行（名字/亚群/方向写错）或 >1 行（四元组不唯一）都**立刻报错**，
  不要让补标静默失败或标错点
- `group` 用 `up`/`down` 与脚本里的分组列一致（本例 `group = ifelse(coef > 0, "up", "down")`）
- 标签 CSV 导出时带上 `source` 列 → 事后能分清「规则内 top5」与「规则外补标」

## 3. 补标的三条纪律

| 纪律 | 理由 |
|---|---|
| **不改样式**（同一 `geom_text_repel` 层、同一 `red4`/`blue4`） | 用户只说「补标」，未要求视觉区分；另加样式 = 未经授权的改动 |
| **只补点名的那个点，不顺手补别的** | 顺手补 = 变成批量改动，越过「只改指定项」 |
| **主动说明坐标轴范围没变** | 该点本来就画在图上（只是没有名字），`ymax` 早就是它；不说用户会怀疑图被改大了 |

## 4. 验收三件套（缺一不可，全部要数字）

1. **图上 OCR 直读**出该基因名：`vision_describe(dm_png)` → 本次 `TMSB4X @(3374,406) 置信 1.0`
2. **汇总表 `n_labels` 恰好 +1**：本次 DM 80 → 81，其余四图 80 / 65 / 80 / 80 **一个没变**
3. **全库补标行数 == 1**：逐图读 `*_toplabels.csv` 数 `source == "manual_supplement"` → 证明无越权补标
   ```r
   sum(sapply(c("Aging","DM","Ex_Young","Ex_Old","Ex_DM"),
     function(x) sum(read.csv(paste0(".../fig_volcano_", x, "_8sub_FINAL_toplabels.csv"))$source == "manual_supplement")))
   # → 1
   ```

## 5. 老版必须留（用户说「老版保留」= 覆盖前先备份）

```
task3/figures/_v1_top5only/          # cp 老版 5 图 × 4 格式 = 20 文件，之后才允许覆盖
task3/scripts/xx_FINAL_v1.bak.R      # 脚本老版（小文件直接 cp）
```

- **不要等用户问「老版还在吗」**。「老版保留」是交付前的动作，不是交付后的补救
- 一个脚本循环出 5 张图、只有 1 张真变化时：照跑全量（同脚本同参数、内容确定），
  但汇报里要点明「另外 4 张标签数不变，只是文件被重写了一遍」—— 不要含糊成「都改了」

---

## 6. 坑：`base::rbind()` 追加 dplyr tibble

```
numbers of columns of arguments do not match
```

`top_genes` 经 dplyr 管道产出是 `tbl_df`；即使两边**列数一致**，`base::rbind()` 也会校验失败。
⇒ 一律改用 **`dplyr::bind_rows()`**（能安全混用 tibble / data.frame）。
兜底：先 `as.data.frame(top_genes, stringsAsFactors = FALSE)` 降级成普通 data.frame。

已记入 `cns-visualization` 技能库（`record_error`，Common Issues）。

## 7. R 脚本「静默失败」定位配方（无任何输出就报错时）

**现象**：`source(script)` 直接抛错，但 stdout 里**看不到脚本前面已打印的任何 `cat`**
（输出随错误一并丢弃）→ 看不出挂在第几步。此时**不要盲猜、不要原样重跑**，逐表达式钉死：

```r
exprs <- parse("脚本.R", encoding = "UTF-8")     # 一个顶层语句 = 一个元素
env <- new.env(parent = globalenv())
for (i in seq_along(exprs)) {
  ln <- attr(exprs[[i]], "srcref")[1]
  ok <- TRUE
  withCallingHandlers(                       # ⚠️ 必须在 tryCatch 内侧，否则永不触发
    tryCatch(eval(exprs[[i]], envir = env), error = function(e) ok <<- FALSE),
    error = function(e) {
      cat("FAIL expr", i, "行", ln, ":", conditionMessage(e), "\n")
      cl <- sys.calls()
      for (k in seq_len(min(20, length(cl))))
        cat(sprintf("[%02d] %s\n", k, paste(deparse(cl[[k]])[1], collapse = "")))
    })
  if (!ok) break
}
```

实测输出（一次定位成功）：

```
[17] rbind(top_genes, data.frame(gene = aging$gene[hit], celltype = ...
[18] rbind(deparse.level, ...)
[19] stop("numbers of columns of arguments do not match")
```

三个关键点：
- **挂在 `for` 循环表达式里时**（整个循环是一个 expr）：先 `eval` 前置语句，再把
  `env$COMPS` 覆写成**只含出问题的那一项**（`list(list(label="DM", sheet="O_Pre_vs_OD_Pre"))`），
  单独 eval 循环表达式 → 调用栈里就能看到循环体内具体那一行
- `sys.calls()` 里的字面调用（`[17] rbind(...)`）就是答案，比读代码猜快得多
- ⚠️ **`withCallingHandlers` 包在 `tryCatch` 外面时永远不触发**（错误被 tryCatch 直接 unwind 掉）——
  症状是「循环好像跑完了、却没打印 FAIL」，会白绕好几轮。判断依据：看不到 FAIL 行但产物缺失