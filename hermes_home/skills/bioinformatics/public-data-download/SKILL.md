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
