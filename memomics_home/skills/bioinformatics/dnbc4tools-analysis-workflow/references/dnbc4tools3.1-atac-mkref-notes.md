# dnbc4tools 3.1 atac mkref 实测笔记（2026-09-01 · GRCh38 + gencode v32）

本文件记录 dnbc4tools 3.1（官方 FTP 渠道，注意**比 GitHub tag 2.1.3 新**）在 Windows-WSL2 环境构建人类 ATAC 索引的完整实测：
版本差异、成功命令、产物结构、假失败诊断路径。执行任何 3.1 mkref 前先读本笔记。

## 背景

- 软件：`ftp://ftp.cngb.org/pub/CNSA/data7/CNP0008672/Single_Cell/CSE0000574/dnbc4tools-3.1.tar.gz`（527,613,238B）
- 安装：解压到 WSL2 `/opt/dnbc4tools3.1/`（**不能解压到 /mnt 挂载盘**，ELF 二进制在 drvfs 上无法执行）
- 输入：`GRCh38.primary_assembly.genome.fa`（844.7MB gz，解压 3.15GB）+ `gencode.v32.primary_assembly.annotation.gtf`（43MB gz，解压 1.30GB）
- GTF 预处理：`dnbc4tools tools mkgtf --ingtf genes.gtf --output genes.filter.gtf`（3.1 默认动作=mkgtf 过滤，统计动作名是 `stats`；实测自动检测 gene_type，37489 基因通过）
- WSL2 .wslconfig：memory=48GB / processors=16 / swap=8GB（dnbc4tools 官方要求 ≥50GB，48GB+swap 实测可跑）

## ⚠️ 3.1 vs 2.1.3 atac mkref 版本差异（--help 实测）

| 项 | 2.1.3 | 3.1 |
|----|-------|-----|
| `--threads` | ✅ 有（默认4） | ❌ **删除**（chromap 建索引单线程；传了报 `unrecognized arguments: --threads 16` 直接退出） |
| 新增参数 | — | `--tag`(默认transcript) / `--kmer`(默认17) / `--window`(默认7) / `--noindex` / `--chloroplast` |
| `--prefix` | chr | **默认 None**——人类 GRCh38 必须显式 `--prefix chr`（混合物种不支持 prefix） |
| 产物位置 | `genomeDir/` 根下 | ⚠️ 指定 `--species` 后自动建 **`genomeDir/<species>/` 子目录**，全部产物在子目录内 |

**结论：照抄 2.1.3 教程命令必踩坑。执行前先 `dnbc4tools atac mkref --help` 核对当前版本参数表。**

## 成功命令（3.1 · 人类 GRCh38）

```bash
dnbc4tools atac mkref \
  --fasta /data/GRCh38_ref/GRCh38.primary_assembly.genome.fa \
  --ingtf /data/GRCh38_ref/genes.filter.gtf \
  --species Homo_sapiens \
  --prefix chr \
  --genomeDir /data/GRCh38_ref/GRCh38_atac_index
```

### 产物结构（3.1，注意 species 子目录）

```
/data/GRCh38_ref/GRCh38_atac_index/Homo_sapiens/
├── ref.json                    # version=3.1, genome=fasta/genome.fa, index=fasta/genome.index
├── cmd.txt
├── fasta/
│   ├── genome.fa               # 3,151,417,447 B (~3.15GB)
│   └── genome.index            # 12,310,203,776 B (~12.3GB, chromap 索引)
├── genes/
│   └── genes.gtf               # 1,295,178,175 B (~1.3GB)
└── regions/
    ├── chrom.sizes             # 376B（chr1-22+X+Y+M）
    ├── tss.bed                 # 3,593,022B
    └── promoter.bed            # 2,446,532B
```

ref.json 关键字段：`species: Homo_sapiens`、`chrmt: chrM`、`genomesize: hs`、`blacklist: None`（3.1 不强制 blacklist）。

## 🔴 假失败诊断（本次最重要教训）

**现象**：包装脚本 exit 1，后台进程报"exited"，日志尾部只有
`cat: /data/GRCh38_ref/GRCh38_atac_index/ref.json: No such file or directory`。

**真相**：mkref **实际成功**。日志中间有：
```
2026-09-01 02:06:52 ATAC reference building finished.
MKREF_EXIT=0
```
脚本失败点在 mkref 成功**之后**：脚本按 2.1.3 习惯去 `genomeDir/` 根目录 cat ref.json，
但 3.1 产物在 `genomeDir/Homo_sapiens/` 子目录 → cat 失败 → `set -e` 触发 → 整个包装脚本 exit 1。

**判活/判完成规则（不要信退出码）**：
1. 读真实 log：找 `MKREF_EXIT=0` + `ATAC reference building finished`（或对应工具自己的 finished 字样）
2. 进 `genomeDir/<species>/` 子目录验证：`cat ref.json` + `stat fasta/genome.index genes/genes.gtf regions/tss.bed`
3. 产物文件大小核对（见上表），非空即成功

**代价提醒**：人类 GRCh38 索引约 **16GB**，误判失败重跑纯浪费 3 分钟 + 16GB 磁盘写。

## Windows-WSL2 落地要点

- 命令形式：`wsl -e bash /mnt/e/DNB/_step3_mkref_v2.sh`（复杂引号命令写 .sh 再 wsl -e bash，不要在 bash -c 里套复杂引号）
- WSL stdout UTF-16 乱码 → 日志落盘重定向后 read_file 读取（如 `> /mnt/e/DNB/_mkref_v2.log 2>&1`）
- 后台执行：写 .sh → `terminal(background=True, notify_on_complete=True)`
- 产物拷回 Windows：`cp -r /data/.../Homo_sapiens /mnt/e/Human_gene_reference/GRCh38_atac_index/`（16GB 约数分钟）
- 目录约定（用户明确）：工具包 → `E:/DNB`，人类参考原始文件 + 索引 → `E:/Human_gene_reference/`

## 验证 checklist（每次 mkref 后跑）

```bash
# 1) 子目录内 ref.json
cat <genomeDir>/<species>/ref.json
# 2) 关键产物非空
stat -c '%s %n' <genomeDir>/<species>/fasta/genome.fa \
                 <genomeDir>/<species>/fasta/genome.index \
                 <genomeDir>/<species>/genes/genes.gtf \
                 <genomeDir>/<species>/regions/{chrom.sizes,tss.bed,promoter.bed}
# 3) chrom.sizes 应含全部染色体（人类 chr1-22+X+Y+M）
head <genomeDir>/<species>/regions/chrom.sizes
```

## 关联

- 完整 WSL 执行细节 → `windows-bioinformatics-batch-processing/references/wsl-linux-binary-execution.md`
- v2.1.3 官方参数权威核录 → `references/dnbc4tools-v213-official-facts.md`
- rna mkref（STAR）差异可能类似（3.1 是否删 --threads 需单独 `rna mkref --help` 核对）