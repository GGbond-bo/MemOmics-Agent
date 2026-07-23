# scTour — 参考文献

## 原始论文

- **Li, Q.** (2023). scTour: a deep learning architecture for robust inference and accurate prediction of cellular dynamics. *Genome Biology*, 24, 149.  
  DOI: [10.1186/s13059-023-02988-9](https://doi.org/10.1186/s13059-023-02988-9)  
  PMID: 37386652

## 摘要

scTour 是一种基于深度学习的单细胞转录组动力学推断方法。它使用变分自编码器（VAE）和神经常微分方程（Neural ODE）框架，同时估计:

1. **发育伪时间（Developmental Pseudotime）**：无需指定起始细胞
2. **转录组向量场（Transcriptomic Vector Field）**：不区分 spliced/unspliced mRNA
3. **潜在空间（Latent Space）**：结合内在转录组结构和外源伪时间排序

此外，scTour 支持:
- 跨数据集预测（用训练好的模型预测新数据的伪时间/向量场/潜在空间）
- 批次不敏感推断
- 对细胞子采样具有鲁棒性
- 可扩展到大数据集

## 核心方法

scTour 的架构包含两个主要组件：

1. **TNODE（Transcriptomic Neural ODE）**：一个 VAE 框架，编码器将基因表达映射到潜在空间，解码器从潜在空间重建表达。同时，一个神经 ODE 在潜在空间中学习连续的动力学轨迹。

2. **损失函数**：由三部分组成
   - 从编码器潜在空间的重建误差（权重 α_recon_lec）
   - 从 ODE 求解器潜在空间的重建误差（权重 α_recon_lode）
   - KL 散度正则化项（权重 α_kl）

## 官方资源

- 文档: https://sctour.readthedocs.io/
- GitHub: https://github.com/LiQian-XC/sctour
- PyPI: https://pypi.org/project/sctour/
- Conda: https://anaconda.org/conda-forge/sctour
- Zenodo: https://zenodo.org/records/7538567

## 相关方法对比

| 方法 | 伪时间 | 向量场 | 潜在空间 | 无监督 | 跨数据集预测 | 批次校正 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| scTour | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Monocle3 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Slingshot | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| scVelo | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| CellRank | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Palantir | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| PHATE | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |