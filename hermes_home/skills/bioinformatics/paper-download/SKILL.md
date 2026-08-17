---
name: paper-download
description: "搜索并下载学术论文PDF，支持arXiv/PubMed/bioRxiv等平台"
when_to_use: "[paper-download] 需要下载单篇论文PDF（DOI/PMID/arXiv ID），仅下载不分析"
version: 1.1.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: []
    difficulty: basic
    language: Python
    category: General Utility
prerequisites:
  r_packages: []
  python_packages: []
---

# 文献下载

搜索并下载学术论文PDF，支持arXiv/PubMed/bioRxiv等平台。

## When to Use

当你需要下载单篇论文 PDF 时触发。仅下载，不分析（分析用 paper-summary）。

## Triggers

- `下载文献` / `下载pdf` / `下载论文` / `找论文` / `获取文献`

## Pipeline

1. **搜索论文**: 用 `search_papers` 根据标题/关键词搜索，获取 PMID/DOI
2. **下载PDF**: 用 `download_pdf(doi=..., url_or_pmid=...)` 下载到 `work/papers/`
3. **验证PDF**: `file <path>` + `fitz.open().page_count` 确认是真 PDF 且页数正确

## Preprint Fallback（付费墙受阻时恢复策略）

当 `download_pdf` 因付费墙/Cloudflare 反爬全部失败时，不要放弃：

1. **查预印本**: 用 `search_papers` 搜索论文标题 → 找 EuropePMC 结果中 `source: "PPR"` 的条目（预印本源）
2. **取预印本 DOI**: PPR 条目通常带 `10.1101/YYYY.MM.DD.XXXXXX` 格式的 bioRxiv DOI
3. **curl 下载**: curl 对代理的处理优于 Python requests，直接从 bioRxiv 下载：
   ```
   curl -L -o "work/papers/<FirstAuthor><Year>_<Topic>.pdf" \
     -H "User-Agent: Mozilla/5.0 ... Chrome/120.0.0.0 Safari/537.36" \
     --max-time 180 \
     "https://www.biorxiv.org/content/10.1101/<preprint_doi>v1.full.pdf"
   ```
4. **验证页数**: `file` 命令可能误判（Safari PDF header 导致）→ 用 `fitz.open().page_count` 确认实际页数
5. 预印本内容与正式发表版基本一致，可直接用于解读和参数提取

> 详细步骤 + 实例见 `references/preprint-fallback.md`

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| download_pdf 全部策略失败 (paywall/Cloudflare) | 正式发表版需订阅或被反爬拦截 | 执行 **Preprint Fallback** → 从 bioRxiv 下载预印本 |
| file 命令显示 PDF 仅 3 页但实际 37 页 | file(1) 仅检查文件头，Safari PDF header 误导 | 用 `fitz.open().page_count` 验证实际页数 |
| EuropePMC PDF render 返回 404 | 文章为订阅制，PMC 未托管 PDF | 走 Preprint Fallback 流程 |

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `steps` | 搜索论文 → 下载PDF → 验证PDF | 失败时自动回退 Preprint Fallback |

## Proven Scripts

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

## References

- Source: MemOmics built-in (v1.1.0)
- Category: 文献搜索
- Language: Python
- 预印本回退策略: `references/preprint-fallback.md`
