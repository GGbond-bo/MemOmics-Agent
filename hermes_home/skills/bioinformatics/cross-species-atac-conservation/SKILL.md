---
name: cross-species-atac-conservation
description: >
  纯 ATAC-seq 跨物种 CRE 保守性定量评估方法（专利方案）。
  三层递进：L1 序列保守 → L2 染色质可及性保守 → L3 TF 结合动态保守。
  核心创新：B 类 CRE 检出（序列+可及性保守，但 TF 足迹分歧）。
  不需要 RNA/Hi-C/ChIP——纯 ATAC 数据即可运行完整评估。
  触发词：跨物种 CRE / ATAC 保守性 / CRE 可代替性 / 调控元件保守性评估 /
  cross-species ATAC / enhancer conservation / B类CRE / CRECS
trigger_level: RED 必触发
version: 1.0.0
---

# 跨物种 ATAC CRE 保守性评估（纯 ATAC）

## 一句话定位

用两个物种的 ATAC-seq 数据，定量评估每个调控元件（CRE）在物种间的保守程度，
输出 A/B/C/D 四级分类。**不需要 RNA-seq**。

## 三层评估框架

```
L1 序列保守性（不需要 ATAC 测序数据）
  ├─ liftover 坐标映射（rheMac10 → hg38）
  ├─ phastCons/phyloP 保守性分数
  └─ JASPAR motif 有无/位置/拷贝数比较
  输出: S_seq ∈ [0,1]

L2 染色质可及性保守性（需要两个物种的 ATAC）
  ├─ peak overlap: liftOver + Jaccard 指数
  ├─ 信号强度: Spearman ρ
  ├─ 细胞类型特异性可及性一致性
  └─ 衰老动态: species×age 混合效应模型 🔑
  输出: S_acc ∈ [0,1]

L3 TF 结合动态保守性（需要两个物种的 ATAC）
  ├─ TF footprinting 跨物种比较（HINT-ATAC / TOBIAS）
  ├─ 衰老变化中富集 motif 一致性
  └─ TF 结合强度衰老轨迹比较
  输出: S_tf ∈ [0,1]
```

## B 类 CRE —— 核心创新

```
A 类: S_seq 高 + S_acc 高 + S_tf 高 → ✅ 完全保守
B 类: S_seq 高 + S_acc 高 + S_tf 低 → 🔴 隐形炸弹！
      序列和染色质都保守，但 TF 结合模式不同。
      纯序列方法（phastCons/GERP）看不到 B 类。
      本方法是第一个能检出 B 类的方法。
C 类: S_seq 高 + S_acc 低 → 序列保守但不可及
D 类: S_seq 低 → 序列不保守
```

## 专利框架

- **独权**：三层递进整合（序列+可及性+TF结合）→ CRECS 综合评分 → A/B/C/D 分类
- **从权 2-4**：收窄物种/组织/统计方法
- **从权 5-6**：进化锚点校准法确定权重和阈值
- **从权 7**：输出形式（热图+分类标签）
- **从权 8**：细胞类型特异性评估
- **从权 9-10**：留口子——RNA 增强层、Hi-C 增强层（不做但从权里占位）

## A25 防御五锚点

| 锚点 | 防御逻辑 |
|------|---------|
| 数据绑定物理结构 | ATAC-seq peak 矩阵来自高通量测序仪的物理测量 |
| CRE 是分子实体 | 每个 CRE 对应基因组具体坐标，可实验验证 |
| 计算机不可省略 | 23万细胞×10万CRE×混合效应模型→人脑无法手动完成 |
| 产业技术效果 | 输出 B 类 CRE 清单→避免猴模型转化失败 |
| 错误检测机制 | 细胞类型锚定验证：跨物种细胞类型无法对齐→标记"仅供参考" |

## BNIP3 验证设计

- BNIP3 HRE 位点（-94bp）：人-小鼠已验证保守，人-猴首次比较
- 预期：三层全保守 → A 类
- 负对照：选已知灵长类调控分歧的 CRE → 预期判 B 类
- 一正一反验证方法的区分度

## 数据需求

| # | 数据 | 来源 | 用途 |
|---|------|------|------|
| 1 | 猴海马 ATAC-seq | 用户自有 | L2+L3 |
| 2 | 人海马 ATAC-seq | ENCODE/GEO 下载 | L2+L3 |
| 3 | 基因组序列+liftover链 | UCSC | L1 |
| 4 | phastCons/phyloP | UCSC | L1 |
| 5 | JASPAR motif | JASPAR | L1+L3 |

## 工具链

| 层 | 工具 | 环境 |
|----|------|------|
| L1 | UCSC liftOver, phastCons, JASPAR API | Shell/Python |
| L2 | ArchR (peak calling, 差异可及性, mixed model) | R 4.6.1 |
| L3 | HINT-ATAC / TOBIAS (footprinting) | Python |
| 整合 | 逻辑回归（进化锚点校准）| Python/R |

## 项目结构

```
results/atac-cross-species/
├── data/               # 下载的人ATAC + 猴ATAC
├── archr/               # ArchR Arrow 文件
├── L1_sequence/         # liftover + phastCons 结果
├── L2_accessibility/    # peak overlap + 信号 + 衰老动态
├── L3_footprinting/     # TF footprinting 跨物种
├── L4_integration/      # CRECS 综合评分 + A/B/C/D 分类
├── figures/
├── patent/              # 交底书 + 独权草案
└── log/
```
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="ATAC-seq 分析 —— {样本}",
     context="方法: {ArchR/Signac} | 参数: {peak calling参数} | 结果: {n} peaks {m} motifs",
     knowledge_base_info=<KB内容>,
   )
   辩论: peak质量如何？FRiP分数？motif富集合理吗？与RNA数据一致吗？
3. save_conclusions(module="03_advanced", topic="ATAC", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
