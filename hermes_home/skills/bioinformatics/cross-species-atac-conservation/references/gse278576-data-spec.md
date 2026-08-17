# GSE278576 人海马 ATAC 数据规范（2026-08 实测）

## 1. 官方元数据（NCBI GEO 实测）

- 标题：Epigenetic and 3D genome reprogramming during the aging of human hippocampus
- 40 个神经正常供体海马多组学（RNA + ATAC + 甲基化 + 3D），80 样本，20-100 岁全生命周期
- 平台 GPL24676（Illumina NovaSeq 6000）

## 2. bigwig 命名 = 海马亚区/细胞类型 × 年龄组

文件名 `GSE278576_ATAC_<区域/细胞类型>[_age<组>].bw`：

| 前缀 | 是什么 | 属于海马？ |
|------|--------|:---:|
| CA1 / CA2-CA3 / DG / SUB | 海马 4 大解剖亚区 | ✅ 核心 |
| Astro / Oligo / OPC / Microglia / Macro | 胶质/免疫细胞 | ✅ |
| LAMP5 / PVALB / SST / VIP / Chandelier / NR2F2 | 神经元亚型 | ✅ |
| Endo / VLMC / T-Cell | 血管/免疫 | ✅ |

**用户常见误解**："这些都是亚群的 ATAC" —— 实际是**海马亚区 + 细胞类型 × 年龄组的聚合信号**。
- 无 age 后缀（`VIP.bw`）= 全部年龄合并总信号
- 带 age 后缀（`VIP_age20-40.bw`）= 该年龄组信号，**衰老对比必须用带 age 的**

## 3. fragments 在 GSM 级不在 GSE 级

GSE 主页 suppl 只有 bigwig + h5 + RAW.tar（89GB）；**fragments 在 GSM 样本页**：
```
https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549xxxx/suppl/GSM8549xxxx_hcXX_atac_fragments.tsv.gz
```
每样本需 **2 个文件**：`fragments.tsv.gz`（1-3.7GB）+ `.tbi.gz`（索引，ArchR createArrowFiles 必需）。

## 4. 40 个 ATAC 样本 GSM 对照（已验证开头 4 个）

hc77=GSM8549615, hc78=GSM8549616, hc5579=GSM8549617, hc76=GSM8549618, hc29=GSM8549619, hc6052=GSM8549620, ...（其余 34 个 GSM8549621-9654 连续）

## 5. 测试版挑选策略（本会话确定）

猴侧 Y/O 两组 → 人侧 2 年轻 + 2 老年：hc78(20M) + hc5579(25F) = Young；hc98(82F) + hc9(95F) = Old → QC 后 29,357 cells，年龄跨 60+ 年。

## 6. 下载经验

- 40 样本全量 fragments ≈ 52GB，~6KB/s 带宽 100 天不可行 → 换高速网络或用 bigwig 先行
- 下载清单+脚本放 `E:/专利/Human_Hippocampus_ATAC/`（download_40_fragments.bat + GSE278576_40_samples_download_list.txt）
- 残缺文件（<1% 大小）会被 `if not exist` 跳过 → 先清理残缺文件再下
