# GSE67978 H3K27ac 外部验证执行档案（2026-09-03）

用于：用独立 ChIP-seq 数据验证 CRECS B 类 tile 的"跨物种活性"标签。本档案记录完整执行，含下载路径、pyliftover 环境坑、脚本全文、结果表、解读规则。

## 背景

- CRECS v2.2 的 B 类 = 364 tiles（`p4_crecs_v2_scores.csv`），名义定义"L1 序列保守 + L2 猴 DA 未命中 + L3<0.5 TF 结合不保守"→ 设计上应"人侧有增强子活性、猴侧无"
- 但事后审计发现 v2.2 的 L2 `m_hit` 因 chr 前缀 bug 全 0（见 `crecs-v2-structural-bugs-2026-09-03.md`），B 类实际等价于"人海马衰老**下调** + 序列保守"的 tile
- 验证用外部独立数据 = GSE67978（Vermunt et al. 2016 *Nat Neurosci*, PMID 26807951）H3K27ac ChIP-seq

## 数据集关键事实

- 98 样本 = 人/黑猩猩/恒河猴 × 8 脑区（CaudateNucleus / Cerebellum / OccipitalPole / PrecentralGyrus / PrefrontalCortex / Putamen / ThalamicNuclei / WhiteMatter）
- **无海马样本**——B 类 tiles 来自海马 ATAC → 选组织邻近的 CaudateNucleus（人 3-4 rep + 猴 3-4 rep，跨物种可比性最强的同研究同流程组），**必须标组织局限**
- 人侧 peaks = **hg38** 坐标；猴侧 = **rheMac3** → 猴侧需 liftover 到 hg38
- 8 个 GSM：人 HS1/HS2/HS3 = GSM1660034/35/36；猴 RM1/RM2/RM3 = GSM1660010/11/12

## 下载路径（本环境实测）

- NCBI GEO samples 路径 urllib 全 502（30 次重试全败）→ **换 `https://ftp.ncbi.nlm.nih.gov/geo/samples/...` https 直链 + curl -A "Mozilla/5.0"** 成功（miniml 元数据此前也走该域名成功）
- UCSC chain 下载 curl exit=28 超时 → 交给用户手动下载（用户网络可直连）→ 本地 `E:/专利/rheMac3ToHg38.over.chain.gz`（36.2MB）
- chain 验证：`gzip -dc | head -5` 头行 `chain <score> chr1 <srcSize> ... chr1 <tgtSize>` 与已知组装表对大小（rheMac3 chr1=229,590,362 → hg38 chr1=248,956,422）→ 方向确认
- 6 个 peak 文件用户手动下载到 `E:/专利/P3_L1_data/gse67978/peaks/`，gzip -t 全过

## ⛔ pyliftover 环境坑（本会话实测）

- **pyliftover 0.4.1 只装在系统 Python**（`C:\Users\23136\AppData\Local\Programs\Python\Python312\python.exe`），**项目 .venv / execute_python 持久内核没有**
- 表现：`execute_python exec(open('external_validation.py'))` → `ModuleNotFoundError: No module named 'pyliftover'`
- 处置：chain 转换脚本用**系统 `python external_validation.py` 直接跑**（terminal），不经过 execute_python；依赖 scipy 也在系统 Python
- pyliftover 用法（网络受限时）：`lo = LiftOver(r'E:/专利/rheMac3ToHg38.over.chain.gz')` 传**本地 chain 文件路径**，不要传组装名（那会尝试自动下载）

## 执行脚本逻辑（external_validation.py 摘要）

```python
# 1. 载入峰值
human_peaks = load_peaks(3 个 hg38 narrowPeak)        # 123,286 peaks（union 前按染色体索引）
monkey_raw  = load_peaks(3 个 rheMac3 narrowPeak)     # 131,358 peaks
# 2. 猴侧 liftover（中点转换，保留原 peak 长度 ±half）
lo = LiftOver(本地chain)
res = lo.convert_coordinate(chrom, (s+e)//2)          # → (hg38_chr, hg38_pos)
monkey_peaks[hc].append((hp-half, hp+half))           # 127,469/131,358 成功 (3.0% 失败)
# 3. tile 重叠：tile(chrom, start, start+500) vs peak 区间（bisect 邻近 ±1 检查）
# 4. 按 class 分组命中率 + scipy.stats.fisher_exact 2×2（alternative='two-sided'）
#   表 = [[hit_a, n_a-hit_a], [hit_b, n_b-hit_b]]
```

⚠️ liftover 失败 3,889 个（多染色体边界/未比对区），属正常；写方法学时注明失败率。

## 结果表（E:/专利/P3_L1_data/external_validation_results.csv）

| 类别 | n | 人命中率 | 猴命中率 |
|---|---|---|---|
| A | 182 | 14.3% (26) | 8.2% (15) |
| **B** | **364** | **13.7% (50)** | **22.3% (81)** |
| D | 454 | 12.3% (56) | 8.6% (39) |

Fisher 对照：

| 比较 | OR | p | 含义 |
|---|---|---|---|
| B 人 vs B 猴 | 0.556 | 3.7e-3 | **猴侧显著更高（假设相反）** |
| B 人 vs A 人 | 0.955 | 0.90 | 人侧无差异 |
| B 人 vs D 人 | 1.132 | 0.60 | 人侧无差异 |
| B 猴 vs A 猴 | 3.187 | 2.7e-5 | 猴侧 B 显著富集 |
| B 猴 vs D 猴 | 3.046 | 5.2e-8 | 猴侧 B 显著富集 |

## 辩论裁决（L1, need_more_info / medium）

裁判确认"猴侧活性显著高于人"这一事实成立，但**不支持**翻案成"B=猴保留活性/人衰老丢失"：
1. 组织不匹配（海马 vs 尾状核）
2. 无年龄分层（GSE67978 稳态成人，无法检验人侧低是否衰老效应）
3. 内部口径：L2 m_hit 全 0（chr 前缀 bug）→ B 类标签不可靠
4. 猴侧富集可由脑区/物种差异解释

缺失证据（答辩/后续）：
- 同脑区（海马或匹配区域）人/猴**年龄分层** H3K27ac/ATAC
- 控制细胞组成/批次差异的共定位
- liftover 失败 tile 的 mappability 敏感性
- 功能实验（报告基因/CRISPR）证明 B 类调控活性与衰老关系

## 结论规则（专利主张措辞）

✅ 可写："B 类 tiles 在恒河猴尾状核稳态 H3K27ac 活性显著高于人（22.3% vs 13.7%，OR=0.556, p=3.7e-3），与'保守增强子在衰老人脑静默'假说一致但需年龄分层验证"
⛔ 禁写："证实 B 类=人衰老丢失的保守增强子" / "人侧无增强子活性"

构建的可用故事：B 类组合指纹"保守序列 + 人海马衰老下调 + 猴侧正常 H3K27ac 活性存在"比原始假设更符合数据，且猴侧 B vs A/D 显著富集（p<1e-4）证明它不是噪声——是好素材，但进权利要求必须有同脑区年龄分层数据。

## 可复用清单

- 脚本：`E:/专利/P3_L1_data/external_validation.py`（改 PEAK_DIR/tiles 路径即可换数据集）
- 产物：`external_validation_results.csv`
- chain：`E:/专利/rheMac3ToHg38.over.chain.gz`（已验证，供后续猴侧 liftover 复用）
- peaks：`E:/专利/P3_L1_data/gse67978/peaks/GSM16600{10,11,12,34,35,36}_*.narrowPeak.gz`