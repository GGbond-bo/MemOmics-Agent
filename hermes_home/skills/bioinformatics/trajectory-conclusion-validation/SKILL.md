---
name: trajectory-conclusion-validation
description: "轨迹/拟时序类结论的定稿前验证（换根枚举、换嵌入独立性、供体级配对统计、固定多重检验族、结论分级措辞）。触发：Monocle3/Slingshot/scVelo 跑出伪时间后要下结论、运动或处理前后细胞在轨迹上的位置比较、判断伪时间轴是「分化轨迹」还是「细胞身份差异」、辩论/审稿要求补稳健性检验。"
when_to_use: "[trajectory-conclusion-validation] 拟时序/轨迹分析出结果后、写结论前；用户问某组在轨迹上位置差别、分化方向对不对；辩论裁决要求补敏感性检验；跨 R 版本跑 monocle3 的环境问题。配合 trajectory-analysis（方法流程）使用：那本讲怎么跑，这本讲跑完怎么才能下结论。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [trajectory, pseudotime, monocle3, robustness, sensitivity, donor-level-stats, multiple-testing, 03_高级分析]
    difficulty: advanced
    languages: [R]
    category: scRNA
---

# 轨迹结论验证 — 跑完 Monocle3 之后、写下结论之前

方法流程见 `trajectory-analysis`（new_cell_data_set → preprocess_cds → 注入 UMAP → cluster_cells → learn_graph → order_cells）。
**本 skill 管的是"这个伪时间结论能不能写"**。

## 🔴 一句话前提

**伪时间轴 = 「你选的那个嵌入 + 你选的那个根」下算出来的量。** 换嵌入或换根会改变方向、甚至翻转结论。
→ 因此：**结论必须过四道闸再写**；不过闸的效应只能写成"探索性/不可判定"，不能用"X 诱导 Y 转换"这类措辞。

## 四道闸（按顺序，全部要跑）

| 闸 | 做什么 | 判据 / 处置 |
|---|---|---|
| ① 根稳健性 | 在**已 saveRDS 的 cds** 上枚举多根：各细胞类型占比最高的 principal node + 最高度数节点 + 随机节点，逐个 `order_cells(root_pr_nodes=...)` | 先把每个根的伪时间**按与基线的 Spearman 符号归一化**（`pt * sign(rho)`）再比效应量；与基线 `\|rho\|` 很高的根若同向 ⇒ 稳健。**唯一反向的那个根，先查它是不是插进了目标分支内部**（本次 TypeII_max 根 rho=0.561、Δ 由 +1.65 翻成 −0.89）——报出根位置与 rho，别当反证 |
| ② 嵌入独立性 | 路径 A 注入 Seurat UMAP 后，`learn_graph()` 学的是 **Seurat 的降维几何**。必须跑一次不注入的对照：`preprocess_cds(num_dim=50)` → `reduce_dimension(umap.metric="cosine")` → cluster/learn/order | 比三样：伪时间 Spearman rho、**同一批 marker 在两轴上的负载方向**（锚定）、效应量方向。rho 低但 marker 同向 ⇒ 轴同源、几何不同；**效应方向在嵌入间翻转 ⇒ 该效应不可下结论**；替代嵌入下**多种细胞类型同向位移** ⇒ 更像整体/技术漂移（组成、深度、批次），不是某类型的特异效应 |
| ③ 统计单位 | 组间/前后差异**一律以样本/供体为单位**（每供体每时间点 ≥3 细胞取均值 → 配对检验） | 配对 Wilcoxon + rank-biserial + **符号翻转置换** + **bootstrap 95%CI** + 供体固定效应模型（校正测序深度/细胞数）。**禁止**把细胞级 Wilcoxon/Mann-Whitney 当结论——伪重复会把 p 压到 1e-100 量级 |
| ④ 固定多重检验族 | 把**敏感性检验一起算进同一个 BH 家族**（换根 × 细胞类型、队列拆分、替代嵌入），一次 `p.adjust(family, "BH")` | ⛔ **不准事后缩族**（"只看目标细胞类型"= alpha 膨胀）。全族 FDR 不过 0.05 ⇒ 未校正 p 只能写"探索性" |

## 判读：把"分化"和"身份差异"分开（最容易下错结论的地方）

| 观察 | 结论 |
|---|---|
| 分化/发育程序 marker（如肌生成 PAX7/MYF5/MYOD1/MYOG/MYH3）与伪时间**无相关**，而谱系 marker（如 MYH7/MYH1/TNNT1）强相关 | 轴是**细胞身份/状态差**（纤维型、亚型…），**不是分化轨迹**；"1 partition 单一连通" ≠ 真实分化 |
| 根端细胞类型是人为指定的；**去掉该类型重跑，同一轴仍在**（\|rho\| 高、方向反向） | 只能称"**计算根端 / 伪时间起点**"，不能称生物学分化起点 |
| 根端细胞是静息态（如 PAX7+ 但 MKI67 0%、MYOD1 极低、DLK1/SPRY1+） | 支持"静息态被当作根端"，但不支持"正在分化" |
| 效应量出现在小细胞群里（如 162 细胞散在 6 组，每供体 6–41 个） | 低功效 ⇒ 移出主结论，标"不可判定"（≠"无效应"） |

## 结论分级交付（措辞纪律，经 L2×2 + L1 辩论裁决认可）

| 级别 | 写法 | 禁用词 |
|---|---|---|
| **A 保留（限定）** | "伪时间轴主要刻画**本嵌入下**的 X 身份/程序；根端为计算意义上的起点；单连通 ≠ 真实分化轨迹" | 分化起点 / 真实谱系轨迹 / 某诱导某转换 |
| **B 不可判定** | "现有数据不能支持 X 沿该轴发生可下结论的位移：方向在基线、换根、独立降维间不稳定，全族 FDR ≥ 0.11；仅探索性，需 IHC/蛋白或独立队列验证" | "X 诱导 Y 转换"；把未校正 p 写成确认性结论 |
| **C 移出主结论** | "低功效/不可判定，移至补充材料或限制段，不作主张" | 写成"无效应" |

必须一并交付：**未排除混杂清单**（根选择偏倚 / 注入 UMAP 的几何影响 / 单核 vs 单细胞模态 / 年龄性别批次深度未入模型 / 细胞级 FDR 膨胀）+ **最小验证集与失败阈值**（例：配对活检 MYH7/MYH1/MYH2 免疫荧光；≥2 个独立验证不同向 ⇒ 淘汰 B）。

## 环境：monocle3 与 Seurat 装在两个 R 小版本里（跨版本桥接）

内核（平台 execute_r）固定某个 R；monocle3 常只装在**另一个** R 的库里，而那个 R 没有 Seurat。
→ **不要重装包**：① 在 Seurat 那侧导出纯 RDS（counts / meta.data / umap）；② 用另一个 R 的 **Rscript 绝对路径**在 bash 里直调跑 monocle3（`--` 之后给脚本；不要用 `cmd //c '...'` 包装，MSYS 会把参数吃掉、cmd 只起交互 banner，日志文件都不会生成）；③ 伪时间 CSV 回主 R 做统计出图。
可直接复用：`scripts/monocle3_cross_version_bridge.R`（导出 + 构建 + 多根枚举一体）。

**Monocle3 两个必踩的包级坑**：
- ⛔ **不要 `library(igraph)`**（2.0+）：`igraph::clusters()` 遮蔽 `monocle3::clusters()` → `partitions()`/`clusters()` 报 `Must provide a graph object (provided wrong object type)`。需要时写 `igraph::V(pg)` / `igraph::degree(pg)` 前缀。
- `saveRDS(cds)` 的 `does not save annoy or hnsw nearest neighbor indices` 警告可忽略——`order_cells()`（换根）与 `plot_cells()` 都能在回读的 cds 上跑；只有继续 `graph_test()`/`find_gene_modules()` 才需要 `save_monocle_objects()`。
- 这些坑的**方法流程**归 `trajectory-analysis`（该 skill 为人工撰写、暂不可自动改写），故在此并列记录。

## 交付物清单（跑完一轮轨迹分析应产出）

`results/pseudotime_full.csv`（每细胞：pseudotime + celltype/注释/分组/样本）
`results/pseudotime_root_<name>.csv`（每个根的伪时间，供敏感性复核）
`results/traj_paired_wilcoxon.csv`（供体级配对 + Δ + rank-biserial + p + FDR）
`results/traj_root_sensitivity_paired.csv`（多根 × 细胞类型的 Δ）
`results/traj_typeII_delta_CI.csv`（bootstrap CI）
`results/traj_fixed_FDR_family.csv`（固定家族全部 p/FDR）
`results/traj_cross_embedding_marker_anchoring.csv`（marker 在两轴上的 rho 方向）
`results/trajectory_summary.md`（A/B/C 分级 + 限制声明 + 验证集）
`figures/` 300dpi：轨迹图（细胞类型/伪时间/分组/注释各一）、多根对照图、独立降维对照图、伪时间 × 组小提琴、供体级配对斜率图、效应热图、根敏感性条形图。

📄 完整配方与本次实例数值（MF_2000：2132 细胞，RSS/TypeI/TypeII，24 供体配对）见 `references/robustness-gates-and-donor-level-stats.md`。

## ⛔ 收尾强制协议

```
1. rail_review(post)（output_dir 传「一眼能看到本次全部产物的那一层」；组件型会话传 <sid> 根）
2. debate_analysis —— 结论合成前必辩（本次经 L1 设计 + L2 结论 + L2 定稿三轮）
   辩论前先 search_papers 拿真实 PMID/DOI；裁决的 recommended_params / next_actions / blocks
   要逐条落地（补跑敏感性），裁决未完成前不得把效应写进主结论
3. skill_evolution(record_run)（脚本 + 参数 + 结果摘要）
4. 更新 task_plan.md（Phase 状态 + 显式产出路径）
5. 汇报时主动问：本次脚本要沉淀吗
```

> ⚠️ 与 `enrichment-conclusion-validation`（DEG→GO/KEGG 结论定稿前四项验证）是同一族思路的**不同模态版本**：那本管富集结论，"轴是不是真的"这类轨迹结论归本 skill；两者都由"结论验证"这一族派生，供 curator 后续合并考虑。