# Preprint Fallback — 付费墙 PDF 下载恢复策略

## 问题场景

`download_pdf()` 返回 `"All download strategies failed"`，原因是：
- 期刊付费墙（Genome Research, Nature, Cell 等）
- Cloudflare 反爬保护
- 代理/VPN 导致 EuropePMC PDF render 不可达

## 恢复流程

### Step 1: 搜索预印本版本

用论文标题调用 `search_papers`，检查 EuropePMC 返回结果：

```python
search_papers(query="<paper title>", max_results=5)
```

在返回的 `papers` 数组中查找 `source: "PPR"` 的条目。PPR = Preprint。

### Step 2: 获取预印本 DOI

PPR 条目通常带 bioRxiv DOI（格式 `10.1101/YYYY.MM.DD.XXXXXX`）。

### Step 3: curl 下载（非 Python requests）

curl 对 Windows 代理环境的处理优于 Python requests：

```bash
curl -L -o "work/papers/<FirstAuthor><Year>_<Topic>.pdf" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  --max-time 180 \
  "https://www.biorxiv.org/content/<preprint_doi>v1.full.pdf"
```

如果 v1 失败，尝试 v2。下载后检查文件大小（通常 > 1MB 才是真 PDF）。

### Step 4: 验证 PDF 页数

`file` 命令可能误判页数（尤其是 Safari 生成的 PDF header），用 Python 确认：

```python
import fitz
doc = fitz.open("path/to/paper.pdf")
print(doc.page_count)  # 真实页数
doc.close()
```

## 成功案例

| 论文 | 期刊 | 正式版 | 预印本 DOI | 结果 |
|------|------|--------|-----------|------|
| Rubenstein et al. 2025 "Muscle fiber-type gene regulatory circuitry" | Genome Research | 10.1101/gr.280051.124 (付费墙) | 10.1101/2023.09.26.558914 | bioRxiv v1, 37 页, 5.3MB ✓ |

### 实际执行记录

```
# Step 1: search_papers 返回 PPR 条目
source: "PPR"
DOI: 10.1101/2023.09.26.558914

# Step 2: curl 下载
curl -L -o "MEMOMICS_HOME/work/papers/Rubenstein2025_Muscle_Multiome_Exercise.pdf" \
  -H "User-Agent: Mozilla/5.0 ... Chrome/120.0.0.0 Safari/537.36" \
  --max-time 180 \
  "https://www.biorxiv.org/content/10.1101/2023.09.26.558914v1.full.pdf"

# 输出: 5.3MB, file 报告 3 页（误判）, fitz 确认 37 页 ✓
```

## 注意事项

- 预印本与正式发表版主要内容一致，但可能缺少同行评审后的修改
- `file` 命令对某些 PDF header（尤其 Safari WebKit 渲染的）不可靠，始终用 fitz 验证
- bioRxiv 也偶有 Cloudflare 保护，但 curl + Chrome UA 通过率远高于 Python requests
- 如果 v1 和 v2 都失败，尝试不带版本号的 `.full.pdf` URL
