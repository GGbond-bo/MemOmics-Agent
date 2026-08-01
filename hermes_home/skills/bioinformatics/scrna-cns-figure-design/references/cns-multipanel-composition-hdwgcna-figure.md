# CNS 级多面板拼图配方 — hdWGCNA Figure（2026-08-01 被用户接受版）

用户原话："这个figure我不满意，排版我也不满意，我希望你能按照CNS级别拼Figure"。
第一次失败版 = 官方 PNG 直接横向粘贴 + 底部文字条（cowplot draw_image 需要 magick，
且工具 PNG 字体/配色不统一 → 看起来像拼贴画）。以下是被接受版的完整配方。

## Figure Contract（拼图前先写）

```
Core conclusion: hdWGCNA 共表达网络识别出衰老/糖尿病/运动响应的肌纤维模块，
                red 模块（胰岛素信号/AMPK/血管）被衰老与 T2D 压制、年轻运动逆转、老年运动无效
Archetype: asymmetric mixed-modality（hero 热图 + 方法/机制支持面板）
Backend: R（用户全程 R 工作流）
Final size: 183mm × ~150mm（Nature 单栏宽）
Panel map: a=软阈值 b=树状图 c=模块×五效应热图(★HERO) d=GO e=KEGG f=hub 网络
Evidence hierarchy: hero=c；validation=a+b；mechanism=d+e+f
Reviewer risk: metacell 级伪重复 → 结论条标注个体级验证需求；red 功能过泛 → GO/KEGG 限定 top terms
```

## 布局（patchwork design 或 base viewport）

```
┌──────────────────────────────────────────────┐
│ a. soft power   │   b. dendrogram            │   ← 方法建立（小）
├──────────────────────────────────────────────┤
│ c. module × 5 effects  heatmap  (★HERO 全宽) │   ← 主效应（大，横跨）
│   行=模块按 Aging 排序, 列=5 效应, 星标显著性 │
├───────────────┬───────────────┬──────────────┤
│ d. GO bubble  │ e. KEGG bubble│ f. hub 网络  │   ← 机制（小）
├───────────────┴───────────────┴──────────────┤
│ CONCLUSIONS: red=可逆靶点 / purple-magenta=   │
│ T2D特异 / marker验证 / 统计提醒(n=metacells)  │   ← 结论条
└──────────────────────────────────────────────┘
```

## 数据准备（每个 panel 从 CSV/RDS 重绘，不贴 PNG）

1. **模块×效应热图**：`official_module_trait_cor.csv` + `_p.csv` 是宽表
   `5 effects × (module×cell-group)` 列（如 `all_cells.red`、`RSS.red`）。
   只取 `^all_cells\\.` 列 → strip 前缀 → 去掉 grey → 按 Aging 排序 →
   melt 成 long：effect/module/cor/p/sig(***/<0.01, **/<0.05)。ggplot2 geom_tile +
   scale_fill_gradient2(mid=0, blue-white-red)。
2. **软阈值**：`official_softpower_table.csv` → Power vs SFT.R.sq 折线，标注最佳 power=10。
3. **树状图**：优先从 wgcna 对象 `PlotDendrogram` 输出；若需 raster 可用 readPNG 嵌入。
4. **GO/KEGG**：官方模块重新富集（enrichGO BP + enrichKEGG，bitr SYMBOL→ENTREZID），
   按模块取 top terms → 气泡图（x=GeneRatio, y=Description, size=Count, color=p.adjust）。
   **red 模块富集到 hsa04910 Insulin signaling + hsa04931 Insulin resistance — 这是全文最强机制证据。**
5. **hub 网络**：`official_hub_genes.csv`（kME 排序）取 top 10-12 → igraph 网络或
   kME 排名条形图。

## 被接受版本的关键决策

- **hero = module×effect 热图**（直接回答"哪个模块响应哪个效应"），横跨全宽
- **结论条 4 行**：red=可逆靶点(Aging−0.264/T2D−0.252/ExYoung+0.271/ExOld−0.233)、
  purple 0 GO=全新 T2D 模块、marker→module 验证(快肌8/9,慢肌10/10)、统计提醒
- **GO/KEGG 必须重跑官方模块**（遗留的 module_go.rds 是旧底层版只有 6 模块，不能用）
- **debate 服务故障时**：给结构化 pro/con 替代辩论（正方=方向一致性+KEGG先验+marker验证；
  反方=细胞级伪重复/insulin 信号检测局限/purple 真新性），如实标注"服务故障，正式裁决待补"

## 导出

SVG（可编辑）+ PDF（TrueType Arial）+ TIFF（600dpi）+ PNG（300dpi 预览）+ source_data CSV。
文件名 `Fig_hdwgcna_final.{svg,pdf,tiff,png}`。

## 验证锚点模式

验证脚本（独立重算 cor 值 + 断言文件存在/尺寸）写进 Temp 目录 `hermes-verify-*.R`，
结果持久化到 `hdwgcna/log/verify_hdwgcna_pubfig_status.txt` 再清理临时脚本：
```
VERIFY run_step7.R(kME) + run_step8.R | 2026-08-01 04:08:37 | 9 pass / 1 fail
black_hub=FKBP5,... | cor: black_Aging=-0.512 magenta_Aging=0.39
```
小 CSV（hub_top10 只有 10 行）会触发验证脚本 `>1000 bytes` 误判 → 阈值按内容类型放宽。

## Windows/MSYS R 执行坑（本会话实测）

- **/tmp 下的 R 脚本 → segfault exit 139**（连 read.csv 都崩）。根因：MSYS 虚拟路径
  R 读不到脚本文件。修复：脚本写到 E:/ 工作目录，`Rscript --vanilla ./script.R`。
- **PATH 上 R 4.4.2 被污染**（装包后 .Rprofile 库路径损坏）→ 用 `--vanilla` 绕过
  .Rprofile，或换第二个 R 安装（本机 R 4.5.3 正常但缺绘图包，最终用 R 4.4.2 --vanilla
  + 显式 .libPaths(c("C:/Users/23136/AppData/Local/R/R-4.4.2/library"))）。
- **enrichR .onAttach 联网检查**（maayanlab.cloud 超时挂起）→ `loadNamespace("hdWGCNA")`
  + `hdWGCNA::` 前缀绕过 .onAttach。
- **heredoc 写 R 脚本被 bash 转义**（`\\.` 被吃）→ 用 write_file 工具或 Python
  pathlib 写文件（避免 heredoc 转义 + 避免被误判为删除操作）。
