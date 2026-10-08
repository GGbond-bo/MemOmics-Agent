# 案例：MEF2C / MEF2C-AS1 read 归属质疑（2026-10-01 实测）

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
```

产出：`results/44_mef2c_locus_stats.csv`、`results/44b_overlap_decomposition.csv`、
`figures/44_MEF2C_locus_from_GTF.{png,svg,pdf}`、`figures/44b_MEF2C_AS1_overlap_decomposition.{png,svg,pdf}`

## 三、自身数据的交叉一致性反证（最有说服力的一条）

同一张 DEG 表（`DEG_fdr05_coef025_5contrasts_formatted.xlsx`）里两个基因的行为**完全相反**：

| 对比 | 亚群 | MEF2C-AS1 coef | FDR | 方向 |
|---|---|---|---|---|
| O_EX | Pure Type IIA | 0.709 | ~0 | Post > Pre ↑ |
| O_EX | Pure Type I | 0.491 | ~0 | Post > Pre ↑ |
| O_EX | OTUD1+(II) | 0.722 | ~0 | Post > Pre ↑ |
| DM_EX | Pure Type I | 0.440 | ~0 | Post > Pre ↑ |
| DM_EX | Pure Type IIA | 0.333 | ~0 | Post > Pre ↑ |
| DM_EX | LRP1B+(I) | 0.423 | 3.9e-217 | Post > Pre ↑ |
| Y_EX | Pure Type IIX | 0.275 | 1.9e-38 | Post > Pre ↑ |

而 **MEF2C 在所有 contrast / 亚群里都没过阈**（FDR 不显著或 |coef| < 0.25）。

→ **若两者共享 counts，应当同向同幅度；实测一个显著上调、一个纹丝不动 = 反证归属是干净的。**
（注意：过滤后的表里查不到某基因 ≠ 未检出 —— MEF2C 之所以缺席是**被阈值剔除**，要去未过滤表/raw counts 查。）

## 四、给合作者的英文回信骨架（数字均已核实，可直接改）

> **Where the overlap is.** The two genes are transcribed head-to-head from opposite strands at their 5′ ends.
> MEF2C is on the minus strand (chr5:88,717,117–88,904,257) and MEF2C-AS1 on the plus strand
> (chr5:88,883,328–89,466,398). Their **gene spans** overlap over **20,930 bp** (chr5:88,883,328–88,904,257);
> their 3′ ends are ~750 kb apart.
>
> **Why the overlap doesn't mix the reads.** (1) UMI counting only operates on **exons** — the span overlap is almost
> entirely intronic. Decomposed at exon level, the actual overlapping sequence is only **422 bp across 3 short blocks**
> (88,883,328–88,883,466; 88,889,308–88,889,324; 88,903,938–88,904,203) ≈ **2% of the span overlap**; the remaining
> ~20.5 kb sits in introns/intergenic space and is never counted. (2) The two genes are on **opposite strands**.
>
> **We can also verify this empirically in our own data.** MEF2C-AS1 is quantified independently and is strongly
> **upregulated after exercise** in several subclusters (Pure Type IIA coef 0.71, FDR ≈ 0; Pure Type I coef 0.49, FDR ≈ 0;
> OTUD1+(II) coef 0.72, FDR ≈ 0; Y_EX Pure Type IIX coef 0.28, FDR 1.9e-38), whereas MEF2C itself stays below
> threshold in every contrast. If the two genes were sharing counts, they would move together — they don't.
>
> I can send the locus figure generated directly from GENCODE v32 showing both gene models, their strand directions,
> and the exon-level decomposition of the overlap.

## 五、回信纪律

- **不要提议跑 ATAC 来回答这个问题**：ATAC 无 read→基因归属信息。ATAC 只能回答另一个问题（该位点运动后是否变开放）。
- 链特异性可以提，但**别当唯一论据**（会被追问到具体 Cell Ranger 版本的 ambiguous UMI 规则，需查官方文档）。
- 回信必带数字：span bp / exon bp / 段数 / 百分比 / 坐标区间。
- 生物学侧（MEF2C 过表达 → IIX→IIA 慢氧化表型）的证据链：PMID 10790363（MEF2 受钙信号调控肌纤维类型）、
  MEF2C-AS1 调控 MEF2C 的文献（PMID 36198203 等）。引用前用 `bioinformatics-fact-retrieval` 核验 PMID/DOI。