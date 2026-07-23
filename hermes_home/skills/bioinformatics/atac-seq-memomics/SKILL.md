---
name: atac-seq-memomics
description: "ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出"
version: 2.1.0
prerequisites:
  r_packages: ["ArchR", "Signac", "Seurat", "chromVAR", "motifmatchr", "ChIPseeker", "BSgenome.Hsapiens.UCSC.hg38"]
  python_packages: ["MACS2"]
  system_requirements: "ArchR needs R >=4.5.0 (TFMPvalue dep); Signac/Seurat can stay on R 4.4.x. See references/windows_setup.md for dual-R setup. Java >=8, >=16GB RAM for >50K cells"
---

# ATAC-seq 分析 (ArchR)

## Windows 双 R 环境 (ArchR + Seurat/Signac 共存)

ArchR 需要 R ≥ 4.5.0（依赖 TFMPvalue），而 Seurat/Signac 在 R 4.4.x 上运行良好。不要升级系统 R —— 装第二个 R 到独立目录：

```
默认 R (R 4.4.2, 在 PATH)        独立 R (R 4.6.1, 不在 PATH)
├── Seurat 5.5.0                  ├── ArchR
├── Signac 1.17.1                 └── BSgenome.*
└── SCENIC / CellChat / ...
```

调用：普通脚本用 `Rscript`，ArchR 脚本用 `"E:/Program Files/R/R-4.6.1/bin/Rscript.exe"`。

完整安装指南见 `references/windows_setup.md`。

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

- R 默认装 C:\Program Files\ → 用户偏好 E 盘（C 盘空间有限），安装时手动改路径
- ``C:\Program Files\R\`` 下的文件无法从 bash 删除（Windows 权限），需 Windows 卸载程序
- 不要勾选 "将 R 添加到系统 PATH"（避免和已有 R 冲突）
- ArchR 安装 ~20-30 分钟
