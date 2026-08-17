# GSE278576 人海马 ATAC 数据集实战：选文件 + fragments vs bw 决策

> 2026-08 猴-人跨物种 CRE 保守性专利项目实战记录。
> 用户带宽 ~6KB/s 极慢，选文件策略 = 数据需求的最小充分集。

## 数据集基本信息

- **GSE278576**（Science 2026, "Epigenetic and 3D genome reprogramming during the aging of human hippocampus"）
- 40 个神经正常供体海马，4 年龄组：20-40 / 40-60 / 60-80 / 80-100
- 多组学：snRNA + snATAC + DNA methylation + 3D chromatin（Multiome）
- 80 个 GSM 样本（40 RNA + 40 ATAC）

## 文件类型地图（看懂 GEO suppl 列表）

### bigWig 信号轨道（~100-350MB/文件，亚群×年龄聚合信号）
命名规则：
```
GSE278576_ATAC_<细胞类型或亚区>.bw             ← 全年龄合并（总览）
GSE278576_ATAC_<细胞类型或亚区>_age20-40.bw    ← 年龄组拆分
GSE278576_ATAC_<细胞类型或亚区>_age40-60.bw
GSE278576_ATAC_<细胞类型或亚区>_age60-80.bw
GSE278576_ATAC_<细胞类型或亚区>_age80-100.bw
```

**关键点：CA1 / CA2-CA3 / DG / SUB = 海马解剖亚区（不是独立脑区！）**
- CA1 = 海马角1区（衰老中最易受损，AD 最早累及）
- CA2-CA3 = 海马角2/3区
- DG = 齿状回（成体神经发生地，衰老中新生急剧下降）
- SUB = 下托（海马输出枢纽）
- 其余：Astro/Oligo/OPC/Microglia = 胶质细胞；LAMP5/PVALB/SST/VIP/Chandelier/NR2F2 = 神经元亚型；Endo/VLMC = 血管细胞

用户（从骨骼肌转脑方向）会问"CA1/DG 是什么"——**必须用类比解释**（如肌肉分快肌/慢肌），不能默认对方懂脑解剖。

### raw_feature_bc_matrix.h5（50-220MB/样本 ×40）
- Multiome 原始矩阵（snRNA+snATAC 联合）
- 只有想重跑自己的聚类才需要

### GSM 级 fragments.tsv.gz + .tbi.gz（1-3.7GB/样本，共 ~52GB）
- **不需要下 89GB 的 GSE278576_RAW.tar**（tar 里就是这些 fragments）
- URL 模式：
```
https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549xxxx/suppl/GSM8549xxxx_hcXX_atac_fragments.tsv.gz
（GSM8549nnn 目录是固定的，所有样本都在里面；必须同时下 .tbi.gz 索引）
```

### ⛔ 不要下的
- GSE278576_RAW.tar（89.2GB）
- 所有 RNA_*.bw（用户明确不要 RNA）
- hippocampus_RNA_seurat_object（3.1GB，RNA 数据）
- 40 个 h5 矩阵（如果只用聚合信号）

## fragments vs bw 决策（专利项目核心）

| 需求 | bw（100-350MB） | fragments（1-3.7GB/样本） |
|------|:---:|:---:|
| L2 可及性保守（peak overlap + 信号强度 + 年龄动态） | ✅ 够 | ✅ |
| L3 TF footprinting（真实验证 TF 结合） | ❌ 做不了 | ✅ 能做 |
| 按细胞类型重聚类 | ❌ | ✅ |

**决策建议**：拿受理（3个月）→ bw 基本够（L2 是专利独权核心）；要完整实施例 → 补 4 个 fragments（2年轻+2老年 ~10GB）做真 footprinting。

## 本项目的下载落地

- 目录：`E:/专利/Human_Hippocampus_ATAC/`
- 下载清单：`GSE278576_40_samples_download_list.txt`（hc编号+GSM号+直链URL）
- 批量脚本：`download_40_fragments.bat`（跳过已下、断点续传、自动补 .tbi）
- 40 样本 hc 编号：hc11/hc12/hc19/hc26/hc29/hc35/hc40/hc73/hc76/hc77/hc78/hc8/hc81/hc9/hc98/hc1134/hc1153/hc1203/hc1216/hc1265/hc1271/hc13344/hc13394/hc13414/hc1745/hc212191/hc46426/hc4781/hc5021/hc5087/hc5551/hc5579/hc5610/hc5614/hc6021/hc6052/hc69984/hc73787/hc935/hc937

## 铁律提醒

- 用户带宽极慢（~6KB/s）：大文件先下 1 个验证，再批量
- 用户手动下载时：Agent 提供清单+脚本+URL，确认文件完整性后再分析
- 下载完成通知后：ArchR createArrowFiles() 构建人侧 Arrow → 猴-人 CRE 跨物种比较
