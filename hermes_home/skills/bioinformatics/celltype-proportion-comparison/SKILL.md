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
- **⛔ 定稿导出 = PNG + PDF 一次同时出，不要只出 PNG 等用户开口（2026-08-17 Specialized MF cluster1 实测）**：
  用户拿到 PNG 后追了一句"要生成pdf格式啊"，随即又补"保留png"——**PDF 是矢量投稿版、PNG 是 300dpi 预览版，两者都要，PDF 不是 PNG 的替代品**。
  脚本里对同一 `p_scaled` 对象连续两次 `ggsave`：
  `ggsave('xxx.png', p_scaled, dpi=300, bg='white', limitsize=FALSE)` +
  `ggsave('xxx.pdf', p_scaled, device='pdf', bg='white', limitsize=FALSE, useDingbats=FALSE)`
  交付清单同时列 PNG 与 PDF（用户会按文件大小/存在性核对）。
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
- **⛔ 3柱衰老逆转正式版 = 全部 3 个两两比较，含 Y_Pre vs O_Post（需现场补算，2026-08-17 cluster2 实测）**：用户说\"cluster2 画三组（年轻、老年运动前后），正式版\"时，**3柱图上所有两两比较都要标注**（用户 6 柱场景已强调过\"所有两两比较\"，3 柱同样适用）——即 Y_Pre vs O_Pre（独立）+ O_Pre vs O_Post（配对）+ **Y_Pre vs O_Post（独立，跨时间对角线）**。其中 Y_Pre vs O_Post **不在标准 9 比较表里**（预计算只做 YvsO/OvsOD 两个基线跨组）→ **在正式版脚本内现场补算**：复用补0百分比网格 `ct_data`，对 `COMP_PAIRS <- list(c('Y_Pre','O_Pre'), c('O_Pre','O_Post'), c('Y_Pre','O_Post'))` 循环跑 配对(O运动)/独立(其余) Wilcoxon + per_celltype BH——**不要为此重跑整条预计算管线**，脚本自带三比较计算即可。实测 cluster2 全不显著：YvsO p=0.065（FDR=0.195，Cliff's +0.54 = 🟡趋势）、O运动 p=0.578（配对）、YvsO_Post p=0.178——交付口径 = \"趋势候选，中位 0%→5.4% 方向成立但未过阈值\"，与 3柱正式版 24×32mm、p/FDR 两版、PNG+PDF 规则相同。
- **糖尿病逆转板块**：3 柱 **O_Pre / OD_Pre / OD_Post**，比较子集 = OvsOD + OD运动
- 每个亚群 p 值 + FDR 两版（PNG+PDF），3柱 = 24mm×32mm（宽度自适应公式）
- **目录分离**：`figures/reversal_aging/` + `figures/reversal_diabetes/`（用户强调"分好目录"）
- 亚群选择 = 上表"逆转判定 YES/方向成立"的亚群（实测：衰老逆转 6 个 = LRP1B+(I)/Pure Type IIX/RP_high(II)/RP_high(I)/Pure Type I/OTUD1+(II)；糖尿病逆转 2 个 = Pure Type IIX/Pure Type IIA）
- 绘图脚本统一参数化：`plot_3grp(celltype, groups, comparisons, annot_col, out_tag, outdir)`，循环跑两个板块

### 4 柱"臂内效应"模式（2026-08-17 Specialized MF cluster1 用户拍板）

用户说"cluster1 出 4 个柱子，老年运动前后，老年糖尿病运动前后，p 值和 fdr 都要出" → **既不是 6 柱全组，也不是 3 柱逆转板块，而是 O_Pre/O_Post/OD_Pre/OD_Post 四柱**，回答"每个臂内部运动有没有效果"：

- **groups** = `c('O_Pre','O_Post','OD_Pre','OD_Post')`；**比较子集** = 3 个：O_Pre vs O_Post（老年运动，配对）+ OD_Pre vs OD_Post（糖尿病运动，配对）+ O_Pre vs OD_Pre（老年 vs 糖尿病基线，独立）——配对用 base_id、独立用 Cliff's delta（方向翻转，正值=后者高）
- **p/FDR 两版 = 给用户绘图函数加 `label_type` 参数**（用户原函数 `label` 写死 `FDR=`；`label_type='fdr'` → `FDR=`+fdr 列，`label_type='p'` → `p=`+p.value 列），**同一个函数跑两遍出两张图**，不要写两套函数
- 实测结果（cluster1，7-8 样本/组）：三比较全不显著——O 运动 p=0.469/FDR=0.703、OD 运动 p=0.156/FDR=0.469、O vs OD p=0.902——**方向全在但全不显著**，交付时如实说"4 柱口径无显著变化"，不要因不显著就不标注（用户要求 p/FDR 都标出来，不显著的括号也画）
- ⚠️ 此模式与 6 柱版 cluster1 的显著性结论**冲突预警**：6 柱版 Y_Pre vs O_Pre p=0.027（Python 补 0 口径）/p=0.234（用户 R 口径不补 0）；4 柱版只问臂内。交付时声明口径（是否补 0 + 比较数），详见 Pitfalls"补不补 0 + 比较数会反转结论"

### ⛔ "下一个群" = 先探索预览，不定稿（2026-08-17 Specialized MF cluster2 实测）

**触发场景**：cluster1 已定稿（26×32mm + PDF）后，用户说"下一个群" / "画下一个" —— **不要直接套用定稿模板批量出下一亚群**。用户会中途补一句"下一个群先看预览，探索"——正确顺序 = 每个新亚群**一律先出探索版**（140×110mm 全幅 + raw p 标注）→ 等用户确认效果/样式 → 才走定稿（柱数规则 mm + p/FDR 两版 + PNG+PDF）。探索→定稿门禁对每个亚群独立生效，即使模板已建立。cluster2 探索版实测全部不显著（O 运动 p=0.578 / OD 运动 p=0.219 / O vs OD p=0.318，中位比例 O_Pre 5.4% → O_Post 2.4% / OD_Pre 9.9% → OD_Post 6.7%、n=7/组），交付时如实说"无显著变化"。

- **⛔ 探索版 = 6 组全画，不是 4 柱（2026-08-17 用户纠正"预览版是6组啊"）**：cluster2 预览曾按 cluster1 的 4 柱模板（O/OD 臂内）出图被纠正——**探索预览 = 全部 6 组**（Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post），4 柱模式只在用户明确说"出 4 个柱子"（如 cluster1 定稿）时用。脚本 `target_grps` 与 `target_cmps` 必须显式区分探索（6 组 5 比较）与定稿（4 柱 3 比较）两种配置，不要复用上一定稿模板。
- **⛔ 6 组图上必须标注全部 5 个两两比较，含年轻组（2026-08-17 用户纠正"不是需要标注所有两两比较吗？年轻运动这些不需要标记吗？需要"）**：标准 5 比较 = 3 配对（Y/O/OD 各组 Pre→Post）+ 2 独立（Y_Pre vs O_Pre、O_Pre vs OD_Pre）。**不能只标 O/OD 臂内比较**——young exercise（Y_Pre vs Y_Post）、young vs old（Y_Pre vs O_Pre）都必须有括号。用户官方绘图函数本来就不过滤显著性（有效值就标），Agent 端脚本可能因 NA/漏配导致部分比较没标 → 交付前 R 侧打印 `nrow(sig)` 核对=5。
- **⛔ 稀疏亚群配对检验 insufficient_n（NA）→ 补0补偿才能标注（2026-08-17 cluster2 实测）**：某亚群在年轻组几乎不存在（zone2：Y_Pre 中位 0%，10 样本 6 个 0 细胞）时，Y_Pre vs Y_Post 配对在用户原口径（不补 0，只取双边都有细胞样本）仅 2 对 <3 → `insufficient_n` p=NA → 绘图 filter `!is.na` 静默跳过该比较 → 图上缺年轻运动括号，用户会质疑"年轻运动怎么没标"（本次就是这么被抓）。**修复 = 对 NA 行补 0 补偿**：无该亚群细胞的样本按 0% 参与配对 → 全样本配出 N 对（cluster2 = 10 对）→ p 可算（实测 10 对方向混乱 p=1.0 = 真正无差异），在 `global_fdr_table` 里用 `bind_rows` 替换该 NA 行（注释写明"补0配对补偿 + 其余比较仍用用户原口径"），图上即可补标。⚠️ p=1.0 的 bracket 因所在组比例低被分配在图底部、标签小且与箱体/散点重叠，OCR/肉眼都可能漏看（OCR 常把 'p=1' 读成 'D='）——交付时主动说明"它画上了，只是位置低"，别等用户问。

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

### ✅ 18+4 拆分落地 = 六图布局（2026-08-16 用户拍板执行版）

用户确认\"可以拆分\"并给出具体需求：**18 程序 + 4 身份，各自出 6 组图 / 5 效应图 / 亚群图（不分组别）= 6 张**。统一脚本 `fig_split_v10.py` 一次跑通（PNG+PDF+SVG 三格式）：

| 图 | 内容 | 行列 |
|----|------|------|
| FigA1_program_6groups | 18 程序 × 6 type × 10 亚群 | z-score，6 面板横排 |
| FigA2_program_5effects | 18 程序 × 5 效应 × 10 亚群 | Cohen's d + 星号显著性 |
| FigA3_program_subcluster | 18 程序 × 10 亚群 | 不分 type，z-score |
| FigB1_identity_6groups | 4 身份 × 6 type × 10 亚群 | z-score |
| FigB2_identity_5effects | 4 身份 × 5 效应 × 10 亚群 | Cohen's d |
| FigB3_identity_subcluster | 4 身份 × 10 亚群 | 不分 type，z-score |

- 18 程序 = 22 − 4 身份（scoreI/II/IIa/IIx 拆出），程序按 5 功能轴分组（代谢/结构/再生/应激-炎症/萎缩-纤维化）带左侧色带
- 样式沿用 v7 架构（RdBu_r、无白缝 CELL=1.0、行分组 0.2、面板间距 1.8、亚群标签贴底）
- ⚠️ 曾踩坑：脚本里 `Identity` 色键未定义 → `KeyError: 'Identity'`（color_map 的 group 键必须覆盖所有组名，加 `'Identity': ...` 修复）

### 🎻 亚群 top1 基因集小提琴图（2026-08-16 用户点名要 "每个亚群画自己top1的基因打分的小提琴图"）

**触发场景**：用户从 FigA3（18 程序 × 亚群 z-score 热图）看到各亚群有对应高表达基因集（"RSS 就非常高表达 Fibrosis"），要求**每个亚群画自己 top1 基因打分的小提琴图，横坐标是亚群**——验证各亚群 signature 打分。

**top1 挑选方法（与 FigA3 同口径）**：样本级聚合表（`agg_sample_v2.csv`，annotation_L3 分组）→ 每打分跨 10 亚群行内 z-score（`scipy.stats.zscore`，`result_type='expand'`）→ 每亚群 `sort_values(ascending=False).index[0]`。必须排除 4 个身份打分（scoreI/II/IIa/IIx）——用户看的 FigA3 是 18 程序版，OTUD1+(II) 在 22 打分里 top1=scoreII（身份打分）但 18 程序里 top1=scoreAtrophy，口径不同结果不同，先按图口径。已验证签名：RSS→Fibrosis、Specialized MF→Denervation、RP_high(II)→Glycolysis、LRP1B+(I)→AMPK_PGC1a、RP_high(I)→scoreSarcomeric、OTUD1+(I)→scoreInflammatory、OTUD1+(II)→scoreAtrophy（z=0.58 弱，该亚群无突出程序）。

**⛔ z-score 方向陷阱：按亚群跨基因集标准化会退化出全亚群同一伪 top1（2026-08-20 最后两轮实测）**：挑每亚群 top1 打分时若按**错误方向**标准化（`Z = sub_agg.apply(zscore, axis=1)`，即每个亚群跨所有基因集标准化），会得到**无区分度的伪 top1**——本项目 scoreSarcomeric（泛肌纤维结构程序，肌节基因）在全部 10 亚群 z≈3.2-3.5 都是 top1，4 张图全是同一个基因集、毫无意义。**正确方向 = 每个基因集跨亚群标准化**（行=基因集：`Z.values.mean(axis=1)`/`std(axis=1)`，见 cns-effect-matrix 同款）。若全亚群 top1 相同，先怀疑标准化方向错了，不是数据真的如此。**用户明确"每张图都是独立的"（2026-08-20）**：每张小提琴图各自选出该亚群自己的高分基因集、与纯 type 对照对比即可，**不要因跨图 top1 相同/重复就统一改公式或否定方案**——sarcomeric 全 top1 是标准化方向 bug，换正确方向后各亚群自然分化（RSS=Fibrosis、SMF=Denervation、LRP1B+=AMPK…）。

**⛔ y 轴选 raw AUCell 值，不是 z-score（2026-08-16 用户问"我不确定是z-score，还是原始AUCell"）**：小提琴展示的是**分布形状**——raw AUCell（0-1）直接反映真实水平分布；z-score 会把每个基因集自己的分布拉平到 0 附近，小提琴形状（峰/尾/偏态）失真。**z-score 适合热图（跨亚群相对比较），raw 适合分布图（绝对水平）**——nature-figure 惯例。**⚠️ 每个亚群 top1 基因集不同 → 横轴之间高度不可直接比较**（实测 Inflammatory 中位 0.040 vs Sarcomeric 0.511，天生量级差）——必须在小提琴标签下加小字标注每个亚群对应的基因集名，避免误读。

**实现配方（50 万细胞级 CSV）**：`pd.read_csv(usecols=['annotation_L3']+[top1_map[s]+'_AUC' for s in targets])` 只读 6 列（382MB 文件秒读）→ 每亚群抽样 ≤3000 细胞（`groupby(...).sample(n=min(3000,len(x)), random_state=42)`，形状稳定且不糊）→ `ax.violinplot` + 中位数黑短线 + jitter 散点（每亚群 ≤800 点、alpha 0.45）→ nature-figure rcParams（Arial、pdf.fonttype=42、svg.fonttype=none、font.size 7）。完整代码见 `references/subcluster-top1-violin.md`。

### ⛔ "画自己显著高表达的基因集" = 亚群 vs 纯型的数据实算，不靠 FigA3/memory 挑（2026-08-20 实测纠正）

**触发场景**：用户从打分热图看到各亚群有对应高表达基因集，要求"每个亚群匹配 3 个纯纤维（Pure I/IIA/IIX），画**自己显著高表达**的基因集打分小提琴图"。

**关键区分两类"top1"口径**（极易混淆）：
- **口径 A（FigA3 签名，memory 里存的）**：样本级聚合 → 行内 z-score → 每亚群 `argmax`，回答"哪个基因集是**该亚群最高的**"。RSS→Fibrosis、LRP1B+→AMPK、RP_high(I)→Sarcomeric 等。
- **口径 B（用户此处真正要的："自己显著高表达"）**：每个亚群 vs 3 个纯型 **逐基因集算 avg Cohen's d（方向 = 亚群−纯型）**，选 **d 最大且为正**（亚群比纯型高）的程序基因集。回答"该亚群**相对纯纤维**最能区分/上调哪个程序"。

**⛔ 用户点名“画 FigureA3 里这个基因集”时，FigA3 表 = 权威映射，逐亚群照表用，不许默默换成口径 B，也不许两口径混用**（2026-08-20 实测用户“怎么跑去神经了？”）：用户上传 FigA3 的“亚群×top1基因集”对照表并说“画这个”时，该表就是用户认定的基因集映射，必须逐亚群照表用：LRP1B+(I)=AMPK_PGC1a、OTUD1+(I)=scoreInflammatory、OTUD1+(II)=scoreAtrophy、RP_high(I)=scoreROS、RP_high(II)=Glycolysis。**Z 值锚定以“当前 meta 数据重算的行内 z-score top1”为准，不以上传旧表的 z 数值死记**——RP_high(I) 在旧表是 scoreSarcomeric (z=2.00)，但用户确认“scoreROS这个啊”（当前 meta 该亚群 z 最高已变为 scoreROS z=2.01 > Sarcomeric 1.79），即亚群无需照抄旧表的基因集名错值，z 最高才是真 top1，用户会纠正。上一套 5 亚群图用口径 B（数据实算 avg Cohen's d vs 3 纯纤维）把 OTUD1+(I)/(II) 选成了 Denervation（d=0.44/0.39），与图 A3 表的 Inflammatory/Atrophy 冲突 → 用户看到 OTUD1 图挂 Denervation 直接质问“怎么跑去神经了？”。**规则**：① 用户拿出 FigA3 表/叫出该表基因集名 → 用表值，不重算、不替换；② 两口径对状态型亚群（OTUD1 系列）分歧：口径 A（z-score 该亚群最高）= Inflammatory/Atrophy，口径 B（vs 纯纤维 d 显著）= Denervation；③ 同一套多亚群图必须整套统一到一个口径——混合 = 图间基因集口径不一致，用户一眼抓矛盾；④ 用户明确说“数据实算 / 按 vs 纯纤维显著”才用口径 B，未指定时默认口径 A（FigA3 表）；⑤ 用户对逐亚群基因集的一致性/来源高度敏感（“我先确定你用的那个亚群和top1基因集”→ 交付前先跟用户对齐映射表并得到确认，再画整套）。AMPK_PGC1a × LRP1B+(I)+3 纯纤维本身两口径一致，是该图安全起点。

**⛔ 必须用口径 B 现算，不能查 memory/FigA3——可数据实算验证口径 A 的选择常“不算显著”**（2026-08-20 实测）：
| 亚群 | 上一轮(口径A/记忆)选的 | 数据实算 avgD | vs纯型明细 | 真·口径B top |
|------|----------------------|--------------|-----------|-------------|
| OTUD1+(I) | scoreTNFA | +0.17 | vs Pure I 仅 +0.00（几乎无差异！）| **Denervation (+0.44)** |
| RP_high(I) | scoreAtrophy | +0.10 | vs IIA 仅 +0.02 | **Sarcomeric (+0.80)** |
| RP_high(II) | scoreInsulin | +0.02 | vs IIA/IIX 为**负**（亚群不比纯型高）| **Sarcomeric (+0.63)** |
| OTUD1+(II) | Denervation | +0.39 | 一致 | Denervation ✅ |
| LRP1B+(I) | AMPK_PGC1a | +0.41 | 可用但 OxPhos+0.60/FAO+0.56 更高 | OxPhos/FAO |

**规则**：
1. **排除 4 个身份打分（scoreI/II/IIa/IIx）**——它们定义纤维身份，目标亚群如 LRP1B+(I)/OTUD1+(I)/RP_high(I) 本身是 I 型样，scoreI 天然高，属"身份自证"不算"程序信号"。只在 18 个程序基因集中选。
2. **always 从数据现算 avg Cohen's d vs 3 纯型**，选最大且为正的程序基因集；发现"上轮/记忆选的基因集 vs 某纯型 d≈0 甚至是负"→ **必须向用户披露差异并让其拍板**（选数据 top vs 保留上轮），不要默默改用户已确认选择（铁律 28）。用户要"自己显著的"时，数据实算 top 才是正解。
3. 交付对比表（亚群 / 上轮基因集 / 数据top / 差异说明），让用户决策，再一次性画齐。

### 📊 基因集响应筛选量化阈值（2026-08-16 用户问\\\"哪些可以删\\\"）

用效应表（22 基因集 × 10 亚群 × 5 效应 = 1100 检验，BH 校正）做响应强度筛选的**量化标准**：

- 🟢 **可删**：平均|d| < 0.25 且 50 格显著 ≤ 2（实测：无）
- 🟡 **慎删/弱响应**：平均|d| < 0.45 且 显著格 ≤ 5（实测 4 个：Fibrosis 0.323/0格、mTORC1 0.369/0格、scoreStress 0.434/0格、scoreInflammatory 0.436/0格）
- ✅ **保留（有特异信号）**：d 大 + 方向一致 + 特异亚群集中——即使显著格=0（实测 Fibrosis：RSS 亚群 Aging d=0.79/ExOld d=0.82，虽 FDR q>0.45 但方向一致 = 故事线资产，用户自己抓出\"RSS 好像很显著\"）；scoreROS/scoreRegMyon/Denervation 也是 0 显著格但有强方向性（Aging/ExOld |d|>1）
- 全 22 排序（响应从强到弱）：scoreIIa(1.37/14格) > Glycolysis(1.23/14) > FattyAcidMetabolism(0.95/9) > scoreIIx(0.93/5) > scoreOxPhos(0.91/10) > scoreSenMayo(0.79/9) > ... > mTORC1(0.37/0) > Fibrosis(0.32/0)
- ⚠️ **删基因集前先查特异亚群 d 值**——`gene_set_response_summary.csv` 的\"弱响应(慎删)\"基于 FDR 格数，不代表无生物学信号；结论 = 只删 mTORC1（全轴无方向），Fibrosis 因 RSS 特异保留
- 分析脚本 `analyze_response.py`（读 effect5_d_v2.csv 长表算平均|d| + 显著格数 + 各轴方向）

### 📚 T2D 骨骼肌基因集文献来源（路线 B，2026-08-16 下载）

用户要\"糖尿病相关打分\"且选路线 B（文献基因集）→ 已下载到 `E:/骨骼肌锻炼/papers/T2D/`：

| 文献 | PMID | 价值 |
|------|------|------|
| **Mootha 2003 Nat Genet**（`10.1038_ng1180.pdf`） | 12808457 | ⭐ 经典：PGC-1α 响应基因（氧化磷酸化）在 T2D 肌肉协调下调 —— T2D 打分金标准，首选提取 |
| **Schön 2026 Diabetes**（`10.2337_db25-0625.pdf`） | 41563348 | T2D 肌肉线粒体呼吸降低 + SMRT/bulk RNA 整合 |
| **Xiao 2026 Cells**（`10.3390_cells15110979.pdf`） | 42274572 | 运动改善 T2D 多组学程序（与\"运动逆转\"故事最对口，用 hdWGCNA 找模块） |
| Sreekumar 2002 Diabetes | 12031981 | ❌ 反爬拦截需手动下载 |

- 全文 txt 提取：`results/<session>/papers/Mootha2003_NG_fulltext.txt` 等三份
- 与路线 A（hdWGCNA T2D 模块基因：purple=全新 T2D 模块、magenta=T2D 特异且运动压不住、red=可逆靶点胰岛素信号+AMPK）互补；用户先选 B 后可能转 A


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

## 统计标注与出图执行纪律（2026-08-20 FigC1 AMPK 4亚群小提琴实测）

### ⛔ 大样本 p 值浮点下溢：报 `<1e-6`，不报 `0.0`
单细胞亚群对比 n 巨大（LRP1B+(I) 31,331 vs Pure Type I 166,747 细胞）时 `mannwhitneyu` 返回 p≈0.0（下溢），
`round(p, 6)` → `0.0` = 精度谎言。**打印/汇报一律阈值改写**：`('<1e-6') if p < 1e-6 else round(float(p), 6)`；
图星号逻辑不变（`p<1e-6 → ***`）。

### ⛔ 大样本「星号骗人」：小效应也 p*** → 星号必须配效应量
n=166k vs 31k 时 vs Pure Type I d=0.21（小效应、慢肌共性）仍 p<1e-6 → 光挂 `***` 会让读者误读为强差异
（用户对效应量极其敏感）。规则：① 图注/注释必须星号配 d 值（`vs Type I d=0.21 small p***`）② 结论措辞分级：
d≥0.5 才说"富集/差异强"，d<0.3 说"统计显著但效应小（共性/趋势）"，用"富集"不用"特异" ③ 汇报三件套 =
中位数 + p（<1e-6 改写）+ 效应量 Cohen's d。

- **⛔ 多亚群图必须是「单一模板脚本 + 改参数」，不许每张重写代码；每个看图脚本立即存 scripts/（2026-08-20 用户\"代码都不一样\"\"跑完也不保存\"）**：用户会逐张核对\"你画的 A 图跟 B 图是不是同一个脚本\"——**同一个模板脚本（如 fig_C1_AMPK_violin_4sub.py）只改 3 处参数（目标亚群、基因集列、颜色）出全套**，保证 5 张图代码和风格完全一致；每张图重起炉灶写新代码 → 风格/星号规则/标签全漂移，用户一眼发现\"你跟 Figure X 就不是一个图\"。**每个成熟脚本立即 write_file 到 scripts/ 目录并登记**，不靠记忆/聊天记录（用户原话\"跑完的脚本也不保存一下，保存到script目录里啊\"）——脚本首次跑通后立刻落盘，不能等到用户问\"脚本呢\"。改图只 patch 脚本里对应常量并重跑，不要在对话里手写整段新代码。
小提琴/比较图亚群太多（>5-6 个）占版面时：优先保留「主角 + 干净纯型对照」（本次 = LRP1B+(I) + Pure Type
I/IIA/IIX 共 4 个），**排除特殊状态群 RSS（纤维化/去神经/代谢塌陷）与 SMF（去神经/再生）以及 RP_high/OTUD1
系列**（无核心故事、占位且拉低对照纯度）。特殊状态群的代谢塌陷是另一故事，混一起分散注意力。选型疑问先问用户
（铁律 28），改版后文件名带版本标记（`_4sub`）。

### ⛔ 「光说不做」升级版：交付 = 真实落盘文件 + 可给路径，不是叙述（2026-08-20 FigureC1 尾部实测）

本轮最严重的用户信号，远超 boxplot 场景的"说了就跑"：
- "你一直没执行代码，光说不做，我不是聊天"
- "所以图到底在哪里呢？"（多次，图从未真正生成时）
- "跑完的脚本也不保存一下，保存到script目录里啊" "你没有放到script里面吗？"

**根因两类**：
1. **把"描述将画/已画"当成交付**——声称"图已生成/5张已交付"但实际文件从未落盘，或脚本从未执行。用户要的是**磁盘上真实存在、路径可给、vision/OCR 通过**的图文件。
2. **发空参工具调用**——write_file 缺 `path`/`content`、execute_python 缺 `code` 时调用**静默什么都不做**（不报错、不产出），却能连续空转多轮，拖到最后才醒悟。**只要发现连续 1-2 次工具调用参数为空/未携带实际代码，立即停下诊断参数序列化问题，换 execute_code 或直接把完整代码写进 code 参数，不要继续发空参。**

**执行铁律（本类任务）**：
- 说"画/出图/交付" = 同轮必须有**真实执行**写完文件；**结束语永远带着绝对路径 + 文件已落盘确认**。给不出路径 = 没完成，不许说"已完成"。
- 每个成熟脚本跑通后**立即 write_file 抢救到 scripts/**（用户会审计）——脚本在 scripts/ 不在 = 交付不完整（"跑完也不保存"）。
- 用户问"图在哪/跑了吗" → **先 search_files/read_file 查产出物和时间戳**，用证据回答（产物在=交付路径；产物不在=承认没跑、立即补跑），不要凭空自认/也不要撒谎声称已生成。
- 多亚群/多版本图：改版只 patch 一个**已认可模板脚本**的常量并重跑保存，同一轮内闭环（改→跑→给路径），不留"我改了，你确认"这种无执行收尾。

### ⛔ L1 辩论裁判解析失败 → 同内容重试 1 次，modify 裁决必须落地（2026-08-20 实测）
L1 辩论返回 `verdict: need_more_info` + `low` + `verdict_parse_error` 时是**模型 JSON 被推理草稿污染，
不是裁决失败**——用相同 topic/context 重试 1 次（实测重试即得 `modify` + `high`）。`verdict=modify` =
**必须把 recommended_params/reasoning 的修正意见实际执行**（本案例：p 报 <1e-6、星号补 d、结论弱化）并重跑
后再汇报，不要把 modify 当"通过"了事。反方意见即便整体被驳回，可操作项（如打印精度）通常值得采纳。连续 2 次
解析失败才升级 L2/换 mode。

## Pitfalls
- **⛔ 亚群 vs 纯纤维小提琴的两套星号口径并存——用户说「按之前代码画」先分清用哪套（2026-08-20）**：同类「主角 vs 3 纯纤维」图存在两个已验证模板，星号标注口径不同，混用会被用户抓到「怎么跟 Figure X 不是一个图」：① **fig_C1_AMPK_violin_4sub.py（用户当次指定「按我之前代码」）** = 星号按 **Cohen's d 效应量分级**（>=0.8***/0.5**/0.3*/ns），不挂 p，避细胞级伪重复虚标；② **fig_C1_5sub_rawp_effsize.py（另一会话用户拍板）** = **raw p 星号 + d 数值双标注**。**先确认用户指定哪个模板再画**（「参考 fig_C1_AMPK_violin_4sub.py」= d 分级），整套统一口径不混用。详见 references/main-vs-pure-4sub-violin-template.md 与 references/subtype-vs-fiber-violin.md。
- **⛔ rail_review(post) 的 code_executed 传 `exec(open(...).read())` 会误报"代码过短(1 行)"（2026-08-20 实测）**：审查器按 code_executed 的字符/行数判"是否完整代码"，一行 exec 调用被当成偷懒 stub → post 审查 failed。**必须先 read_file 完整脚本，把完整多行脚本内容（≥200 字符，含注释）传给 code_executed 再跑 post**，不要缩写成一行 exec。同理 rail_review(pre) 的 required_packages 只列脚本真实 import 的包（见后续 egg/stringr 误报坑）。
- **⛔ 多亚群克隆脚本时 sed 全局替换会破坏 subcluster_map 映射行（2026-08-17 实测被抓）**：从已跑通的 05 脚本克隆 06 时用 `sed -i 's/cluster1/cluster2/g'`，结果**第 17 行 `subcluster_map <- c(zone1='cluster1', zone2='cluster2', ...)` 也被替换成 `zone1='cluster2'`**——zone1 的映射被静默改坏。**克隆后必须检查映射行/非目标字符串**（grep 看所有 clusterN 出现位置，逐行核对语义），映射表这类"包含但不等于目标名"的行要用 patch 单独恢复。更稳做法：先复制再 `sed` 只替换 `ct <- 'clusterX'`、`target_ct`、`ggsave` 文件名三处（精确锚定），映射行不动。
- **⛔ 探索版脚本故意不依赖 egg（绕开 check_env 误报导致的 rail_review(pre) 拦截，2026-08-17 实测）**：探索版 140×110mm 全幅**不需要 `egg::set_panel_size`**（只有定稿按柱数规则才需要）。写探索脚本时**故意不加载 egg**、`required_packages` 只列该阶段真实需要的（dplyr/tidyr/ggplot2），这样 rail_review(pre) 不会被 check_env 对 egg 的误报卡住（egg 装在 E:/R-libs 但 check_env 用默认 R 库路径探测 → 永远误报 MISSING）。定稿脚本再单独用 egg。**通用原则：rail_review(required_packages) 只列脚本实际 import 的包，不为"可能用到"的包付拦截代价**。
- **⛔ stringr 误报 → 用 base R 等价函数替代，从源头消除**：check_env 探测不到 E:/R-libs/R-4.5.3 里的 stringr → rail_review(pre) 拦截。最稳修复不是修环境，而是**脚本里不用 stringr**：顶部加 `str_detect <- function(x, pattern) grepl(pattern, x)`、`str_remove <- function(x, pattern) sub(pattern, '', x)` 两个 shim，代码照写 `str_detect(...)` 调用不变，依赖归零。（2026-08-17 cluster1/2 脚本已内置此 shim，头部注释"不用 stringr"）
- **⛔ Seurat `dim()` = (genes, cells) — ncol 是细胞数、nrow 是基因数（2026-08-17 实测报错）**：Specialized MF 实测 `dims: 11630 cells x 51227 genes`（脚本 `cat('dims:', ncol(obj), 'cells x', nrow(obj), 'genes')` 输出），但此前被误报成"51,227 细胞 × 11,630 基因"（把 ncol/nrow 语义读反）。**验证铁律：亚群细胞数求和必须等于报告的细胞数**（59+3022+822+808+1254+4912+753=11,630 ✓）。汇报任何细胞数前先核对 dims 顺序 + 亚群求和，用户对数字精度极敏感。
- **⛔ Python 显著性实现可直接复用（2026-08-17 实测，R 库 DLL 损坏/不想冷启动时的保底路径）**：比例显著性计算不必死磕 R（coin::wilcoxsign_test 非标准写法 + R 库 DLL 坑），pandas+scipy 一次跑通：`scipy.stats.wilcoxon`（配对，按 base_id inner_join 后两列）/ `mannwhitneyu(v2, v1)`（独立）+ `statsmodels.stats.multitest.multipletests(method='fdr_bh')` 双 FDR（per_celltype + 全局）。Cliff's delta 方向翻转 Python 实现：`gt += np.sum(b > x); lt += np.sum(b < x); d = (gt-lt)/(n1*n2)`（正值 = 后者组高，符合用户直觉）。完整脚本见 `references/specialized-mf-proportion-case.md`（02_significance.py 模式，9 比较对 × 7 亚群 = 63 行）。
- **⛔ 两条显著性管线的 CSV schema 不一致，跨读必炸（2026-08-17 实测 KeyError）**：本会话存在两套显著性结果：**Python 版 `02_significance.py` 写出的 CSV** 用 `subcluster/comparison/g1/g2/paired/p/eff/n1/n2` 列名（`comparison` 是 `YvsO/OvsOD/...` 缩写键、`paired` 是字符 'True'/'False'），**R 版用户管线/绘图脚本**内部用 `annotation_L3/group1/group2/p.value/test_type`。**读取 CSV 前必须先 `print(df.columns)` 确认是哪套 schema**——拿 Python 版列名拼 R 版查询（如 `df['annotation_L3']`）直接 KeyError；同样，R 绘图脚本若想消费 Python 版 CSV 也要重命名列（`rename(subcluster='annotation_L3', group1='g1', ...)`）。**更稳做法：正式版/探索版绘图脚本内自带三比较显著性计算（复用百分比网格），不读外部 CSV**——预计算 CSV 只用于给用户交付全表，绘图永远现场算，避免 schema 漂移。
- **⛔ significance CSV 的 `paired` 列是字符型 'True'/'False'——过滤必须 `paired != 'True'`，不能 `paired == FALSE`（2026-08-17 实测被自己坑）**：read.csv(stringsAsFactors=FALSE) 读进后 `paired` 是 character，`paired == FALSE`（逻辑值）永远匹配不到 → comp_sig 0 行 → 图上没有显著性标注但脚本不报错。探索图/定稿图脚本读取显著性 CSV 时**统一用 `paired != 'True'`（或 paired=='False' 取反）筛选独立比较**。交付前 R 侧打印 `nrow(comp_sig)` 与预期比较数核对，防止\"图出来了但没标注\"的静默失败。
- **⛔ 图空白/黑底检查必须三指标，不能只看文件大小或"非白%"（2026-08-12 被用户两次纠正）**：
  `egg::set_panel_size` 处理后的对象经 `ggsave()` 输出 PNG **默认纯黑背景**（实测 94.8% 像素
  纯黑 [0,0,0]，视觉=黑屏几道灰）——而"非白像素 95%"恰好会把它误判成"有内容"！
  正确三指标（PIL）：① `dark%`（RGB 全部 <100 的像素占比）<10 ② `colored%`
  （max-min>30 的彩色像素）>1（正常箱线图有彩色箱体/点）③ 内容边界框存在
  （非白非黑像素的 min/max 范围）。`png()` 设备 + `set_panel_size` 组合还可能出空白/黑底，
  **统一用 `ggsave(..., bg="white")` 输出 PNG**。文件大小 ≠ 内容正确（3.9KB 空白和 55KB 黑底都骗过人）。
- R 环境：`.libPaths('E:/R-libs/R-4.5.3')` + R-4.5.3 全路径；readr 不在该库用基础 `write.csv`；CSV 首列空表头 → `row.names=1`
- `coin::wilcoxsign_test(diff_val ~ 1)` 非标准配对写法，但 exact→approx fallback 链有效，不用改（用户脚本无需修正）
- `complete(nesting(samplename, base_id, type), fill=list(Proportion=0))` 补缺失组合（0 细胞样本）必需（2026-08-14 起 L3 流程默认；**用户官方 R 管线不补 0**，见下一条）
- **⛔ 补不补 0 + 比较数会反转结论（2026-08-17 Specialized MF 实测）**：用户官方 R 管线（5 比较）不补 0 → cluster1 Y_Pre vs O_Pre p=0.234 **不显著**；Agent Python 版（9 比较）补 0 → p=0.027 **边缘显著**——同数据两口径结论相反！根因 = 比较数不同（BH-FDR 严格度）+ 补 0（0 值堆积极敏感 vs 不补 0 引入选择偏倚、只让\"至少 1 个该亚群细胞\"的样本参与）。**交付规则**：① 报告必须显式声明\"是否补 0 + 比较数\"；② 比例表同时给\"0 值样本数\"；③ 结论区分\"普遍性上升（补 0 检验）vs 丰度上升（不补 0 检验）\"；④ 用户官方代码口径（5 比较不补 0）= 交付默认，但与补 0 版结论冲突时主动披露差异。详见 `references/specialized-mf-user-r-pipeline.md`
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
- `references/subtype-vs-fiber-violin.md` — **慢肌类亚群 vs 纯纤维「自己显著高表达基因集」小提琴图**（2026-08-20）：5 亚群 × 3 纯纤维，口径 B 数据实算 avg Cohen's d 选 top1 + **raw p 星号 + 效应量 d 数值双标注**（用户拍板，非效应量分级星号）+ 细胞级 Mann-Whitney 伪重复局限披露 + 可复用脚本 `fig_C1_5sub_rawp_effsize.py`
- `references/main-vs-pure-4sub-violin-template.md` — **「主角亚群 vs Pure I/IIA/IIX」4-sub 小提琴模板**（2026-08-20 用户指定 fig_C1_AMPK_violin_4sub.py）：单栏 90×62mm nature-figure 版、主角浅蓝+纯纤维标准配色、**星号按 Cohen's d 分级（≥0.8***/0.5**/0.3*/ns）非 p 值**、不截断 Y 轴、PNG+SVG+PDF+TIFF 四格式、5 亚群实例 d 值表 + 期望中位数逐项核对 + 删旧图=移入备份目录。⚠️ 与 subtype-vs-fiber 的 raw-p 星号是两套口径，用户说"按 fig_C1_AMPK_violin_4sub.py / 之前代码画"用本模板。
- `references/specialized-mf-proportion-case.md` — **Specialized MF 11,630 细胞比例显著性案例（2026-08-17）**：Python 显著性管线完整代码（pandas+scipy wilcoxon/mannwhitneyu + 双 FDR + Cliff's delta 方向翻转）、9 比较对定义、六组比例中位数表、显著性要点（zone5 衰老↓ p=0.0046 / 糖尿病轴全不显著）+ **探索箱线图模板（03_boxplot_6grp_cluster1.R：zone→cluster 改名映射、手动括号 raw p 标注、paired 列字符型坑、cluster1 衰老↑/运动↑ 方向与"运动逆转去神经"预期相反→需 pseudobulk 验证）**
- `references/specialized-mf-user-r-pipeline.md` — **用户官方 R 管线（显著性 5 比较 + plot_celltype_proportion 画图函数）可复用版（2026-08-17，用户说"你要记住了"）**：六色配色/配对虚线/手动括号/FDR 白底标注完整函数、5 比较对定义、`&&`→`&` 与删 coin 分支的 rail_review 修复、**补 0 vs 不补 0 口径反转结论案例（cluster1 YvsO p=0.234 vs 0.027）与辩论裁决（普遍性 vs 丰度）**
- `references/mf-l3-proportion-case.md` — 骨骼肌 MF L3 10 亚群实测案例：脚本结构、显著性结果、Pure Type I/IIA 结论与响应者分析
- `references/mf-score-analysis.md` — AUCell 打分跨组差异实测：相关性冗余/独立结构、衰老/糖尿病/运动三轴显著结果、SenMayo 解读陷阱、去神经化基因集评估（SCN4A 方向坑 + NCAM1 缺失 + 重叠检查）、缺失打分建议（Glycolysis/AMPK-PGC1α 等）、真实文献 PMID 清单
- `references/xlsx-geneset-wide-format.md` — 用户基因集 xlsx 宽表格式追加/编辑铁律 + openxlsx 损坏文件修复配方（zipfile 解析读取 + openpyxl 从零重建）
- `references/go-term-selection-per-subtype.md` — 亚群 GO 富集词条筛选（MF_L3_GO_AllLists.xlsx）：Log(q-value)≤-1.3 过滤 + **特异性优先选词条算法**（挑亚群独有词条，不是 marker 命中数优先——第一版给 10 亚群全挑共享 sarcomere 词条被用户否决）+ 正刊 GO 词条挑选方法论（去冗余/差异化/锚定身份/dotplot）+ L2 辩论警示（LRP1B+ 突触需注明 NMJ、RSS 泛 growth 换 BMP、RP_high 核糖体注明管家基因背景）+ openpyxl 科学计数法/read_only 无 dimensions 坑 + **CNS 级别 GO dotplot 完整配方**（关键词驱动选词条 → ggplot2 dotplot：shape=21、size=Enrichment、fill=-log10(q) 蓝白红渐变、PNG+PDF 双导出）。触发词："GO词条" / "富集词条" / "MF_L3_GO_AllLists" / "亚群富集" / "GO dotplot" / "GO富集图"
- `references/cns-effect-matrix-aucell.md` — **CNS 级效应矩阵图组配方**（2026-08-14）：细胞级 AUCell meta CSV → 样本级聚合（防伪重复）→ Cohen's d + Wilcoxon 三效应（Aging/Exercise/T2D）→ 三图架构（Fig1 效应矩阵热图 + Fig2 配对个体响应 + Fig3 Aging-vs-Exercise 效应散点）+ 逆转率公式 + 可直接复用的 Python 实现 + **五效应扩展版 + 颜色语义问答三步核实 + v5→v6 定稿参数（tight_layout/add_axes 坑、亚群标签 y=-0.15、Fig7 转置）+ v6→v7 无白缝 CELL=1.0 + v7→v8 六组分布热图标签布局 + v8→v9 多面板重构（像 fig1 v7 那样）+ 真实分数 vs z-score 决策 + pandas MultiIndex×zscore numpy 层修复**。触发词："CNS级别" + "AUCell打分" / "效应矩阵" / "逆转矩阵" / "主刊图" / "PNG没变PDF对了"
- `references/subcluster-top1-violin.md` — **亚群 top1 基因集小提琴图配方**（2026-08-16）：top1 挑选方法（样本级聚合→行内 z-score→argmax，必须排除 4 身份打分）+ **y 轴用 raw AUCell 非 z-score 的决策**（分布形状 vs 相对高低）+ 每亚群抽样 ≤3000 + violinplot 完整代码 + 已验证亚群签名（RSS→Fibrosis 等 7 个）+ 用户六色配色。触发词："top1 小提琴" / "每个亚群画自己top1" / "亚群 signature 打分" / "原始AUCell还是z-score"
- `references/aucell-score-figures.md` — **AUCell 打分图全套约定总纲（heatmap+violin，2026-08-20 多轮纠正沉淀）**：数据口径（细胞级/样本级/五效应表）、**z-score 方向陷阱**（按亚群跨基因集标准化→全亚群同一伪 top1）+ 每张图独立选基因集、热图布局（CELL=1.0 无白缝/行分组 0.2/面板 1.8/标签位置）、**matplotlib invert_yaxis 上下颠倒坑**、小提琴规范（Y 轴原始分数不截断/星号按 raw p 分级 + 效应量 d 数值双标注/不算 BH-FDR/标准 bracket 无框无注释）、PDF-vs-PNG 渲染分叉（tight_layout+add_axes 坑）、图稿参数记忆（Fig_type6_v9、Fig_C1_AMPK_violin_4sub）。触发词："打分热图" / "五效应图" / "六组图" / "亚群top1" / "小提琴图" / "无白缝" / "bracket星号" / "红蓝热图"

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | skeletal_muscle | aging | 2026-08-17 | 01_extract_meta.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 02_significance.py | - | - |  |
| - | - | - | 2026-08-17 | 03_boxplot_6grp_cluster1.R | - | - |  |
| - | - | - | 2026-08-17 | 03_boxplot_6grp_cluster1.R | - | - |  |
| - | - | - | 2026-08-17 | 03_boxplot_6grp_cluster1.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 03_boxplot_6grp_cluster1.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 04_user_style_proportion.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 04_user_style_proportion.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 04_user_style_proportion.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 05_boxplot_4grp_cluster1_pfdr.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 05_boxplot_4grp_cluster1_pfdr.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 07_explore_4grp_cluster2_p.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 08_final_3grp_cluster2_pfdr.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 09_explore_6grp_cluster3_p.R | - | - |  |
| human | skeletal_muscle | aging | 2026-08-17 | 10_final_3grp_cluster3_pfdr.R | - | - |  |
