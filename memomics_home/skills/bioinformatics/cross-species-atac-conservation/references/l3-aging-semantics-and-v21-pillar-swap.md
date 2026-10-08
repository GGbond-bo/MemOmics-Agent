# L3 衰老关联：元件 vs 基因集语义边界 + v21 三层承重换柱 + 数据对称性检查

> 本文件记录 2026-09-14 专利评审会话沉淀的三块可复用知识。做「跨物种衰老 CRE 专利」的 L3 层设计、独权承重、或两侧数据对齐时必读。

## 一、元件 vs 基因集：L3 衰老关联的语义铁律（用户显式纠正）

**用户当场纠正**："但是我们的是元件，你却要基因集？"

- 衰老基因集（SenMayo / CellAge / 灵长类甲基化时钟靶基因）是**表达语义**（基因名单）。
- 本方法的判定对象是**可及性元件**（染色质调控单元），是**调控语义**。
- 两者之间隔着 enhancer→gene 链接，这层链接本身错误率极高（增强子远距离作用、promoter 归属含糊）。
- **⛔ 铁律**：任何时候都不得把「基因集筛元件」写成 L3 的硬 AND 生死判定条件。让表达级名单给可及性级元件做生死判定，审查员和无效宣告对手都会咬这个错配。

**正确边界（v21 定案）**：
- **L3 主门 = 物种内年龄效应**（数据里回归测得，独立金标准，唯一硬门、唯一生死判定）。
- **SenMayo/CellAge = 可选后验富集检验**（软校验、非硬 AND、不要求单个元件命中）——只做「命中元件是否显著富集于衰老基因邻域」的集合级 Fisher 富集。
- 这样命门从「语义错配硬伤」变成「可证伪的富集结论」，反而多一条从权可写（"输出元件富集于衰老基因的邻域"）。

**另一层已证事实**：`cor(x, age/寿命)` 与 `cor(x, age)` 结果完全相同（Pearson 对线性缩放不变），所以「相对年龄对齐」数学上等于没改，不能靠它跨物种对齐衰老尺度。

## 二、v21 独权承重换柱：从「同向率」到三层验证

**为什么换**：v15 独权 S3 承重 = 跨物种方向同向率，被自身数据否掉（46.36% < 随机 50%，r=−0.0971，二项 p=1.9×10⁻⁹）。「随年龄同向」≠「随衰老同向」——猴 31 岁从未被当成人 89 岁，各算各的符号，只证明「随各自历法年龄符号一致」。

**换成三根各有独立金标准的柱子**：
| 柱 | 金标准 | 本地数据 |
|---|---|---|
| L1 序列保守 | phyloP（phastCons 背书） | hg38.phyloP100way/30way bigWig ✅ |
| L2 跨物种可及性 | ATAC 直接测量 | 人 265,909 细胞 + 猴 161,497 细胞 meta ✅ |
| L3 衰老关联 | 年龄效应（数据回归）+ 基因集后验 | Age 列 ✅ / SenMayo+CellAge 待补 |

**创造性锚必须重立**：换柱后「可替代性」被 L2 承接，但「两物种都可及」≈ D1 郭国骥 overlap≥0.5 判功能保守，三柱 AND 会被读成「D1+D2+公开基因集」显而易见组合。主锚改立为**衰老维度**（五件对比专利全无年龄梯度，本案"元件年龄效应回归"独有）。A26.4 措辞：独权落点从「可替代性」诚实改为「跨物种保守衰老调控元件的筛选方法」，可替代性降为权 10 下游用途。

## 三、数据对称性检查：两文件大小悬殊先读结构，别急着判"数据错"

用户质疑：人侧 `project_tilemat.rds`(29MB) vs 猴侧 `monkey_tile_matrix`(206MB) 差距大，直觉"数据肯定不对"。

**正确诊断顺序**（先 readRDS 读 class/dim/是否 sparse，再下结论）：
```r
h <- readRDS("人侧.rds"); class(h); dim(h); is(h,"sparseMatrix")
m <- readRDS("猴侧.rds"); class(m); dim(m); is(m,"sparseMatrix")
```
**真相**（本例）：两个文件根本不是同一类东西——
- 人侧 29MB = **ArchRProject 空壳**（3 样本测试残件 O1_Hip_1/Y3_Hip_1/Y3_Hip_2，35,879 细胞而非 265,909，无 TileMatrix，Arrow 已丢失）。
- 猴侧 206MB = **dgCMatrix 完整信号矩阵**（20 样本 × 6,085,841 tile，83.5% 非零）。
- 差距根源 = 「空壳 project」vs「完整 sparse 矩阵」，不是数据算错，但人侧那个文件确实不能用。

**教训**：宣称两个文件"对称可比"前，必须先核实两侧 class/dim/样本数/sparse 一致；一个 `.rds` 文件名带 "project" 很可能是 ArchRProject（元数据+指针）而非信号本体。

## 四、ArchR TileMatrix 提取 recipe（人侧完整重建）

- `createArrowFiles(..., addTileMat=TRUE)` 时 TileMatrix **已嵌入 arrow**，重建 project 后直接 `getMatrixFromProject(proj, useMatrix="TileMatrix")` 提取，**不用重跑 addTileMatrix**（慢）。
- ⚠️ ArchR 1.0.3 `rowRanges(se)` 为空是预期，tile 坐标从 `rowData(se)` 前 3 列取（chr/start/end），勿用 rowRanges。
- 用 `list.files(dir, pattern="\\.arrow$", recursive=FALSE)` 只取顶层 arrow，避开 `FilteredProjects/` 子目录里重复的单样本测试残件（本案例人侧 40 个真实 arrow vs 子目录 81 个含重复）。
- 按样本聚合 → samples×tiles：`agg <- t(rowsum(t(assay(se)), group=se$Sample))`。
- 两侧 tile 坐标不同源（人 hg38 vs 猴 T2T-MFA8），`human_tile_coords.csv` 与 `monkey_tile_coords.csv` 不能直接对齐——需统一同源网格（v21 记为技术前提）。

## 相关脚本
- `E:/专利/交付_跨物种衰老可替代性专利/scripts/rebuild_human_tilematrix_full.R`（人侧完整 40 供体 TileMatrix 重建，产出对齐猴侧三件套）
- v21 蓝图：`E:/专利/交付_跨物种衰老可替代性专利/重新规划_三层验证承重_v21蓝图.md`
