# ArchR TileMatrix 提取：方向 / 命名 / 裸 arrow 直读（2026-09-15 实跑验证）

跨物种 ATAC 项目里，要把「每样本 × tile 的覆盖比例矩阵」抽出来（对齐到猴侧），踩了四个坑，浪费近一天。全记录在此，下次直接照做。

## 坑 1：方向 — `rowMeans` 不是 `colMeans`

`getMatrixFromProject(proj, useMatrix="TileMatrix", binarize=TRUE)` 返回 SummarizedExperiment：

- **行 = tile**（~606 万），**列 = 细胞**（~1 万）
- 要「每个 tile 跨细胞的覆盖比例」（长度 = tile 数）→ 必须 `Matrix::rowMeans(assay(se))`
- 错用 `colMeans` → 得到「每个细胞一个数」（长度 = 细胞数），列名变成 `样本名#细胞barcode`，这就是 40 样本只出 2.8MB 假矩阵（40×10910）的根因

**判定口诀**：打印出来的向量名字是 `GSM8549615_hc77#ACGCACGGTATTCGCT-1`（带 barcode）= 细胞方向，错了；应该是 `chr1:1-500` 这种 tile 坐标才对。

## 坑 2：`Matrix::rowMeans` 丢弃向量名 → 合并变 0 列

```r
v <- Matrix::rowMeans(assay(se))   # v 没有 names()！
do.call(rbind, list_of_v)          # 按 NULL 名对齐 → 40 × 0 空矩阵
```

`Matrix::rowMeans()` 返回的向量**不带 names**。tile 坐标也不在 `rownames(assay(se))`（ArchR 1.0.3 的 rownames 是 NULL），而在 **`rowData(se)`** 的前几列（`seqnames` / `start`）。

**正确补名**：
```r
rd  <- rowData(se)
tile_names <- paste0(rd$seqnames, ":", rd$start, "-", rd$start + 499)  # tileSize=500
v <- Matrix::rowMeans(assay(se))
names(v) <- tile_names
```

## 坑 3：人侧是「裸 arrow 文件」，别找 Save-ArchR-Project.rds

人侧数据（GSE278576 的 40 ATAC donor）在 `ArchR_Arrow_QC/` 下**平铺 40 个 `GSMxxxx_hcXX.arrow`**——
没有 `Save-ArchR-Project.rds`、没有 `sub_` 目录、没有 PeakMatrix。之前一直找 project rds 所以空转。

**裸 arrow 内部已经有 TileMatrix**，用 h5py 直读（Python 端，无需 ArchR）：

```python
import h5py, numpy as np

# 每个 .arrow 的 TileMatrix 键结构：
#   TileMatrix/Info/FeatureDF      -> tile 坐标表 (seqnames + start, tileSize=500)
#   TileMatrix/Info/CellNames      -> 细胞 barcode
#   每个染色体 group 下预存 rowSums (1 x n_tile) = 该 tile 被多少细胞覆盖

with h5py.File("GSM8549615_hc77.arrow", "r") as f:
    # 1) tile 坐标：FeatureDF
    feat = f["TileMatrix/Info/FeatureDF"]
    seqs  = feat["seqnames"][:]      # 染色体
    starts = feat["start"][:]        # tile 起点的第 0 列? 见下

    # 2) 覆盖细胞数：每染色体 rowSums 拼接 = 覆盖计数
    #    nCells = len(CellNames)
    #    覆盖比例 = rowSums / nCells
```

要点：
- tile 数 = **6,062,095**（hg38，tileSize=500）。这是人侧基准；**猴侧 T2T-MFA8 = 6,085,841，两个参考基因组不同天生不相等**，提取时只要求人侧 40 样本彼此一致，别拿猴侧数当基准。
- 覆盖比例 = 每染色体 `rowSums` / 该样本细胞总数，值域 0~1。
- 大矩阵用**预分配 float32 稠密矩阵**（40×6062095 ≈ 970MB）一次性填入；用 Python list 累积 4000 万非零元素会撑爆内存。

## 坑 4：年龄不在 GEO Series Matrix，在 BioSample

GSE278576 的 Series Matrix `!Sample_characteristics_ch1` 只有 `tissue: hippocampus` + `donor id: hcXX`，**没有 age**。
age/sex 在每个样本链到的 **BioSample** 里：

```python
import urllib.request, re, ssl
def attrs(acc):
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=biosample&id={acc}&retmode=xml"
    xml = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})).read().decode("utf-8","replace")
    return dict(re.findall(r'attribute_name="([^"]+)"[^>]*>([^<]+)<', xml))
# 返回 {'isolate':'hc77', 'age':'20', 'sex':'male', 'tissue':'hippocampus', ...}
```

- 40 donor 全拿到：**20–95 岁（中位 65），20 女 / 20 男**。
- Series Matrix 里的 `!Sample_title` = `hc77_ATAC` 揭示：**GSM 后缀 `_hcXX` = donor_id**，这是把 meta 和 tile 矩阵样本名对齐的键。
- 40 ATAC 样本 = GSM8549615–9654（title 以 `_ATAC` 结尾），后 40 个（9655–9694）= 配对的 snRNA。
- meta 表已落盘：`results/memomics-7839e23a/data/human_meta_40donors.csv`（GSM / donor_id / age / sex / age_group）。

## 一句话结论

人侧「样本 × tile 覆盖比例」矩阵的正确产出 = **裸 arrow 用 h5py 直读（或 ArchR rowMeans 补名）→ 行=tile 方向 → 覆盖比例 = rowSums/nCells → 40×6062095**。年龄从 BioSample efetch 拿，对齐键 = donor_id 后缀。