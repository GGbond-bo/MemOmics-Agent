# 为论文批量补充背景文献（含出版商 403 时的 OA 路径）

触发场景：论文交付后用户说"多下载一些文献"、"再补充补充背景"。此时往往要一次拿下 15–30 篇，`download_pdf` 单篇调用会被出版商反爬拦掉一大半。

## 一、先搜后下：把"下载"当成"检索 → 核验 → 落盘"三步

1. **多主题并行检索**：按论文章节拆主题（本类论文典型 6 类：衰老标志/表观遗传、ATAC 方法学、顺式调控元件注释与保守性、衰老相关可及性、跨物种调控元件比较、非灵长类模型与标志物），每个主题一次 `search_papers`，一轮并行发出去。
2. **只要带 PMID/DOI 的条目**：写进参考文献的每一条都必须能回查。`search_papers` 返回的 `pmid` / `doi` / `pmcid` / `pdf_url` 全部记下。
3. **经典奠基文献单独补检**：原始方法学论文（如 ATAC-seq 原始方法、phyloP、衰老标志、甲基化时钟）在关键词检索里常常漏掉，用 `query_ncbi(db="pubmed", query="<标题全称>")` 直接命中，拿到准确 PMID/DOI/卷期。

> 铁律：**检索没命中的，宁可说没找到，也不要凭记忆写引用。** 凭记忆填 PMID/卷期是这类任务最严重的错误。

## 二、下载失败的真实归因（先诊断，再换方案）

批量下载全失败时，按下面顺序排除，**不要连着重试同一命令**：

| 现象 | 真实原因 | 处置 |
|---|---|---|
| `curl: (35) schannel: next InitializeSecurityContext failed: CRYPT_E_REVOCATION_OFFLINE` | Windows curl 走 schannel，**证书吊销检查离线导致 TLS 握手失败**；同机 Python requests 走 OpenSSL 正常 | 换 **Python requests**。这**不是**网络不通，也**不是**站点反爬——别据此下"网络被墙/站点不可达"的结论 |
| 返回 403，body 几 KB 的挑战页 | 出版商反爬（Elsevier / Wiley / MDPI / Science / Cell Press / aging-us / cshlp 等） | 走下面第三节的 OA 路径 |
| `pmc.ncbi.nlm.nih.gov/articles/PMCxxx/pdf/` 返回 **200** 但只有 ~20KB | 拿到的是 **HTML 不是 PDF** | 必须校验魔数 `content[:4] == b"%PDF"`；200 不等于成功 |
| `europepmc.org/articles/PMCxxx?pdf=render` 返回 403 | 该 render 端点被拦（**与 Europe PMC 的 REST 服务不是同一个主机**） | 用 `www.ebi.ac.uk/europepmc/webservices/rest/...`（实测 200） |
| `www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMCxxx` 返回 404 | 该文不在 PMC OA 子集内 | 换 Unpaywall |

## 三、两条已验证的 OA 路径

### 1. Unpaywall API → 合法 OA 版 PDF

```python
import requests
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                  "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8"})
r = S.get(f"https://api.unpaywall.org/v2/{doi}?email=research@example.org", timeout=30)
loc = (r.json().get("best_oa_location") or {})
for u in (loc.get("url_for_pdf"), loc.get("url")):      # url_for_pdf 优先，url 兜底
    d = S.get(u, timeout=45, allow_redirects=True)
    if d.status_code == 200 and d.content[:4] == b"%PDF" and len(d.content) > 40000:
        open(f"{slug}.pdf", "wb").write(d.content); break
```

### 2. Europe PMC REST 全文 XML（PDF 拿不到时的正解）

```
https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML
```

- 实测 200，**与 `europepmc.org/articles/...?pdf=render` 是不同服务**——后者 403 不代表这条路不通。
- 返回 JATS 全文 XML（正文 + 摘要 + 图注），**内容可核验、足以支撑引用与背景综述写作**。
- 落盘到 `work/papers/pmc_xml/<作者年份_主题>.xml`，与 PDF 分开存放。
- 抽标题/摘要：先 `re.sub(r'<[^>]+>', ' ', x)` 去标签，再 `html.unescape`，最后压空白。

### 3. 明确不可得时就如实说明

MDPI / Frontiers / eLife 等虽为 OA，但直链 PDF 仍可能 403（需要浏览器 cookie）。全部路径失败时：
**如实告知"哪些篇目的 PDF 没拿到"，并给出手动下载指引**，不要为了凑数伪造下载成功。已拿到的全文 XML 照样可用于写作与引用。

## 四、脚本骨架（一次批量跑完，输出成功/失败清单）

```python
for pmc, doi, slug in ITEMS:
    # A) Unpaywall → PDF
    ...  # 见上
    # B) Europe PMC → 全文 XML（PDF 失败时的兜底，仍算"有内容"）
    r2 = S.get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML", timeout=40)
    if r2.status_code == 200 and len(r2.content) > 20000:
        open(os.path.join(XOUT, slug + ".xml"), "wb").write(r2.content)
    time.sleep(0.3)          # 别把 API 打爆
# 最后必须打印三份清单：PDF 成功 / 仅 XML / 全失败
```

**收尾动作**：把新增文献用 `save_reference(action="add")` 收录，`save_reference(action="export")` 确认 .bib 路径；写进论文的每条引用都要能在 PubMed/EuropePMC 通过 PMID 或 DOI 直接核验。

## 五、实测战绩参照（2026-09 一次 36 篇的补文献任务）

| 路径 | 结果 |
|---|---|
| `download_pdf`（Publisher/BMC 类） | 仅 BMC/Genome Biology 系成功（1 篇） |
| Unpaywall → PDF | 3 篇（Nature Communications / Genome Biology / Frontiers 系） |
| Europe PMC fullTextXML | **13 篇**（含 Science Advances、Genome Research、MBE、Nat Commun 等） |
| 全部路径失败 | 6 篇（Cell Press / MDPI / aging-us / cshlp 硬拦）→ 如实报告 |

**结论：Europe PMC REST 是批量补文献的主力，不是兜底。**
