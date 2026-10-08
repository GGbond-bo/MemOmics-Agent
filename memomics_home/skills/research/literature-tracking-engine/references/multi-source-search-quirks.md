# 多源检索的真实语法与坑（Europe PMC / PubMed / OpenAlex）

零 API key 即可跑；本机实测三源直连可达（无需代理环境变量）。
本文件记录的是**实际踩过的坑**，不是上游文档的镜像。

## 1. Europe PMC —— 首选主力源

```
GET https://www.ebi.ac.uk/europepmc/webservices/rest/search
    ?query=(<q>) AND (FIRST_PDATE:[<YYYY-MM-DD> TO <YYYY-MM-DD>])
    &format=json&resultType=core&pageSize=<n>&sort=P_PDATE_D desc
```

- **唯一同时满足「自带摘要」+「日粒度日期过滤」+「零 key」的源** → 用它做主检索，另两源扩召回。
- 摘要字段 `abstractText`；标题/摘要都可能带 HTML 实体与标签 → 统一 `re.sub(r"<[^>]+>", " ")` + 折叠空白。
- 有用字段：`firstPublicationDate`（日粒度）、`citedByCount`、`isOpenAccess`、`journalInfo.journal.title`、`authorString`（逗号分隔，注意末尾句点）。
- 排序 `P_PDATE_D desc`（URL 编码时空格要保留，`urlencode(safe=":,[]\" ")` 里已含空格）。

## 2. PubMed —— 补召回 + 唯一可靠的 PMID

```
esearch: ?db=pubmed&term=(<q>) AND ("YYYY/MM/DD"[dp] : "YYYY/MM/DD"[dp])&retmax=<n>&retmode=json&sort=date
efetch:  ?db=pubmed&id=<逗号分隔 PMID>&retmode=xml&rettype=abstract
```

- ⚠️ **日粒度日期必须写成 `YYYY/MM/DD`（斜杠）**，写 `YYYY-MM-DD` 在 `[dp]` 里不生效。
- ⚠️ **esummary 不返回摘要**（`lit_bridge.py` 的 pubmed 源就只有题录）；要摘要必须走 efetch XML。
- 🔴 **参考文献 DOI 陷阱（本会话真实事故）**：解析 `art.findall(".//ArticleIdList/ArticleId")` 会**连参考文献的
  ArticleIdList 一起抓**，当本文自身的 DOI 缺失时就抓到某一篇引文的 DOI。实测后果：人骨骼肌图谱（EBioMedicine）
  被打上了 `10.1007/s00401-023-02637-2`（一篇 Acta Neuropathologica 的 DOI）→ 去重键、引用、笔记 frontmatter 全错。
  **正确写法**：
  ```python
  for aid in art.findall("./PubmedData/ArticleIdList/ArticleId"):   # 只认本文自己的
      if aid.get("IdType") == "doi": doi = aid.text.lower(); break
  if not doi:                                                       # 兜底：Article/ELocationID
      for el in art.findall(".//Article/ELocationID"):
          if el.get("EIdType") == "doi": doi = clean(el.text).lower(); break
  ```
- 标题含 `<i>`/`<sub>` 等内联标签 → 用 `"".join(el.itertext())` 再 clean，别用 `.text`。
- 出版日期在 `Journal/JournalIssue/PubDate`（Year/Month/Day，Month 可能是 `Aug` 或 `08`），
  也可能是 `MedlineDate`（跨月/跨年）；缺失时退回 `PubmedData/History`。

## 3. OpenAlex —— 覆盖最广 + 引用数

```
GET https://api.openalex.org/works
    ?search=<q>&filter=from_publication_date:<YYYY-MM-DD>,to_publication_date:<YYYY-MM-DD>
    &per-page=<n>&sort=publication_date:desc
```

- 摘要是 **倒排索引** `abstract_inverted_index`（word → [positions]），需还原：按位置排序再 join。
- `ids.pmid` 是 URL（`https://pubmed.ncbi.nlm.nih.gov/xxx`）→ 取最后一段。
- `cited_by_count` 是三源里唯一的引用数来源；`primary_location.source.display_name` 是期刊名。
- ⚠️ **publication_date 可能不是首版日期**：实测一篇 2024 年的 FEBS J 论文（PMID 38464282）
  被 OpenAlex 报成 `2026-09-21`（版本/收录更新）。所以 `pub_date` 只能当"新事"信号，
  **引用前必须用 PMID/DOI 复核**（`lit_bridge.py paper <id>` 或 `cite <id>` 可直接查）。

## 4. 合并与去重的设计理由

- 三源 id 覆盖不同：EPMC 全（doi+pmid）、PubMed 有 pmid（doi 可能缺）、OpenAlex 有 doi（pmid 可能缺）。
- 合并键优先级 **DOI → PMID → 归一化标题**（`re.sub(r"[^a-z0-9]+","",t.lower())`）；
  合并时保留**摘要最长**的记录，并集 `sources` / id / 引用数 —— 否则会把有摘要的版本丢掉。
- 归一化标题做键要小心：标题里非 ASCII 连字符（`‐`）、希腊字母会被剥掉，但两侧记录通常同源同写，够用。

## 5. 跨运行去重索引用法（index.json）

```json
{"updated": "2026-09-25",
 "seen": {"doi:10.1016/j.arr.2026.103272": {"title": "...", "first_seen": "2026-09-25",
          "score": 84, "tier": "A_核心主线", "doi": "...", "pmid": "...", "note": "notes/A_核心主线/xxx.md"}}}
```
- 三个键（doi: / pmid: / t:）都写进 `seen`，任何一个命中即视为已见 → 新的一轮只推真正的新文献。
- 打分文件与候选池可能对不上（源改版本、DOI 被修正），digest 阶段必须 **uid 优先 + 归一化标题兜底**，
  否则日报会静默丢文献。

## 6. 噪声样本与门控（实测）

首跑（窗口 120 天）三源原始 74 条 → 合并 57 → 过滤 22。仅靠 include/exclude 词表时，
以下三类都混进了候选池，**必须靠 `must_match_any` 骨架词硬门槛 + `topic<10` 否决门**才挡得住：

| 噪声 | 为什么被召回 |
|------|-------------|
| 巨噬细胞/纤维化社论（Front Immunol） | 摘要里出现 skeletal muscle |
| 重症肌无力精准治疗综述 | 出现"骨骼肌无力 / neuromuscular"措辞 |
| 高原鱼类 small RNA 数据集（Sci Data） | 含 muscle / gills / skin 关键词 |

处理：门控否决后仍**保留 E 类记录**（附否决理由），下次调词表时有据可依；
汇报时单列"进了池子但被否决的噪声 + 排除词建议"给用户。

## 7. 与既有脚本的关系（避免重复造轮子）

- `nature-academic-search/scripts/lit_bridge.py`：同样是零依赖多源桥（`search` / `paper` / `cite` / `mesh`），
  **适合一次性查询、取单篇元数据、生成引用（APA/GB-T7714/BibTeX/RIS）**；
  但它的 `--year-from` 只到**年粒度**，不适合"最近 7 天"的追踪。→ 追踪用本技能的 `lit_track.py`，
  查单篇/要引用格式时调 `lit_bridge.py`。
- `nature-literature-pipeline`：给的是方法论（六维打分、推送格式、笔记模板、cron 说明，偏 Feishu/MCP 场景）；
  本技能是它的**本地可运行版**，两份的笔记模板与分类口径保持一致（A_核心主线 … E_暂存低优先）。

## 8. 跑完怎么自检（不要凭感觉说"跑通了"）

```bash
python scripts/lit_track.py status                     # 索引键数 / 唯一文献数 / 笔记数 / 运行记录
python - <<'PY'
import json; d=json.load(open('raw/<date>_candidates.json',encoding='utf-8'))
print(d['raw_hits'], d['merged'], d['kept'], d['candidates'], d['errors'])
for r in d['records'][:3]: print(r['uid'], r.get('pmid'), r['title'][:60])   # 抽查 id 是否自洽
PY
```
抽查要点：① `errors` 为空或有失败源（照实汇报）；② DOI↔PMID 是否指向同一篇（防参考文献 DOI 老坑）；
③ 无摘要条数（`reading_depth` 只能标 Metadata only，不能假装精读过）。