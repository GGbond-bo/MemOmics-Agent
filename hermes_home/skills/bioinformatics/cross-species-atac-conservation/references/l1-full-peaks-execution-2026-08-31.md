# L1 全量 peaks 打分执行记录（2026-08-31）

## 场景

用户给了 `human_Hf_peaks.csv`（525,137 peaks）/ `monkey_Hf_peaks.csv`（538,420 peaks，
均为 chr/start/end 三列），质疑"不是两个文件就行了吗？为什么又要 peak matrix？"
→ 确认 L1 只需 peaks.csv，马上全量打分，不再索要任何文件。

## 关键纠正（用户当场抓包）

- Agent 一度要求 PeakMatrix（想重跑"四组 DA"）→ 这是把 L2 层（可及性保守）的需求混入 L1
- L1 序列保守性是**区域属性**：同一 peak 对所有样本/年龄组 phyloP 分数相同 → L1 本身不分组
- "四组比较"只能落在四组各自的 DA 区域（L2/DA 层），与 L1 输入无关
- 铁律：用户给了 peaks.csv 要 L1 → 立即开跑，不要索要额外文件

## 旧产物隔离（用户要求"不要让以前的东西污染现在的分析"）

```bash
cd /e/专利/P3_L1_data && mkdir -p archive_old_da_v1
mv macaque_da_strict_Old.csv macaque_da_strict_Young.csv macaque_da_loose_Old.csv \
   macaque_da_loose_Young.csv l1_seq_scores.csv human_da_Old_phylop.tsv human_da_Young_phylop.tsv \
   l1_phylop_results.csv l1_phylop_local_results.csv test5_phylop.tsv macaque_da_gene_map.csv \
   macaque_human_orthologs.csv human_ortholog_hg38.csv p4_crecs_scores.csv l2_accessibility_scores.csv \
   l3_motif_topTF.csv archive_old_da_v1/
```

注意：`P1_da_young_old.R` 本身在全盘（E:/专利、E:/MemOmics-Agent、D盘）不存在——可能是集群脚本或从未落盘本地；归档其 CSV 产物即可，并在答复中如实说明。

## 全量打分脚本

`E:/专利/P3_L1_data/l1_full_peaks_human.py`（WSL Ubuntu 26.04 + apt python3-pybigwig 0.3.25）：

- 输入：`human_Hf_peaks.csv`（hg38 坐标，直接匹配轨道）
- 三轨道：`hg38.phyloP100way.bw` / `hg38.phyloP30way.bw` / `hg38.phastCons100way.bw`（E:/专利/L1_resources/，23GB 已落盘）
- 每 chromosome 随机采样 200×5kb 窗口做背景零模型 → `p100_bg_pct`（相对背景百分位）
- phastCons 元件判定：posterior>0.5 碱基占比 ≥50% = `conserved_pc=Y`
- NaN 缺口处理：`np.isnan(vals).mean() > 0.2 → None`，缺口小用 `np.nanmean`
- 输出：`v3/l1_full_human.csv`，每 5 万行打印进度

实测速度：0.3ms/peak → 52.5万 peaks × 3 轨道 ≈ 9 分钟。

## 启动方式

```bash
cd /e/专利/P3_L1_data && \
wsl.exe -d Ubuntu -u root -- bash -lc "cd /mnt/e/专利/P3_L1_data && python3 l1_full_peaks_human.py" \
  # terminal(background=True, notify_on_complete=True)
```

## 猴侧

T2T 坐标（NC_088375.1）仍需基因锚定 ortholog 映射（gene_anchor_ortholog.py）后才能用 hg38 轨道打分；
53.8万全量映射策略待定（先评估涉及基因数，见 ortholog-mapping 教训）。

## 方案文档

`E:/专利/P3_L1_data/L1_PROTOCOL_v3.md` — L1 目的/输入/环境/计算方法/步骤/输出，用户要求"做好步骤记录，容易复用和复现"。