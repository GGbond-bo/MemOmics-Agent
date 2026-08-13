# 骨骼肌 MF L3 亚群比例箱线图 — 实测案例（2026-08-12/13）

## 数据
- `E:\骨骼肌锻炼\MF_L3_meta_new.csv`（314MB，508,662 行 ≈ 50 万细胞）
- 列：`samplename`（样本）、`annotation_L3`（Level3 注释）、`type`（组别）、14 打分列
- 48 样本、6 组配对齐全：Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post（Y=Young, O=Old control, OD=Old Diseased/T2D）

## 10 个亚群（细胞数降序）
| annotation_L3 | 细胞数 | 是否画图 |
|---|---|---|
| Pure Type IIA | 171,320 | ✅ |
| Pure Type I | 166,747 | ✅（先跑）|
| Specialized MF | 35,214 | ❌（用户指定跳过，但显著性仍算）|
| LRP1B+(I) | 31,331 | ✅ |
| OTUD1+(II) | 25,766 | ✅ |
| OTUD1+(I) | 24,959 | ✅ |
| RP_high(II) | 16,806 | ✅ |
| Pure Type IIX | 14,130 | ✅ |
| RSS | 13,591 | ❌（用户指定跳过，但显著性仍算）|
| RP_high(I) | 8,797 | ✅ |

## 用户脚本核心结构（复用，勿改写风格）
1. `map_sample_to_group()`: case_when 正则映射 `^Young_\d+_Pre$`→Y_Pre / `^Old_\d+C_Pre$`→O_Pre / `^Old_\d+_Pre$`→OD_Pre 等
2. `extract_base_id()`: `str_remove(samplename, "_(Pre|Post)$")` 配对键
3. `safe_paired_test()`: exact Wilcoxon → coin fallback → approx Wilcoxon（三级）
4. `cliffs_delta()`: `(gt - lt)/(nx*ny)`，n≤30 用 outer()；n>1000 换 rank-based
5. 全局预计算：ALL_COMPARISONS 5 组 + PAIRED_COMPARISONS 3 组（Y/O/OD 各自 Pre→Post）+ 双 FDR
6. `plot_celltype_proportion()`: 手动括号标注（非 ggpubr）、`complete()` 补 0、`Xjitter = GroupIndex ± 0.15`、配对虚线

## 🔴 方向坑（核心教训）
- 用户脚本 `cliffs_delta(x, y)` 中 x=pair[1]（如 O_Pre）、y=pair[2]（如 OD_Pre），**正值 = pair[1] 高** = O 高于 OD
- Agent 第一轮把 `+0.84` 误读成"OD 升高"（按配对比较的直觉），用户从图看出糖尿病明显下降 → 当场纠正
- 修复：改成 `cliffs_delta(y, x)`（正值 = 后者高）+ 输出 `direction` 列显式文字
- **验证方法**：任何效应量都要回到中位数原始数据复核（O_Pre 39.2% vs OD_Pre 30.8% → OD 低）
- 修正后 v2 CSV: `significance_all_celltypes_v2_direction_fixed.csv`；v3 加 Y vs OD 比较 → `significance_all_celltypes_v3_with_YvsOD.csv`（10×6=60 行）

## 双 FDR 设计
- `FDR_per_celltype`: 每亚群内部 5~6 比较 BH 校正（探索性，灵敏）
- `FDR_global`: 所有亚群×所有比较全局 BH（保守，最终结论）
- 绘图参数 `use_global_fdr` 选择用哪列

## Pure Type I 结论（4 组定稿：O_Pre/O_Post/OD_Pre/OD_Post）
- 糖尿病显著↓ I 型：O_Pre 39.2% vs OD_Pre 30.8%，p=0.007，FDR_per_celltype=0.035，Cliff's δ=−0.84，7/7 个体一致
- 老年运动↓：O_Pre→O_Post 39.2→30.7%，p=0.047（raw p 显著，FDR 0.117 不显著）
- 糖尿病运动↓ 不显著：OD 30.8→23.6%，p=0.219
- 年轻运动↑（不显著）：+6.2pp
- 故事：糖尿病压低慢肌，运动方向反转（年轻保慢肌、老年/糖尿病丢慢肌）
- 定稿 4 组理由：Y 组（p=0.232 不显著 + 方向相反）删掉避免解读噪音，主图 4 组 + Y 放补充

## Pure Type IIA 结论（6 组探索版，等用户定组别）
- 衰老显著↓ IIA：Y_Pre 42.8% vs O_Pre 26.6%，p=0.0046，FDR=0.023（II 型萎缩经典）
- Y vs OD（补充比较）：42.8% vs 26.3%，p=0.033（raw 显著，亚群内 FDR≈0.099 边缘）
- 运动：Y↓(−3.25pp)/O↓(−6.56pp)/OD↑(+2.85pp，p=0.469 不显著)
- OD 个体响应：**4 响应者(+2.9~+17.6pp) vs 3 非响应者(−2.9~−9.6pp)**——配对 p 不显著但个体异质性真实存在
- 响应者 vs 非响应者基线：28.09% vs 24.26%，p=1.000 → **基线不预测响应（非 floor effect）**
- 故事策略：糖尿病快肌丢失（有统计）→ 运动个体响应异质性（有数据）→ 不声称"运动普遍有效"

## 出图尺寸（用户指定，2026-08-12/13 最终版）
- **探索图（未定组别）= 140×110mm 全幅大图**（用户明确允许："探索脚本可以 140×110mm 全幅，确定之后再用我指定的参数"）
- **定稿图（用户确认组别后）**：6 柱 = 30mm 宽，5 柱 = 28mm，每少 1 柱 −2mm；高 32mm
- `egg::set_panel_size(width=unit(N,"mm"), height=unit(32,"mm"))` + `ggsave(dpi=300, limitsize=FALSE, bg="white")`
- **⛔ 尺寸教训链**：IIA 的 FDR/p 值**定稿图**曾用 140×110 全幅（被"大小有按照我给的画吗？"抓住）→ 必须按柱数规则；
  随后探索图又被强行套 30mm（被"探索脚本可以全幅"纠正）→ 探索全幅、定稿按柱数。定稿 FDR 版与 p 值版
  同一亚群必须同一宽度 mm。

## 执行环境坑（本会话实测）
- R 必须用 R-4.5.3 全路径 `C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe` + `.libPaths('E:/R-libs/R-4.5.3')`；默认 R-4.4.2 加载不了 4.5.3 编译包
- readr 不在 R-4.5.3 库 → 用基础 `write.csv`
- 生成的 CSV 首列空表头 → 读回时 `row.names=1`
- **⛔ 黑底/空白检查必须三指标，不能只看"非白像素%"**：`egg::set_panel_size` + `ggsave()` 默认
  输出纯黑背景 PNG（94.8% 黑），"非白 95%"会误判成有内容。正确：① `dark%`（RGB 全<100）<10
  ② `colored%`（max−min>30）>1 ③ 内容边界框存在。`png()` 设备 + set_panel_size 也可能出空白
  （3.9KB）→ 统一 `ggsave(..., bg="white")` 输出 PNG。
- 每次 R 脚本运行前检查是否有 `_kernel_worker.R` 孤儿进程堆积（见 windows-bioinformatics-batch-processing 的 references/kernel-worker-orphan-investigation.md）

## LRP1B+(I)（2026-08-13 两版探索图已出，等用户定组别）
- 6 组探索图（140×110mm 全幅）已出两版：`Pure_Type_LRP1B_6grp_pval_explore.png` + `Pure_Type_LRP1B_6grp_FDR_explore.png`
- 显著性（v4 6 比较表，FDR_per_celltype）：
  - OD Pre→Post p=0.0156 FDR=0.056（糖尿病运动↓，−2.26pp，raw p 显著 FDR 边缘）
  - Y vs O p=0.0185 FDR=0.056（衰老↑，Cliff's δ=+0.69，raw p 显著 FDR 边缘）
  - Y vs OD p=0.0878 FDR=0.176（糖尿病↑，边缘）、O vs OD p=0.3176 无差异
  - Y Pre→Post p=0.846、O Pre→Post p=0.219 均不显著
- 故事候选：衰老↑ + 糖尿病运动↓ = "运动把衰老相关升高的 LRP1B+ 压回去"方向，但 FDR 边缘需谨慎
- 定稿时用户原版样式 × {FDR, p 值} 两版（若用户确认组别）
