# download_pdf 反爬/订阅墙：判定与批量开放获取下载

> 实测：2026-09-11 跨物种专利文献支撑任务（14 篇落盘，9 篇经 EuropePMC 批量抓取）
> 适用：任何"一次要下 10–30 篇文献"的场景（专利文书、毕业论文、方法学综述）

## 1. 核心认知：先判定，再下结论

`download_pdf` 全策略失败有**两种完全不同的原因**，处置方式相反：

| 原因 | 表现 | 处置 |
|---|---|---|
| **出版商反爬** | Cloudflare/JS check、返回 HTML、httpx+urllib+scrapling 全失败 | 换开放源（PMC render / Unpaywall / bioRxiv） |
| **文章本身就是订阅内容** | EuropePMC `isOpenAccess=N`、无 `pmcid`、Unpaywall 无免费版 | **换源也没用** → 归入"需机构获取"，如实报告 |

2026-09-11 实测反爬命中：Nature Genetics / Nature / Science / Wiley / Cell(Elsevier)。
**不要靠"试了 4 种策略都失败"来推断订阅** —— 直接查 OA 状态，一次定性。

## 2. OA 状态查询（EuropePMC REST，无需 key）

```python
u = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:{pmid}&format=json&resultType=core"
r = json.loads(get(u))["resultList"]["result"][0]
r.get("isOpenAccess")   # 'Y' / 'N'
r.get("pmcid")          # 'PMCxxxxxxxx' 或 None
```

## 3. 开放全文抓取（按优先级）

```
① PDF   https://europepmc.org/articles/<PMCID>?pdf=render        # 校验 b[:4]==b"%PDF" and len>20000
② XML   https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML   # 校验 b[:5]==b"<?xml"
③ Unpaywall  https://api.unpaywall.org/v2/<DOI>?email=...        # → best_oa_location.url_for_pdf
④ bioRxiv     https://www.biorxiv.org/content/<10.1101/DOI>v1.full.pdf   （见 paper-download 的 preprint-fallback）
```

前置：`ssl.create_default_context()` 关掉证书校验（本机 schannel 证书吊销链易超时），UA 用常规浏览器串。

## 4. 批量执行模板（整批一次 `execute_code`，不要 N 次工具调用）

```python
batch = [ (输出名, PMCID 或 DOI, 目标子目录), ... ]
for name, key, sub in batch:
    if os.path.exists(p) and os.path.getsize(p) > 20000:   # 断点续跑：已存在即跳过
        ok.append((name, "cached", size)); continue
    for u in [pmc_render_url, fullTextXML_url, unpaywall_url]:
        ...
    time.sleep(0.6)     # 温和限速
print(状态回执：成功/失败逐条)
```

关键点：**已存在文件先跳过**（中断后可重跑）、**逐条打印状态回执**（用户要看到哪些成了哪些没成）。

## 5. 订阅内容的交付写法（诚实边界）

失败条目 **不隐藏、不糊弄**，单列一节：

| 文献 | DOI / PMID | 目标目录 | 备注 |
|---|---|---|---|
| de Mendoza 2025 *Nat Genet* News & Views | 10.1038/s41588-025-02194-2 / 40425825 | `01_现有技术对标` | 1 页评述 |

并写明：正规获取途径（图书馆 / 机构 VPN / 文献互助）。
**⛔ 不提供、不尝试任何绕过版权的方式** —— 这句话要显式写进交付件和汇报。

## 6. 已下载文件的附带价值

`download_pdf` 成功时会自动：
- 在同目录写 `.pdf_index.json`（doi + sha256 + 下载时间）→ 文件完整性可校验
- 进全局文献库 `hermes_home/papers/`（Crossref 元数据 + 去重）
- 注册进引用库 `references/library.json` → `save_reference(action="export")` 出 BibTeX/RIS 供 Zotero 导入

交付时说明这三项，用户可直接毕业论文引用。
