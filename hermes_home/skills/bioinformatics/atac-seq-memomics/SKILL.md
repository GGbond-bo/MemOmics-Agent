---
name: atac-seq-memomics
description: "ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出"
version: 3.0.0
prerequisites:
  r_packages: ["ArchR", "Signac", "Seurat", "chromVAR", "motifmatchr", "ChIPseeker", "BSgenome.Hsapiens.UCSC.hg38"]
  python_packages: ["MACS2"]
  system_requirements: "ArchR needs R >=4.5.0 (TFMPvalue dep). R 4.5.3 is the goldilocks version — R 4.4.2 is too old (no TFMPvalue), R 4.6.1 is too new (no Rtools46). See references/windows_archr_setup.md for proven dual-R setup. Java >=8, >=16GB RAM for >50K cells"
---

# ATAC-seq 分析 (ArchR)

## Windows 双 R 环境 (ArchR + Seurat/Signac 共存)

ArchR 依赖 TFMPvalue → 需要 R ≥ 4.5.0。但版本选择有讲究：

| R 版本 | Rtools | TFMPvalue | ArchR 能装？ | 原因 |
|--------|:---:|:---:|:---:|------|
| 4.4.2 | Rtools44 ✅ | ❌ Bioc 3.20 没这个包 | ❌ | TFMPvalue 最早出现在 Bioc 3.21 |
| **4.5.3** | **Rtools44 可用** ✅ | ✅ Bioc 3.22 | ✅ **首选** | Rtools45 安装器有 bug，Rtools44+符号链接更可靠 |
| 4.6.1 | Rtools46 未发布 ❌ | ✅ | ❌ | 没有编译工具，GitHub 包源码编译失败 |

> 🏆 **R 4.5.3 是黄金版本。** 安装到 `C:\Program Files\R\R-4.5.3`（本体小），R 包库放 `E:\R-libs\R-4.5.3`（包很大，放 E 盘）。

调用：普通脚本用 `Rscript`，ArchR 脚本用 `"C:/Program Files/R/R-4.5.3/bin/Rscript.exe"`。

完整安装指南见 `references/windows_archr_setup.md`。

## Signac vs ArchR 选择

| 功能 | Signac | ArchR |
|------|:---:|:---:|
| peak calling | ✅ (需 MACS2) | ✅ (内置) |
| 差异可及性 | ✅ FindMarkers | ✅ |
| TF footprinting | ✅ | ✅ |
| **共可及性 (co-accessibility)** | ❌ | ✅ **ArchR 独占** |
| peak-to-gene linkage | ✅ LinkPeaks | ✅ 更成熟 |

> 跨物种 CRE 保守性评估需要共可及性 → 必须用 ArchR。

## 已知问题

### 🔴 安装相关
- **Rtools45 安装器有 bug** — exit code 2/5，无法静默安装。**解决方案**：复用 Rtools44，在 ucrt64 目录创建 gcc/g++/gfortran 符号链接指向 x86_64-w64-mingw32.static.posix/bin/
- **`.Rprofile` 劫持库路径** — 如果 `~/.Rprofile` 硬编码了 `R-4.4.2-library`，所有 R 版本都会被劫持到错误路径。**解决方案**：改为 `R_version <- paste(R.version$major, R.version$minor, sep='.'); .libPaths(c(paste0('E:/R-libs/R-', R_version), .libPaths()))`
- **Bioconductor 镜像选择** — 清华镜像没有 Bioc 包，西湖大学 (`mirrors.westlake.edu.cn`) 可用。CRAN 用清华，Bioc 用西湖
- **R 包库分离** — R 本体放 C 盘（~100MB），包库放 E 盘（几 GB）。通过 `.libPaths()` 控制

### 🟡 运行相关
- **ArchR Arrow 文件是自定义格式** — 不是 Apache Arrow IPC 也不是 Parquet。只能用 ArchR 包读取，pyarrow 读不了
- **Bash+R segfault (exit 139)** — 在 MSYS2 bash 下跑 R 偶发 segfault。用 `terminal(background=True)` 可缓解
- **BiocManager::install 输出缓冲** — 大包下载时 R 缓冲所有输出，看起来像卡住了但实际在下载。通过检查库目录的包数量判断进度

### 🟢 用户偏好
- **禁止装到 C 盘** — R 包、基因组数据、分析产出全部放 E 盘。R 本体放 C 盘可以（~100MB）
- **安装必须主动监控** — 不能 fire-and-forget。每 30-60 秒轮询进程状态+库目录变化
- **优先使用 `pak::pak()` 装 GitHub 包**（而非 `devtools::install_github()` 或 `remotes::install_github()`）
