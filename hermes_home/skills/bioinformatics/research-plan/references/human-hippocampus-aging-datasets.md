# 人类海马正常衰老 snRNA-seq 数据集 — 专利实施例数据源

> 2026-07-20 · 经 search_geo + search_papers 检索验证

---

## 优先级排序

### 🥇 GSE278576 — 最完美匹配 (PMID: 39463924)

- **标题**: Epigenetic and 3D genome reprogramming during the aging of human hippocampus
- **样本**: 40 个神经正常供体，成人全生命周期
- **数据**: snRNA-seq + snATAC-seq + DNA甲基化 + Hi-C
- **平台**: GPL24676 (Illumina NovaSeq)
- **优势**: 纯正常衰老、40供体可分多年龄组、2024-2025发表
- **GEO**: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE278576

### 🥈 GSE186538 (Franjic 2022, Neuron) — PMID: 34798047

- **标题**: Transcriptomic Taxonomy of Adult Human, Macaque and Pig Hippocampal Cells
- **物种**: 人 + 猕猴 + 猪
- **价值**: 人-猴基因映射参考 + 细胞类型锚定流程
- **局限**: Adult only, 无年龄梯度 → 适合S200, 不适合S330/S340
- **GEO**: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE186538

### 🥉 Wang et al. 2022, Cell Research — PMID: 35750757

- **标题**: Transcriptome dynamics of hippocampal neurogenesis in macaques across lifespan and aged humans
- **物种**: 猕猴全生命周期 + 老年人类
- **引用**: 96次
- **价值**: 猕猴-人方法论参考, 场景高度重合
- **局限**: 人数据可能只有老年组

### 4️⃣ Su et al. 2022, Cell Stem Cell — PMID: 36332572

- **标题**: Glial diversity in human hippocampus across postnatal lifespan
- **焦点**: 胶质细胞(星形/小胶质/少突/OPC)
- **引用**: 63次
- **价值**: 胶质细胞特异性衰老参考

### 5️⃣ Thompson et al. 2025, Nature Neuroscience — PMID: 40739059

- **标题**: Integrated snRNA-seq and spatial transcriptomics atlas of human hippocampus
- **价值**: 最全面的海马亚区空间注释

---

## 数据对接流程

```
GSE278576 → count matrix (.h5/.mtx) + metadata (age, donor_id, cell_type)
  ├─ 按 donor_id + cell_type 分组 → 检查每年龄组≥5个体
  ├─ 年龄分组: 年轻20-40 / 中年40-60 / 老年60+
  ├─ S200: Ensembl BioMart 1:1 ortholog 匹配人-猴基因
  └─ S205: Harmony/scVI 跨物种批次校正
```

## 在专利说明书中的写法

> "实施例使用GEO数据库GSE278576数据集(40例神经正常供体全生命周期人脑海马snRNA-seq)..."
