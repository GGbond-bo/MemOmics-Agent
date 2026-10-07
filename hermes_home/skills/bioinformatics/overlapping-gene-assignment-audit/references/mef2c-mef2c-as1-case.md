# 案例：MEF2C / MEF2C-AS1 read 归属质疑（2026-10-01 实测）

> 原属 skill `overlapping-gene-read-assignment`，2026-10-01 合并进本 skill（两者内容重叠，保留本 skill 为唯一入口）。

人类骨骼肌 snRNA-seq（48 样本 6 组 Y/O/OD × Pre/Post，10 亚群），
DEG = 亚群内细胞级 glmer（coef 阈 0.25 + FDR），5 个 contrast。
合作者（PI 侧）对「MEF2C 运动后无显著变化」的结论提出两层质疑：
①生物学上「抑制 MEF2C 说不通，我预期是相反的」；②方法学上「reads 落在重叠区，你怎么区分 MEF2C vs MEF2C-AS1」。

## 一、坐标事实（GENCODE v32 / GRCh38，从 GTF 直接解析）

| 基因 | 链 | 坐标 | biotype | 跨度 | 转录本 | 外显子记录 | 合并外显子块 | 合并外显子 bp |
|---|---|---|---|---|---|---|---|---|
| MEF2C | chr5 **−** | 88,717,117–88,904,257 | protein_coding | 187,141 bp | 56 | 331 | 36 | 11,755 |
| MEF2C-AS1 | chr5 **+** | 88,883,328–89,466,398 | lncRNA | 583,071 bp | 15 | 62 | 22 | 7,865 |

- **5′ 端相向（head-to-head）**：MEF2C 5′ = 88,904,257（负链），MEF2C-AS1 5′ = 88,883,328（正链）→ 相距 **20,930 bp**
- **3′ 端相距 ≈ 750 kb**（89,466,398 − 88,717,117 = 749,281 bp）
- `gene_type "lncRNA"` = GTF 官方盖章 MEF2C-AS1 非编码（**不需要 FASTA 做 ORF 扫描**）

## 二、重叠拆解（决定性数字）

```
gene_span_overlap   = 20,930 bp   in 1 segment   (chr5:88,883,328-88,904,257)
exon_level_overlap  =    422 bp   in 3 segments  (88,883,328-88,883,466; 88,889,308-88,889,324; 88,903,938-88,904,203)
exon_overlap_pct_of_span = 2.02 %
intronic_or_between = 20,508 bp   (标准 UMI 流程不计数)
exon_overlap_pct_of_MEF2C_exons = 3.59 %
```

产出：`results/44_mef2c_locus_stats.csv`、`results/44b_overlap_decomposition.csv`、
`figures/44_MEF2C_locus_from_GTF.{png,svg,pdf}`、`figures/44b_MEF2C_AS1_overlap_decomposition.{png,svg,pdf}`

**审计包**（`results/44c_MEF2C_AS1_audit/`，16 个文件）：`MEF2C_span.bed` / `MEF2C_exons_merged.bed` /
`MEF2C-AS1_span.bed` / `MEF2C-AS1_exons_merged.bed` / `overlap_gene_span.bed` / `overlap_exons.bed` /
`audit_summary.csv` / `verify.sh`（自带断言，bedtools 缺省走纯 awk 兜底）/ `README.md`（英文，含逐步复现 + 诚实边界）。
4 格式索引图：`figures/44d_MEF2C_AS1_audit_map.{png,svg,pdf}`（Panel A 全基因座 / B 放大重叠区三红段 / C BED 索引表）。

## 三、自身数据的交叉一致性反证（最有说服力的一条）

同一张 DEG 表（`DEG_fdr05_coef025_5contrasts_formatted.xlsx`，sheet = 5 个 contrast，列名含 `gene/celltype/coef/fdr/direction`）
里两个基因的行为**完全相反**：

| 对比 | 亚群 | MEF2C-AS1 coef | FDR | 方向 |
|---|---|---|---|---|
| O_EX | Pure Type IIA | 0.709 | ~0 | Post > Pre ↑ |
| O_EX | Pure Type I | 0.491 | ~0 | Post > Pre ↑ |
| O_EX | OTUD1+(II) | 0.722 | ~0 | Post > Pre ↑ |
| O_EX | Pure Type IIX | 0.812 | ~0 | Post > Pre ↑ |
| DM_EX | Pure Type I | 0.440 | ~0 | Post > Pre ↑ |
| DM_EX | Pure Type IIA | 0.333 | ~0 | Post > Pre ↑ |
| DM_EX | LRP1B+(I) | 0.423 | 3.9e-217 | Post > Pre ↑ |
| Y_EX | Pure Type IIX | 0.275 | 1.9e-38 | Post > Pre ↑ |

命中亚群数：**O_EX 10 个 / DM_EX 9 个 / Y_EX 1 个**（全部 direction = Up）。

而 **MEF2C 在所有 contrast / 亚群里都没过阈**：`46_MEF2C_logFC_matrix_5contrasts.csv`（10×5 矩阵）
最大 |logFC| **0.45**（Ex_Old / OTUD1+(II)），**最小 FDR 0.333** ⇒ 5 contrast × 10 亚群 = 50 个检验全不显著。

→ **若两者共享 counts，应当同向同幅度；实测一个显著上调、一个纹丝不动 = 反证归属是干净的。**
（注意：过滤后的表里查不到某基因 ≠ 未检出 —— MEF2C 之所以缺席是因为**被阈值剔除**，要去未过滤表/raw counts 查。）

## 四、给合作者的英文回信骨架（数字均已核实，可直接改）

> **Where the overlap is.** The two genes are transcribed head-to-head from opposite strands at their 5′ ends.
> MEF2C is on the minus strand (chr5:88,717,117–88,904,257) and MEF2C-AS1 on the plus strand
> (chr5:88,883,328–89,466,398). Their **gene spans** overlap over **20,930 bp** (chr5:88,883,328–88,904,257);
> their 3′ ends are ~750 kb apart.
>
> **Why the overlap doesn't mix the reads.** (1) UMI counting only operates on **exons** — the span overlap is almost
> entirely intronic. Decomposed at exon level, the actual overlapping sequence is only **422 bp across 3 short blocks**
> (88,883,328–88,883,466; 88,889,308–88,889,324; 88,903,938–88,904,203) ≈ **2.02% of the span overlap**; the remaining
> ~20.5 kb sits in introns/intergenic space and is never counted. (2) The two genes are on **opposite strands**.
>
> **We can also verify this empirically in our own data.** MEF2C-AS1 is quantified independently and is strongly
> **upregulated after exercise** in several subclusters (10 subclusters in the old group, 9 in the diabetic group;
> max coef 0.81, FDR ≈ 0), whereas MEF2C itself stays below threshold in **every** one of the 5 contrasts × 10
> subclusters (max |logFC| 0.45, min FDR 0.33). If the two genes were sharing counts, they would move together —
> they don't.
>
> **What is and isn't established.** What is established here is the annotation geometry and the counting principle.
> Two things still need to be confirmed against the actual pipeline: whether the library is 3′ or 5′, and the
> strandedness settings used for quantification (`--soloStrand` / featureCounts `-s` / whether `--include-introns`
> was on). Once those are confirmed I'll send a measured version on top of this.
>
> The figure is derived directly from GENCODE v32 (GRCh38). I also put together an **audit pack** (BED files +
> a single `verify.sh` command) so that you or your bioinformatician can **reproduce every number above in one
> command — no need to take my word for it**. If anything doesn't check out, please point it out directly.

## 五、回信纪律

- **不要提议跑 ATAC 来回答这个问题**：ATAC 无 read→基因归属信息。ATAC 只能回答另一个问题（该位点运动后是否变开放）。
- 链特异性可以提，但**别当唯一论据**（会被追问到具体 Cell Ranger 版本的 ambiguous UMI 规则，需查官方文档）。
- 回信必带数字：span bp / exon bp / 段数 / 百分比 / 坐标区间。
- 中英双版 + 附件清单 + 交付卫生 → `references/collaborator-reply-delivery.md`。
- 生物学侧（MEF2C 过表达 → IIX→IIA 慢氧化表型）的证据链：PMID 10790363（MEF2 受钙信号调控肌纤维类型）、
  MEF2C-AS1 调控 MEF2C 的文献（PMID 36198203 等）。引用前用 `bioinformatics-fact-retrieval` 核验 PMID/DOI。