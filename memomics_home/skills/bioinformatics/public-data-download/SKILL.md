---
name: public-data-download
category: Data Query
description: "精确下载公共组学数据集（指定物种+组织+assay类型）。不做全量调查，直接搜最佳候选并开始下载。"
trigger:
  when:
    - "用户说帮我下载 X 组织 Y 物种 Z 类型数据"
    - "下载人类海马 ATAC、下载小鼠肝脏 RNA-seq 等精确请求"
    - "用户指定了物种+组织+数据类型，要下载而非浏览"
    - "download X data / get public data for Y"
  rules:
    - "跳过澄清问题，直接从请求中提取物种/组织/assay类型"
    - "找到最佳候选后直接开始下载，不要问要开始吗"
    - "仅在多个质量相当的候选、需TB级数据、controlled-access时问确认"
---

# Public Data Download Skill

> 这是 `omics-dataset-retrieval` 的轻量级兄弟 skill。
> 当用户明确指定了物种+组织+数据类型时使用本 skill；
> 当用户想做全量调查时用 `omics-dataset-retrieval`。

## 核心原则

**用户说「帮我下载」= 指令，不是咨询。直接搜→找最佳→开始下载。**

---

## 搜索回退链（按此顺序，前一步有结果就不继续）

### Tier 1: ENCODE（ATAC-seq/ChIP-seq/epigenomics 首选）
```
https://www.encodeproject.org/search/?type=Experiment&searchTerm={tissue}+{species}+{assay}
```
- 若无人类结果 → 直接跳到 Tier 2，不要在 ENCODE 里反复尝试
- 注意：ENCODE 人类数据丰富，但某些组织（如 hippocampus ATAC）可能全是小鼠 → 立刻回退

### Tier 2: GEO (NCBI E-utilities)
```
query: "{tissue}[Title] AND {species} AND {assay}[Title]"
db: gds, retmax: 100
```
- 调用 `search_geo()` 获取候选列表
- 用 `get_geo_details()` 获取每个候选的样本数/摘要/物种
- 筛出真正的人类数据（GEO 摘要可能含多物种，必须用 get_geo_details 验证）

### Tier 3: ArrayExpress (EBI)
```
https://www.ebi.ac.uk/biostudies/api/v1/search?query={tissue}+{species}+{assay}&collection=arrayexpress
```

### Tier 4: PubMed / Semantic Scholar
搜索已发表文献中提及的数据集，然后回到 GEO/ArrayExpress 找 accession。

---

## 数据集评估维度（选最佳）

| 维度 | 权重 | 说明 |
|------|:---:|------|
| 物种匹配 | 必须 | 必须是目标物种 |
| 组织匹配 | 必须 | 必须是目标组织或含该组织 |
| 样本数 | 高 | >20 供体优先 |
| 数据格式 | 高 | Fragment 文件 > BAM > fastq（可直接喂 ArchR/Seurat） |
| 研究方向 | 中 | 与用户的研究方向一致（如衰老/发育/疾病） |
| 发表年份 | 中 | 近 3 年优先 |
| 期刊等级 | 低 | Science/Nature/Cell 数据质量通常更好 |

---

## 下载执行

### 如果找到了最佳候选：
1. **先下 1 个样本验证**（格式/完整性/速度）
2. 验证通过 → 批量下载其余样本
3. 下载目录：`E:/Data/{GSE_ID}/`（不装 C 盘）

### 常用下载命令：
```bash
# GEO FTP 批量下载 fragment 文件
wget -r -np -nH --cut-dirs=4 \
  -A "*fragments.tsv.gz*" \
  https://ftp.ncbi.nlm.nih.gov/geo/samples/GSMnnnnnnn/

# SRA 下载
prefetch SRR_ACCESSION
fasterq-dump SRR_ACCESSION
```

---

## 网络不可用时的兜底

如果当前环境无法访问外网（HTTPS 全部超时）：
1. 如实告诉用户网络不通
2. 提供完整的下载链接清单（URL 列表），让用户在有机器的环境下手动下载
3. 提供下载后的数据导入脚本（ArchR createArrowFiles / Seurat 读取）
4. 不要无限重试 curl/wget

---

## 与 `omics-dataset-retrieval` 的区别

| 维度 | omics-dataset-retrieval | public-data-download |
|------|------------------------|---------------------|
| 触发 | 全面调查 X 疾病的所有组学数据 | 下载人类海马 ATAC-seq |
| 澄清问题 | 7 个（必须全部回答） | 0 个（直接搜） |
| 产出 | CSV catalog + summary report | 下载的数据文件 |
| 搜索广度 | 25+ repositories | 3-4 个（ENCODE→GEO→ArrayExpress→PubMed） |
| 确认环节 | 每个 tier 后 | 仅多候选/大体积/controlled-access 时 |

---

## 参考资料

- `references/human-hippocampus-atac-search-case.md` — 人海马 ATAC 候选数据集搜索案例
- `references/gse278576-human-hippocampus-atac-case.md` — GSE278576 实战：GEO suppl 文件类型地图、海马亚区命名(CA1/DG/SUB)、fragments vs bw 决策、下载清单模板
- `references/gse278576-gsm-fragments-map.md` — GSE278576 的 40 个 ATAC 样本 GSM 映射表（已验证）+ GSM 级 fragments URL 模板 + curl -sI 验证协议
- `references/gse278576-analysis-pipeline.md` — GSE278576 论文官方分析管线：cellranger-arc→SnapATAC2 QC→MACS2(SPM≥4)→pseudobulk 连续年龄 Pearson(FDR<0.1)→HOMER/chromVAR→ABC。用户问"这篇论文用什么方法/对比流程"时直接查此文件；注意 bioRxiv 详细 M&M 在补充材料 DC1/DC2（不在主 PDF），需从 supplementary-material 页面解析 embed 链接

## Pitfalls

1. **过度确认**：用户说「帮我下载」时不要问「要我下载吗？」— 他在发号施令，不是在咨询
2. **在 ENCODE 空结果上反复尝试**：ENCODE 无人类结果 → 立刻跳到 GEO，不要换关键词反复试
3. **GEO 搜索结果含多物种**：GEO 摘要可能混入小鼠数据 → 必须用 `get_geo_details()` 验证物种
4. **下载后放在 C 盘**：用户明确拒绝 — 数据全部放 E:/Data/ 或 E:/ 其他目录
5. **网络不通时装死**：报网络超时后给替代方案（URL 清单 + 手动下载指令），不要静默失败
6. **🔴 fragments 在 GSM 级，不在 GSE 级（2026-08-02 GSE278576 实战教训）**：10x Multiome 数据集（如 GSE278576）的原始 `fragments.tsv.gz` **按样本存放在每个 GSM 页面**，GSE 主 supplementary 页只有聚合文件（bigWig/h5/tar）。用户按 GSE 页面找 fragments 必然"官网找不到"。URL 规律：
   ```
   https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549615/suppl/GSM8549615_hc77_atac_fragments.tsv.gz
   ```
   每个样本要配套 `.tbi.gz` 索引（ArchR 必需）。给下载清单前必须先 `query_ncbi(db="gds", query="GSE278576[ACCN] AND ATAC")` 拉全 40 个 GSM。
7. **🔴 下载清单必须先 curl -sI 验证（用户会审计）**：给用户下载清单前，对每个 URL 跑 `curl -k -sI <url>` 确认 `200 OK` + `Content-Length` 合理（几百 MB-几 GB）。不验证就交付清单 = 用户一打开就发现文件不存在，信任崩塌。验证通过后还要说明"每个样本 2 个文件（.tsv.gz + .tbi.gz）"。
8. **bw vs fragments 用途不同，先问清分析目标**：bigWig = 聚合信号轨道（按细胞类型/年龄组），能做 peak 比较/差异可及性，**不能做 TF footprinting**；fragments = 单细胞原始数据，才能做 L3 footprinting。方法验证 → bw 够；专利实施例完整（含 footprinting）→ 必须补 fragments。
9. **🔴 论文"用什么方法/对比流程"必须下 bioRxiv 补充材料（2026-08-04 实战）**：bioRxiv 主 PDF 通常**不含详细 M&M**（只有正文+图注+参考文献），详细参数（cellranger 版本、MACS2 命令、QC 阈值、Pearson FDR 阈值）在补充材料 DC1/DC2：
   - 入口: `https://www.biorxiv.org/content/10.1101/<doi>v1.supplementary-material`
   - 正则提取页面内 embed 链接: `href="([^"]*(?:supplement|suppl|download)[^"]*)"`
   - DC1 = media-1.pdf（补充图 + M&M 文本）；DC2 = media-2.zip（补充表 S1-S24）
   - curl 对 bioRxiv 偶发 SSL error 35 → 用 Python urllib + unverified SSL context
   - Science 正式版付费墙(403) → bioRxiv 预印本 + 补充材料是免费替代（内容一致）
10. **🔴 核对本地参考基因组文件：'文件在' ≠ '完整下完'（2026-08-28 实测教训）**：用户问"我电脑上有这两个文件吗？不是刚下载但还没下完的"——指 Gencode/EBI 参考文件（`GRCh38.primary_assembly.genome.fa.gz` ≈1.05GB + `gencode.v32.primary_assembly.annotation.gtf.gz` ≈1.2GB，dnbc4tools/STAR mkref 必需）。回答"有/没有"前必须做完整性核对：
   - **存在性**（Windows 多盘）：① `search_files(target='files', pattern='*GRCh38.primary_assembly.genome.fa.gz')` → ② bash `find /c /d /e -iname '*GRCh38*' 2>/dev/null` → ③ PowerShell 全盘 `Get-ChildItem -Path C:\,D:\,E:\,F:\ -Recurse -Include *.fa.gz,*.gtf.gz -ErrorAction SilentlyContinue | Select-Object FullName,Length`
   - **残留检测（未下完铁证）**：目标目录/下载目录存在 `.part` / `.crdownload` / `.td` / `.tmp` 同名文件
   - **gz 完整性**：`gzip -t file.gz && echo OK` 通过 = 可解压；报 CRC/truncated = 损坏需重下
   - **大小/内容抽查**：几 KB 或与期望偏差 >20% = 损坏或 HTML 占位页；`zcat file.gz | head -c 300` 抽查，FASTA 首行 `>`，GTF 首行 `#!genome-build`
   - **防误判**：猴子 T2T 注释（`GCF_037993035.2_T2T-MFA8v1.1_genomic.gtf.gz`）≠ 人类 Gencode v32 — 只按 `*.gtf.gz` 全局搜会撞车，必须逐文件核对物种/版本
   - 报告格式：用表格列出"检查项 / 目标 / 结果"，并标注盘上近似但非目标的文件，避免用户误以为存在
11. **🔴 GEO 下载通道：https://ftp.ncbi.nlm.nih.gov 可用，ftp:// 全挂（2026-09-03 GSE67978 CaudateNucleus H3K27ac 实测）**：同一批 GSM 文件——`ftp://ftp.ncbi.nlm.nih.gov/geo/samples/...` 6 个全 FAIL、`https://www.ncbi.nlm.nih.gov/geo/download/?acc=...&file=...` **猜文件名必然 404**（必须从 miniml 解析真实文件名）、**`https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM1660nnn/<GSM>/suppl/<真实文件名>` 手动 curl = 200 OK 秒下**。**经验：GEO 文件下载首选 `https://ftp.ncbi.nlm.nih.gov` 直链（先手动 curl 单文件验证 200 + Content-Length 再批量）；文件名永远从 GEO miniml（`miniml/GSE*_family.xml.tgz`，tarfile + `ET.iter()` 匹配 `}Sample` 元素 Title/Supplementary-Data）解析，不猜**。GSE67978 档案（98 样本 = 人/黑猩猩/恒河猴 × 8 脑区，H3K27ac，人侧 hg38 / 猴侧 rheMac3，无海马 → CaudateNucleus 人 GSM1660034/35/36 + 恒河猴 GSM1660010/11/12 折中）详见 cross-species-atac-conservation skill `references/crecs-v2-structural-bugs-2026-09-03.md`。
12. **🔴 bash curl 循环批量下载全 FAIL 但手动 curl 同 URL 成功 → 写 Python urllib 脚本（2026-09-03 实测）**：`download_peaks.sh`（for 循环 6 个 GSM）全部 FAIL（`-s` 静默无错误码，`[ -s out ]` 检查失败），但手动 eval 同 URL 200 OK——bash 循环内 curl 与外部行为不一致（疑似 NCBI 对快速连续请求限流/瞬时抖动）。**教训：批量下载写 Python `urllib.request` 脚本（UA=Mozilla/5.0 + 每文件至多 5 次重试指数退避 + `gzip.open().read(64)` 校验 + 已存在跳过），不写 bash curl 循环**；脚本落盘（`download_peaks.py`）再跑也符合铁律 31 落盘纪律。实测 py 脚本单文件 200 OK、gzip 有效（人侧 GSM1660034 = 1,420,452 bytes）。
