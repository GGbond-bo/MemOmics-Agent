# L1 本地 bigWig 批量打分执行记录（2026-08-31）

## 背景
- P3-L1 序列保守性评估：猴 DA tiles（T2T-MFA8v1.1）→ 基因锚定 → 人类 ortholog → hg38 坐标 → phyloP100way 打分。
- 历史（08-09）走 UCSC REST API 逐点查询（慢、限速、易超时），40 区域 20-40min。
- 08-30/31 装好 WSL + Ubuntu 26.04（E盘）+ apt `python3-pybigwig`，bigWig 本地落盘 `E:/专利/L1_resources/`。
- 本次用本地 pyBigWig 重跑全部 40 tiles（秒级、无网络依赖）。

## 关键文件
| 文件 | 说明 |
|------|------|
| `E:/专利/P3_L1_data/l1_seq_scores.csv` | 40 个 DA tiles（含 group/human_gene/hg38_chr/hg38_start/hg38_end）|
| `E:/专利/P3_L1_data/macaque_da_gene_map.csv` | tile → 猴基因 gene_start/gene_end（119 行全 DA tiles）|
| `E:/专利/L1_resources/hg38.phyloP100way.bw` | 9.2GB 本地轨道 |
| `E:/专利/P3_L1_data/l1_phylop_local.py` | 本地打分脚本（写入）|
| `E:/专利/P3_L1_data/l1_phylop_local_results.csv` | 输出：40 行 × 10 列 |
| `E:/专利/P3_L1_data/figures/l1_phylop_conservation.png` | 双面板图 |

## 脚本核心逻辑（pyBigWig 版，与 v3 frac 映射一致）
```python
import pyBigWig, csv
bw = pyBigWig.open('/mnt/e/专利/L1_resources/hg38.phyloP100way.bw')
# 对每行：frac = (tile_start - m_gs) / (m_ge - m_gs)
# h_pos = h_start + frac*(h_end - h_start)；min/max 归一化（负链基因 start>end）
# 窗口 [h_pos-2500, h_pos+2500]；bw.values(f"chr{hg38_chr}", w_start, w_end, numpy=True)
# phylop_mean = mean(vals)；conserved = mean > 0
bw.close()
```

## 运行
```bash
# Windows bash
wsl.exe -d Ubuntu -u root -- bash -lc "cd /mnt/e/专利/P3_L1_data && python3 l1_phylop_local.py"
```

## 结果（40/40 成功，NA=0）
- 保守 28/40（70%）；Old 10/18 = 55.6%；Young 18/22 = 81.8%
- Fisher 双侧 p = 0.088（未达显著）
- 输出列：chrom, tile_start, group, human_gene, hg38_chr, hg38_start, hg38_end, phylop_mean, n_bins, conserved

## 辩论裁决摘要（L1 轻量，2026-08-31，已 record_verdict）
- verdict: `need_more_info`，confidence: `low`
- 正方：方向支持结论（Old 55.6% vs Young 81.8%），40 tiles 全查询成功
- 反方/裁判：
  1. Fisher p=0.088 > 0.05 → 不能声称"显著低于"，只能趋势
  2. phyloP mean>0 二值化缺乏先验阈值/功能支撑（连续分数更稳）
  3. 119→71→40 样本筛选显著缩小功效
  4. 人 phyloP100way 用于猴 CRE → 跨物种比对偏差（谱系特异 indel/重排）
  5. frac 相对位置映射假设 CRE 在直系同源基因内位置守恒，5kb 窗口不一定对应同一调控元件
- missing（补强方向）：ortholog 映射 QC、连续 phyloP 分数、功效分析/置换检验、ENCODE cCRE 等外部验证、批次/混杂控制

## 结论表述铁律（本项目反复教训）
- 小样本 L1 信号一律标注"初步/趋势"，正式版全量复现后才能升格为结论
- 与 08-09 "人侧全量验证推翻"教训同源：基因锚定小样本 Young 保守率（77.3%）曾被推翻，本次本地版（81.8%）依然是同一批 40 tiles——读法更准，但统计功效未变（p=0.088）
- 写专利/论文只能写："Old 组 DA CREs 序列保守率呈下降趋势（55.6% vs 81.8%，Fisher p=0.088，未达显著）"