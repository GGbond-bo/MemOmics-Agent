# M2–M3 复现流水线（tile 级 age-DA → 基因级同源锚定 + Stouffer 聚合）

> 适用：用户要自己跑复现（"我自己跑一遍吧"）、核对 M2/M3 阶段代码与产物、或遇到"猴侧 up/down 文件全是空的"疑问。2026-09-11 用户自跑实证。

## M2：tile 级 age-DA（每物种各跑一遍，ArchR getGroupSE）

关键代码要点：
- **`divideN=FALSE` 必须显式**——ArchR 经典坑：默认 `divideN=TRUE` 会把 counts 除以样本数，导致 `rowSums >= 2*ncol(cnt)` 全过滤，tiles 全灭。这是记忆里修复过多次的 bug。
- **坐标在 `rowData(se)` 前 3 列**（ArchR 1.0.3 不填 rowRanges，`rowData(se)` 的 chr/start/end 才是坐标；RowRanges 空是预期）。
- 年龄取**每样本实际年龄值**（不是组均值）做 Pearson；p = `2*pt(-abs(r*sqrt((n-2)/(1-r^2))), n-2)`；q = `p.adjust(p,"fdr")`。
- 防御补丁：① `anyNA(age)` 要 stop（猴侧脚本容易漏，NA 会静默丢行）；② `|r|=1` 时 `1-r^2=0` → t=Inf/NaN，需显式置 Inf。
- 过滤：`keep <- rowSums(cnt) >= 2 * ncol(cnt)`。

实证数字（2026-09-11 用户自跑确认）：
- 人 40 例：过滤后 up=22 / down=28（q<0.1）✅ 与早期实证逐字吻合
- 猴 20 例：过滤后 **up=0 / down=0**（q<0.1 全灭）

## ⚠️ 猴侧 up/down 空 = 正确结果，不是代码错误

- 猴侧 FDR q<0.1=0 是**统计必然**：n=20（自由度 18）+ 全基因组 500 万+ tiles 做全局 BH 校正。用户第一次跑会以为"文件是空的=代码错了"，**先给结论"真实结果非 bug"，再给数学解释**。
- 专利主流程的方向门控 `w(Z₂)` 用的是**名义 p<0.05（未校正）**，不是 q<0.1——猴侧 p<0.05 未校正仍有 31 万 tiles（5.86%），方向信息存在，M3 门控完全可行。
- M2 真正需要的产物是 **all.csv 全表**（r/p/q 全列）供 M3 聚合；up/down 文件对猴侧非必需，空就空，不用重跑。

## tile 宽度实证：500bp（不是 501bp）

- 用户自跑确认列：`seqnames, idx, start`（idx 连续 1/2/3…，start=0/500/1000 → 间隔 500，end=start+499）。
- 这是 **ArchR TileMatrix 默认 500bp 窗口**，不是"501bp（±250 峰中心锚定）"那种理想化表述——两者是不同实现。
- **交底书/说明书写 tile 宽度必须写真实实现（500bp）**；若源数据确证是 500bp 而文档写了 501bp，需改文档（A26.3 精确性）。写文档前先 head 数据文件确认 start 间隔，不要凭"中心锚定惯例"猜。

## M3：基因级同源锚定 + Stouffer 聚合

输入（3 个）：
1. `human_ageDA_all.csv`（~555 万行：chr,start,end,r,p,q）
2. `monkey_ageDA_all.csv`（~529 万行）
3. 同源表 `monkey_human_orthologs_full.csv`（macaque_gene_id → human_gene_id, human_symbol）——已由 `gene_anchor_ortholog_full.py`（NCBI efetch/esummary 批量，≤200/批）生成，无需重跑在线查询；人 hg38 坐标另有 `human_ortholog_hg38_full.csv`。

核心公式（Stouffer，**不是** Fisher Z）：
```
Z_gene = Σ_{tile ∈ 基因体±2kb} sign(r_tile) · Φ⁻¹(1 − p_tile/2) / √n
```
（tile 级带符号标准分求和 ÷√n，聚合到基因级；Φ⁻¹ = 标准正态分位数函数）

输出：`v5_substitutability_all.csv`（16,031 基因，含 Z_human、Z_monkey、S、class）。
**对账判定**：复现配对表与目标文件前几行逐列一致（尤其 Z 列）即 M3 通过。

## 协作模式（用户自跑复现）

- 用户明确"我自己跑一遍"时：**M2→M7 分步给脚本**，每步带数字对账点（行数/列名/tile 宽度/对账目标行数），让用户能自己核对，避免"我给的结论你还要再查一遍"。
- **先核实输入再给脚本**（用户对"结论老是变"零容忍——先验证文件真实存在+结构，再写下一步代码）。
- "用户以为出错"的结果（up/down 空、FDR 全灭）→ **先给结论定性（真实/non-bug），再给数学必然性**。