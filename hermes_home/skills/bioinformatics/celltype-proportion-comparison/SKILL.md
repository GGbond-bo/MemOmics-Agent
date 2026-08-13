---
name: celltype-proportion-comparison
description: 细胞类型/亚群比例跨组比较箱线图全流程（配对前后 + 独立跨组）。触发词："亚群比例"、"L3 boxplot"、"Proportion (%)"、"6组箱线图"、"FDR标注"、"p值标注"、"画哪几组"、"逆转衰老"。使用场景：scRNA-seq 注释后比较各亚群在 6 组（3 条件×Pre/Post，个体配对）中的比例变化，判断"逆转衰老/逆转糖尿病/运动共同趋势"。包含：分组映射、base_id 配对检验、Cliff's delta 效应量方向约定、双 FDR（亚群内+全局）、探索用 raw p 值/定稿用 FDR 标注、egg::set_panel_size 固定尺寸规则、逐亚群门禁流程、响应者/非响应者分析。
---

# 细胞类型比例跨组比较（Cell Type Proportion Comparison）

## 触发场景
- 用户有 Seurat metadata（`samplename` + `annotation_L3` + `type` 组别），要比较各亚群细胞比例在多个组间的差异
- 骨骼肌锻炼项目：6 组 = Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post（3 条件 × 干预前后，个体配对，base_id 配对键）
- 用户流程（铁律）：**先全亚群显著性 → 逐亚群 6 组探索图 → 用户确认画哪几组 → 两版定稿**

## 🔴 铁律（本类任务）

### 1. 方向约定必须统一（2026-08-12 被用户当场抓住的坑）
- 配对比较 `median(v2 - v1)`：正值 = 后者(Pair2)比前者高 ✅ 符合用户直觉
- 独立比较 `cliffs_delta(x, y)`：**正值 = 前者(x)比后者高** ⚠️ 与用户直觉相反
- **必须翻转为 `cliffs_delta(y, x)` 使正值 = 后者高**（如 OD−O 正值 = OD 升高），并在结果表加 `direction` 列显式写"X 低于/高于 Y"
- ⚠️ 教训：原脚本 `c("O_Pre","OD_Pre")` 返回 +0.84 真实含义是 **O 高于 OD → 糖尿病显著下降**；Agent 误读成"OD 上升"被用户抓住（"糖尿病明明显著下降，你还说是上升"）。**任何效应量符号都必须用中位数原始数据逐个体复核**（如 O 组 39.2% vs OD 组 30.8% → 糖尿病下降），不能只看 delta 符号。

### 2. 用户给脚本时：修改用户的脚本，不要发明新图
- 用户说"改成 p 值" = 把用户脚本里的标注列从 FDR 换成 p.value，标签变 `p=...`，**不是画独立的 -log10(p) 条形图**（被骂"你在画什么鬼"）
- 改完必须跑通用户的原始绘图函数（箱线 + 点 + 配对虚线 + 手动括号），只做参数化最小改动

### 3. 探索用 raw p 值标注，定稿用 FDR
- raw p 能显示更多比较（如 O Pre→Post p=0.047 显著但 FDR=0.117 掉出）——用户探索阶段明确要 p 值
- 论文定稿建议 FDR 或标注写清是 raw p（审稿人会较真）

### 4. 显著性全亚群一次算完存 CSV，绘图读 CSV 不重算
- 包括**不画图的亚群**（用户明确"不要抛开 RSS 和 SMF"，先算显著性）
- 用户会问"为什么调用这么多 R"——把计算和绘图分离：计算一次 → 存 CSV → 每个亚群画图只读 CSV

### 5. 逐亚群门禁
- 先出 6 组探索图 → 给生物学解读（是否逆转衰老/逆转糖尿病/运动共同趋势）→ **等用户确认组别和宽度** → 才出定稿
- 不批量画完所有亚群。一次一个，用户确认再继续

### 6. ⛔ 定稿样式 = 用户原脚本版，不要 CNS 化（2026-08-12 用户明确否决 CNS 版）
- 用户原话："按照我代码出的 Pure Type I 4 组呢？你都 CNS 级别好像也不好看。删掉 CNS 的，就按照我的代码出"
- 本类任务（细胞比例箱线图）house style = 用户脚本：theme_bw、6 组固定配色（Y 绿/O 蓝/OD 红系）、
  配对虚线连线、`FDR=`/`p=` 白底文本标注、手动括号。**不要自动套 nature-figure/CNS 主题**（星号体系、
  theme_classic、同色系浅深配对等已被用户否决）
- 定稿 = 用户原版样式 × {FDR, raw p 值} 两版（每亚群 2 张 PNG + 2 张 PDF），不做 CNS 第三版
- CNS 级优化只在该亚群/数据集本身属于"发表级主图"且用户点名要时才做，默认不做

## 固定尺寸规则（用户指定）
- `egg::set_panel_size(width=unit(N,"mm"), height=unit(32,"mm"))` + `ggsave(dpi=300, limitsize=FALSE, bg="white")`
- **6 柱 = 30mm，5 柱 = 28mm，每少 1 柱 −2mm**；高度恒 32mm

**尺寸规则分层（2026-08-12 两次纠正后最终版）**：
- **探索图（未定组别）**：`png(width=140, height=110, units="mm")` 全幅大图 **用户明确允许**（"探索脚本可以
  140×110mm 全幅，确定之后再用我指定的参数"）——探索图目的是看细节、确认组别，不套固定面板
- **定稿图（用户确认组别后）**：必须按柱数规则 `egg::set_panel_size`：
  `p_main_scaled <- egg::set_panel_size(p_main, width=unit(N,"mm"), height=unit(32,"mm"))`
  → `ggsave(..., plot=p_main_scaled, dpi=300, bg="white", limitsize=FALSE)`
- **FDR 版与 p 值版尺寸必须完全一致**（同一亚群同一组别 = 同一宽度 mm）
- 教训链：曾把 IIA 的 FDR/p 值定稿图用 140×110 全幅出（被"大小有按照我给的画吗？"抓住）；随后又把探索图
  强行套 30mm（被"探索脚本可以全幅"纠正）。**规则 = 探索全幅、定稿按柱数**，交付前自查脚本里
  `png()`/`ggsave()` 尺寸参数属于哪个阶段（探索 or 定稿）

## 标准步骤
1. 读 metadata → 统计各 `annotation_L3` 细胞数 → 确认亚群列表（用户指定哪些跳过）
2. 计算显著性（全亚群 × 比较对）：分组映射（`map_sample_to_group`: `^Young_\d+_Pre$`→Y_Pre 等）→ base_id 配对键（`str_remove(samplename, "_(Pre|Post)$")`）→ 配对 Wilcoxon（按 base_id inner_join，`complete()` 补 0）→ 独立 Wilcoxon → Cliff's delta（方向翻转！）→ 双 FDR（per_celltype BH + 全局 BH）→ 存 CSV
3. 补充比较按用户需求追加（如 `Y_Pre vs OD_Pre` 年轻 vs 老年糖尿病），重算全表
4. 逐亚群：6 组探索图（p 值标注）→ 解读 → 用户定组别 → 定稿
5. 定稿后检查 PNG 非空白（**三指标像素级验证**，见 Pitfalls；不要只信文件大小或"非白%"）
6. 定稿交付前核对尺寸规则（每柱 mm 数，见上节）

## 响应者/非响应者分析（用户关注点）
- 配对组运动后检查个体级响应：逐个体 Pre→Post 变化，数升/降个数（如 OD 组 4 升 3 降）
- **配对 Wilcoxon p 是"差的中位数"，与"中位数之差"不同**——表面上升可能是少数强响应个体拉动
- 响应者 vs 非响应者基线对比（基线比例是否预测响应；p=1.0 = 非 floor effect）→ 结论策略：不声称普遍效应，讲"个体响应异质性"

## Pitfalls
- **⛔ 图空白/黑底检查必须三指标，不能只看文件大小或"非白%"（2026-08-12 被用户两次纠正）**：
  `egg::set_panel_size` 处理后的对象经 `ggsave()` 输出 PNG **默认纯黑背景**（实测 94.8% 像素
  纯黑 [0,0,0]，视觉=黑屏几道灰）——而"非白像素 95%"恰好会把它误判成"有内容"！
  正确三指标（PIL）：① `dark%`（RGB 全部 <100 的像素占比）<10 ② `colored%`
  （max-min>30 的彩色像素）>1（正常箱线图有彩色箱体/点）③ 内容边界框存在
  （非白非黑像素的 min/max 范围）。`png()` 设备 + `set_panel_size` 组合还可能出空白/黑底，
  **统一用 `ggsave(..., bg="white")` 输出 PNG**。文件大小 ≠ 内容正确（3.9KB 空白和 55KB 黑底都骗过人）。
- R 环境：`.libPaths('E:/R-libs/R-4.5.3')` + R-4.5.3 全路径；readr 不在该库用基础 `write.csv`；CSV 首列空表头 → `row.names=1`
- `coin::wilcoxsign_test(diff_val ~ 1)` 非标准配对写法，但 exact→approx fallback 链有效，不用改（用户脚本无需修正）
- `complete(nesting(samplename, base_id, type), fill=list(Proportion=0))` 补缺失组合（0 细胞样本）必需
- 双 FDR 列同时保留：`FDR_per_celltype`（探索灵敏）vs `FDR_global`（保守结论），绘图参数选择
- 效应量列混两种度量：运动比较是 median_diff（百分点），跨组比较是 Cliff's delta（−1~1），**不能直接比大小**，表格必须分开标注
- **多亚群流程避免重复冷启动（用户："为什么调用这么多 R？" / "kernel 不持久化吗？" 2026-08-12）**：
  metadata 314MB 每次 Rscript 冷启动重载 = 浪费。方案：① 计算一次存 `percentage_data.rds`（比例表），
  后续每亚群脚本 `readRDS` 直接画图（最稳）；② 或 `execute_r` 持久内核复用 worker（注意 execute_r worker
  是 R-4.4.2，本项目分析须 R-4.5.3 全路径 + `.libPaths('E:/R-libs/R-4.5.3')`——用 RDS 缓存更省事）
- `Rplots.pdf` 是 R 空设备残留文件（png()/print 组合产生），无内容，交付前忽略/删除，不要当产出物

## 支持文件
- `references/mf-l3-proportion-case.md` — 骨骼肌 MF L3 10 亚群实测案例：脚本结构、显著性结果、Pure Type I/IIA 结论与响应者分析
