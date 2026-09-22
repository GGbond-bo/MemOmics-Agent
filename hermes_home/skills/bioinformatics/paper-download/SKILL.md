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
  python_packages: [Pillow, reportlab, requests]
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

## Figure Download（抓取已发表论文的单张 Figure / Extended Data）

适用：用户要"论文的 Figure N" / "把这张图下载下来" / "figure2 给我 pdf"。

1. **定位图件真实文件名**（禁止猜 URL）：
   ```
   curl -s -L "https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML" -o article.xml
   grep -o 'xlink:href="[^"]*"' article.xml
   ```
   输出即全部图件文件名（`..._FigN_HTML.*` = 正图，`..._FigN_ESM.*` = Extended Data）。图注从 `<fig id="FigN">` 的 `<caption>` 提取（JATS XML，含 a–l 全部面板描述）。
2. **下载 Springer Nature 系图件**（Nature/Nat Cancer/… 同规律）：
   ```
   curl -s -L -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36" \
     -H "Referer: https://www.nature.com/articles/<DOI-slug>/figures/<N>" \
     -o FigN.png \
     "https://media.springernature.com/full/springer-static/image/art%3A<DOI，冒号→%3A、斜杠→%2F>/MediaObjects/<file>_HTML.png"
   ```
   - ⛔ **必须带 User-Agent + Referer**：缺 UA 时服务器返回 `200` 但 **0 字节**——静默空文件，最容易误判成功
   - 扩展名以 XML 中的文件名为准（实测 `.jpg` → 404，仅 `.png` 存在）
3. **PNG → PDF（原尺寸 300 dpi 页）**：`像素/300 = 英寸` → `reportlab` `pagesize=(w*inch, h*inch)` + `drawImage` 满页
4. **验证（必做）**：`http_code==200 & size>0` → `file` 看真实尺寸 → 非白像素比例（<0.02 疑空白）→ `vision_describe` OCR 核对面板字母 / marker / 数值与图注一致
5. 记录来源（DOI/PMID/PMCID/许可）；CC BY-NC-ND 图件**不得改动后**再分发

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| download_pdf 全部策略失败 (paywall/Cloudflare) | 正式发表版需订阅或被反爬拦截 | 执行 **Preprint Fallback** → 从 bioRxiv 下载预印本 |
| file 命令显示 PDF 仅 3 页但实际 37 页 | file(1) 仅检查文件头，Safari PDF header 误导 | 用 `fitz.open().page_count` 验证实际页数 |
| EuropePMC PDF render 返回 404 | 文章为订阅制，PMC 未托管 PDF | 走 Preprint Fallback 流程 |
| Springer 图件返回 200 但 size 0 字节 | 缺浏览器 User-Agent / Referer | 补 `-A "<Chrome UA>" -H "Referer: https://www.nature.com/..."` 重下，核对 `%{size_download}` |
| 图件 `_HTML.jpg` 返回 404 | 该刊只提供 PNG 变体 | 以 Europe PMC XML 里的文件名为准，改用 `_HTML.png` |
| Europe PMC `bin/<file>` 直连 000 / 被拒 | 该路径本机不可达 | 改走 `media.springernature.com/full/springer-static/image/...` |

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `steps` | 搜索论文 → 下载PDF → 验证PDF | 失败时自动回退 Preprint Fallback |

## Proven Scripts

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

| human | bone_marrow | multiple_myeloma | 2026-09-14 | europepmc_fullTextXML_figure_locate.sh | - | - |  |
| human | bone_marrow | multiple_myeloma | 2026-09-14 | europepmc_fullTextXML_figure_locate.sh | - | - |  |
| human | bone_marrow | multiple_myeloma | 2026-09-14 | springernature_figure_download.sh | - | - |  |
| human | bone_marrow | multiple_myeloma | 2026-09-14 | figure_png_to_pdf_300dpi.py | - | - |  |
## References

- Source: MemOmics built-in (v1.1.0)
- Category: 文献搜索
- Language: Python
- 预印本回退策略: `references/preprint-fallback.md`
