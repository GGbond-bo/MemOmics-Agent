# Zhang Xiao 2026 猴脑ATAC-seq注释方法总结

## 文章信息
- **标题**: Multimodal brain cell atlas across the adult macaque lifespan
- **作者**: Xiao Zhang et al.
- **期刊**: bioRxiv 2025.03.11.641786 → 已投Cell
- **数据**: 13只食蟹猴×8脑区×198万细胞（snRNA+snATAC）
- **PDF**: D:/学习文献/ZhangXiao_2026_macaque_brain_cell.pdf

## ATAC-seq注释方法（PDF原文确认）

### 注释方法
> "The regional cell subtype identities were determined by assessing gene expression and locus chromatin accessibility of canonical markers"
> — PDF第246-247行

**是手动canonical marker注释，不是TransferData预测。**

### 细胞类型注释结果
> "Analysis of the snATAC-seq data revealed the same 16 main cell types"
> — PDF第231-232行

ATAC和RNA注释结果一致，都用canonical markers。

### 亚群分类（ATAC-seq中识别的）

| 大群 | 亚群 | Marker基因 | PDF行号 |
|------|------|-----------|---------|
| **星形胶质细胞** | Ast1 | GFAPlow GPC5+ | 261-263 |
| | Ast2 | GFAPhigh EEF1A1+ | |
| | Ast3 | GRIA4+ SEPT4+ | |
| **小胶质细胞** | Mic1 | CD163low CAMD2+ | 268-269 |
| | Mic2 | CD163high DAB2+ | |
| **少突胶质细胞** | ODC1 | OPALIN+（髓鞘形成） | 271-272 |
| | ODC2 | GSN+（细胞运动调控） | |
| **血管细胞** | pericytes | - | 275-278 |
| | perivascular fibroblasts | - | |
| | meningeal fibroblasts | - | |
| | venous/capillary/arterial EC | - | |
| | smooth muscle cells | - | |
| **神经元** | 89种亚群（snRNA-seq） | canonical markers | 248-250 |
| | ATAC-seq数量略少 | | |

### 基因活性矩阵验证
> "correlation of candidate cis-regulatory elements (cCREs) in the main cell types with nearby expressed genes demonstrated the expected cell type correspondences across the two datasets"
> — PDF第236-238行

## 对用户专利的启示

1. **ATAC注释可以用canonical markers** — 张潇文章证明手动marker注释在ATAC上可行
2. **Gene Activity Matrix验证** — 用cCREs与附近表达基因的相关性验证注释一致性
3. **不需要TransferData** — 手动注释更可靠，避免循环论证风险
4. **ATAC亚群数量略少于RNA** — 这是正常的，ATAC分辨率略低

## 用户专利应用建议

- 用张潇的marker列表作为猴侧ATAC注释参考
- 人侧用Zemke 2024的canonical markers注释
- 两侧用同一套marker体系保证可比性
- 专利方法里注明"canonical marker注释，非预测方法"
