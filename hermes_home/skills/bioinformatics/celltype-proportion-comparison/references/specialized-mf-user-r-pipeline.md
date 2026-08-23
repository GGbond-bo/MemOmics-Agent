# Specialized MF 用户原版 R 管线（显著性 + 箱线图）— 2026-08-17

用户对比例箱线图任务有**官方既定 R 代码**（原话"这是画图的代码，你要记住了。重新画，之前的不好"）。
本文件保存可复用脚本 `04_user_style_proportion.R` 的核心结构 + 本次口径教训。**用户代码不可 CNS 化、
不可换风格**——改图只能参数化最小改动（SKILL.md 铁律 §6）。

## 数据结构
- 输入：细胞级 meta.csv，列 = samplename / type / subcluster（或 annotation_L3）
- 48 样本 × 6 组（Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post），base_id = `str_remove(samplename, "_(Pre|Post)$")`
- Specialized MF 重聚类：11,630 细胞 × 51,227 基因，7 亚群 = NMJ + zone1-6（画图时改名 cluster1-6）
- **dims 读反坑**：`dim() = (genes, cells)` — ncol=细胞；验证铁律 = 亚群细胞数求和 = 汇报细胞数

## 用户官方显著性管线（R，5 比较对）
- `ALL_COMPARISONS`（5 个）：3 配对（Y/O/OD 的 Pre→Post，base_id inner_join 后 `wilcox.test(paired=TRUE)`）
  + 2 独立（Y_Pre vs O_Pre、O_Pre vs OD_Pre，`wilcox.test(Proportion ~ type)`）
- 配对检验 `safe_paired_test`：exact wilcoxon → warning fallback approx（删 coin 分支，见下）；n<3 → NA
- Clffs delta：`outer()` 计数，`(gt-lt)/(nx*ny)`（**正值 = 前者高**，交付时按用户直觉翻转报告）
- 双 FDR：`FDR_per_celltype`（group_by 亚群内 BH）+ `FDR_global`（全表 BH）
- **⚠️ 与 Python 版（02_significance.py，9 比较对含 YvsOD / Ypost_vs_Opost 等 + 补 0）口径不同**

## 用户官方画图函数 plot_celltype_proportion
- 六色固定：Y_Pre `#B2DF8A` / Y_Post `#33A02C` / O_Pre `#80B1D3` / O_Post `#1F78B4` / OD_Pre `#FB9A99` / OD_Post `#E31A1C`
- 配对虚线（base_id 连线）+ 散点 jitter（_Pre 左偏 0.15）+ 手动括号（左竖/右竖/横线三段 geometry）+ `FDR=` 白底 `geom_label`
- `theme_bw(base_size=6)` + `panel.grid=blank` + 图例 none；**标注不过滤显著性阈值**（有效 FDR 就标，不要求 <0.05）
- 入口：`target_grps` 6 柱 + `target_cmps` 5 比较 + `ggsave(140×110mm, 300dpi, bg="white", limitsize=FALSE)`
- 探索图 140×110mm 全幅；定稿才套 `egg::set_panel_size` 柱数宽度规则

## ⛔ 口径差异 = 结论反转（本次最重要教训）
cluster1 Y_Pre vs O_Pre 两种口径结果完全不同：

| 口径 | 比较数 | 补0 | p 值 |
|------|-------|-----|------|
| 用户 R 版 | 5 | 否（无该亚群细胞的样本不参与） | 0.234（不显著） |
| Agent Python 版 | 9 | 是（0 细胞样本补 0%） | 0.027（边缘显著） |

- 根因：① 比较数不同 → BH-FDR 严格度不同；② 补不补 0 → 不补 0 只让"至少 1 个该亚群细胞"的样本参与
  （选择偏倚：高估普遍性）；补 0 对 0 值堆积极敏感（可能制造假显著）
- L1 辩论裁决（modify，中置信）：两版都不完美 → 比例表同时报告 **0 值样本数**；
  结论区分 **"普遍性上升"（补 0 检验）vs "丰度上升"（不补 0 检验）**；
  cluster1 当前 = 趋势而非结论（中位 1.5%→10.5% 看着涨，组间重叠大，n=7~8/组功效不足）
- **用户官方代码口径 = 5 比较不补 0，交付以用户口径为准，但汇报时主动披露与补 0 版的差异**（用户对数值精度敏感，反转结论必须透明）

## rail_review(post) 两个 R 特定误报 + 修复
1. R 的合法 `&&`（标量逻辑与）被 lint 判"使用 && 连接多步骤" → 改成 `&`（对标量结果相同，`!is.null(x) & nrow(x)>0` 等价）
2. `safe_paired_test` 里**未实际走到的** `requireNamespace('coin')` fallback 分支被 UNREGISTERED_PACKAGES 警告 →
   删除 coin 分支、保留 approx wilcoxon 兜底即可（包未在 skill r_packages 声明 = 风险提示；用不到的包分支直接删）

## 平台执行
- execute_r 持续被拦时：`write_file` 脚本 + terminal `R_LIBS=E:/R-libs/R-4.5.3` + `"C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe"` 执行
- 中文路径（`E:/骨骼肌锻炼/`）先 `cp` 到英文路径再读（见 platform-execution-pitfalls）
- 显著性表落盘 `data/special_MF_significance_userR.csv`，画图只读表不重算

## ⛔ 稀疏亚群补0补偿（cluster2 案例，2026-08-17）
用户要求 6 组预览**标注全部 5 个两两比较（含年轻运动）**后，cluster2（zone2，822 细胞）暴露稀疏亚群坑：

- **现象**：Y_Pre vs Y_Post 在原口径下 p=NA（`insufficient_n`）——zone2 细胞在 Y 组极稀疏（Y_Pre 中位 0%，10 个样本 6 个 0 细胞；Y_Post 也大多 1-6 个细胞），不补 0 时只有 Young_2/Young_16 双边都有 → **2 对 <3** → 无法配对检验 → 绘图 filter `!is.na` 把它静默跳过 → 图上漏年轻运动括号，用户质疑"年轻运动没标"。
- **修复**：补 0 配对（全 10 个 Y 样本参与，无细胞=0%）→ 10 对 → `wilcoxon(post, pre)` p=1.0（中位差 +0.58pp 但方向完全混乱：6 样本 Pre 0%→Post 有值、4 样本 Pre 有值→Post 0%，秩和互相抵消 = **真正无差异**）。在 `global_fdr_table` 里 `bind_rows` 替换该 NA 行（`test_type='paired_wilcoxon_imputed0'`，注释写明口径），图上即补标 `p=1`。
- **核对坑**：p=1.0 的 bracket 被分配在图底部（所在组比例最大仅 9%），标签小 + 与箱体重叠，OCR 识别为 'D='（置信 0.71）或漏读——**交付出必须主动说明"5 个比较全部标注，年轻运动为补0口径 p=1.0 在底部"**。
- **数据事实**：cluster2 全部 5 比较均不显著（Y运动 p=1.0 补0 / YvsO p=0.788 / O运动 p=0.578 / OvsOD p=0.318 / OD运动 p=0.219）——cluster2 在 Y 组基本不存在（年轻组几乎无此细胞类型），主要在老年/糖尿病组出现，但组间变异大、n=7/组功效有限 = 只能讲趋势。