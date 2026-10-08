# awk 解析 GTF/GFF attributes：转义坑与排查顺序

来源：2026-10-01 实测（MEF2C / MEF2C-AS1 归属审计包）。同一个脚本连改两版才修好，
中间一轮被"干净的全 0 报告"误导。

## 一、坑的完整形态

GTF 第 9 列是 attributes：`gene_id "ENSG..."; gene_name "MEF2C"; gene_type "protein_coding";`

想取 `gene_name`，第一直觉是在 `awk -F'\t'` 里写：

```awk
split($9, a, "gene_name \""); nm=a[2]; sub(/\".*/, "", nm)     # ❌
```

**两个问题**：

1. `awk: warning: regexp escape sequence \`\\"\` is not a known regexp operator`
   —— awk 正则里 `\"` 不是合法转义（`"` 本身无需转义）；
2. 把转义去掉改成 `split($9,a,"gene_name ")` 之后，**整个 awk 程序解析异常**，
   `step1_gene_span.bed` / `step2_exons_raw.bed` 变成空文件 ⇒ 后续所有数字变 **0**、
   断言 `NOT PASS`。表面上是一份"格式完全正常、只是数字全 0"的报告。

## 二、稳写法（零转义，实测一次通过）

```awk
$3=="gene" && (index($9,g1)||index($9,g2)) {
  if (match($9, /gene_name "[^"]+"/)) nm=substr($9,RSTART+11,RLENGTH-12); else next
  printf "%s\t%d\t%d\t%s\t0\t%s\n",$1,$4-1,$5,nm,$7
}
```

- `match()` 的 `RSTART/RLENGTH` 是 awk 标准内建，跨 gawk/mawk/busybox awk 都可用；
- 偏移量：`gene_name "` 是 11 个字符，尾部还有 1 个 `"` ⇒ `RLENGTH-12`；
- **正则字面量里出现 `"` 是合法的**（引号不是正则元字符），不需要任何反斜杠；
- 同族习惯：R 里同理不写反斜杠（用 `fixed=TRUE` / 字符类 `[.]`），
  Python 里 f-string 优于 `%` 格式化——**凡多层转义，就换一种写法让转义消失**。

## 三、排查顺序（这一课比修法更贵）

被"干净的全 0 报告"误导的那一轮，回执是这样拿到的：

```bash
bash verify.sh <GTF> | tail -25      # ❌ 错误行在最前，被 tail 吃掉
```

`tail` 只留下了末尾的正常报告版式（`gene-span overlap : 0 bp` / `NOTE: numbers differ`），
awk 的报错在上方、**看不见** ⇒ 第一反应变成"是不是 GTF 版本变了/数据变了"。

**正确顺序**：

1. 复现类脚本一律 `> log 2>&1`（或 `tee`）**全量落盘**，先读全量再看结论行；
2. 数字全是 0 时，第一个怀疑对象是 **stderr**，不是输入数据；
3. 修完后**必须重新实测出原始数字**（本例 span=20930 / exon=422 / 3 段）才算修好——
   只看 exit 0 或"报告格式正常"不算；
4. 用同一个脚本做**双路径验证**（bedtools 路径 + awk 兜底路径）结论一致，才能交给第三方。