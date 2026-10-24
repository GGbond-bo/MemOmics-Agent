# RUVr + MAST 逐亚群 × 多对比 DEG —— 运行手册（集群投递）

> 用户固定复用的一支脚本（`muscle_RUV_MAST.R`）：**每亚群 × 每比较组 独立跑一轮**，
> 样本级 pseudobulk 估 RUVr 因子 → 当协变量进细胞级 MAST。MF 已跑通（10 亚群 × 5 对比 = 50 csv 先例），
> 2026-10-09 复用到 MuSC（6 亚群 × 5 对比 = 30 轮，投 node4）。
> 脚本留档：`results/<sid>/scripts/muscle_RUV_MAST_MuSC.R`（全量）+ `smoke_MuSC.R`（冒烟）。

## 一、流程骨架（每轮 8 步）

1. **取亚群**：`subset(obj, cells = colnames(obj)[obj$annotation_L3 == ct])`
   —— **必须用 cell names**，⛔ 不要 `which()` 整数索引（`cells=` 语义是细胞名；传整数靠位置恰好对上才不出错，换对象顺序就取错细胞，且不报错）。
2. **样本/组校验**：每样本细胞 ≥ `min_cells`(10) → 保留；组内唯一样本 ≥2，否则跳过。
3. **配对判断**：`table(individual, type)` 双向计数 → 配对个体 ≥2 且 ≥60% 行 → 加 `(1|individual)`（`glmer`）；否则**打印告警后降级 `bayesglm`**（不许静默降级）。
   个体从 `samplename` 推：`sub("_(Pre|Post)$", "", Sample)` —— rds 里通常**没有** `individual` 列。
4. **按样本聚合**（pseudobulk）：`data_ind <- mat %*% make.tform(pathdf$Sample, u = pids)` → 样本 × 基因计数矩阵。
5. **edgeR 段**：`DGEList` → `rowSums(edgeR::cpm(d_e) > 1) >= 3` → `calcNormFactors("TMM")` → `estimateGLMCommonDisp` → `estimateGLMTagwiseDisp` → `glmFit` → `residuals(type="deviance")`。
6. **RUVr**：`RUVr(x = round(d_e$counts), k = k_actual, residuals = res1)` 取 `W_1..W_k`；
   `k_actual = min(nruv, df_resid - 1)`（实测 16 样本 → 残差 df 5 → k 下调到 4，脚本打印 `!! k 下调`）。
7. **MAST**：`zlm(~ stim + W_1 + … + W_k [+ (1|individual)])`，**分块** `chunk_size=500`：`FromMatrix` → `zlm`；
   连续组件 `C` + 离散组件 `D` **各取一次 Wald**（`waldFromZlm`：`vcov` 是 3 维数组，**两种维度序都要试**。
   见本 skill §细胞级 MAST 陷阱 3）。
8. **汇总**：主结果取 `resC`（全空则退回 `resD` 并标 `component="D"`）→ BH → 按 p 排序 → merge D 组件列
   （`suffixes = c("", "_D")`）→ 写 `<前缀>_<亚群>_<对比>_sDEG.csv`。

## 二、固定口径（改前必须问用户）

- 对比固定 5 组：3 个**组内配对**（`Y_Pre_vs_Y_Post` / `O_…` / `OD_…`）+ 2 个**组间独立**（`Y_Pre_vs_O_Pre`、`O_Pre_vs_OD_Pre`）。
- 输出文件名前缀沿用旧口径（本例 MuSC 版仍用 `muscle_`）—— **下游脚本按固定列名/列序解析**，
  ⇒ **加列（如 `component`）或改名都要先问用户**（13 列 → 14 列）。
- `direction` 列 = `"<grp2> > <grp1> (coef>0)"`，是**组级常量**（`nunique()==1`）⚠️ 不能当逐行上下调用（见本 skill 交付章节）。
- `method` 列记**实际降级后**的方法。
- **`C` 组件 = 表达量、`D` 组件 = 检出率**，两种不同的量，⛔ 不能混着说"上调"。

### 组名短码映射（MuSC 实测；MF 同族）

| rds 真实取值 | 短码 |
|---|---|
| `Young_normal` | `Y_Pre` |
| `Young_normal_Post` | `Y_Post` |
| `Old_normal` | `O_Pre` |
| `Old_normal_Post` | `O_Post` |
| `Old_diabete`（拼写照用户给的） | `OD_Pre` |
| `Old_diabete_Post` | `OD_Post` |

```r
md$type <- dplyr::recode(as.character(md$type), "Young_normal" = "Y_Pre", ...)
short_codes <- c("Y_Pre","Y_Post","O_Pre","O_Post","OD_Pre","OD_Post")
if (!all(md$type %in% short_codes))          # ⛔ 不能用 anyNA()
  stop("type 映射失败 -> ", paste(setdiff(unique(md$type), short_codes), collapse=", "))
print(table(md$type))                         # 映射表必须进日志
```

🔴 **守卫必须用 `%in%` 集合判定**：`dplyr::recode` 对未命中值是**原样保留、不产生 NA**，
所以 `anyNA()` 抓不到漏映射 —— 而 `factor(levels=)` 那版会把真值全抹成 NA ⇒
**30 轮全部打印「跳过：组别缺失」，退出码 0、零报错、输出目录空**（MF/MuSC 都踩过）。

## 三、五个坑（按严重度，全部实测）

| # | 症状 | 根因 | 修 |
|---|---|---|---|
| K1 | `unable to find an inherited method for function 'cpm' for signature 'object = "DGEList"'` | `library(MAST)` 连带载入 `SingleCellExperiment`，其 S4 泛型 `cpm` 劫持裸调用 | `edgeR::cpm(d_e)`（见本 skill §细胞级 MAST 陷阱 5） |
| K2 | 30 轮全「跳过：组别缺失」，rc=0 | `factor(levels=)` 遇真实取值全变 NA | 短码映射 + `%in%` 集合守卫（§二） |
| K3 | 不报错但**部分基因无声消失** | `FromMatrix`/`zlm` 失败被 `tryCatch` 吃掉 | 诊断并打印：`n_tested <- sum(lengths(chunkIdx))` vs `length(unique(got_gene))`，差值 = 丢失数；`sum(sapply(results, is.null))` = 失败块数 |
| K4 | 显著基因数随 FDR 口径漂移 | 主结果 `$fdr` 只对进入 `main` 的基因做 BH，D 组件另做一次 | **不跨对比合并后 p.adjust**；族口径（亚群内×对比内×组件内）跟用户确认后固定 |
| K5 | 反复落盘拖慢 | 每亚群 `saveRDS` | 一次 `readRDS` 后用内存对象；集群侧走"一个作业跑完整链"或常驻会话 |

## 四、集群投递（本例 node4 · 2026-10-09）

- 解释器**写死**进作业（⛔ 不要靠 PATH 默认）：
  `export PATH=/cluster/share/zhangxiao6/software/miniconda3/envs/R4.41/bin:$PATH && Rscript <脚本>`
  （实测集群 R 4.4.1 / edgeR 4.4.2；`library(MAST)`/`RUVSeq`/`lme4` 齐备）。
- `remote_cluster` 的 `submit` 返回 `exit=124 / Command timed out after 20s` **但作业已起来** → 用 `ps` 核实，**别判失败**。
- wrapper 打 `rc=0` **不接 Rscript 真退出码** ⇒ 判断成败只能看日志有无 `Execution halted` / `Error`。
- 本地 `rail_review(pre)` 按**本机**包清单拦集群作业（本例拦在缺 `RUVSeq`）⇒ 解绑三步见
  `remote-cluster-execution` 铁规 3.1（那次本机安装与运行无关，必须主动向用户交代口径）。
- 大输入（本例 662MB rds）走 `large_cache` 账本 + 持久化问询（`remote-cluster-execution` 铁规 10）。
- 🔴 **投递后做一次早期失败核对**（`ps` + `tail -30 日志` + `ls 产物目录`），**然后停手** ——
  实测全量作业 15:08:54 投递、**15:10:37 就死在第一轮的 `cpm` 行**，而按 `ps` 汇报"在跑"导致用户
  15:13 来问「我在 node4 上没看到任务」。见 `remote-cluster-execution` 铁规 6.1。

## 五、先跑冒烟版，再放全量（本类脚本的固定做法）

30 轮 x `glmer` 串行代价极高（用户 `ncores=1` → 16 已确认；SF 集群 112 核基本全空）。
**冒烟版只改 2 行**，其余一字不改：

```r
outdir    <- "MuSC_RUV_smoke"      # 全量："MuSC_RUV_result"
celltypes <- head(celltypes, 1)    # SMOKE          ← 取第 1 个亚群
for (nm in names(COMPARISONS)[1])  # SMOKE          ← 只跑第 1 个对比
```

⇒ 1 亚群 × 1 对比，正好是崩过的那一段；首轮崩溃 1 分钟内暴露。

## 六、汇报骨架

① 每亚群 × 每对比一行（基因数 / FDR<0.05 / up / down / method / k_used / n_cells）；
② **静默丢失基因**若不为 0 必须报；
③ `component` 列来自 C 还是 D；
④ 配对是否成立（`[meta] 细胞 N | 样本 N | 个体 N | 亚群 N` 那行 —— 个体数偏离预期就说明随机效应降级了）。