# L1 序列保守性公共资源 — 下载清单与 MFA8 chain 现状（2026-08-29 实测）

## 1. hg38 保守性 bigWig（UCSC，已验证 HTTP 200 + Content-Length）

存档到 `E:/专利/L1_resources/`（后台串行下载脚本 `E:/专利/P3_L1_data/download_l1_resources.py`，每 64MB 写进度到 `progress_<name>.log`）。

| 文件 | URL | 大小 | 用途 |
|------|-----|------|------|
| `hg38.phyloP100way.bw` | https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP100way/hg38.phyloP100way.bw | 9.87 GB | 主评分（UCSC API 同款 track，批量替代逐点查询） |
| `hg38.phastCons100way.bw` | https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phastCons100way/hg38.phastCons100way.bw | 5.89 GB | 保守区段佐证 |
| `hg38.phyloP30way.bw` | https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP30way/hg38.phyloP30way.bw | 8.40 GB | 灵长类专用版本 |

三文件共 ~24 GB。验证完整 = `os.path.getsize(out) == 服务器 Content-Length`（脚本已含）。

## 2. 人猴 chain 现状（关键发现：UCSC 没有 MFA8 的 chain）

| 尝试 | 结果 |
|------|------|
| `hg38ToMacFas5.over.chain.gz` | ✅ 存在（40.6 MB），但对应 **MacFas5 旧组装**（2013），与 T2T-MFA8v1.1 坐标系不同 |
| `macFas8 / mfa8 / macFas6 / mfaT2T` | ❌ 全部 404 — UCSC 没有收录 T2T-MFA8v1.1 |
| NCBI Remap API v1/v2/assembly id/remap | ❌ 全部 404（`api.ncbi.nlm.nih.gov/core/remap/v1/...` 本会话探测 endpoint 均不存在，勿依赖） |
| 物种身份 | 猴脑 = Macaca fascicularis T2T-MFA8v1.1（GCF_037993035.2，上海交大提交，Complete Genome），染色体 NC_088375.1 起 21 条 |

**结论**：跨物种 L1 坐标转换**不能靠 UCSC chain**。已验证可用路径 = **基因 ortholog 手工映射**（`E:/专利/P3_L1_data/macaque_da_gene_map.csv`：猴 NC_088xxx tile → 猴基因 → human ortholog gene → hg38 坐标；`l1_phylop_fill_v3.py` 用 tile 在猴基因内相对位置 frac 映射到人基因对应位置 ±2500bp → 5kb 窗口查询 phyloP100way）。

## 3. 本机下载模式（Windows 宿主实测）

- ⚠️ `curl` / `nslookup` 访问 UCSC 全部 DNS 超时/HTTP 000（本机走 Python 侧代理）——**用 Python `urllib.request` 下载**（4MB chunk + 每 64MB 记录进度），不要用 curl/wget。
- 后台运行：Hermes `terminal(background=True, notify_on_complete=True)`（禁止 nohup/& 包装）；3 文件**串行**下载避免带宽互挤，预计数小时。
- 后续用：phyloP bigWig 本机批量查询（pyBigWig）替代逐点 UCSC API（原 `query_phylop` 每次 sleep 0.3s，40 区域 20-40 min）。