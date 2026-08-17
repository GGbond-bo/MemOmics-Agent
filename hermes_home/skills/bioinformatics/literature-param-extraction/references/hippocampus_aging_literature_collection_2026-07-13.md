# 海马体(猴vs人)衰老方向跨物种 snRNA-seq 文献收集

> 创建日期: 2026-07-13 (原始)
> 更新日期: 2026-07-13 (本Session — Cloudflare 封锁更新 + 全文提取结果)
> 分析方向: 猕猴↔人类 海马体衰老 snRNA-seq 跨物种可替代性评估

## ⚠️ 重要更新: Cloudflare 全面封锁（2026-07-13）

**本Session验证**: 所有自动PDF下载策略(包括之前认为可靠的 `download_pdf(doi=...)`) 均已失败。
- `download_pdf(doi=...)` 之前成功下载 Wang 2022 Cell Res / Wang 2025 Genome Med / He 2024 PLoS One
- **本Session**: 同样的DOI → 所有策略返回 1.8KB HTML captcha 页面
- 之前下载成功的PDF是磁盘残留，不是本次下载的

**当前推荐**: 手动下载 + terminal提取 (详见 SKILL.md 回退路径 B 的 Cloudflare 策略)

## ✅ 已有PDF全文（磁盘残留）

下列文件已存在于 `work/papers/` 并可提取：

### 1. He et al. 2024, PLoS ONE (PMID: 39591421)
- **DOI**: 10.1371/journal.pone.0311374
- **文件**: `He_2024_PLoSONE_substitute_model.pdf` (4.4 MB)
- **提取**: ✅ 70,502 chars, 1,054 lines — 全文完整提取
- **主题**: 小鼠替代人研究海马小胶质细胞在衰老和AD中的可行性
- **核心方法**: Seurat + Harmony + MAST (FindMarkers) + Monocle2 + homologene (14,034同源基因)
- **发现**:
  - 共享: Cell_APOE/Apoe比例随年龄上升方向一致；Cell_CX3CR1/Cx3cr1稳定
  - 差异: 人类特异IL1RAPL1/SPP1亚群在小鼠中不存在；衰老DEG变化方向相反
  - 结论: 小鼠不能完全替代人类，但在特定共享通路上有替代价值
- **局限性**: 仅小胶质细胞；仅定性比较；无量化评分系统；无预测模型

### 2. Wang et al. 2025, Genome Medicine (PMID: 40296047)
- **DOI**: 10.1186/s13073-025-01469-x
- **文件**: `10.1186_s13073-025-01469-x.pdf` (13.6 MB)
- **提取**: ✅ 140,028 chars, 2,514 lines — 全文完整提取
- **主题**: 恒河猴10脑区 snRNA-seq 衰老图谱 (~330,000 nuclei)
- **核心方法参数**:
  - Seurat v4.0.2, STAR v2.7.9a, Mmul_10 (Ensembl v102)
  - QC: nGene≥500, nUMI≥1000, MT%≤10%, UMI/gene≥1.2, DoubletFinder 10%
  - NormalizeData + ScaleData (regress: sex+UMI+MT%+CC.differences) + RunHarmony
  - FindAllMarkers(MAST), min.pct≥25%, Bonf.P<0.05, avgFC≥1.5
  - CellChat v2.1.2 (CellChatDB.human, ~3300互作对)
  - clusterProfiler v4.0.5, org.Hs.eg.db

### 3. Wang et al. 2022, Cell Research (PMID: 35750757)
- **DOI**: 10.1038/s41422-022-00678-y
- **文件**: `10.1038_s41422-022-00678-y.pdf` (2.5 MB)
- **提取**: ⚠️ **图片式PDF** — 正文为扫描图像, PyMuPDF仅提取528字节(附图说明)
- **主题**: 猴全生命周期海马神经发生 + 老年人类海马对比
- **回退**: 需手动从 EuropePMC HTML 提取方��参数

## ❌ 未下载（Cloudflare/付费墙拦截）

### 4. Franjic et al. 2022, Neuron (PMID: 34798047)
- **DOI**: 10.1016/j.neuron.2021.10.036
- **状态**: ❌ PDF Cloudflare拦截；✅ HTML全文已获取(28KB) via EuropePMC
- **主题**: 人/猴/猪海马+内嗅皮层细胞类型跨物种分类
- **重要**: 258引用, 直接跨物种比较框架

### 5. Xiong et al. 2025, Mol Biol Evol (PMID: 40036868)
- **主题**: 树鼩跨物种海马衰老

### 6. Ma et al. 2022, Science (PMID: 36007006)
- **主题**: 灵长类前额叶皮层细胞类型进化

### 7. Sun et al. 2025, Neuron (PMID: 39788089)
- **主题**: 脑衰老单细胞综述

## 📊 提取参数汇总（Wang 2025 Genome Med — 最完整）

| 参数类别 | 具体参数 | 值 |
|---------|---------|-----|
| QC | min_genes | ≥ 500 |
| QC | min_UMI | ≥ 1,000 |
| QC | MT%上限 | ≤ 10% |
| QC | UMI/gene ratio | ≥ 1.2 |
| QC | 双细胞率 | DoubletFinder 10% |
| 归一化 | 方法 | NormalizeData (LogNormalize) |
| 批次校正 | 方法 | RunHarmony (按个体) |
| 降维 | PCA → Harmony → UMAP | 默认参数 |
| 聚类 | 工具 | FindNeighbors + FindClusters (Seurat v4) |
| Marker | 方法 | FindAllMarkers(MAST test) |
| Marker | 阈值 | min.pct≥25%, Bonf.P<0.05, avgFC≥1.5 |
| 跨物种 | 基因映射 | BioMart (Ensembl v102) 一对一orthologs |
| 细胞通讯 | 工具 | CellChat v2.1.2, CellChatDB.human |
| 衰老DEG | 方法 | MAST, 协变量: UMI+CC.differences+sex |
| 组成分析 | 方法 | 线性回归, sex协变量, P<0.05 |
| 富集 | 工具 | clusterProfiler v4.0.5 |

## 💡 跨物种比较方法论对比

| 维度 | He 2024 (鼠→人) | 本课题方案 (猴→人) |
|------|-----------------|-------------------|
| 评价方式 | 定性描述 | **量化5维度评分 S₁-S₅** |
| 细胞覆盖 | 仅小胶质细胞 | 全海马细胞类型 |
| 预测模型 | ❌ 无 | ✅ XGBoost跨物种预测 |
| 同源基因 | homologene (14,034) | BioMart / babelgene |
| 统计验证 | Pearson + Kruskal-Wallis | 评分 + SHAP + 交叉验证 |

## 🧪 专利策略

- **方向一**: 多维可替代性评分系统 → 发明专利(方法类)
- **方向二**: 跨物种域适应预测模型 → 发明专利(算法类)
- **方向三**: 保守性衰老基因集 → 发明专利(组合物类)
- **验证**: 无需人脑实验, 用GSE278576/GSE199243等公开数据做外部验证

## 📌 关键教训（本Session积累）

1. `download_pdf(doi=...)` **不再可靠**（2026-07-13验证所有DOI均被Cloudflare拦截）
2. `extract_params_from_pdf` 工具路径硬编码错误: 脚本实际在 `hermes_home/skills/bioinformatics/...` 而非 `skills/...`
3. 替代方案: `terminal` 直接运行 `python hermes_home/skills/bioinformatics/literature-param-extraction/scripts/extract_pdf.py`
4. PyMuPDF(fitz) 在 conda 中可用但在 `execute_code` 沙箱中不可用
5. 部分学术PDF为图片扫描版(Wang 2022 Cell Res) → PyMuPDF无法提取文本
6. EuropePMC HTML页面(非PDF)有时可获取 → 可作为回退
7. 手动下载是当前唯一可靠的PDF获取方式
