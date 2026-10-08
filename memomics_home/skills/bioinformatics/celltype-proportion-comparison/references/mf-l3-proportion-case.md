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
- 修正后 v2 CSV: `significance_all_celltypes_v2_direction_fixed.csv`；v3 加 Y vs OD 比较 → `significance_all_celltypes_v3_with_YvsOD.csv`（10×6=60 行）；v4 最终 → `significance_all_celltypes_v4_6comp.csv`

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

## Pure Type IIA 结论（6 组定稿：IIA3 mode = 只标 YvsO/YvsOD/OD运动 3 比较）
- 衰老显著↓ IIA：Y_Pre 42.8% vs O_Pre 26.6%，p=0.0046，FDR=0.028（II 型萎缩经典）
- Y vs OD（补充比较）：42.8% vs 26.3%，p=0.033（raw 显著，亚群内 FDR≈0.099 边缘）
- 运动：Y↓(−3.25pp)/O↓(−6.56pp)/OD↑(+2.85pp，p=0.469 不显著)
- OD 个体响应：**4 响应者(+2.9~+17.6pp) vs 3 非响应者(−2.9~−9.6pp)**——配对 p 不显著但个体异质性真实存在
- 响应者 vs 非响应者基线：28.09% vs 24.26%，p=1.000 → **基线不预测响应（非 floor effect）**
- 故事策略：糖尿病快肌丢失（有统计）→ 运动个体响应异质性（有数据）→ 不声称"运动普遍有效"
- 定稿文件：`Pure_Type_IIA_6grp_pval_v4.png/.pdf` + `Pure_Type_IIA_6grp_FDR_v4.png/.pdf`（30×32mm，FDR 版 6 比较全标）

## 出图尺寸（用户指定，2026-08-12/13 最终版）
- **探索图（未定组别）= 140×110mm 全幅大图**（用户明确允许："探索脚本可以 140×110mm 全幅，确定之后再用我指定的参数"）
- **定稿图（用户确认组别后）**：6 柱 = 30mm 宽，5 柱 = 28mm，每少 1 柱 −2mm；高 32mm
- **标准实现（2026-08-13）**：`width_mm <- 30 - (6 - n_groups) * 2` → `egg::set_panel_size(p, width=unit(width_mm,'mm'), height=unit(32,'mm'))`
- `ggsave(dpi=300, limitsize=FALSE, bg="white")`
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
- **⛔ 像素检查分母 bug（2026-08-13 OTUD1+(I) 误报空白）**：循环步长 3 采样时，分母误用区域总像素
  （2,158,000）而实际只采样 239,000 点 → nonwhite% 低估 9 倍 → 误报"图空白"冤枉图本身。
  修复：分母必须 = 实际采样点数（或用 `img.getdata()` 全像素、`img.crop().getdata()` 精确面板区域）。
  真正确认内容 = 精确面板区域（30×32mm 居中 = 872-1226 × 860-1238px @300dpi）nonwhite 17-18%、
  colored 6%、dark 5-6% 才正常。
- 每次 R 脚本运行前检查是否有 `_kernel_worker.R` 孤儿进程堆积（见 windows-bioinformatics-batch-processing 的 references/kernel-worker-orphan-investigation.md）
- reasonix（用户其他工具）会在本机跑 execute_r 测试 → 遗留 `_kernel_worker.R` 孤儿进程（父进程退出不回收）。
  用户确认非本会话责任；堆积时可安全 kill（只杀 `_kernel_worker.R`，不碰任何数据文件）

## LRP1B+(I) 定稿（2026-08-13，6 组，LRP1B4 mode = 4 比较）
- 用户指定标注：Y_Pre vs O_Pre / Y_Pre vs OD_Pre / O_Pre vs OD_Pre / OD_Pre vs OD_Post
- 显著性（v4）：YvsO p=0.0185 FDR=0.056（衰老↑）、YvsOD p=0.0878 FDR=0.176（边缘）、OvsOD p=0.318 FDR=0.381（n.s.）、
  OD运动 p=0.0156 FDR=0.056（糖尿病运动↓，−2.26pp）
- 故事候选：衰老↑ + 糖尿病运动↓ = "运动把衰老相关升高的 LRP1B+ 压回去"方向，但 FDR 边缘需谨慎
- 定稿文件：`LRP1B__I__6grp_p.value.png/.pdf` + `LRP1B__I__6grp_FDR_per_celltype.png/.pdf`（30×32mm）
  （注意：文件名用原名 gsub 后 `LRP1B__I_`，不带 Pure_Type 前缀）

## OTUD1+(II) 定稿（2026-08-13，6 组，OTUD4 mode = 4 比较）
- 用户指定标注：Y_Pre vs Y_Post / O_Pre vs O_Post / Y_Pre vs OD_Pre / O_Pre vs OD_Pre
- 显著性（v4）：Y运动 p=0.084 FDR=0.126（↑边缘）、O运动 p=0.047 FDR=0.106（↑显著，+5.05pp 全亚群最大运动效应）、
  YvsOD p=0.025 FDR=0.106（OD 高于 Y，显著）、OvsOD p=0.053 FDR=0.106（OD 高于 O，边缘）
- 故事：糖尿病↑ OTUD1+(II) + 三组运动全部↑ = "运动/代谢应激响应亚群"，老年运动尤其敏感
- 定稿文件：`OTUD1__II__6grp_p.value.png/.pdf` + `OTUD1__II__6grp_FDR_per_celltype.png/.pdf`（30×32mm）

## Pure Type IIX 定稿（2026-08-13，6 组，IIX5 mode = 5 比较）
- 用户初始指定：Y_Pre vs O_Pre / Y_Pre vs OD_Pre / O_Pre vs OD_Pre / O_Pre vs O_Post（IIX4 mode）
- 用户中途追加：OD_Pre vs OD_Post（"再补一个老年糖尿病运动前后的显著性"）→ IIX5 mode，旧 4 文件删除替换
- 显著性（v4）：YvsO p=0.133 FDR=0.200（n.s.）、YvsOD p=0.0185 FDR=0.094（OD 高于 Y，raw 显著）、
  OvsOD p=0.259 FDR=0.275（n.s.）、O运动 p=0.0312 FDR=0.094（↓，raw 显著）、OD运动 p=0.109 FDR=0.200（↓，n.s.）
- 故事候选：糖尿病↑ IIX + 两个运动都↓ = "运动逆转糖尿病相关 IIX 升高"方向，raw 显著 FDR 边缘
- 定稿文件：`Pure_Type_IIX_6grp_p.value.png/.pdf` + `Pure_Type_IIX_6grp_FDR_per_celltype.png/.pdf`（30×32mm）

## OTUD1+(I) 定稿（2026-08-13，6 组，OTUD1I1 mode = 只标 1 比较）
- 用户指定：只标 O_Pre vs O_Post（老年运动，全亚群唯一信号）
- 显著性（v4）：O运动 p=0.0469 FDR=0.281（↑ +2.00pp，raw 显著 FDR 不显著）、其余 5 比较全 n.s.
- 故事：信号弱（仅 1 个 raw p<0.05），用户仍要求出图（6 组 + 只标 O 运动）
- 定稿文件：`OTUD1__I__6grp_p.value.png/.pdf` + `OTUD1__I__6grp_FDR_per_celltype.png/.pdf`（30×32mm）

## RP_high(II) 定稿（2026-08-13，3 组 = Y_Pre/O_Pre/OD_Pre 运动前基线，RPHIGH2 mode = 2 比较）
- 用户指定：画 3 个运动前组（年轻/老年/老年糖尿病），标注显著性
- **用户中途删除比较**："RP_high(II) 的年轻和老年糖尿病的显著性不要" → 从 COMPS3（3 比较）改 RPHIGH2
  （YvsO + OvsOD 2 比较），删除含 YvsOD 的旧图重出
- 显著性（v4）：YvsO p=0.161 FDR=0.484（n.s.）、OvsOD p=0.097 FDR=0.484（唯一边缘，OD 高于 O）、YvsOD p=0.887 已删不标
- 3 组基线无配对连线（PAIRED 循环只处理 Pre/Post 对，全 Pre 组 line_data=NULL，符合预期）
- **宽度 = 24mm（3 柱规则）**：`width_mm <- 30 - (6-3)*2 = 24`，高 32mm
- 定稿文件：`RP_high_II__3grp_p.value.png/.pdf` + `RP_high_II__3grp_FDR_per_celltype.png/.pdf`（24×32mm）

## RP_high(I) 探索（2026-08-13，等用户决定）
- 6 组探索图已出：`RP_high_I__6grp_explore.png`（140×110mm 全幅）
- 显著性（v4）：OvsOD p=0.053 FDR=0.318（唯一边缘）、YvsO p=0.193、Y运动 p=0.193、其余 n.s. → 信号弱，
  建议跳过或只标 OvsOD（用户尚未拍板）

## 文件名修正（2026-08-13 用户抓住）
- Agent 曾无条件给所有亚群加 `Pure_Type_` 前缀 → OTUD1+(II) 变成 `Pure_Type_OTUD1__II__...`（错误，原名不带 Pure Type）
- 修复：`cell_clean <- gsub('[+() ]', '_', celltype)` 直接用原始 annotation_L3 名称
  - 带 Pure Type（Pure Type I/IIA/IIX）→ `Pure_Type_IIA_...` 保留
  - 不带（OTUD1+/LRP1B+/RP_high）→ `OTUD1__II_...` / `LRP1B__I_...` / `RP_high_I_...`
- 受影响旧文件全部删除重出，交付清单说明"旧图已删"

## 目录组织（2026-08-13 用户要求）
- 结果目录分三个子目录：`figures/`（全部图）、`scripts/`（R/Python 脚本）、`data/`（显著性 CSV + RDS 缓存）
- 用户原话："把图片和脚本各种建一个图片目录和脚本目录，不要放在一起"
- 通用脚本结构：`01_build_cache.R`（一次性构建 percentage_data.rds + sig_table_v4.rds）→
  `02_plot_celltype.R "celltype" 6 p.value p.value final IIX5`（参数化：亚群/组数/标注列/tag/模式/comp_mode）
- `verify_xxx.R` 交付前核对标注比较数 + p/FDR 值（写 .R 文件跑，勿用 bash -e 内联）

## execute_r 持久内核实测结论（2026-08-13）
- **worker 实际是 R-4.5.3**（实测确认，非 R-4.4.2；`.libPaths` 设置跨调用保留）
- **纯计算跨调用保留 ✅**：`execute_r` 定义变量 test_var=12345，第二次调用同一 PID 仍存在（worker 复用）
- **画图场景不可靠 ❌**：绘图函数内 `print(p)`（用户脚本自带）→ ggplot print 需要图形设备，kernel worker
  无设备 → 内核错误 → execute_r 静默回退新 Rscript 进程 → 变量全丢
- **结论：本类任务首选 RDS 缓存方案**（01_build_cache → 02_plot_celltype readRDS），不依赖 execute_r 持久内核
- 若必须用 kernel：删除函数内 `print(p)`（ggsave 保存已足够）；execute_r.py 已加 logger 记录 kernel error
  （不再静默吞掉，便于诊断）
- 已提交修复：`memomics/bio_tools/execute_r.py` 加 kernel error 日志（passes 全量 pytest）

## bash `$` 展开坑（2026-08-13 两次踩坑）
- `Rscript -e "paste(sub$group1, sub$group2)"` 在 bash 双引号里 `$group1` 被展开为空 → `paste(sub, sub)`
  → 匹配失败误报 "NOT FOUND"（浪费 2 轮诊断）
- **R 验证/调试代码一律 write_file 成 .R 脚本再跑**，不用 -e 内联；或内联时 `\$` 转义

## pytest 验证注意（2026-08-13）
- 本机裸 `pytest` 指向 Python312（无 pytest 模块，报 No module named pytest）→ 不是代码失败
- 正确入口：项目 venv `.venv/Scripts/python.exe -m pytest -m "not external and not network and not live_llm and not gpu and not ssh and not lab and not docker and not browser" -q` → EXIT=0（296-297 passed + 1 skipped）
- results/ 下的 R 脚本 pytest 不执行（webui/tests 只覆盖仓库 Python 源码），验证 = 真实运行 + 产出物 + 像素检查
