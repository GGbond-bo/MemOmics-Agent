# ArchR vs SnapATAC / SnapATAC2 对比调研（2026-08-11）

核心依据: Luo et al. Genome Biol 2024 (PMID 39152456, 独立第三方 benchmark, 8 pipeline × 6 datasets × 10 metrics) + ArchR (PMID 33633365) / SnapATAC (PMID 33637727) / SnapATAC2 (PMID 38191932) 原论文 + 本项目 40 样本实战。

## 一句话结论

选工具 = 选生态 + 选降维算法。ArchR = R 全家桶（功能最全、唯一有 co-accessibility），但聚类精度在独立 benchmark 中垫底；SnapATAC2 = Python 速度+精度之王（非线性降维），但需自己组装功能。**SnapATAC v1 已被 v2 取代，新项目别用。**

## 核心算法差异

| | ArchR | SnapATAC v1 | SnapATAC2 |
|---|---|---|---|
| 降维 | 迭代 LSI（线性, tf-idf+SVD） | Diffusion maps（非线性） | Laplacian eigenmaps（非线性） |
| feature | 500bp tiles 或 MACS2 peaks | 5000bp bins | 500bp bins 默认 |
| 相似度 | — | Jaccard | Jaccard 或 cosine |
| 数据对象 | Arrow (HDF5) + ArchRProject | .snap | AnnData (on-disk) |
| 单细胞上限 | 1.2M/8h | 100万 (Nyström) | 线性扩展 |
| 多组学 | scATAC+scRNA | 无 | scATAC/scRNA/scHi-C/multiome |

## Benchmark 关键结论（Luo 2024）

1. **聚类精度**: 简单数据集 aggregation 最优、SnapATAC2 第二、ArchR/Signac 稀有亚型差; 复杂层级数据集（Chen2019 小鼠皮层）**SnapATAC/SnapATAC2 最优、ArchR 垫底**（FNS>60% vs <40%）。Signac 普遍好于 ArchR。
2. **文库大小偏倚**: LSI 方法（ArchR/Signac）latent components 与测序深度强相关 (|r|=0.5-0.75)，第一成分几乎总是文库大小，需剔除 (r>0.75)；SnapATAC/SnapATAC2 (Jaccard) |r|<0.3。
3. **可扩展性**: SnapATAC2 最快（on-disk AnnData 线性）；ArchR 内存最低（Arrow on-disk, 1.2M/8h）；**SnapATAC v1 内存随细胞数平方增长，>20K cells 桌面机吃力**。
4. **基因活性评分**: SnapATAC/SnapATAC2 在多个数据集中优于 ArchR/Signac（反驳 ArchR 论文自称最优）。
5. **peaks vs bins**: 聚类性能几乎无差异（Chen2019 peak 仅轻微更好）→ 不必纠结特征类型，Windows 无 MACS2 时 TileMatrix 完全可用。
6. **参数敏感性**: SnapATAC 系列对 latent dimensions 非常敏感（d 增大性能骤降，建议 15-30）；ArchR 中间敏感（10-50 合理）。

## 功能矩阵（ArchR 独占项 = 跨物种 CRE 专利需求）

| 功能 | ArchR | SnapATAC2 |
|---|---|---|
| co-accessibility (共可及性) | ✅ 独占 | ❌ |
| peak-to-gene linkage | ✅ 成熟 | ❌ |
| QC/doublet 内置 | ✅ 最省心 | 手动 |
| motif/footprint | ✅ 内置 | 部分/需组装 |

## Benchmark 量化细节补充（2026-08-11 读全文后补）

- **文库大小偏倚数值**：LSI 方法（ArchR/Signac）latent components 与测序深度 |r|=0.5–0.75，第一成分几乎总是文库大小，须剔除 r>0.75 成分；SnapATAC/SnapATAC2（Jaccard）|r|<0.3。
- **基因活性评分**：SnapATAC/SnapATAC2 在 10XPBMC + Chen2019 多数场景优于 ArchR/Signac（**直接反驳 ArchR 论文自称最优**）。ArchR 仅在 10XPBMC 轻微胜 Signac。
- **scRNA 整合**：multiome 数据集 unpaired 整合测试，SnapATAC/SnapATAC2 更好，ArchR underperform。
- **时间/内存**：SnapATAC2 运行最快；ArchR 内存最省（HDF5 on-disk）；SnapATAC v1 内存随数据集平方级增长 = 最不可扩展。
- **参数敏感性**：SnapATAC 系列 latent dims 极敏感（建议 15–30）；ArchR 中等（10–50）。
- **gene activity vs 注释**：若注释主要靠 gene score → marker，SnapATAC 系列可能更可靠（对我们的 TileMatrix marker 注释方案是旁证——ArchR 注释精度本就有短板，用标签转移/gene score 升级是正路）。

## 选择指南

- R 用户 / 需要 co-accessibility / peak-to-gene → **ArchR**
- Python 用户 / 复杂层级组织 / 稀有亚型 / >100K cells / 多组学 → **SnapATAC2**
- 务实混合方案: SnapATAC2 做聚类（精度+速度），ArchR 做下游功能分析（co-accessibility/linkage/footprint）——两者都吃 fragment 文件，中间产物可互相导入。

## 对跨物种 CRE 专利项目的含义

保持 ArchR 正确（co-accessibility 是专利核心，40 样本 QC 管线已跑通，换工具代价大）；但报告或方案中涉及"聚类方法选择"论证时，可引用 Luo 2024 说明 ArchR 聚类精度局限、选择理由落在 co-accessibility 独占功能上。
