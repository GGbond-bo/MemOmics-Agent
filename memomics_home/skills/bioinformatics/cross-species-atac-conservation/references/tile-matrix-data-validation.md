# samples×tiles 核矩阵形状校验（L2/L3 输入，防"假矩阵"）

## 背景
跨物种 CRE 保守性 L2（染色质可及性保守）与 L3（TF 结合动态保守）的输入是一张
**「样本 × 统一同源网格 tile」核矩阵**：行 = 样本，列 = 同源网格的每个 tile
（本方案统一网格 = **6,085,841** 个 500bp tile，猴 T2T-MFA8 与人 hg38 经 liftOver
对齐到同一套网格）。生成或复用这张矩阵前，必须先验证列是真的 tile，不是细胞条码。

## 一个真实踩坑（2026-09-14）
用户问"这个矩阵是不是假的"，文件 `human_tile_matrix_samples_x_tiles.rds` ：
- 错误产物：`40 × 10910`，列名 = `GSM8549634_hc6021#GTTACAGGTACCGTTT-1`（**样本#细胞条码**），
  且 10910 列全部来自**单个样本 hc6021**。
- 根因：loop 里把 `colMeans` 作用到了**细胞级**数据（10910 个细胞），而不是 **tile 级**
  （~608 万 tile），且只处理了一个样本的细胞。
- 正确形状应为 `40 样本 × ~6,085,841 tile`。

## 判定「列是 tile 还是细胞条码」三招
1. **列名格式**：
   - tile → `chr:start-end`（如 `NC_088375.1:0-499`），或**列名为空**（坐标存独立
     `xxx_tile_coords.csv`，列顺序与矩阵列一一对应）。
   - 细胞条码 → `样本名#barcode`（含 `#`，后面是 10x barcode 尾缀如 `-1`）。
2. **列数量级**：tile 数 ≈ 统一网格数（~608 万）；细胞条码数 ≈ 单样本细胞数（~1 万）。
   `ncol` 偏离 6,085,841 一个数量级以上 = 几乎可以肯定是细胞级或样本子集。
3. **含 `#` 的列比例**：`sum(grepl("#", colnames(m)))` 接近 `ncol` → 全部是细胞条码，必错。

## 权威参考产物（本专利项目，磁盘实存）
- 猴侧矩阵：`E:/专利/file/monkey_tile_matrix_samples_x_tiles.rds`
  = `20 × 6,085,841`（样本 M1..Y7 共 20；列名**全空**，坐标在
  `E:/专利/file/monkey_tile_coords.csv`，格式 `NC_088375.1:0-499` 500bp 递增）。
- 人侧正确 tile 源（不要再手写 cell 级矩阵）：
  - `E:/专利/ArchR_Output/project_tilemat.rds` = ArchRProject（已 addTileMatrix；观测到
    35,879 cells、`Sample` 列仅 3 个唯一值 → 是 3 样本**测试子集**，非 40 全样本）。
  - `E:/专利/ArchR_Output/markers_age_tiles.rds` = SummarizedExperiment `6,085,841 × 2`
    （tile × Old/Young）→ 这才是同源网格 tile 级的现成矩阵。
- 人侧 40 样本 arrow 源：`E:/专利/Human_Hippocampus_ATAC/ArchR_Arrow_QC/ArrowFiles/`
  （`GSM8549615_hc77.arrow` … 共 40 个）。

## 修复路径（把人侧做成 40 样本 × 6,085,841 tile）
1. 从 ArchRProject 取 tileMatrix（`getMatrixFromProject(proj, useMatrix="TileMatrix")`
   或从 arrow 的 TileMatrix 读），得到 `cells × tiles`。
2. 按 `Sample` 列把 cells 分组，每组 `colMeans` 得到该样本的 tile 可及性向量 → `rbind`
   成 `40 × 6,085,841`。
3. 保存时**列名与 monkey_tile_coords.csv 的 tile 顺序严格对齐**（同源网格），否则 L2/L3
   逐 tile 比较会错位。

## 铁律
任何"样本×tile"矩阵交付/复用前，先打印 `dim()` + 列名前 3/后 3 + `sum(grepl('#',colnames))`
三件套核实是 tile 不是细胞条码，再插进下游。列数不是 ~608 万、或列名带 `#`，就是假矩阵。