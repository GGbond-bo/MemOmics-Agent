# NMF/cNMF vs hdWGCNA vs Hotspot — 方法选择速查

> 来源：2026-07 骨骼肌 snRNA-seq F2 设计会话。用户明确要求"用工具调查一下"后，
> 用 search_papers 验证了文献（PMID/年份/引用量），本文件记录验证结果与决策逻辑。

## 文献证据（已验证 PMID）

| 方法 | 文献 | PMID | 期刊 | 引用量级 |
|------|------|------|------|:---:|
| cNMF | Kotliar D et al. 2019 | 31282856 | eLife | ~500+ |
| hdWGCNA | Morabito S et al. 2023 | 37426759 | Cell Rep Methods | ~600+（3年内超 cNMF，单细胞共表达最主流） |
| Hotspot | DeTomaso Y & Yosef N 2021 | — | Nat Biotechnol | ~500 |

- hdWGCNA 2023 发表，不到 3 年引用超过 2019 年的 cNMF → 审稿人认可度最高
- 骨骼肌肌纤维亚型上 NMF/WGCNA/Hotspot 均无直接应用文献 → 用户是较早系统应用者（叙事优势）

## 决策逻辑（终端分化细胞场景）

```
数据是肌纤维/终末分化细胞？
  ├─ 是 → NMF/cNMF 首选（见下）
  └─ 否（肿瘤/免疫/发育，程序切换明确）→ hdWGCNA 可选主图

为什么 NMF 更适合终端分化细胞：
  1. 共表达网络"平坦" — WGCNA 软阈值拟合差、TOM 区分度低
  2. NMF 输出细胞级 loading（H 矩阵）→ 直接 program×condition 可视化
  3. NMF 计算轻量（pseudobulk 矩阵秒级），hdWGCNA 需 metacells + 大内存
  4. cNMF consensus 提供"程序稳定性"统计证据

推荐组合（CNS 叙事闭环）：
  F2 主图 2f：cNMF 程序发现（program × cluster 热图 + program × condition 折线图）
  S3 附图：hdWGCNA 验证（模块树状图 + module-trait correlation + hub gene）
  一致性：NMF program 基因集 vs WGCNA module 基因集 → Jaccard / 桑基图
  叙事：F2"我们发现一个衰老退化程序" → F4 DEG 独立验证程序内基因 → 多方法闭环
```

## Hotspot 何时才需要

- 空间转录组（局部邻域共表达）
- 发育/过渡态的瞬时共表达爆发（<2% 细胞的局部结构）
- 不输出细胞 loading → 无法直接画条件间变化，F2 类任务不适用

## 实施参数

| 步骤 | NMF/cNMF | hdWGCNA |
|------|----------|---------|
| 输入矩阵 | pseudobulk 按 cluster×condition 聚合（10群×5条件=50 样本） | metacells（每群 50-100 个） |
| 特征基因 | top 2000-3000 HVG | 同左 |
| 核心调用 | cNMF 跑 k=5-8 取 consensus | FindWGCNAModules（软阈值+TOM+动态剪切） |
| 注释 | 每 program top50 基因 GO/KEGG | 每 module 基因 GO/KEGG |
| 条件变化 | H 矩阵 boxplot（program×condition ANOVA） | ModuleEigengenes 聚合后 ANOVA |
