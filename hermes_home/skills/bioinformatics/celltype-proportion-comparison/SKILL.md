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

### 打分解读生物学坑
- **scoreSenMayo 在肌纤维里衰老反而↓（FDR=0.007）**——SenMayo 是"衰老细胞"打分，肌纤维里下降不代表更年轻，更可能是衰老肌纤维丢失年轻表达谱但未进入典型衰老细胞态（或 SenMayo 主要在免疫/基质细胞高）。**肌纤维里谨慎解读，别写成"肌肉更年轻"**
- 衰老轴（Y vs O）与糖尿病轴（O vs OD）是不同模式：衰老 = IIa+OxPhos+Sarcomeric 全面↓；糖尿病 = Type I 程序↓ + Type II 程序↑（向糖酵解倾斜）——分开讲
- 运动唯一显著信号：老年运动回升 IIa 程序（FDR=0.031），这是"运动逆转"的关键证据点
- **基因集评估要点**（去神经化等自定义基因集）：① 检查方向相反基因（如 SCN4A 去神经时**下调**，与 SCN5A 上调共存会互相抵消）② 补经典 marker（去神经必加 **NCAM1**，Lai 2024 Nature 用它定义去神经纤维）③ 查与已有打分重叠（Atrophy/RegMyon/Sarcomeric 重叠基因 → 共线性，不能都讲）④ 缺哪类打分按研究问题补齐（骨骼肌衰老+糖尿病运动最少要补：Glycolysis 与 OxPhos 配对、AMPK-PGC1α 运动开关、Autophagy、Adipogenesis、Fibrosis）——详见 `references/mf-score-analysis.md` 与 `references/geneset-supplement-2026-08.md`
- **⛔ 交付 R 基因向量必须完整，程序化生成（2026-08-14 用户两次纠正）**：用户会数基因数
  （"那些基因，你怎么省略了？给我完整的啊"）。**从 CSV/数据文件程序化生成 R 代码**（读
  new_genesets_final.csv → 10 个/行分组 → 拼 `Name <- c(...)`），**不要手抄**（手抄=截断风险）；
  生成后验证每集基因数与源数据一致（200/158/11/16/27/200/200/90）。每集内部 `unique()` 去重
  （Reactome 原始自带重复，95 条目→90 唯一）。msigdbr 26.1.0 API 变更：`category=`→`collection=`、
  KEGG 用 `CP:KEGG_LEGACY`（旧名）、KEGG_MEDICUS 碎片化不适合打分——详见
  `references/geneset-supplement-2026-08.md`

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

## 支持文件
- `references/mf-l3-proportion-case.md` — 骨骼肌 MF L3 10 亚群实测案例：脚本结构、显著性结果、Pure Type I/IIA 结论与响应者分析
- `references/mf-score-analysis.md` — AUCell 打分跨组差异实测：相关性冗余/独立结构、衰老/糖尿病/运动三轴显著结果、SenMayo 解读陷阱、去神经化基因集评估（SCN4A 方向坑 + NCAM1 缺失 + 重叠检查）、缺失打分建议（Glycolysis/AMPK-PGC1α 等）、真实文献 PMID 清单
- `references/xlsx-geneset-wide-format.md` — 用户基因集 xlsx 宽表格式追加/编辑铁律 + openxlsx 损坏文件修复配方（zipfile 解析读取 + openpyxl 从零重建）
- `references/go-term-selection-per-subtype.md` — 亚群 GO 富集词条筛选（MF_L3_GO_AllLists.xlsx）：Log(q-value)≤-1.3 过滤 + **特异性优先选词条算法**（挑亚群独有词条，不是 marker 命中数优先——第一版给 10 亚群全挑共享 sarcomere 词条被用户否决）+ 正刊 GO 词条挑选方法论（去冗余/差异化/锚定身份/dotplot）+ L2 辩论警示（LRP1B+ 突触需注明 NMJ、RSS 泛 growth 换 BMP、RP_high 核糖体注明管家基因背景）+ openpyxl 科学计数法/read_only 无 dimensions 坑 + **CNS 级别 GO dotplot 完整配方**（关键词驱动选词条 → ggplot2 dotplot：shape=21、size=Enrichment、fill=-log10(q) 蓝白红渐变、PNG+PDF 双导出）。触发词："GO词条" / "富集词条" / "MF_L3_GO_AllLists" / "亚群富集" / "GO dotplot" / "GO富集图"
