# Windows/WSL 下执行 Linux 生信二进制（dnbc4tools 3.1 实测 2026-09-01）

场景：用户提供华大 dnbc4tools（Linux x86-64 闭源二进制 tar.gz）在 Windows 本机 WSL2 上安装并构建 GRCh38 ATAC 索引。本文件记录**可复用的执行技巧与实测数值**，与 `wsl-process-verification.md`（判活）互补。

## 核心结论（四个坑 + 解法）

### 坑1：WSL 命令 stdout 乱码（UTF-16）→ 落盘读取
`wsl -e sh -c '...'` 直接回传 stdout 到 Windows bash 会读成 UTF-16 乱码（free/ls 输出都乱）。
**解法**：让 WSL 命令把输出**写入 /mnt/e/ 下的落盘文件**（如 `> /mnt/e/DNB/_probe.txt 2>&1`），再用 `read_file` 读该文件——不再依赖 stdout 转码。本会话所有探测/验证都走这条，零乱码。

### 坑2：tar.gz 不能解压执行在 /mnt/e 挂载盘 → 解压到 WSL 内部 /opt
- /mnt/e（NTFS/9P 挂载）上 ELF 可执行位与性能都有问题，dnbc4tools 必须在 WSL 内部文件系统运行。
- **策略**：tar.gz 留 Windows 盘归档（用户要求工具/人类文件放 E 盘即可），解压到 `/opt/dnbc4tools3.1/`，参考数据仍走 `/mnt/e/Human_gene_reference/` 访问，索引产出最后再拷回 E 盘。
- 解压后目录结构应与文档一致：`dnbc4tools` + `external/`（含 conda 运行时）+ `lib/` + `misc/` + `sourceC4.bash`。
- 67175 个文件（503MB gz → 解压 ~1.75GB）约 1-3 分钟解压完成。

### 坑3：复杂命令引号嵌套失败（unexpected EOF）→ write_file 写 .sh
`wsl -e sh -c '... awk -F"\t" '\''$3=="gene"'\'' ...'` 多层转义最终 `unexpected EOF` / `exit_code=2`。
**解法**：用 write_file 写完整 `.sh`（如 `_step2_filter.sh`），再 `wsl -e bash /mnt/e/DNB/_step2_filter.sh` 执行。所有含 awk/引号/变量插值的命令一律先写脚本。
**教训**：连续失败 4 次（上限 3）才换方案太晚，第一次引号报错就该立即转 write_file。

### 坑4：dnbc4tools 是 v3.1 而文档是 2.1.3 → 先 --help 核对再执行
用户下载渠道是 CNGB FTP（比文档里的 BGI CloudDrive 更快，无需访问码）：
```
ftp://ftp.cngb.org/pub/CNSA/data7/CNP0008672/Single_Cell/CSE0000574/dnbc4tools-3.1.tar.gz
```

**v3.1 命令差异（实测 --help）**：

| 子命令 | 2.1.3 文档 | 3.1 实测 |
|--------|-----------|----------|
| `tools mkgtf --action` | `stat` / `check` | **`stats`** / `check` / `mkgtf`（默认=mkgtf 过滤）——统计动作名改成了 `stats` |
| `tools mkgtf --type` | 需显式传 | 默认 `auto` 自动检测（实测识别出 `gene_type`），可不传 |
| `atac mkref` | `--fasta --ingtf --species --prefix --threads --genomeDir` | 全保留 + 新增 `--tag`(默认transcript) `--kmer`(17) `--window`(7) `--noindex` `--chloroplast` |
| `--prefix` | `chr` | 默认 None；人类 GRCh38 必须 `--prefix chr`；混合物种不支持 prefix |

**实测参考数值（人类 GRCh38 + gencode v32 primary）**：
- FASTA .gz 806MB → 解压 3.15GB
- GTF .gz 42MB → 解压 1.33GB
- `tools mkgtf` 过滤：60669 gene → 37489 保留（protein_coding + lncRNA + IG_*/TR_*），输出 1.29GB / 37488 gene 行
- `atac mkref` 参数：`--species Homo_sapiens --prefix chr --threads <n> --genomeDir /data/GRCh38_ref/GRCh38_atac_index`

## WSL 环境检查快速命令（落盘版）
```bash
wsl -e sh -c 'echo "=== free -g ===" > /mnt/e/X/_p.txt; free -g >> /mnt/e/X/_p.txt 2>&1; \
echo "=== nproc ===" >> /mnt/e/X/_p.txt; nproc >> /mnt/e/X/_p.txt; \
echo "=== uname ===" >> /mnt/e/X/_p.txt; uname -a >> /mnt/e/X/_p.txt; \
echo "=== tar type ===" >> /mnt/e/X/_p.txt; file /mnt/e/X/pkg.tar.gz >> /mnt/e/X/_p.txt'`
# 然后 read_file("E:/X/_p.txt")
```
- `.wslconfig` 只设 `[wsl2] memory=48GB`（用户批准后）→ 实测 WSL 内 free 显示 47GB 可用（约 1GB 开销）。修改后必须 `wsl --shutdown` 重启生效。
- 内存门槛：ATAC chromap 建索引远低于 STAR，47GB/16 核实测可跑（官方建议 ≥50GB 是保守值，chromap 不需要那么高）。

## 一句话流程（ATAC 索引构建）
```
下载(CNGB FTP) → 解压到 /opt → ./dnbc4tools -v + atac mkref --help 核对 → 解压 FASTA/GTF 到 /data/... → tools mkgtf(stats→mkgtf) 生成 genes.filter.gtf → atac mkref --prefix chr → 验证 ref.json + genome.index/chrom.sizes/tss.bed/promoter.bed/blacklist → 拷贝回 E 盘交付
```