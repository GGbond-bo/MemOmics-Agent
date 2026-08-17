# Import GEO Public ATAC Fragment Files into ArchR

## When to use this guide

When a GEO dataset provides pre-processed ATAC fragment files (`.tsv.gz` + `.tbi.gz` Tabix-indexed) instead of raw fastq. This is common for high-profile publications — saves alignment step entirely.

## Key GEO ATAC data pattern

Many recent ATAC-seq datasets on GEO provide fragment files in supplementary data:
- `*_fragments.tsv.gz` — gzipped TSV: columns are typically `chr`, `start`, `end`, `barcode`, `count`
- `*_fragments.tsv.gz.tbi.gz` — gzipped Tabix index

These can be **directly imported into ArchR** via `createArrowFiles()` — no alignment needed.

## Known human hippocampus ATAC datasets

| Dataset | Samples | Tissue | Direction | Publication | Format |
|---------|:-------:|--------|-----------|-------------|--------|
| **GSE278576** | 40 ATAC | Hippocampus | Aging | Science 2026, PMID 42490474 | fragments.tsv.gz |
| GSE147672 | 26 (hipp) | Multi-region brain | AD/PD reference | — | bulk/scATAC |
| GSE226529 | 6 | Hippocampus | AD vs Control | — | bulk ATAC |

## ENCODE limitation

ENCODE has **no human hippocampus ATAC-seq** as of 2026-07. All 4 `snATAC-seq` experiments under "hippocampus" are *Mus musculus*. For brain ATAC data, GEO is the primary source.

## Import workflow

```r
library(ArchR)

# Step 1: Download fragment files from GEO FTP
# ftp://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549XXX/suppl/

# Step 2: Create Arrow files directly from fragments
addArchRGenome("hg38")

ArrowFiles <- createArrowFiles(
  inputFiles = c(
    "sample1_fragments.tsv.gz",
    "sample2_fragments.tsv.gz"
  ),
  sampleNames = c("sample1", "sample2"),
  minTSS = 4,
  minFrags = 1000,
  addTileMat = TRUE,
  addGeneScoreMat = TRUE
)

proj <- ArchRProject(
  ArrowFiles = ArrowFiles,
  outputDirectory = "ArchR_Output",
  copyArrows = TRUE
)
```

## Metadata retrieval

GEO Series Matrix files (`GSE278576_series_matrix.txt.gz`) contain sample characteristics (age, sex, tissue). Download from:
`https://ftp.ncbi.nlm.nih.gov/geo/series/GSE278nnn/GSE278576/matrix/`

Extract with Python:
```python
import GEOparse
gse = GEOparse.get_GEO(geo="GSE278576", destdir="./")
# Access sample characteristics via gse.phenotype_data
```

## File size estimation

Typical human ATAC fragment file: 1-3 GB per sample (tsv.gz). 40 samples ≈ 80-120 GB total.
Consider downloading a subset first to validate the import pipeline.

## Batch download script (GSE278576 — 2026-07-30 validated)

The script below was validated against NCBI E-utilities API and FTP. All 40 GSM fragment URLs confirmed reachable via HTTP HEAD. 

**Important**: On Windows, NCBI HTTPS connections fail due to schannel certificate revocation checks. Use `curl -k` to bypass. If download speed < 100 KB/s, use a VPN or cloud VM.

```bash
#!/bin/bash
# download_gse278576_fragments.sh
# Download 40 human hippocampus ATAC fragment files from GSE278576
# (Science 2026, PMID 42490474 — Epigenetic and 3D genome reprogramming
#  during the aging of human hippocampus)

set -e
BASE="https://ftp.ncbi.nlm.nih.gov/geo/samples"
OUTDIR="GSE278576_human_hippocampus_ATAC"

GSMS=(
  GSM8549615 GSM8549616 GSM8549617 GSM8549618 GSM8549619
  GSM8549620 GSM8549621 GSM8549622 GSM8549623 GSM8549624
  GSM8549625 GSM8549626 GSM8549627 GSM8549628 GSM8549629
  GSM8549630 GSM8549631 GSM8549632 GSM8549633 GSM8549634
  GSM8549635 GSM8549636 GSM8549637 GSM8549638 GSM8549639
  GSM8549640 GSM8549641 GSM8549642 GSM8549643 GSM8549644
  GSM8549645 GSM8549646 GSM8549647 GSM8549648 GSM8549649
  GSM8549650 GSM8549651 GSM8549652 GSM8549653 GSM8549654
)

for gsm in "${GSMS[@]}"; do
  prefix="${gsm:0:8}"
  url="${BASE}/${prefix}nnn/${gsm}/suppl/"
  
  donor=$(curl -k -s "$url" 2>/dev/null | grep -oP "${gsm}_\K[^_]*(?=_atac)" | head -1)
  [ -z "$donor" ] && echo "⚠️  $gsm: could not resolve donor" && continue
  
  mkdir -p "${OUTDIR}/${donor}"
  
  for suffix in "_atac_fragments.tsv.gz" "_atac_fragments.tsv.gz.tbi.gz"; do
    fname="${gsm}_${donor}${suffix}"
    dest="${OUTDIR}/${donor}/${fname}"
    [ -f "$dest" ] && [ "$(stat -c%s "$dest" 2>/dev/null || echo 0)" -gt 1000 ] && continue
    echo "  📥 $donor/$fname"
    curl -k -C - -L -o "$dest" "${url}${fname}" || echo "  ❌ Failed"
  done
done

echo "=== Done ==="
```

## Network considerations

- **NCBI HTTPS requires `-k` flag on Windows**: schannel certificate revocation check blocks NCBI. Use `curl -k`.
- **Download speed**: NCBI FTP may be rate-limited (observed ~6 KB/s from some regions). Use VPN or cloud VM if needed.
- **Resume support**: `curl -C -` enables resume for interrupted downloads.
- **File verification**: Fragment files should be 500 MB - 3 GB. Files < 10 MB are likely error pages.

## ⚠️ bigwig vs fragments — 选哪个（2026-08-02 用户问"为什么都是亚群的ATAC"后明确）

**GSE278576 的 suppl 目录同时提供两种粒度的数据，用途完全不同：**

| 格式 | 粒度 | 能做什么 | 大小 | 适用 |
|------|------|---------|------|------|
| `*_ATAC_<CellType>_age<group>.bw` | **亚群聚合**（按细胞类型×年龄组聚合的信号） | L2 可及性比较（peak overlap + 信号强度 + 年龄动态） | ~100-350MB/文件 | 跨物种可及性保守性比较（够用） |
| `*_atac_fragments.tsv.gz`（GSM 级） | **单细胞原始**（每个 barcode 的插入片段） | L2 + L3 真 TF footprinting | **~1.3GB/样本** | 需要 footprinting 时 |

**用户对"亚群聚合"数据的反应**：当用户问"为什么你给我的都是亚群的ATAC呢？"——指的是 bigwig（细胞类型×年龄组聚合信号）。要摆脱亚群粒度必须用 fragments（单细胞级）。**回答数据选择问题前先分清用户要的是哪个粒度。**

**⚠️ GSM 级 fragments 单独可下 — 不需要 89GB 的 GSE278576_RAW.tar！**

每个样本的 fragments 在**独立的 GSM suppl 目录**（不需要下载系列级的 RAW.tar）：

```
https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549615/suppl/
├── GSM8549615_hc77_atac_fragments.tsv.gz        (~1.3GB)
└── GSM8549615_hc77_atac_fragments.tsv.gz.tbi.gz
```

GSM→文件 URL 生成规则：`https://ftp.ncbi.nlm.nih.gov/geo/samples/{gsm[0:8]}nnn/{gsm}/suppl/{gsm}_{donor}_atac_fragments.tsv.gz`

**⚠️ 下载完整性验证（2026-08-02 实锤）**：用户此前"下载"的 hc77/hc78 只有 2.0MB / 0.7MB，而服务器真实大小是 **1.31GB**（完成度 0.15%）。**下载后用 HTTP HEAD 对比 Content-Length，<50% 视为未完成**：

```bash
curl -k -sI "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549615/suppl/GSM8549615_hc77_atac_fragments.tsv.gz" | grep -i content-length
# 对比本地文件大小；差异 >10 倍 = 断点未续传/下载失败
```

**带宽现实（~6KB/s 时）**：1.31GB/样本 ≈ 60 小时；40 样本 ≈ 100 天 → 不可行。决策树：
- 只做 L2（可及性比较）→ 下 bigwig（~1GB 核心 8 个文件，2 天）
- 必须做 L3（真 footprinting）→ fragments，但需换高速网络（学校/机房服务器）或放弃人侧 footprinting 用 motif 代理
- **专利 3 个月受理时限下推荐**：先下 bigwig 跑通 L2 核心方法，L3 用 motif 代理 + 从权留位（见 SKILL.md motif 小节）
