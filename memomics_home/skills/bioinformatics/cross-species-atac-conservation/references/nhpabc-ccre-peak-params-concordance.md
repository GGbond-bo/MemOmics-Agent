# NHPABC cCRE 管道参数 + 物种一致性 concordance 图模板（2026-08-29）

来源：用户拿张潇 GitHub（NHPABC 项目）脚本核对 peak 报错 + 本会话 InN/Astro/OPC 三张 concordance 图实证。

## 1. Peak calling 显式参数（张潇脚本 vs ArchR 默认）

张潇 NHPABC 脚本原文（cell-subtype basis, each individual）：

```
addGroupCoverages:      minCells=40, maxCells=5,000, minReplicates=2, maxReplicates=10
addReproduciblePeakSet: MACS2 v2.2.7.1, maxPeaks=500,000, cutOff=0.01
输出 = 501-bp fixed-width peaks
```

| 参数 | 张潇显式 | ArchR 默认 | 影响 |
|------|---------|-----------|------|
| maxCells | 5,000 | 500 | pseudo-bulk 覆盖深度差 10 倍 |
| maxReplicates | 10 | 5 | 每组最多用几个个体做重复 |
| minCells | 40 | 40（同） | 组内最少细胞 |
| minReplicates | 2 | 2（同） | 至少几个重复 |
| maxPeaks | 500,000 | 150,000 | peak 数量上限 |
| cutOff | 0.01 | 0.05 | MACS2 q 值阈值更严 |

**教训**：用户脚本 `addGroupCoverages(groupBy="celltype")` 不传参数 = 用默认 500/5，组内覆盖深度不足；按张潇参数显式设置更贴近 NHPABC 标准。peak calling 流程结构两者完全相同（先 GroupCoverages 再 ReproduciblePeakSet），报错不是流程错，是文件系统 + 参数两件事。

## 2. cCRE 过滤标准（专利实施例参考值）

```
Step 1: PeakMatrix → Seurat
  pm <- readRDS("<Subtype>.rds")  # ArchR PeakMatrix 对象（peaks × cells）
  rds <- CreateSeuratObject(counts=pm, assay="peaks", meta=meta)
  rds <- NormalizeData(normalization.method="RC", scale.factor=1e6)  # CPM

Step 2: Peak × Individuals mean-CPM 过滤
  Mean CPM > 4 在 ≥4 个猴样本   AND
  Mean CPM > 0 在 ≥12 个猴样本
  → cCRE（calculate_cCRE 函数）

peak-to-gene: addCoAccessibility(aggregation k=10, window 500kb, distance constraint 250kb)
```

## 3. addGroupCoverages HDF5 报错修复链（"Unable to open file"）

报错样：`HDF5. File accessibility. Unable to open file` + `Group Astro._.O2_Hip_3 (1 of 40)`。

根因按概率排查：
1. **上次中断残留**：之前跑过 addGroupCoverages 中途报错退出 → GroupCoverages 目录留下空/损坏 .h5 或临时锁定文件 → 本次写同名文件失败
2. **磁盘满/配额满**：`df -h` 检查
3. **并发 ArchR 实例**：多个 R 进程写同一 Project/共享 tmp/ → 锁冲突（先 `ps aux | grep R`）

修复（顺序执行）：
```r
unlink(file.path(getOutputDirectory(proj), "GroupCoverages"), recursive=TRUE)
proj <- addGroupCoverages(ArchRProj=proj, groupBy="celltype",
                          minCells=40, maxCells=5000, minReplicates=2, maxReplicates=10,
                          force=TRUE)
proj <- addReproduciblePeakSet(ArchRProj=proj, groupBy="celltype",
                               pathToMacs2=pathToMacs2,
                               maxPeaks=500000, cutOff=0.01, force=TRUE)
```

## 4. 细胞类型比例物种一致性 concordance 图模板

**用途**：每细胞类型一张，对比人/猴随年龄组的比例变化是否同向。已复用 3 次：InN_concordance_v2 → Astro_concordance_v2 → OPC_concordance_v2。

**布局**：两个 facet（human/monkey）× x 轴年龄 stage（Young/Middle/Old/EO）× y 轴细胞类型 %；均值轨迹线 ± SEM 阴影 + 个体散点；**Spearman ρ + p + Bootstrap 95% CI 标在面板右上角两行**（勿放底部，会压 x 轴刻度标签）。

**统计口径（图注必须写，审稿人查）**：
- 统计单位 = **个体**（human 40 / monkey 21），不是细胞数（防伪重复）
- 检验 = Spearman（年龄序数 4 级），KW 做四组差异；未做多重比较校正（探索性）
- CI = Bootstrap 5000 次 95% 百分位
- 小样本提醒：monkey Young 仅 n=4

**⛔ 猴侧按个体去重陷阱**：猴 63 文库（M1_Hip_1...）≠ 21 个体。算 per-individual 统计必须先按 `Individual` 列去重——本会话曾按文库去重误报 n=20，实际 `monkey_meta.csv` unique(individual)=21（Y3/Y4/Y5/Y7=4, M1-M5=5, O1-O6=6, V1-V6=6）。⚠️ 与 NHPABC 论文 23 只有出入（meta 实际 21），写论文以实测 meta 为准。

**论文表述（审慎版，裁判裁决后定稿）**："no significant age-associated change ... directions concordant but confidence intervals spanning zero; the lack of detectable change is consistent with, though not proof of, cross-species stability." 双不显著 ≠ 效应为 0（可能功效不足）。

## 5. 专利结论表约定（用户要求：后续新结论慢慢补充）

- 文件：`conclusions/专利结论表.md`（v1.0，可追加版）
- 编号：P-01, P-02 ... 递增，旧结论不动
- 列结构：结论一句话 · 数值证据 · 方向性 · 方法 · 数据来源 · 状态
- 已收录（2026-08-29）：
  - P-01 Astro 显著同向下调（hu ρ=-0.65 p=6e-6 / mon ρ=-0.54 p=0.014）
  - P-02 OPC 显著同向下调（hu ρ=-0.48 p=0.002 / mon ρ=-0.63 p=0.003）
  - P-03 Micro partial support（hu -0.38* / mon -0.36 ns）
  - P-04 InN 两物种均无显著变化（同向稳定，不作过度声称）
  - P-05 ODC 跨物种分歧反例（hu +0.42** / mon -0.01 ns）
  - P-06 ExN 均无显著趋势（hu -0.10 / mon +0.15 ns）
- 方法总述：个体为单位（h40/m21）、Spearman 趋势、KW、Bootstrap CI
- 配色提案（Okabe-Ito 色盲安全，用户未最终确认前不改记忆）：ExN #0072B2 / InN #D55E00 / Astro #009E73 / Micro #CC79A7 / ODC #E69F00 / OPC #56B4E9 / VS #F0E442 / ChP #8C8C8C / Unknown #BBBBBB