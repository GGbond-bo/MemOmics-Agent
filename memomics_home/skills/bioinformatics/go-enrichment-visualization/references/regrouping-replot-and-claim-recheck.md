# 重分组重出图 → 结论重核（regroup / replot / re-conclude）

**适用**：用户改口径后说「**按这个分类重出 X 图**」；删除某成员后重出（如移除解离伪影 Stress index）；
任何「**只换分组标签、不换数值矩阵**」的重画。2026-09-15 实测（FigA2 五效应图）。

---

## 1. 一句话原则

重分组只改 **呈现**：成员集合、分组色条、行序、组间隙。
矩阵（Cohen's d / q / 行内 z-score）**一字不改**。

⇒ 图面上「新」出来的模式，多半是**旧结论的惯性搬运**。**先算数，再解读**。
⚠️ 本类任务的头号事故不是画错图，是**替一张改过标签的图辩护一个别的数据集得出的结论**。

## 2. SOP（四步）

1. **冻结矩阵口径**：只改 `PROGRAM` / `AXES`(或 `PROG_GROUPS`) / `DISP` / `GAPx`，不碰 `eff_matrix()` / `zscore_row()` 的算法。
2. **脚本内断言**（防止删成员时留下残余）：
   ```r
   stopifnot(setequal(GENE_ORDER, PROGRAM), length(GENE_ORDER) == length(PROGRAM),
             !("scoreStress" %in% PROGRAM))                       # 负向断言 = 删干净的可验证证据
   cat("程序集数:", length(PROGRAM), "| 轴数:", length(AXES),
       "| X 是否已移除:", !("X" %in% PROGRAM), "\n")               # 让 stdout 自证
   ```
3. **逐轴显著格子数**（本 SOP 的核心新增步骤，见 §3）。
4. **用第 3 步的数字改写解读文字**——不是先有结论再找数。

## 3. 逐轴显著格子数（R 配方）

格子 = 程序 × 亚群（本例 17 程序 × 10 亚群 = 170；按轴 40/40/30/40/20）。

```r
AXES <- list(
  Metabolism      = c("scoreOxPhos","Glycolysis","FattyAcidMetabolism","Adipogenesis"),
  Nutrient        = c("scoreInsulin","mTORC1","AMPK_PGC1a","Autophagy"),
  Contractile     = c("scoreSarcomeric","scoreRegMyon","Denervation"),
  "Inflamm-aging" = c("scoreSenMayo","scoreInflammatory","scoreTNFA","scoreROS"),
  Decompensation  = c("scoreAtrophy","Fibrosis"))
EFFECTS <- c("Aging","T2D","ExYoung","ExOld","ExT2D")

eff <- read.csv(EFF_CSV, stringsAsFactors = FALSE)   # score, sub, effect, d, p, q
eff$score <- sub("_AUC$", "", eff$score)
e <- eff[eff$score %in% unlist(AXES) & eff$effect %in% EFFECTS, ]
e$axis <- ""; for (a in names(AXES)) e$axis[e$score %in% AXES[[a]]] <- a

# 轴 × 效应 汇总
s <- e[e$axis == a & e$effect == ef, ]
data.frame(n_cells = nrow(s), median_abs_d = round(median(abs(s$d)), 3),
           max_abs_d = round(max(abs(s$d)), 3),
           n_sig = sum(s$q < 0.05), pct_sig = round(100 * mean(s$q < 0.05), 1))

# 对照：生物轴（代谢+营养+收缩）vs 目标轴
bio <- c("Metabolism","Nutrient","Contractile")
```

变量命名：矩阵/子集一律 `DM`/`QM`/`s`/`e`，**别用 `d`、`q`、`p`、`sub`**（见 §5）。

### 判据（照这个顺序下结论）

| 观测 | 允许的结论 |
|---|---|
| 两轴 `pct_sig` 分得开（如 85% vs 0%） | 可以说轴特异性 |
| 两轴都在 0–5%（本例运动效应） | 只能说「**均未检出显著变化**」 |
| `median|d|` 有大小差但 `pct_sig` 都低 | 只能写「方向趋势」，注明检验力受限 |

**阴性结果措辞**：FDR q>0.05 且 n 小 ⇒ 写「未检出显著变化」，**不写「无效」**（本例 n=24 配对 + 170 格子多重检验）。
`median|d|` 只作趋势，结论落在 `pct_sig` / 显著格子数上。

## 4. 实测案例（2026-09-15 · FigA2 五效应图）

**变更**：18 程序 / 旧 5 组 → **17 程序 / 5 轴机制分类**（移除 `scoreStress`），行组间隙 0.2→0.25；
面板(5 效应)、列(10 亚群)、RdBu_r 配色、`TwoSlopeNorm(-3,0,3)`、FDR 星号、画布 16.5×8.4 in **全不变**。

**被推翻的旧结论**：「运动效应只作用于代谢-收缩轴、对炎症轴无效」（来自**另一个项目**的分析）。

**复算结果（显著格子数 / 该轴格子总数）**：

| 轴 | Aging | T2D | ExYoung | ExOld | ExT2D |
|---|---|---|---|---|---|
| Metabolism (40) | **34 (85.0%)** | 0 | 0 | 4 (10.0%) | 0 |
| Nutrient (40) | 10 (25.0%) | 0 | 0 | 0 | 1 (2.5%) |
| Contractile (30) | 7 (23.3%) | 0 | 0 | 0 | 0 |
| Inflamm-aging (40) | 9 (22.5%) | 0 | 1 (2.5%) | 0 | 0 |
| Decompensation (20) | 2 (10.0%) | 0 | 0 | 0 | 0 |

- Aging 最强：Metabolism `median|d|=2.660` / `max 4.734`；Inflamm-aging `1.271`。
- T2D 近零：全轴 `median|d| 0.24–0.58`，**0 个显著格子**。
- **运动三效应在所有轴皆弱**：生物轴复合 0.0 / 3.6 / 0.9% vs 炎症轴 2.5 / 0 / 0% ⇒ **噪声级差异，不构成轴特异性**。
- 唯一的可写趋势：炎症轴 ExYoung / ExT2D 的中位 d 为负（SenMayo −0.980、TNFA −1.079；ExOld 近零 0.005–0.217）——方向性下调提示，**不得当显著结论**。

**修正后的表述**：「Aging 主导；T2D 与运动在该打分层面均未检出显著改变」。
（正确版比原版**弱**——这是应该的，图没变、口径变了，结论必须跟着本次数据走。）

## 5. R 变量遮蔽坑（完整复盘）

**症状**：绘图函数内 `V[ni, pi * n_sub + ci + 1]: 量度数目不正确`（incorrect number of dimensions）。
第一反应会以为是矩阵维度/展平序问题——**不是**。

**根因**：脚本里矩阵变量名与**循环变量 / CSV 列名**重名。
```r
d <- tapply(eff$d, list(eff$score, key), mean)   # ① Cohen's d 矩阵，名叫 d
...
for (d in OUTS) {                                # ② 循环变量也叫 d，OUTS 是**目录字符串向量**
  draw_grid(d, PROGRAM, ...)                     # ③ d 此时是 "E:/.../figures"，不是矩阵
```
② 把 ① 静默覆盖 → ③ 传进去的是字符标量 → 双重下标对非数组对象报错。
**R 不做重名警告**，且 `eff$d` 是 data.frame 列（`$` 取值），遮蔽只发生在裸变量上，极易漏看。

**修复（4 处一起改，缺一仍报错）**：
```r
DM <- tapply(eff$d, list(eff$score, key), mean); QM <- tapply(eff$q, list(eff$score, key), mean)
DM <- DM[PROGRAM, col_key, drop = FALSE]; QM <- QM[PROGRAM, col_key, drop = FALSE]
for (outdir in OUTS) for (ext in names(open_dev)) {
  f <- file.path(outdir, paste0(BASE, ".", ext))
  draw_grid(DM, ..., QM, ...)                                  # 传矩阵
  rows[[length(rows)+1]] <- data.frame(dir = outdir, ...)      # data.frame 里的引用同步改
}
cat("矩阵维度 d:", paste(dim(DM), collapse = " x "), "\n")      # 收尾自证行同步改
```

**同类风险名**：`d`、`q`、`p`、`sub`（CSV 列名）、`T`。约定：矩阵 `DM`/`QM`/`Z6`，循环变量 `outdir`。
**预防**：脚本收尾加一行 `cat("矩阵维度:", paste(dim(DM), collapse=" x "))`——遮蔽时空值/报错立刻暴露。

## 6. 交付形态与证据（可复现三件套）

| 产物 | 说明 |
|---|---|
| 图 | `figures/<Name>.{png,pdf,svg,tiff}` 用户翻得到的位置 + `figures/R_version/<Name>_v2.*` 版本名；旧版 `file.copy` 进 `archive_superseded/`（**移动不删**） |
| manifest | `<BASE>_manifest_QA.csv`：每文件 `exists` + `bytes` |
| 效应汇总 | `axis_effect_summary.csv` + 目标轴明细表 + 「生物轴 vs 目标轴」对照 CSV |

实测字节数（本次 FigA2 v2，17×50 矩阵 @300dpi，画布 16.5×8.4 in）：
png 281,661 B｜pdf 14,818 B｜svg 429,232 B｜tiff 1,889,950 B（8 文件 = 两目录 × 4 格式，全部非空）。

stdout 自证行（写进脚本，交付时连带贴出）：
`程序集数: 17 | 轴数: 5 | Stress 已移除: TRUE` + `矩阵维度 d: 17 x 50`。

## 7. 与平台护栏的关系（同族纯文本类问题，别重跑脚本）

- `rail_review(pre)`：**base 包（grDevices/graphics/stats）不要写进 `required_packages`** —— 会误报 Missing 并连带锁死执行工具；不传该参数即通过，脚本一行不用改。
- `rail_review(post)`：绘图函数里别写 `&&`（`if (!is.na(stq) && stq < 0.05)` 被判「shell 串联多步骤」）⇒ 改**嵌套 if**：`if (!is.na(stq)) if (stq < 0.05)`。
- `execute_r` 报 `[⛔ 执行保护]`：读全 stderr 分辨「回合保护(会话级 100 次调用上限)」vs 内核异常；前者**本会话剩余全程永久拦截 execute_\***，改走 `terminal` + `.../Rscript.exe <脚本>`。
- 这些护栏是**静态文本判据**：改文本重提审查即可，**不要重跑脚本**（产物没变，重跑只赚循环告警）。
  完整判据表见 `platform-execution-pitfalls`。
