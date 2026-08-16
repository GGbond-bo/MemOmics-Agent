---
name: celltype-proportion-comparison
description: 细胞类型/亚群比例跨组比较箱线图全流程（配对前后 + 独立跨组）+ AUCell 打分跨组差异分析（score*_AUC 列）。触发词："亚群比例"、"L3 boxplot"、"Proportion (%)"、"6组箱线图"、"FDR标注"、"p值标注"、"画哪几组"、"逆转衰老"、"打分差异"、"AUCell score"、"score boxplot"、"打分跨组"、"score*_AUC"。使用场景：scRNA-seq 注释后比较各亚群在 6 组（3 条件×Pre/Post，个体配对）中的比例变化，判断"逆转衰老/逆转糖尿病/运动共同趋势"，并对已有 AUCell 打分列做同样的跨组差异分析。包含：分组映射、base_id 配对检验、Cliff's delta 效应量方向约定、双 FDR（亚群内+全局）、探索用 raw p 值/定稿用 FDR 标注、egg::set_panel_size 固定尺寸规则、逐亚群门禁流程、响应者/非响应者分析、打分聚合/相关性冗余检查/基因集评估。
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

### 7. ⛔ "说了就跑"：动作承诺必须同轮绑定工具调用（2026-08-14 用户两次抓）
- 用户原话："你看，你又没跑，为什么？"——Agent 说"我马上写脚本/马上跑"却在本轮结束时没有任何
  工具调用，被用户当场抓住（违反 SOUL 铁律 -1）。
- 用户说"跑"/"继续"/"画"/"出图" → **同一轮回复内必须出现工具调用**（execute_r/terminal/write_file），
  绝不说"我下一步会跑"就结束。
- 分步长任务时每轮至少推进一个真实工具动作；纯叙述性回复（计划/解释）不被用户接受为"执行"。

### 8. ⛔ 用户问"你到底跑了吗"——先查自己的工具执行记录再答，禁止凭空自认"没跑"（2026-08-14）
- 用户原话："我都做到这里了，为什么没有跑呢？"（用户贴出 11:20 write_file + 11:28 terminal 输出证据）
- 教训：用户质疑"跑了没有"时，Agent **凭空自认"我上一轮没跑"**，但用户贴的执行日志显示
  实际上写脚本（write_file 3077B）和跑 terminal（输出"逆转候选汇总"）**都已发生**——Agent 犯了
  **双重错误**：① 没有先查工具执行记录（search_files/read_file 看产物）就下结论 ② 把"没跑"这种
  自我贬低当成了默认答案，反而无视了真实日志。
- 正确流程：用户问"跑了没有/为什么没跑" → **先 read_file/search_files 查产出物和日志**（CSV/PNG/脚本
  是否在盘、时间戳是否匹配）→ 用证据回答。产物在 = 跑了，直接交付结果；产物不在 = 没跑，立刻补跑。
- 结果文件示例：逆转分析产物 `data/reversal_analysis.csv`（列：annotation_L3, aging_pp, diab_pp,
  Oex_pp, ODex_pp, rev_aging_O, rev_aging_OD, rev_diab, aging_p/fdr, diab_p/fdr, Oex_p/fdr, ODex_p/fdr）
- **交付"结果"永远优先于讨论"为什么没跑"**：先给用户结果表，再解释执行问题，不要反过来。

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

## 比较子集选择（comp_mode，2026-08-12 用户逐亚群指定）

- 用户对每个亚群会**明确指定画哪些比较的显著性**，且逐亚群不同。例如本会话：
  - Pure Type IIA：只标 Y_Pre vs O_Pre / Y_Pre vs OD_Pre / OD_Pre vs OD_Post（3 个）
  - LRP1B+(I)：Y_Pre vs O_Pre / Y_Pre vs OD_Pre / O_Pre vs OD_Pre / OD_Pre vs OD_Post（4 个）
  - OTUD1+(II)：Y_Pre vs Y_Post / O_Pre vs O_Post / Y_Pre vs OD_Pre / O_Pre vs OD_Pre（4 个）
  - Pure Type IIX：Y_Pre vs O_Pre / Y_Pre vs OD_Pre / O_Pre vs OD_Pre / O_Pre vs O_Post（4 个）→ 用户中途补 OD_Pre vs OD_Post 变 5 个
- **脚本必须支持参数化比较子集**（`comp_mode` 参数 + 预定义列表，如 `COMP_SUBSET <- list('all'=..., 'IIA3'=..., 'LRP1B4'=..., 'OTUD4'=..., 'IIX4'=..., 'IIX5'=...)`），不能硬编码全部 6 比较
- 用户可能中途追加比较（"type IIX 再补一个老年糖尿病运动前后的显著性"）→ 加新 mode 重跑，**旧图删除替换**
- **用户也可能中途删除比较**（2026-08-13 RP_high(II)：去掉 Y_Pre vs OD_Pre 的显著性）→ 定义只含剩余比较的
  新 mode（如 RPHIGH2 = YvsO + OvsOD 两个）重跑替换，**不要保留已删比较的旧图**
- **宽度随柱数自动适配（通用脚本标准实现）**：`width_mm <- 30 - (6 - n_groups) * 2`（6柱=30mm，每少1柱−2mm），
  `egg::set_panel_size(p, width=unit(width_mm,'mm'), height=unit(32,'mm'))`——不要硬编码 30mm，3 组=24mm、
  2 组=22mm 会出错
- 交付前用 R 侧核对**标注比较数 = 用户要求的数量**（如 5/5），不要只信图"看起来对"
- 括号按 p 值从小到大排列（防重叠逻辑），**顺序 ≠ 用户列表顺序**，但每个比较的值必须正确

## 文件名与目录组织（2026-08-12 用户要求）

- **文件名必须用 `annotation_L3` 原始名称**：`gsub('[+() ]', '_', celltype)`，**不要强制加前缀**
  - 原名称带 "Pure Type"（Pure Type I/IIA/IIX）→ 保留 `Pure_Type_IIA_...`
  - 原名称不带（OTUD1+(II)/LRP1B+(I)/RP_high(II)）→ `OTUD1__II_...` / `LRP1B__I_...`（错误示例：强加前缀成 `Pure_Type_OTUD1__II_...` 被用户抓住）
- **结果目录分三个子目录**（用户明确要求"图片和脚本各种建一个目录，不要放在一起"）：
  ```
  L3_boxplot_explore/
  ├── figures/   ← 全部图（PNG+PDF）
  ├── scripts/   ← 全部 R/Python 脚本（含通用画图脚本 02_plot_celltype.R + 像素检查脚本）
  └── data/      ← 显著性 CSV + percentage_data.rds + sig_table_v4.rds 缓存
  ```
- 替换旧图时先 `rm` 旧文件再重跑，交付清单里说明"旧图已删"

## 响应者/非响应者分析（用户关注点）
- 配对组运动后检查个体级响应：逐个体 Pre→Post 变化，数升/降个数（如 OD 组 4 升 3 降）
- **配对 Wilcoxon p 是"差的中位数"，与"中位数之差"不同**——表面上升可能是少数强响应个体拉动
- 响应者 vs 非响应者基线对比（基线比例是否预测响应；p=1.0 = 非 floor effect）→ 结论策略：不声称普遍效应，讲"个体响应异质性"

## 逆转衰老/逆转糖尿病亚群识别（2026-08-14 用户定义标准 + 实测）

用户问"如何定义逆转衰老/逆转糖尿病的亚群"——**标准 = 衰老/糖尿病把比例推向一个方向，运动把它拉回**：
- 衰老效应 `aging_pp` = median(O_Pre) − median(Y_Pre)（pp）
- 糖尿病效应 `diab_pp` = median(OD_Pre) − median(O_Pre)
- 老年运动 `Oex_pp` = median(O_Post) − median(O_Pre)；糖尿病运动 `ODex_pp` = median(OD_Post) − median(OD_Pre)
- `rev_aging_O` = (aging_pp>0 & Oex_pp<0) | (aging_pp<0 & Oex_pp>0)（方向相反 = 逆转候选）
- `rev_aging_OD` = 同逻辑用 ODex_pp；`rev_diab` = (diab_pp>0 & ODex_pp<0) | (diab_pp<0 & ODex_pp>0)
- **样本少（n=7/组）先看趋势（方向成立），再报 P/FDR**——用户原话："先找出有趋势的，再看看它的 P 值和 FDR"

**结果分级交付（实测排序）**：
- 🔴 **强逆转候选**：方向成立 + 至少一个 raw p<0.05（如 LRP1B+(I)：衰老↑ p=0.019 + OD 运动↓ p=0.016；Pure Type IIX：老年运动↓ p=0.031）
- 🟡 **趋势候选**：方向成立但 p 不显著（如 Pure Type IIA：衰老显著↓ FDR=0.028 + 糖尿病运动回升 +6.5pp 但 p=0.47）
- ⚫ **不逆转**：运动方向与衰老/糖尿病**同向**（如 RSS 衰老↑ p=0.0002 但运动继续↑；Specialized MF 运动同向大幅↑）——不能讲逆转故事
- ⚠️ 注意"运动加深疾病效应"型：糖尿病↓ + 运动也↓（如 Pure Type I 糖尿病 FDR=0.042 显著 + 老年运动 p=0.047 继续↓）= 同向加深不是逆转，解读要分开
- 产出：`data/reversal_analysis.csv`（全亚群 × 上述列），脚本 `scripts/13_reversal_analysis.R`

### ⛔ 逆转板块隔离铁律（2026-08-14 用户发火级别纠正："你衰老逆转模块，放什么OD？尼玛的"）

**两个板块的列/比较严格隔离，禁止跨板块混放：**
- **衰老逆转板块**：只放 **Y_Pre vs O_Pre（衰老效应）** + **O_Pre vs O_Post（老年运动）**——**一个 OD 都不允许出现**
- **糖尿病逆转板块**：只放 **O_Pre vs OD_Pre（糖尿病效应）** + **OD_Pre vs OD_Post（糖尿病运动）**
- 教训：第一版把 LRP1B+(I) 的"糖尿病运动↓ p=0.016"写进衰老板块当证据（\"衰老↑+糖尿病运动↓\"），被用户怒斥——糖尿病运动信息属于糖尿病板块，混进衰老板块 = 概念污染
- 交付表头必须能自证板块纯净：衰老板块列名 `aging_es/aging_p/aging_fdr/ex_es/ex_p/ex_fdr`，糖尿病板块列名 `es_diab/p_diab/fdr_diab/es_odex/p_odex/fdr_odex`，重跑脚本后自查无 OD 列混入衰老板块

### 逆转板块出图模式（2026-08-14 用户拍板）

用户要求"按照衰老逆转和糖尿病逆转分别出图，记得分好目录"：
- **衰老逆转板块**：有趋势的亚群全部画 3 柱 **Y_Pre / O_Pre / O_Post**，比较子集 = YvsO + O运动
- **糖尿病逆转板块**：3 柱 **O_Pre / OD_Pre / OD_Post**，比较子集 = OvsOD + OD运动
- 每个亚群 p 值 + FDR 两版（PNG+PDF），3柱 = 24mm×32mm（宽度自适应公式）
- **目录分离**：`figures/reversal_aging/` + `figures/reversal_diabetes/`（用户强调"分好目录"）
- 亚群选择 = 上表"逆转判定 YES/方向成立"的亚群（实测：衰老逆转 6 个 = LRP1B+(I)/Pure Type IIX/RP_high(II)/RP_high(I)/Pure Type I/OTUD1+(II)；糖尿病逆转 2 个 = Pure Type IIX/Pure Type IIA）
- 绘图脚本统一参数化：`plot_3grp(celltype, groups, comparisons, annot_col, out_tag, outdir)`，循环跑两个板块

## 打分分析（AUCell score 跨组比较，2026-08-13 扩展）

metadata 里带 `score*_AUC` 列（AUCell 打分）时，用**同一套 6 组配对框架**做打分差异分析，与比例分析并列两条腿：

- **样本级聚合**：细胞级打分列先按 `samplename` 取均值 → 48 样本 × N 打分 → `saveRDS(score_sample_level.rds)` 缓存；组间检验完全复用比例框架（base_id 配对 / 双 FDR / Cliff's delta 方向约定）
- **打分冗余检查（相关性矩阵）**：14 打分 Spearman 相关 + 聚类热图（ComplexHeatmap `Heatmap(cor_mat, col=colorRamp2(c(-0.6,0,0.6), c('#313695','white','#A50026')))`）——**高相关对（|r|>0.7）说明打分冗余，解读时不能两个都讲**；独立打分（与其他打分 max|r|<0.5）是真正正交信号。实测骨骼肌 14 打分：Sarcomeric↔I (r=0.71)、Sarcomeric↔II (r=0.71)、ROS↔I (r=0.77) 冗余；**RegMyon (max|r|=0.47)、Inflammatory (0.46) 独立**
- **打分 × 6 组热图**（大文章风格）：行 z-score + 格子星号（FDR * / ** / ***）——Nature/Cell 肌肉图谱标准展示
- **⛔ 用户问\"已经是 AUC 了怎么还要 z-score\"时这样答（2026-08-13 实测）**：AUC 解决\"细胞间可比\"（同一打分内
  细胞 A vs B），z-score 解决\"打分间可比\"（跨打分比相对模式）。不同打分的 AUC 绝对尺度差几个数量级
  （实测 scoreI 全距 0.217 vs scoreInflammatory 全距 0.0017），直接画原始 AUC 热图会被高分打分整行刷红、
  低分打分整行刷蓝，组间差异（哪怕 FDR 显著）在颜色上完全看不出。行 z-score = 每行相对自身均值/标准差的偏离，
  展示\"哪些打分在哪些组相对升/降\"。除非数据尺度本身统一，否则 AUC 热图必须行 z-score。可选 min-max 行归一化
  替代（保留 0-1 区间更\"看得懂\"），但都不是绝对 AUC。
- **亚群 × 打分热图（2026-08-13 新增）**——区分\"亚群特征\" vs \"状态\"打分的核心图：
  - **主图**：行=亚群、列=打分（全组平均 AUC，按亚群行 z-score），`cluster_rows=FALSE, cluster_columns=FALSE` 固定顺序（亚群按用户给的顺序，打分按类别顺序），ComplexHeatmap `colorRamp2(c(-2,0,2), c('#2166AC','white','#B2182B'))`
  - **进阶版（按组别拆分）**：列=亚群×组别（10亚群×6组=60列），`column_split = grp`（6 块）+ `top_annotation = HeatmapAnnotation(Group=grp_colors)`——看同一亚群打分随组别的变化
  - **亚群特征指纹**：从聚合 CSV 读每亚群 top3 打分 + low 打分（如 Pure Type I top3 = TypeI 0.82/Sarc 0.43/TypeII 0.33，low 恒为 SenMayo≈0.03）
  - **区分度分析（CV）**：每打分跨亚群的 `CV = sd/mean`——纤维类型打分 CV 高（TypeI 0.36/TypeII 0.36/TypeIIx 0.29，**区分亚群**）；状态打分 CV 极低（Stress 0.04/Inflam 0.03/TNFA 0.05/SenMayo 0.07，**亚群间几乎一致**）→ 结论：纤维类型打分组间差异讲\"组成\"，状态打分（应激/炎症/衰老）是\"组别敏感、亚群不敏感\"的信号，解读时分开
- **关键打分箱线图**：挑显著打分（如 IIa/OxPhos/Type I/Type II/Insulin/Sarcomeric）出 6 组箱线，p 值标注从打分差异 CSV 读（不重算），与比例图同风格

### 打分分层放置策略（22 打分怎么摆，2026-08-15 用户问"你觉得我们该怎么放这个打分呢？"）

用户拿到 22 打分问"怎么放"——**推荐拆两层放，不要 22 个全堆一张图**：

- **主图 = 18 程序/通路打分**（SenMayo/Stress/TNFA/Inflammatory/Glycolysis/FAO/Denervation/AMPK_PGC1a/Autophagy/Adipogenesis/mTORC1/Fibrosis 等）：打分 × 亚群热图（行=打分、列=亚群），颜色 = 6 组均值或五效应 Cohen's d——这才是要讲的生物学故事（衰老-炎症轴 vs 代谢-结构轴）
- **附图/验证 = 4 身份打分（scoreI/II/IIa/IIx）单独一张小图**：作用是验证注释对不对（IIX 亚群应 scoreIIx 高），不回答生物学问题，放进主图会跟亚群定义自说自话（循环论证）
- **纤维漂移（I↔IIa↔IIx）不靠打分讲**：用比例箱线图（已定稿那套）讲方向性——打分热图讲不了漂移方向
- 一句话原则：**身份打分 = "证明亚群是真的"（验证层）；程序打分 = "亚群在衰老/运动下怎么变"（故事层）**——两类问题不同，混一张图读者抓不到重点
- 备选（用户要一张大图全包含）：身份打分做成主热图**顶部的行注释条**，18 程序做主区——信息密度高但视觉仍分层
- ⛔ **用户问方案/看法（"你觉得怎么放""你怎么看"）= discussion 模式，直接给建议，不要先跑一堆工具验证**——身份 vs 程序分层是既定结论（本 skill + memory 已有），除非建议依赖未确认的数据细节（如打分列名、亚群列表），否则凭上下文直接答；乱调 execute_python/search_files 会被系统回合保护拦截（本会话实测，纯咨询问题撞 100 次回合保护）
- **⛔ 唤醒/状态检查上下文中的"怎么放"决策交付模板（2026-08-15 唤醒 #16 实测）**：Phase 1 已完成、用户未决问题是"肌肉身份怎么放打分"时，唤醒回复 = ① 三源核对（task_plan Phase 状态 + figures 产出物 + process list 后台）② 确认 Phase complete、后台已关 ③ **直接呈现分层推荐**（主图=18 程序打分×亚群热图，颜色=五效应 d；附图=4 身份打分小图作验证层；备选=身份做顶部行注释条）④ 列出 2-3 个候选选项让用户选——**不创建新 task_plan、不自动开跑、不重复验证已确认的数据**。用户当时给的选项集：按亚群拆分热图（打分×亚群×组别）/ 打分矩阵旁挂身份条 / 只保留整体热图——都映射到上述分层方案，未来遇到直接给推荐分层而不是再列一遍选项

### 打分解读生物学坑
- **scoreSenMayo 在肌纤维里衰老反而↓（FDR=0.007）**——SenMayo 是"衰老细胞"打分，肌纤维里下降不代表更年轻，更可能是衰老肌纤维丢失年轻表达谱但未进入典型衰老细胞态（或 SenMayo 主要在免疫/基质细胞高）。**肌纤维里谨慎解读，别写成"肌肉更年轻"**
- 衰老轴（Y vs O）与糖尿病轴（O vs OD）是不同模式：衰老 = IIa+OxPhos+Sarcomeric 全面↓；糖尿病 = Type I 程序↓ + Type II 程序↑（向糖酵解倾斜）——分开讲
- 运动唯一显著信号：老年运动回升 IIa 程序（FDR=0.031），这是"运动逆转"的关键证据点
- **基因集评估要点**（去神经化等自定义基因集）：① 检查方向相反基因（如 SCN4A 去神经时**下调**，与 SCN5A 上调共存会互相抵消）② 补经典 marker（去神经必加 **NCAM1**，Lai 2024 Nature 用它定义去神经纤维）③ 查与已有打分重叠（Atrophy/RegMyon/Sarcomeric 重叠基因 → 共线性，不能都讲）④ 缺哪类打分按研究问题补齐（骨骼肌衰老+糖尿病运动最少要补：Glycolysis 与 OxPhos 配对、AMPK-PGC1α 运动开关、Autophagy、Adipogenesis、Fibrosis）⑤ **区分度/信息量审查：泛谱系身份基因集在谱系同质子集中零区分度（2026-08-15 用户问"肌肉身份要放在这上面吗"）**——MF 子集数据（全部是肌纤维）里泛肌肉身份基因（MYH/ACTA1/TNNT/TPM）每群高表达 → 行内 z-score 后整行均色、无信息，不要为"显得完整"加恒定行。判断标准 = 该基因集在子集内部是否有跨亚群/跨组差异。身份信息已由亚型特异打分覆盖（scoreI/II/IIa/IIx = Fiber Identity 组）；CNS 惯例 = 身份基因走 UMAP FeaturePlot/marker 表佐证注释（如 MYH7/MYH2/MYH1），不塞进通路/效应打分热图——详见 `references/mf-score-analysis.md` 与 `references/geneset-supplement-2026-08.md`
- **⛔ 基因集语义污染判断（2026-08-14 实测 Denervation 案例）**：**任何打分出现"全亚群 × 多效应轴"一致方向的反直觉模式（如去神经打分运动后反而全亚群升高），先怀疑基因集语义污染而非生物学真信号**。诊断三步：① 出 **6 组原始 AUC 均值热图（不做效应、不做 z-score）**——区分"基线本来就高" vs "某组暴增"（实测 Denervation：Y_Pre 0.023 → O_Post 0.065 翻倍 = 运动后暴增而非基线高）② 查基因集构成与已有程序重叠（Denervation 11 基因中 **MYOG/RUNX1/NCAM1/MYH8 也是 RegMyon 再生核心标志**——运动诱导肌核再生被误捕为"去神经"，属假信号）③ 一个基因可属于多个生物学程序，基因集打分无法区分，必要时剔除重叠基因重算或正文注明局限。④ **用户质疑"你是不是算错了"→ 手动重算 + 展示原始均值表，并解释 Cohen's d 对低基线打分的放大效应**（见下方专项）。⑤ **用户采纳剔除重叠基因方案（2026-08-14）**：用户主动提议 Denervation 基因集改为 **8 基因** = CHRNA1/CHRNG/CHRND/SCN5A/KCNMB1/NCAM1/NGFR + RUNX1，**去掉 MYOG/MYH8/GAP43**。**⛔ 重叠基因 ≠ 一律剔除——逐基因查文献（2026-08-14 用户当场纠正 Agent 的倾向）**：用户说"RUNX1 也算上吧，我观察到它确实可能跟去神经有关"——这是对的，**RUNX1 有硬核去神经文献**：Zhu et al. 1994 MCB (PMID 7969143, AML1 受神经支配调控) + Wang et al. 2005 Genes Dev (PMID 16024660, Runx1 去神经后诱导、防萎缩)。所以只剔除**无去神经特异性的纯再生/施万标志**（MYH8=发育型肌球蛋白、MYOG=肌生成 TF、GAP43=施万细胞），**RUNX1 保留**（去神经应答 TF + 再生必需，双面基因，生物学上本就交织）。污染诊断的正确执行 = 先查每个重叠基因的单基因文献再决定去留，不是机械剔除。更新 `pathway_score_CLEAN.xlsx`（SuppTable3 宽表，Class/Signature/Annoation/Genes 四列 + 基因逐列展开）时按用户版本执行，并按 Class 分类整理（AChR 亚基 CHRNA1/CHRNG/CHRND | 离子通道 SCN5A/KCNMB1 | 粘附/神经营养受体 NCAM1/NGFR | 转录因子 RUNX1）；来源三篇：Covault & Sanes 1985 PNAS (PMID 3892537) / Tang et al. 2009 MBC (PMID 19109424) / Lai et al. 2024 Nature (PMID 38649488)。⑥ **净化后重算对比（2026-08-14 用户重跑验证）**：用户用 8 基因重跑 AUCell → 运动轴效应**回落但未消失**（ExOld +1.03→+0.96、ExT2D +0.82→+0.80），Aging 反而略升（+0.59→+0.73）= 剩余 8 基因本身参与 NMJ 重塑，**预期管理：净化 ≠ 运动轴归零**；T2D 轴仍无信号（d≈0）。详见 `references/denervation-geneset-contamination.md`
- **⛔ 效应计算被质疑时的重算验证流程 + Cohen's d 低基线放大效应（2026-08-14 实测，用户问"你有没有算错"）**：
  - 场景：效应热图显示 Denervation 全亚群全效应正，但 6 组原始打分热图显示只有 SMF 绝对分高——用户质疑"是不是算错了"。
  - **响应顺序（先重算后解释）**：① 从 `effect5_d_table.csv` 抽出该打分行全部 50 个效应值 → ② 从 `agg_sample.csv`（样本级聚合表）**用 scipy.stats / pandas 手动重算 Cohen's d**（`d = (g2.mean − g1.mean)/pooled_sd`，逐亚群 × 逐效应）→ ③ 逐格比对与表值一致 → **先回答"没算错"（用重算表作证）** → ④ 再解释为什么数据本身就是这样。
  - **核心解释（绝对水平 ≠ 相对变化）**：效应热图颜色 = Cohen's d（相对变化），不是绝对分。**起点极低的打分（AUC 0.02~0.03）+ 样本内方差小 → 绝对变化仅 +0.003~+0.008 也能得 d=+0.3~+1.0**（SD 小 → d 大）。所以"效应图全红"≠"绝对分高"，而是"每个亚群都在涨"（不管起点多低）。
  - 实测数值（Denervation，Y_Pre→O_Pre）：LRP1B+(I) 0.0197→0.0231（+17%）、OTUD1+(I) 0.0266→0.0309（+16%）、SMF 0.0305→0.0663（+117%）→ **Aging 列全红是真的，但绝大多数亚群绝对变化微小**，颜色深浅（d）放大了这种微小变化。
  - 运动轴更极端：ExOld（O_Pre→O_Post）全亚群几乎翻倍（+71%~+179%）= 基因集污染实锤（运动诱导再生），与原始打分热图交叉验证。
  - **验证用原始均值表交付**：`效应 | d=+x.xxx | Y_Pre=0.0197 → O_Pre=0.0231 (n=10→7)` 格式逐亚群列出，让用户亲眼看到"低起点小涨也有大 d"——比口头解释更有说服力。用户对效应量计算会亲自验证，必须给足数值证据。
- **⛔ 交付 R 基因向量必须完整，程序化生成（2026-08-14 用户两次纠正）**：用户会数基因数
  （"那些基因，你怎么省略了？给我完整的啊"）。**从 CSV/数据文件程序化生成 R 代码**（读
  new_genesets_final.csv → 10 个/行分组 → 拼 `Name <- c(...)`），**不要手抄**（手抄=截断风险）；
  生成后验证每集基因数与源数据一致（200/158/11/16/27/200/200/90）。每集内部 `unique()` 去重
  （Reactome 原始自带重复，95 条目→90 唯一）。msigdbr 26.1.0 API 变更：`category=`→`collection=`、
  KEGG 用 `CP:KEGG_LEGACY`（旧名）、KEGG_MEDICUS 碎片化不适合打分——详见
  `references/geneset-supplement-2026-08.md`

### CNS 级"效应矩阵"图组（2026-08-14 实测：AUCell meta CSV → 三图架构 + 五效应扩展版）

当用户要"CNS 级别/主刊审美"且数据集是**细胞级 meta CSV**（每行=细胞，含 samplename/type/annotation_L3 + 22 个 AUCell 打分列，50 万细胞级）时，用效应矩阵图组替代逐打分箱线图——一张图回答"哪些打分被衰老/运动/糖尿病改变"。实测成功案例：`MF_AUCell_meta.csv`（508,661 细胞 × 58 列）。

- **⛔ 格式复用铁律（用户原话"按照Figure1的格式出啊"）**：用户认可某图格式后要求扩展（如 3 面板→5 面板），必须**原样复刻布局/配色/标注，只改用户要求的维度**；**从 `results/<session>/log/system_log.jsonl` 提取原图生成代码**（search_files pattern=`输出文件名` → 命中行 args.code）在其上改，禁止凭记忆重写或自行创新布局（曾自作主张改成 50 列大宽图被打回）。
- **统计设计（防伪重复）**：50 万细胞直接算 = 伪重复。先 `samplename × annotation_L3` 聚合打分均值（48样本×10亚群=479行）→ 每 打分×亚群×效应 组合算 **Cohen's d + Wilcoxon 秩和 p（BH 校正）**
- **三效应**：Aging(O_Pre−Y_Pre) / Exercise_O(O_Post−O_Pre) / T2D(OD_Pre−O_Pre)
- **五效应扩展（用户拍板版）**：Aging / T2D / ExYoung(Y_Post−Y_Pre) / ExOld(O_Post−O_Pre) / ExT2D(OD_Post−OD_Pre) 五面板并排 → 回答"糖尿病是否拖累运动对衰老的逆转"。⚠️ L1 辩论 verdict=modify：并排面板无组间检验（ExOld vs ExT2D），**只能当趋势展示，不能下因果结论**
- **逆转率**（仅对 Aging 显著组合）：`reversal = 1 - (O_Post − Y_Pre)/(O_Pre − Y_Pre)`；>0=向年轻回拉，<0=恶化。实测中位数：Metabolic +0.21 / Identity +0.36 / Senescence −0.07 → "运动是衰老的镜子，只照见代谢-结构这一半"。
- **Fig1 Hero 效应矩阵**：N 面板横排（Aging/Exercise/T2D 或五效应）+ 左侧功能轴色条 + 右侧逆转率条；行=打分按功能轴分组（Metabolic/Identity/Senescence），列=亚群；红蓝 diverging（#2166AC→白→#B2182B）±3 截断，星号=p<0.05
- **Fig2 配对个体响应**：Aging |d| top-4 组合画老年个体 Pre→Post 连线（samplename 去 `_Pre/_Post` 后缀配对），配对 wilcoxon p 标标题
- **Fig3 效应散点**：x=Aging d、y=Exercise d，每点=打分×亚群，颜色=功能轴，加对角线——一眼看出"只有代谢轴在对角线（运动逆转衰老）、炎症轴贴 x 轴（运动无效）"
- **6 组原始打分热图（效应矩阵的诊断姐妹版，2026-08-14 用户点名要）**：效应矩阵只给差值、丢绝对水平；用户问"为什么这个打分全亚群都高"时直接出 6 组原始打分热图（列=6组×10亚群=60，行=22打分行内 z-score，组色带 Pre 浅/Post 深，RdBu ±2.2）→ 一眼区分"基线本来就高" vs "某组暴增"。**读单一行时看原始均值表（z-score 抹掉绝对尺度）**。Denervation 案例实证：Y_Pre 0.023 → O_Post 0.065 = 运动后暴增（基因集污染假信号）。配方见 `references/denervation-geneset-contamination.md`
- **结论模板**：逆转率按功能轴分层就是故事（实测：Metabolic 中位 +0.21、Identity +0.36、Senescence −0.07）→ "运动是衰老的镜子，只照见代谢-结构这一半"。交付时结论先行，图作为证据
- 完整实现配方 + 可直接复用的 Python 代码 + 五效应版布局细节 → `references/cns-effect-matrix-aucell.md`

### ⛔ 用户问\"红色代表谁上升\"（效应矩阵颜色语义问答，2026-08-14 实测）

用户拿到效应矩阵热图后问\"红色代表谁上升？\"——**禁止凭记忆/凭直觉答，必须三步核实后答**：

1. **追溯真实生成代码**：保存的脚本可能是空壳 stub（实测 `aucell_cns_figure.R` 只有 33 行读数据代码，真正的热图代码在 execute_code 调用里）→ 从 `results/<session>/log/system_log.jsonl` 提取（search_files pattern=`Fig1_five_effects_matrix` 或 `TwoSlopeNorm` → 命中行 json 的 args.code）
2. **解码配色 + 符号约定**：读出 `LinearSegmentedColormap.from_list(...)` 三色锚点 + `TwoSlopeNorm(vmin, vcenter=0, vmax)` + 效应定义（`eff_defs` 元组顺序）。**五效应版实测**：`['#2166AC','#F7F7F7','#B2182B']` = 蓝→白→红，`d = (g1.mean − g2.mean)/SDpooled`（**正 d = 元组前项组更高 = 红色**）。eff_defs：Aging=(O_Pre,Y_Pre)、T2D=(OD_Pre,O_Pre)、ExYoung=(Y_Post,Y_Pre)、ExOld=(O_Post,O_Pre)、ExT2D=(OD_Post,OD_Pre) → **Aging 列红 = 老年组打分高（衰老上调）；T2D 列红 = 糖尿病组高；Ex* 列红 = 运动后高（运动上调）**。蓝 = 负 d = 效应组更低
3. **用真实数据验证符号**：从 `effect5_d_table.csv` 抽一个生物学上方向明确的行（如 OxPhos 衰老应下降 → Aging 轴 d 应为负）确认符号方向与预期一致，再答。若发现反直觉结果（如 SenMayo 在 Aging 轴 d 为负 = 老年组 SenMayo 反而低于年轻组，原始均值 Y_Pre=0.034 vs O_Pre=0.030）→ **如实报告反直觉点**并建议确认打分方向/样本构成，不要掩盖

⚠️ 与比例箱线图 Cliff's delta 方向约定（正值=后者高）**不同**：效应矩阵 Cohen's d 约定为**前项组（效应组）高=正=红**——两套约定并存，回答前必须看代码，不能套用箱线图约定。

### ⛔ 效应量大 ≠ 统计显著：热图颜色深 ≠ 显著（2026-08-14 用户问"Fibrosis 这个RSS好像很显著啊"实测）

**触发场景**：用户看按 Cohen's d 着色的效应矩阵/热图，某格颜色很深（尤其 RSS 这类特异亚群），说"XX 好像很显著啊"。

**必须区分两个概念**：
- **效应量（Cohen's d）**：热图颜色依据。d=0.79/0.82 属于"大效应"，视觉上红得非常抢眼
- **统计显著性（raw p / FDR q）**：Welch t / Wilcoxon 检验结果。小样本（每组 4-6 个体）下 **d 大 ≠ p 显著**——个体间方差大，检验功效不足

**Fibrosis×RSS 实测（5 格全不显著）**：
| 轴 | Cohen's d | raw p | FDR q |
|-----|----------|-------|-------|
| RSS\|Aging | 0.79 | 0.193 | 0.457 |
| RSS\|T2D | 0.68 | 0.456 | 0.639 |
| RSS\|ExOld | 0.82 | 0.383 | 0.543 |

**处理流程**：
1. 用户质疑某格"显著" → **立即查 `effect_table.csv`（含 raw p）或 `effect5_q_table.csv`（FDR q）+ `effect5_d_table.csv`（d），不许凭热图颜色/记忆回答**（本次就是靠 read_file 三张表实锤：d 大但 p 全不显著）
2. 如实说"你对了一半"：效应量确实大（颜色深的原因），但统计上不显著（raw p / FDR q 数值摆出来）
3. 报告语言铁律：**只能写"呈升高趋势（d=0.79）"、"效应量大但未达显著"，绝不能写"显著"**——用户会拿 q 值对质
4. 如果用户想支撑显著性：说明功效不足的根因（每组 n=4-6），可建议 paired 检验（个体配对提功效）或增加个体数；`gene_set_response_summary.csv` 的 n_sig_all=0 就是"整体无 FDR<0.05 格"的权威依据
5. "删除哪个基因集"类筛选决策：d 大 + 方向一致 + 特异亚群集中 = 保留（故事线资产）；d 小 + 全轴无方向 = 可删。**筛选标准是"是否有特异信号"，不是"是否显著"**

⚠️ 相关坑：`gene_set_response_summary.csv` 里"弱响应(慎删)"判定基于 FDR<0.05 格数=0，但该判定**不代表该基因集无生物学信号**（可能只是小样本检验不出）——引用该表下删除结论前先查特异亚群 d 值。

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
  实际是 **R-4.5.3**（2026-08-13 实测确认，非 R-4.4.2），本项目分析须 R-4.5.3 全路径 +
  `.libPaths('E:/R-libs/R-4.5.3')`——但画图场景不可靠，用 RDS 缓存更省事）
- `Rplots.pdf` 是 R 空设备残留文件（png()/print 组合产生），无内容，交付前忽略/删除，不要当产出物
- **⛔ execute_r 持久内核画图场景不可靠（2026-08-12 实测）**：纯计算（定义变量/读 RDS）跨调用保留
  （同一 PID 复用 ✅），但**绘图函数内 `print(p)` 会触发内核崩溃 → execute_r 静默回退新 Rscript 进程 →
  变量全丢**（ggplot print 需要图形设备，kernel worker 无设备）。结论：本类绘图任务**首选 RDS 缓存方案**
  （01_build_cache.R 构建 percentage_data.rds 一次性 → 02_plot_celltype.R 每个亚群 readRDS 秒级画图），
  不要依赖 execute_r 持久内核画图。若一定要用 kernel，去掉函数里的 `print(p)`（ggsave 足够）。
- **⛔ bash 双引号内 `Rscript -e "..."` 的 `$` 变量展开坑（2026-08-12 两次踩坑）**：`-e "paste(sub$group1, sub$group2)"`
  在 bash 双引号里 `$group1` 被 bash 展开为空 → 变成 `paste(sub, sub)` → 匹配全部失败返回 "NOT FOUND"，
  误判"数据缺失"。**R 验证/调试代码一律 write_file 写成 .R 脚本再 Rscript --vanilla 跑**，不要用 -e 内联，
  或内联时全部 `\$` 转义。
- **出图前核对用户指定的比较子集数量（comp_mode）**：交付前用 R 侧 `verify_xxx.R` 检查标注数 =
  用户要求数（如 5/5），且每个比较的 p/FDR 值从 sig_table 核对（bash $ 坑：验证脚本用 write_file）
- **`fwrite(row.names=TRUE)` 写的 CSV 首列是空表头 `\"\"`**（2026-08-13 踩坑）：pandas 读必须 `pd.read_csv(path, index_col=0)`，
  否则 `df['annotation_L3']` 直接 KeyError。R 侧 `fread()` 读它首列名也是 `\"\"`——统一记住\"行名导出 = 空表头第一列\"。
- **data.table 的 `DT[i, ..cols]` 语法在 for 循环/脚本里不可靠**（2026-08-13：top3 循环输出被吞，返回空）：
  跨列逐行操作（如\"每亚群 top3 打分\"）改用 Python pandas（`df.rename` 后 `r[cols].sort_values()`）或显式
  `as.data.frame()` 转 base R 再索引，不要依赖 `..` 前缀语法在复杂循环里的行为。
- **⛔ 用户已有基因集 xlsx 的追加/编辑格式铁律（2026-08-13 被用户两次抓住）**：\n  `pathway_score.xlsx` 这类用户手工维护的基因集表是**宽表格式**——每个基因占一列（D 列起逐列展开），\n  不是 TAB 分隔挤一个单元格！追加新基因集时必须保持同样格式（`Class | Signature | Annoation | 基因1 | 基因2 | ...`）。\n  教训链：① Agent 用 `write.xlsx` 把 8 个新基因集写成 `ABCB6\\tADORA2B\\tAGL...` 单格 → 用户\"一看就有问题\"；\n  ② Agent 改写成宽表但用 openxlsx 重写 → 生成损坏文件（zip 引用 `xl/drawings/drawing1.xml` 但文件缺失，\n  openpyxl 直接 KeyError / dims 1x1）→ 用户\"你都不调查吗\"。\n  **正确方案**：备份原文件后，用 **openpyxl 从零重建**（`Workbook()` 新建、按宽表写入、`wb.save`），\n  不要用 openxlsx 重写用户已有文件（写入会带损坏 drawing 引用）；原文件格式读取用 zipfile 直接解析\n  `xl/sharedStrings.xml` + `xl/worksheets/sheet1.xml`（sharedStrings 索引 + 行列坐标 → 基因宽表），\n  openpyxl 读损坏文件会崩但 zipfile 解析一定能拿到数据。写入前先备份，写入后重读验证行数/列数/基因数。\n  参考 `references/xlsx-geneset-wide-format.md`。
- **⛔ `requireNamespace(p, quietly=TRUE)` 只查包描述元数据、不加载 DLL——坏包会显示 TRUE 假象（2026-08-14 实测）**：
  E:/R-libs 批量 DLL 损坏时，`requireNamespace('digest')` 返回 TRUE 但 `library(digest)` 报
  `LoadLibrary failure`。**真实验证包能否加载必须**：
  `tryCatch({suppressPackageStartupMessages(library(p, character.only=TRUE)); TRUE}, error=function(e) FALSE)`
- **⛔ R 库批量 DLL 损坏时：最多修一轮，再坏就转 Python（2026-08-14 突破性经验，当天靠它交付成功）**：
  症状 = 多个包报 `LoadLibrary failure: 找不到指定的程序`（digest/cluster/Matrix/vctrs…）或
  `lazy-load database ... is corrupt`（vctrs.rdb），且分布在多个库根目录（E:/R-libs/R-4.5.3、
  C:/Program Files/R/R-4.5.3/library、C:/Users/<user>/R/R-4.5.3-library 三处）。
  逐包重装是陷阱（修好 digest 冒出 cluster、修好 cluster 冒出 vctrs——无底洞）。**正确路径**：
  中间结果（聚合表/效应表）**先落盘 CSV** → 用 Python（pandas+seaborn+matplotlib）直接读 CSV 出图，一次成功。
  实测：R 端修 6+ 轮无产出后转 Python，立即交付三张 CNS 级图（seaborn 0.13.2 + matplotlib 3.11 本机健康）。
- **⛔ 别在环境检查上打转（用户原话："你老是检查terminal干什么全是报错" / "为什么还在跑terminal呢？？？"）**：
  连续 ≥2 轮没有任何图/文件/明确结果产出 = 已在打转。立即要么出图、要么换栈、要么如实报告阻塞点。用户说
  "找原因，先不执行" = 只诊断不改，诊断完给根因，不要顺手执行修复。
- **⛔ 交互框 Markdown 表格会错位——交付数据表用等宽代码块（2026-08-14 用户两次抓"还是错位的，真的"）**：
  在聊天交互框里用 Markdown 表格（`| 亚群 | Y_Pre | ... |`）展示 10 亚群 × 6 组数值表时，**客户端渲染会
  按内容撑开列宽导致表头与数值错位**（用户两次反馈"还是错位的"）。修复：改用 **等宽代码块**（``` 包裹、
  每列固定宽度、数字统一小数位）保证绝对对齐——用户确认"这样对齐了"。但用户同时说"我更喜欢之前那种"——
  指之前用 matplotlib 生成的表格**图**（PNG，横向紧凑 + 公式全称表头如 `Aging (O-Y)`/`ExYoung (Y_post-pre)`）。
  结论分层：**交互框内**用等宽代码块（对齐优先）；**交付产物**用 matplotlib 表格图（样式优先，列宽显式对齐）；
  用户偏好"之前那种" = matplotlib 表格图样式，但必须修好列宽对齐（见下一条 pitfall）。
- **⛔ matplotlib 表格图列宽对齐 + CJK 字体（2026-08-14 用户抓"最上面的栏跟下面的数值栏，大小不统一"）**：
  用 matplotlib 画**数据表格图**（行=亚群、列=效应值）时，表头列宽与数值列宽必须用**同一套显式列宽数组**
  （`col_widths = [0.16] + [0.168]*5`，表头循环与数据行循环都 `x = sum(col_widths[:c])` 定位）——
  若表头用 text 自由摆放、数值用 `ax.table`/自动列宽，两者会对不齐（用户一眼看出）。自查：OCR/截图核对
  表头 x 坐标与数值列 x 坐标一致。另：**DejaVu Sans 无 CJK 字形**——图内注释/表头一律英文
  （如 "red = positive effect" 而非中文），中文会变方框（Glyph missing 警告）。
- **⛔ `_AUC` 后缀不匹配 → pivot/reindex 全 NaN → 全白热图（2026-08-14 实测，vision 抓住）**：
  AUCell meta CSV 打分列名带 `_AUC` 后缀（`scoreOxPhos_AUC`），而热图脚本的 `score_names` 列表可能没带。
  `df.pivot_table(...)` 后 `d.reindex(score_names)` → 22 行全 NaN → `cmap(norm(NaN))` 全透明/白 → 生成
  **看似正常尺寸、实则全白的热图**（vision 主色 93.5% 空白，OCR 无行标签，ASCII 亮度图主体全亮）。
  ① 修复：读 CSV 后先 `df["score"] = df["score"].str.replace("_AUC$", "", regex=True)` 再 pivot，或 col_map
  把 `_AUC` 列映射回裸名。② **必须加数据非空断言**：`assert d.notna().all().all()`，脚本跑完自己拦截全白图，
  不要把白图交付（用户会当场打开看）。③ 绘图前用 vision_describe 做一次质量门（见下条）。
- **⛔ 出图后 vision 质量门 + 样式回归契约（2026-08-14 用户否决 v2 后 v3 恢复）**：
  用户认可某版图（v1）后要求换数据重出——**重做版必须严格保持 v1 的样式契约，任何偏离都会被一眼抓出**：
  ① **行标签必须完整基因集全名**（scoreOxPhos/scoreSenMayo/Denervation…22 个），不能只留 3 个分组名
  （Metabolic/Fiber Identity/Senescence）——用户原话"没有基因集的名字，要么就是简写，为啥偷懒？"
  ② **配色必须用户认可的红蓝白 RdBu**（#2166AC→白→#B2182B），换色系/混入青黄杂色会被打回"颜色没有之前的好看"
  ③ **列模块严格对齐 + label 全部在图形外**（行标签左侧、面板标题顶部、亚群标签底部斜排；不能挤进图形内部）
  ④ **交付前用 vision_describe 对比 v1/v2/v3 三张图**：OCR 查行标签完整性、主色查配色、ASCII 亮度图查格子
  是否画出来（全亮 = 白图）、亚群标签坐标查是否在图形内。先自查再交付，不要等用户说"你画的图有问题"。
- **⛔ matplotlib `plt.tight_layout()` + `fig.add_axes()` 颜色条不兼容 → PNG/PDF 渲染分叉（2026-08-14 v5→v6 关键修复）**：
  同一脚本里 `plt.tight_layout()` 与手动 `fig.add_axes([...])` 颜色条共存会触发 `UserWarning: Axes not compatible with tight_layout`，
  后果 = **PNG 底部标签被裁剪/热图空白，而 PDF（矢量）正常**——用户看到"PNG 没变、PDF 对了"的诡异分叉，误以为是缓存。
  修复 = 去掉 tight_layout，改用 `fig.subplots_adjust(left=,right=,bottom=,top=)` 手动布局，三种格式渲染一致。
  **判断 PNG 是否真更新**：别只看文件大小/时间戳，用 vision_describe 看主色（热图区不应 60%+ 灰白 #e0e0e0）+ 裁剪底部 OCR 确认标签贴边。
  亚群标签离热图太远的正确参数 = 底部 45° 斜排 `y=-0.15`（不是 -1.9）。详见 `references/cns-effect-matrix-aucell.md` v5→v6 节。
- **⛔ Fig7 打分×亚群热图必须转置（2026-08-14 用户明确：y轴是基因集名字，亚群是x轴）**：y=22 打分、x=10 亚群，不要默认行=亚群列=打分；行分组色带移左侧。
- **⛔ type×亚群 六组分布热图标签布局（2026-08-15 用户三连纠："亚群在下面，type在上面，label又在图内了"）**：
  出"6 组原始打分 × 10 亚群"分布热图（列=6type×10亚群=60，type 间间隙 1.2、亚群无间隙 CELL=1.0，行=22 打分 z-score）
  时：**亚群标签必须在底部 45° 斜排、type 标签在顶部、所有 label 在图形外**。底部标签若进图内 =
  画布底部留白不够 + y 坐标没同步下移：`SUB_H=5.0`（不是 3.2）+ 标签 `y=HEAD_H+n_rows*CELL+0.9`（不是 +0.25），
  两者必须同步调，否则 `bbox_inches='tight'` 会把标签裁回图内（与 v6 tight_layout 坑同源）。脚本
  `fig_type6_v8.py` 为最终可用版。详见 `references/cns-effect-matrix-aucell.md` v7→v8 节。
- **⛔ matplotlib 逐格热图白色间隙根因 = CELL<1.0（2026-08-14 用户抓 小色块之间不要有白色间隙 且以 v1 为基准）**：
  用 `ax.add_patch(Rectangle((x,y), CELL, CELL, edgecolor=none))` 逐格画热图时，**CELL 必须 = 1.0 填满整个单元格**；
  手滑改成 0.94/0.82 会在相邻格子间留 0.06/0.18 白色缝隙（与 edgecolor 无关，edgecolor=none 也留缝），用户一眼看出与 v1 的差异。
  修复 = 格子宽/高 = 行/列间距 = 1.0 严格匹配。用户提列宽调小时改 figsize/xlim 收窄整体图宽，**不要用 CELL<1.0 制造更窄**（那会同时产生白缝）。
  行分组间隙最终值 = `ri += 0.2`（用户明确指定），面板间距 PANEL_GAP=1.8 保持不变。最终可用脚本 `fig_v7_final.py`。详见 `references/cns-effect-matrix-aucell.md` v6→v7 节。
- **⛔ 六组分布热图（type×亚群）当用户说\"像 figure1 v7 那样\"→ 直接复用多面板横排架构（2026-08-15）**：
  单张 60 列大矩阵（v8）反复调标签后用户拍板\"你能不能像 figure1 v7 那样呢？它的脚本是对的，出图也很好\"。
  正确响应 = **从用户已认可图的脚本（fig_v7_final.py）复制改数据源，而不是继续在 v8 上打补丁**：6 个 type 各一个面板横排、
  每面板 10 亚群列、亚群标签 45° 贴底 y=-0.15、type 标题顶部、行分组 0.2、无白缝 CELL=1.0、subplots_adjust 手动布局。
  产物 `fig_type6_v9.py` → `Fig_type6_by_subcluster_v9.png`。用户确认\"很完美\"。
- **⛔ \"真实 AUCell 分数\"诉求 → 别卡死在窄区间，默认还是 z-score（2026-08-15）**：
  用户要\"真实的 AUCell 分数\"时若实现为 `TwoSlopeNorm(vmin=0, vcenter=0.05, vmax=0.20)` 会被打回（\"你把值卡死在0.2,其他的怎么办呢？还是z-score吧\"）——
  AUCell 绝对分集中在 0-0.2，vmax=0.2 把绝大多数格子压到同色丢信息。要么全 0-1/数据驱动 max 映射，要么（用户终态）回到行内 z-score。
  **z-score 仍是本类热图默认**；回 z-score 要同步改数据层 + 颜色层（TwoSlopeNorm(-2,0,2) + colorbar 刻度 [-2,-1,0,1,2] + 标签 row z-score）。
- **⛔ pandas MultiIndex × z-score 两大坑 + numpy 层修复（2026-08-15）**：① `apply(lambda r: zscore(r), axis=1)` 把 DataFrame 变 Series（scipy zscore 返回 ndarray）→ MultiIndex 列丢失 → `Z.loc[name,(tp,sub)]` 报 `IndexingError: Too many indexers`；② `(Z_raw - Z_raw.mean(axis=1))` 报 `cannot join with no overlapping index names`（MultiIndex 列与 Series 广播）。**✅ 修复 = numpy 层向量化**：`Z=Z_raw.copy(); Z[:]=(Z_raw.values - Z_raw.values.mean(axis=1,keepdims=True)) / Z_raw.values.std(axis=1,ddof=0,keepdims=True)`——`.values` 取底层数组运算再写回，MultiIndex 完整保留。详见 `references/cns-effect-matrix-aucell.md` v8→v9 节。

## 用户上传图识别（2026-08-14 实测）
- 用户上传项目产出图（如 Fig1_five_effects_matrix PNG）问"能识别这个图吗" → **不要只凭肉眼描述**，先 `vision_describe(image_path)` 拿 OCR + 元素检测 + ASCII 亮度图事实清单，再结合项目上下文（本 skill 的图格式约定）回答
- 识别要点：读标题（如 "AUcell pathway activity across myofiber subtypes... n=24"）、面板结构（1×5 并排 = Aging/T2D/ExYoung/ExOld/ExT2D）、行顺序（22 打分按功能轴分组）、图例（Cohen's d ±3 红蓝 diverging）
- 识别后主动确认用途：这张图是谁做的/哪一版/要不要在它基础上改（如更新 Denervation 行）——用户上传旧图常伴随新诉求（改基因集/改版），识别只是入口

## 支持文件
- `references/mf-l3-proportion-case.md` — 骨骼肌 MF L3 10 亚群实测案例：脚本结构、显著性结果、Pure Type I/IIA 结论与响应者分析
- `references/mf-score-analysis.md` — AUCell 打分跨组差异实测：相关性冗余/独立结构、衰老/糖尿病/运动三轴显著结果、SenMayo 解读陷阱、去神经化基因集评估（SCN4A 方向坑 + NCAM1 缺失 + 重叠检查）、缺失打分建议（Glycolysis/AMPK-PGC1α 等）、真实文献 PMID 清单
- `references/xlsx-geneset-wide-format.md` — 用户基因集 xlsx 宽表格式追加/编辑铁律 + openxlsx 损坏文件修复配方（zipfile 解析读取 + openpyxl 从零重建）
- `references/go-term-selection-per-subtype.md` — 亚群 GO 富集词条筛选（MF_L3_GO_AllLists.xlsx）：Log(q-value)≤-1.3 过滤 + **特异性优先选词条算法**（挑亚群独有词条，不是 marker 命中数优先——第一版给 10 亚群全挑共享 sarcomere 词条被用户否决）+ 正刊 GO 词条挑选方法论（去冗余/差异化/锚定身份/dotplot）+ L2 辩论警示（LRP1B+ 突触需注明 NMJ、RSS 泛 growth 换 BMP、RP_high 核糖体注明管家基因背景）+ openpyxl 科学计数法/read_only 无 dimensions 坑 + **CNS 级别 GO dotplot 完整配方**（关键词驱动选词条 → ggplot2 dotplot：shape=21、size=Enrichment、fill=-log10(q) 蓝白红渐变、PNG+PDF 双导出）。触发词："GO词条" / "富集词条" / "MF_L3_GO_AllLists" / "亚群富集" / "GO dotplot" / "GO富集图"
- `references/cns-effect-matrix-aucell.md` — **CNS 级效应矩阵图组配方**（2026-08-14）：细胞级 AUCell meta CSV → 样本级聚合（防伪重复）→ Cohen's d + Wilcoxon 三效应（Aging/Exercise/T2D）→ 三图架构（Fig1 效应矩阵热图 + Fig2 配对个体响应 + Fig3 Aging-vs-Exercise 效应散点）+ 逆转率公式 + 可直接复用的 Python 实现 + **五效应扩展版 + 颜色语义问答三步核实 + v5→v6 定稿参数（tight_layout/add_axes 坑、亚群标签 y=-0.15、Fig7 转置）+ v6→v7 无白缝 CELL=1.0 + v7→v8 六组分布热图标签布局 + v8→v9 多面板重构（像 fig1 v7 那样）+ 真实分数 vs z-score 决策 + pandas MultiIndex×zscore numpy 层修复**。触发词："CNS级别" + "AUCell打分" / "效应矩阵" / "逆转矩阵" / "主刊图" / "PNG没变PDF对了"
