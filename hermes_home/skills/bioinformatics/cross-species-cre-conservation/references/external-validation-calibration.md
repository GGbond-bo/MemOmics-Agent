# 外部验证数据源 + 阈值校准配方（CRECS v2.2 实证 + v3 修复）

## 场景
CRECS 复合评分的 L3（TF 结合保守）用方向级 Jaccard × 固定缩放因子 + 固定阈值评分时，
出现 C=0 / B 全在一个方向 / 99.4% 同一类的"分布假象"。两条修复路径：
- **路径 1（外部验证）**：公共 ChIP-seq 数据直接检验预测层 claims
- **路径 2（阈值校准）**：参考集校准 L3 阈值与缩放因子，消除人为常数
- **路径 3（v3 实测，最强）**：直接用真实 H3K27ac 峰逐 tile 命中替换池级常量（见下）

## 外部验证数据源（脑区 H3K27ac ChIP-seq）

### GSE67978 — 首选（人/猴/猩猩同源增强子直接比较金标准）
- 标题: Epigenomic annotation of gene regulatory alterations during evolution of the primate brain
- 文献: Vermunt et al. 2016, Nat Neurosci (PMID 26807951)
- 设计: **8 个成人脑区 × 3 物种**；人 3 生物学重复/区、黑猩猩 2、恒河猴 3 → 98 样本
- **2026-09-03 实证修正**：解析 98 样本后**无海马**（8 脑区含尾状核 CaudateNucleus 等）；人侧文件为 **hg38**、猴侧为 **rheMac3**（不是 hg19！）→ 人侧可直接交叉，猴侧需 `rheMac3ToHg38.over.chain.gz`（`https://hgdownload.soe.ucsc.edu/goldenPath/rheMac3/liftOver/rheMac3ToHg38.over.chain.gz`；本地验证 36.2MB / 13.6M 行，from=rheMac3 chr1 229.6Mb to=hg38 chr1 248.96Mb）
- 适用: 人 vs 恒河猴同源增强子 H3K27ac 活性直接比较（尾状核等脑区）；跨组织借用（如海马 tiles vs 尾状核 peaks）只能写"脑区保守性提示"，不能写"海马已证实"
- 下载: GEO 系列页 → 每 GSM 的 supplementary peak（`https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM1660nnn/<GSM>/suppl/<GSM>_*_peaks.narrowPeak.gz`）

### GSE40465 — 补充（人脑增强子图谱）
- 标题: Large-Scale Identification of Coregulated Enhancer Networks in the Adult Human Brain
- 文献: Vermunt et al./2014 (PMID 25373911)；87 个解剖区域、151 样本 H3K27ac
- 适用: 人侧海马/脑区 H3K27ac 增强子活性验证

### 其他候选
- GSE158931: 人/黑猩猩/恒河猴皮层神经元（谷氨酸能/ GABA 能）H3K27ac，细胞类型分辨率（PMID 32214253 同领域）
- GSM1660027: 恒河猴前额叶皮层 H3K27ac（属 GSE67978）

## GEO 下载小技巧
- miniml FTP 路径 `https://ftp.ncbi.nlm.nih.gov/geo/series/GSE67nnn/<ACC>/miniml/<ACC>_family.soft.gz`
  可能 404（990B 非 gzip 错误页）→ 改用 web 端批量抓 GSM 详情块：
  `https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=<ACC>&targ=gsm&form=text&view=quick`
  然后 grep `!Sample_title|!Sample_source_name|!Sample_organism|supplementary_file`
- **批量下载被拦（curl/python 连续 502/timeout）时**：停止重试，把精确 per-GSM 链接列表给用户手动浏览器下载 → 验证 gzip 完整性 + **从文件名确认组装版本**（不要假设 hg19）后再分析。2026-09-03 实证：NCBI https 全 502、UCSC 超时，改为用户手动下载一次成功。

## 阈值校准配方（修复 C=0 缩放陷阱）

### 陷阱复现（诊断法）
```python
l3_score = min(1.0, JACC[dir] * 5)   # up=0.213, down=0.034（真实 Jaccard）
# up: 0.213*5=1.065 → min → 恒 1.0 ≥ 0.5 → 永落 A/D，永不 B
# down: 0.034*5=0.17  < 0.5 → 恒落 B（l1=1 时）
# 结论: 分类完全由缩放因子决定；C=0 是数学必然非生物学
```

### 校准步骤（路径 2）
1. **阳性参考集**: GSE67978 人 H3K27ac peaks（真增强子，需先确认组装版本）
2. **阴性参考集**: 随机基因组 tile，按阳性集染色体分布抽样 + GC 分布匹配（复用
   `l3_topN_motif.R` 的 `mk_bg()`，n=2000, seed=42）
3. **L3 分布计算**: 对两组分别跑 motif 富集（matchMotifs → fg_mean/bg_mean → fc 排序，
   见 results/memomics-cd677556/scripts/l3_topN_motif.R），得到两组 fc 分布
4. **阈值选择**: ROC（阳性 vs 阴性）或 Youden J 最大化 → 数据驱动阈值
   （替代人为 0.5）；缩放因子同理从分布分位数反推（替代人为 ×5）
5. **重算分类**: A/B/C/D 四分类；预期恢复中间态 C

## v3 实测修复（路径 3，2026-09-03 后半程，产物已落盘）

比 ROC 校准更直接：**用真实 H3K27ac 峰逐 tile 命中替换池级 Jaccard 常量**。B 类从 364（伪实证）→ 49（真实证据）。

```python
# 分类规则（v3.1）:
#   D: l1=0（不保守）
#   B: h3k_m=1 & h3k_h=0   # 保守 + 猴活性保留 + 人活性失去
#   A: h3k_h=1 & h3k_m=1   # 保守 + 双活性保留
#   C: 其余                 # 中间态（h3k_h=1&h3k_m=0 或双 0，但保守）
```

### 输入与结果
- 人侧 GSM1660034/35/36（hg38，48,706/23,271/51,309 peaks）——无需 liftover
- 猴侧 GSM1660010/11/12（rheMac3，38,063/31,621/61,674 peaks）→ rheMac3ToHg38 chain
  （midpoint 转换 + half 扩展；成功 127,469/131,358 = 97%）
- 新分类: **A=47（人 100%/猴 100%）B=49（人 0%/猴 100%）C=450（人 6.4%/猴 0%）D=454**
- B 类语义 = "人类谱系中活性丧失的保守增强子候选"（保守 + 人活性失去 + 猴活性保留）——
  可直接进专利实施例，且比 v2.2 的 B（364 个池级常量伪实证）可信得多
- 产物: `E:/专利/P3_L1_data/p4_crecs_v3_scores.csv`（含 class31）/ `p4_crecs_v3_summary.csv` / `p4_crecs_v3.py`

### v3 附带教训（比阈值本身更重要）
- ⚠️ **锚点平移表（gene-anchor 5kb 窗）与 500bp tile 网格 start 不对齐** → set 精确匹配必 0，
  不是 chr 前缀问题（修前缀 272,307 锚点加载后 `da_m` 仍全 0）。tile 级命中必须用真实实验峰
  + 区间重叠（bisect ± 重叠判定），别用锚点平移。
- ⚠️ **B 类定义强制 h3k_m=1 & h3k_h=0 时，人 vs 猴 Fisher 必然显著（p~1e-29）——定义自证，
  不是独立验证**。独立验证须用不同于分类依据的第三数据源（footprint / 不同脑区 / 不同 assay）。
- ⚠️ **跨组织借用**：海马 tiles vs 尾状核 peaks，且 GSE67978 无年龄分层 → 专利措辞限
  "候选/提示/脑区保守性提示"，禁写"已证实 TF 结合差异"（与辩论裁决 need_more_info 一致）。

### 关键产物路径（本会话参考）
- `E:/专利/P3_L1_data/p4_crecs_v2_scores.csv` — CRECS v2.2 输出（chr,start,direction,r,phyloP_nearest,m_hit,l1,l2,l3,crecs,class）
- `E:/专利/P3_L1_data/p4_crecs_v2_2.py` — v2.2 评分脚本（含 l3_score 缩放逻辑）
- `E:/专利/P3_L1_data/p4_crecs_v3.py` + `p4_crecs_v3_scores.csv` — v3 修复版（真实 H3K27ac 命中）
- `E:/专利/rheMac3ToHg38.over.chain.gz` — 猴→人 chain（用户手动下载，已验证）
- `E:/专利/P3_L1_data/gse67978/peaks/GSM16600{34,35,36}_..._hg38_peaks.narrowPeak.gz` + `GSM16600{10,11,12}_..._rheMac3_peaks.narrowPeak.gz`
- `E:/MemOmics-Agent/results/memomics-cd677556/scripts/l3_topN_motif.R` — motif 富集框架（校准直接复用）

## 辩论裁决口径（外部验证后措辞）
- L3 预测层证据（motif 富集/Jaccard）→ 专利措辞限"候选/提示"，禁写"已证实 TF 结合"；
  ChIP-seq/footprint 重叠阳性才可升级为"增强子活性直接证据"
- 外部验证的 Fisher 检验（B 类 vs A/D 的 ChIP 重叠率）是"直接证据"层的关键输出；
  但当分类本身就用同一 ChIP 数据定义时，Fisher 是自证——需第三数据源独立验证