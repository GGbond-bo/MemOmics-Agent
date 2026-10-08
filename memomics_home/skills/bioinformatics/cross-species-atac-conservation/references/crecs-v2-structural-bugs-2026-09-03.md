# CRECS v2.2 结构性缺陷复盘 + GSE67978 外部验证档案（2026-09-03）

触发场景：用户拍板"先按 1 和 2 做"（① ChIP-seq 外部验证 ② 校准 L3 阈值/缩放因子消 C=0）。
本文档 = v3 校准开发的输入事实集。核心脚本：`E:/专利/P3_L1_data/p4_crecs_v2_2.py`（144 行）。

## 1. 缺陷 1：L3 池级常量 → C 类数学上不可达（C=0 真正根因）

```python
L3_JACC = {'up': 0.213, 'down': 0.034}          # 第 13 行：池级均值常量，非逐 tile Jaccard
l3_score = min(1.0, L3_JACC[direction] * 5)      # 第 81 行
    # up   → min(1.0, 1.065) = 1.0
    # down → min(1.0, 0.17)  = 0.17
crecs = 0.4*l1 + 0.3*l2 + 0.3*l3                  # 第 82 行
if l1_score == 0:            cls = 'D'            # 第 83-84
elif l1==1 and l2>=0.5 and l3<0.5:  cls = 'B'      # 第 85-86
elif crecs >= 0.8:           cls = 'A'            # 第 87-88
else:                        cls = 'C'            # 第 89-90
```

推导（0.213/0.034 来自 l3_topN_motif.R 池级富集 Jaccard，见 L3-B 节）：
- `up & L1=1 & L2≥0.5` → crecs = 0.4+0.15+0.3 = **0.85 ≥ 0.8 → 恒 A**，且 l3=1.0 不落 B
- `down & L1=1` → l3=0.17<0.5 → **恒 B**（l2≥0.5 恒真，见缺陷 2）
- `L1=0` → 恒 D
- **C 分支（l1==1 & l3≥0.5 & crecs<0.8）在所有组合下不可达** → C=0 是逻辑缺陷，不是"阈值下无落点"
- 推论：B 类 364 tiles 全部来自 down 侧（up 0 个）是同一根源的副产物，B 类清单本身被方向截断污染

教训：评分脚本检查时若 `l3_score` 来自 `L3_JACC[direction]` 固定 dict → 池级常量顶替逐 tile 值。
"某类空/某类全单向" → 先查评分来源，不是先调阈值。

## 2. 缺陷 2：L2 染色体命名不匹配 → 静默全 miss（被容错掩码掩盖）

- `monkey_peaks_hg38_map.csv`（289,523 行）`hg38_chr` 列无 `chr` 前缀（`1/2/X`）
- `human_ageDA_all.csv`（5,555,248 行）chr 列带前缀（`chr1/chr2/...`）
- v2.2 `monkey_hit(chrom='chr1', start)` 查 `hg38_hits[('chr1',...)]`（键来自 map 的 '1'）→ 永远 miss
- 证据：`p4_crecs_v2_scores.csv` 第 7 列 m_hit 全 0（1000/1000）
- 容错掩码：`l2_score = 0.5 + 0.5*m_hit` 下限钳制 0.5 → B 类条件 `l2>=0.5` 恒真 → 无报错、自洽、实际失效
- 修复：`ch = ch if ch.startswith('chr') else 'chr'+ch` 统一命名（覆盖检查从 0/1000 → 1000/1000）
- 同 class 教训（已有记录）：L1 全量打分 bg key chr 前缀归一化；criteria：**跨输入源 chr/seqnames 格式绝不能假设一致**

## 3. 锚点平移精度（v3 猴侧同源坐标决策依据）

- 基因锚点映射：289,523 行（hg38 ↔ 猴 NC 坐标，基因 TSS±5kb 窗）
- top500 up/down 1000 tiles：1000/1000 可映射（命名修复后）
- 最近锚点距离：**中位 22,289bp / p25 1,594bp / p75 180,456bp**；<10kb 仅 426/1000；>1Mb 有 22
- 结论：对 500bp tile 的同源序列提取，锚点平移误差过大（>10kb 序列基本不相关）→ **仅作 fallback**，优先 UCSC chain liftover
- 产物：`crecs_tile_hg38_monkey_map.csv`（1000 行：tile_chr/tile_start/monkey_chr/monkey_coord/anchor_dist）

## 4. GSE67978 数据集档案（方案① ChIP-seq 外部验证）

- 全称：Epigenomic annotation of gene regulatory alterations during evolution of the primate brain
- **98 样本 = 人/黑猩猩/恒河猴 × 8 脑区**，H3K27ac ChIP-seq，无海马
  - human：CaudateNucleus 4 / Cerebellum 4 / OccipitalPole 4 / PrecentralGyrus 5 / PrefrontalCortex 3 / Putamen 4 / ThalamicNuclei 3 / WhiteMatter 5
  - chimp：6 脑区 3-6 rep（无 PrefrontalCortex 外的？实测 CaudateNucleus 3/Cerebellum 5/OccipitalPole 3/PrecentralGyrus 3/PrefrontalCortex 6/Putamen 3/ThalamicNuclei 3/WhiteMatter 3）
  - rhesus：8 脑区 4-5 rep
- 每样本 4 文件：`<GSM>_H3K27ac_<Species>_Brain_<Region>_<ID>_{hg38|rheMac3}.bw` + `_peaks.narrowPeak.gz` + `_peaks.txt.gz` + `_treat_pileup.bedgraph.gz`
- 参考基因组：人侧 **hg38**（直接可比 B 类 tiles）；猴侧 **rheMac3**（恒河猴旧组装，≠ 本专利猴数据 T2T-MFA8）
- 组织匹配决策：B 类来自海马 ATAC，GSE67978 无海马 → 选 **CaudateNucleus**（尾状核，端脑内侧，人 4/猴 4 rep 最均衡）折中，报告时标注组织局限
- 元数据解析脚本：`scripts/parse_gse67978_miniml.py` → `gse67978_samples.tsv` + `gse67978_peaks.txt`（320 链接）

## 5. 下载路径经验 + 网络阻塞执行纪律

- **miniml 优先**：`https://ftp.ncbi.nlm.nih.gov/geo/series/GSE67nnn/GSE67978/miniml/GSE67978_family.xml.tgz`（11.4KB gzip ✅）；**SOFT 路径**（`soft/GSE67978_family.soft.gz`）实测返回 990B 非 gzip（疑似 404 页）❌
- samples 路径 urllib 下载（6 文件 × 5 重试）全 **HTTP 502 Bad Gateway**（UA + 指数退避 3/6/12/24/48s 均无效）
- UCSC chain 下载 curl `--max-time 180` 超时 **exit=28**（hgdownload.soe.ucsc.edu 不可达）
- 连续失败 6 次触发系统循环干预 3 次 → **纪律**：下载型任务 2 次尝试全败就停；沉淀 record_error → 汇报阻塞 + 替代路径（换域名/换源/零网络/交用户）→ 有离线主线先推进
- 零网络可推进主线（本场景）：方案②校准完全离线可用——phyloP 索引（v4/l1_full_human.csv 本地）、锚点映射（本地）、双物种 DA 网格（本地）、BSgenome 人序列（本地）

## 6. v3 校准方向（用户待拍板方案 A）

1. L3 从池级常量 → 逐 tile 连续变量（金标准 motif Jaccard 需 chain；零网络替代 = phyloP 连续 p100_mean + 修复后猴 DA 命中 + 效应量 r 的保守代理）
2. 去 `min(1.0, J*5)` 截断，保留连续值
3. 双阈值/分位数定义 A/B/C/D（C=中间态自然非空）
4. L2 用命名修复后的真实 m_hit（不再恒 0）
5. 已知阳性/阴性增强子校准：外部 ChIP-seq（GSE67978，网络恢复后）或 ENCODE cCRE；内部 A/D 类作基线对照
- ⚠️ 语义取舍必须向用户明示：L3 用保守代理时，专利用语从"TF 结合 Jaccard"调整为"保守活性代理"，不能混写