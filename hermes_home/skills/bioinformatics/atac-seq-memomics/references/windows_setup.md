# Windows 双 R 环境搭建 (ArchR + Seurat/Signac 共存)

## 问题

ArchR 依赖 TFMPvalue → 需要 R ≥ 4.5.0，但 Seurat v5 + Signac 在 R 4.4.x 上稳定运行。
不能直接升级系统 R（可能破坏现有分析环境）。解决方案：装两个 R，互不干扰。

## 双 R 架构

```
R 4.4.2 (默认 PATH, C:\Program Files\R\R-4.4.2)    R 4.6.1 (独立目录, E:\Program Files\R\R-4.6.1)
├── Seurat 5.5.0                                        ├── ArchR
├── Signac 1.17.1                                        ├── BSgenome.Hsapiens.UCSC.hg38
├── SCENIC / CellChat / monocle3 / ...                   ├── BSgenome.Mmulatta.UCSC.rheMac10
└── 不动它                                               ├── motifmatchr / chromVAR / TFBSTools
                                                         └── ComplexHeatmap / nabor / ggrepel / ...
```

## 步骤

### 1. 下载 R 4.5+ 安装包

```bash
# 清华镜像加速
curl -L "https://mirrors.tuna.tsinghua.edu.cn/CRAN/bin/windows/base/R-4.6.1-win.exe" -o /e/tmp/R-4.6.1-win.exe
```

### 2. 安装到非 C 盘

```bash
# 静默安装到 E 盘（用户 C 盘空间有限）
/e/tmp/R-4.6.1-win.exe /VERYSILENT /DIR="E:\Program Files\R\R-4.6.1" /NOICONS
```

⚠️ **不要勾选"将 R 添加到系统 PATH"** — 避免和默认 R (4.4.2) 冲突。

### 3. 安装 ArchR + 依赖

```r
# 用 R 4.6.1 的 Rscript 执行以下脚本：
.libPaths("E:/Program Files/R/R-4.6.1/library")
options(repos = c(CRAN = "https://mirrors.tuna.tsinghua.edu.cn/CRAN/"))

# BiocManager
if (!requireNamespace("BiocManager", quietly = TRUE))
  install.packages("BiocManager", lib = "E:/Program Files/R/R-4.6.1/library")

# Step 1: Bioconductor 依赖
BiocManager::install(
  c("GenomicRanges", "GenomeInfoDb", "Biostrings", "Rsamtools",
    "rtracklayer", "BSgenome", "motifmatchr", "TFBSTools",
    "ComplexHeatmap", "ggplot2", "gridExtra", "nabor", "ggrepel",
    "data.table", "magrittr", "plyr", "dplyr"),
  lib = "E:/Program Files/R/R-4.6.1/library",
  update = FALSE, ask = FALSE
)

# Step 2: 基因组包
BiocManager::install(
  c("BSgenome.Hsapiens.UCSC.hg38", "BSgenome.Mmulatta.UCSC.rheMac10"),
  lib = "E:/Program Files/R/R-4.6.1/library",
  update = FALSE, ask = FALSE
)

# Step 3: ArchR (GitHub)
if (!requireNamespace("devtools", quietly = TRUE))
  install.packages("devtools", lib = "E:/Program Files/R/R-4.6.1/library")

devtools::install_github(
  "GreenleafLab/ArchR", ref = "master",
  repos = BiocManager::repositories(),
  lib = "E:/Program Files/R/R-4.6.1/library",
  upgrade = "never"
)

# Step 4: 验证
library(ArchR, lib.loc = "E:/Program Files/R/R-4.6.1/library")
cat("ArchR version:", as.character(packageVersion("ArchR")), "\n")
```

### 4. 调用方式

```bash
# 普通 Seurat/Signac → 默认 R (4.4.2, 在 PATH)
Rscript seurat_analysis.R

# ArchR → 显式指定 R 4.6.1
"E:/Program Files/R/R-4.6.1/bin/Rscript.exe" archr_atac.R

# Python 跨环境编排
python -c "
import subprocess
R45 = 'E:/Program Files/R/R-4.6.1/bin/Rscript.exe'
R44 = 'Rscript'
subprocess.run([R45, 'scripts/01_archr_atac.R'], check=True)  # ArchR
subprocess.run([R44, 'scripts/02_seurat_downstream.R'], check=True)  # Seurat
"
```

## 已知陷阱

- **`C:\Program Files\R\R-4.6.1\` 无法从 bash 删除** — Windows 权限保护。用 Windows 卸载程序或手动删除
- **ArchR 安装 ~20-30 分钟** — 大量 Bioc 依赖 + BSgenome 基因组包（~1-2GB）
- **TFMPvalue 是瓶颈包** — 这是为什么 ArchR 需要 ≥4.5.0 的根本原因
- **用清华镜像** — CRAN/Bioc 主站在国内慢，清华镜像稳定
- **`lib=` 参数必须显式指定** — 否则 R 4.6.1 会默认装到 C 盘的 library 目录

## 功能对比：Signac vs ArchR

| 功能 | Signac (R 4.4.2 可用) | ArchR (需 R 4.5+) |
|------|:---:|:---:|
| peak calling | ✅ (需 MACS2) | ✅ (内置) |
| peak overlap 跨物种 | ✅ (liftover + bed) | ✅ |
| 差异可及性 | ✅ FindMarkers | ✅ |
| TF footprinting | ✅ | ✅ |
| **共可及性 (co-accessibility)** | ❌ | ✅ **ArchR 独占** |
| peak-to-gene linkage | ✅ LinkPeaks | ✅ 更成熟 |

跨物种 CRE 保守性评估中，共可及性是关键信号（同一个增强子-启动子互作在猴和人之间是否保守）。这个功能 Signac 没有 → 必须 ArchR。
