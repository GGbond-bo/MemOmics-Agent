# bigWigAverageOverBed 官方用法（L1 批量打分执行工具）

> 来源：UCSC kent 官方源码 `src/utils/bigWigAverageOverBed/bigWigAverageOverBed.c`（GitHub ucscGenomeBrowser/kent，blob sha 59038d8380e3b730e9e626834a35f638060d611c，2026-08-31 抓取）。该仓库没有 README——**官方文档就是源码里的 usage()**。

## 命令（一行）

```
bigWigAverageOverBed in.bw in.bed out.tab
```

- `in.bw` = bigWig 轨道（如 hg38.phyloP100way.bw）
- `in.bed` = peak 区域（**bed 3 列：chr、start、end**）
- `out.tab` = 输出表

**无 Windows 官方二进制** —— 只能 Linux/WSL/集群跑；集群上直接：
```bash
wget http://hgdownload.soe.ucsc.edu/admin/exe/linux.x86_64/bigWigAverageOverBed
chmod +x bigWigAverageOverBed
```

## 输出 6 列（官方逐字语义）

| 列 | 含义 |
|----|------|
| name | bed 的 name 字段（**必须唯一**，重名直接 `errAbort: duplicated in input bed`） |
| size | 区间 bp 数 |
| covered | bigWig 覆盖到的碱基数 |
| sum | 覆盖区域值之和 |
| **mean0** | 平均分，**未覆盖碱基按 0 计** = sum/size |
| mean | 仅覆盖碱基的平均 = sum/covered |

**phyloP L1 打分用 `mean0`**：peak 区间一般全覆盖两者几乎相等；phyloP 是正负值（负=加速进化，正=保守），未覆盖按 0 参与平均最严谨。

## 参数

```bash
bigWigAverageOverBed -minMax -tsv hg38.phyloP100way.bw peaks.bed out.tab
```

- `-minMax` → 追加两列：区间内最小/最大值
- `-tsv` → 输出带表头
- `-bedOut=out.bed` → 额外输出"原 bed + mean 列"（可作合并键）
- `-sampleAroundCenter=N` → 只取区间中心 N bp 采样（一般不用）
- `-stats=stats.ra` → 输出总体统计

## 坑位

1. **ArchR CSV（chr1_1000_2000）要先拆成 3 列 bed**：
   ```python
   import pandas as pd
   df = pd.read_csv("human_Hf_peaks.csv")
   coords = df.iloc[:,0].astype(str).str.split("_", expand=True)
   coords.iloc[:,:3].to_csv("peaks.bed", sep="\t", header=False, index=False)
   ```
2. **区间名必须唯一**（工具内部 `checkUniqueNames` 硬校验）——导出 bed 时给每行唯一 id 或只用 3 列
3. 大文件（525k peaks）跑起来秒级到分钟级，远快于 UCSC REST 逐点查询（0.35s 限速）

## 与 pyBigWig 二选一（不需要两个都装）

| 选哪个 | 适合 |
|--------|------|
| **pyBigWig**（pip/conda 装进 Linux 环境，如用户 sc-scanpy env） | 打分与后续处理同脚本，推荐 |
| **bigWigAverageOverBed**（UCSC 官方二进制） | 不想进 Python、零依赖、下载即用 |

pyBigWig 等价的打分调用：`pyBigWig.open(bw).stats(chr, start, end, type="mean")[0]`。

## L1 方法学"官方"引用（写论文/专利方法学段用）

- **phyloP** = Pollard KS et al., *Detection of nonneutral substitution rates on mammalian phylogenies*, Genome Res 2010. **PMID:19858363**
- **phastCons** = Siepel A et al., *Evolutionarily conserved elements in vertebrate, insect, worm, and yeast genomes*, Genome Res 2005. **PMID:16024819**
- 跨物种调控保守顶级范例：Sarropoulos et al., Science 2026（PMID:41610256）；Wang et al., Sci Adv 2026（PMID:41984952）
- 说明：phyloP/phastCons 是领域标准打分，不是某篇专利/工具"官方定义"；张潇 NHPABC 公开脚本只含 ArchR/MACS2/Seurat cCRE 注释，**没有 phyloP 评分段**——那正是本专利 L1 的增量。