#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lit_track.py — 文献追踪引擎（无 MCP / 无 cron 的本地实现，零 API key）

子命令：
  search   多源检索（Europe PMC / PubMed / OpenAlex）→ 跨源合并去重 → 骨架词硬门槛 + 排除词过滤
           → 跨运行去重（index.json）→ raw/<date>_candidates.json（含摘要，供 LLM 打分）
  digest   读 LLM 打分结果 raw/<date>_scored.json → 校验六维上限并重算总分
           → raw/<date>_digest.md + notes/<tier>/<AuthorYear_kw>.md + 更新 index.json / runs.jsonl
  status   查看索引规模与历史运行

用法（在放着 config.yaml 的库目录里跑）：
  cd <library>
  python <skill>/scripts/lit_track.py search --days 120 --pool 30     # 首次建库窗口
  python <skill>/scripts/lit_track.py search --days 7   --pool 30     # 日常窗口
  python <skill>/scripts/lit_track.py digest --date 2026-09-25 --top 5
  python <skill>/scripts/lit_track.py status
  也可 export LIT_TRACK_ROOT=<library> 或传 --root <library> 指定库目录。

依赖：Python 3.10+ 标准库 + PyYAML（只用于读 config.yaml）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

UA = "MemOmics-lit-track/1.0 (+https://github.com/GGbond-bo/MemOmics-Agent)"
TIMEOUT = 40
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
OPENALEX = "https://api.openalex.org/works"

ROOT = Path(os.environ.get("LIT_TRACK_ROOT") or Path.cwd()).resolve()
CFG = ROOT / "config.yaml"


def use_root(p: str | None) -> None:
    """重绑库目录（module 级全局，所有函数共用）。"""
    global ROOT, CFG
    if p:
        ROOT = Path(p).resolve()
        CFG = ROOT / "config.yaml"
    (ROOT / "raw").mkdir(parents=True, exist_ok=True)
    (ROOT / "log").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- http
def http_get(url: str, params: dict | None = None, tries: int = 3) -> bytes:
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(clean, safe=":,[]\" ")
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
        except Exception as e:                       # 单源重试，不拖垮整体
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def http_json(url: str, params: dict | None = None) -> dict:
    return json.loads(http_get(url, params).decode("utf-8", "replace"))


def clean(s: str | None) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


# ---------------------------------------------------------------- sources
def search_europepmc(query: str, start: str, end: str, n: int) -> list[dict]:
    """Europe PMC：唯一自带摘要 + 日粒度日期过滤的源（FIRST_PDATE + sort=P_PDATE_D desc）。"""
    q = f'({query}) AND (FIRST_PDATE:[{start} TO {end}])'
    data = http_json(EPMC, {"query": q, "format": "json", "resultType": "core",
                            "pageSize": n, "sort": "P_PDATE_D desc"})
    out = []
    for it in ((data or {}).get("resultList") or {}).get("result") or []:
        ji = it.get("journalInfo") or {}
        j = (ji.get("journal") or {}).get("title") or ""
        out.append({
            "source": "europepmc",
            "pmid": it.get("pmid") or "",
            "doi": (it.get("doi") or "").lower(),
            "title": clean(it.get("title")),
            "abstract": clean(it.get("abstractText")),
            "authors": [a.strip() for a in (it.get("authorString") or "").rstrip(".").split(",") if a.strip()],
            "year": it.get("pubYear") or (ji.get("yearOfPublication") or ""),
            "pub_date": it.get("firstPublicationDate") or ji.get("dateOfPublication") or "",
            "venue": j,
            "citations": it.get("citedByCount"),
            "is_oa": bool(it.get("isOpenAccess") == "Y"),
            "url": f"https://europepmc.org/article/{it.get('source', 'MED')}/{it.get('id', '')}",
        })
    return out


def search_pubmed(query: str, start: str, end: str, n: int) -> list[dict]:
    """PubMed：esearch(日粒度 dp) → efetch XML 取摘要。"""
    p_start, p_end = start.replace("-", "/"), end.replace("-", "/")
    term = f'({query}) AND ("{p_start}"[dp] : "{p_end}"[dp])'
    ids = http_json(EUTILS + "esearch.fcgi", {"db": "pubmed", "term": term, "retmax": n,
                                              "retmode": "json", "sort": "date"})
    idlist = (((ids or {}).get("esearchresult") or {}).get("idlist")) or []
    if not idlist:
        return []
    raw = http_get(EUTILS + "efetch.fcgi", {"db": "pubmed", "id": ",".join(idlist),
                                            "retmode": "xml", "rettype": "abstract"})
    root = ET.fromstring(raw)
    out = []
    for art in root.findall(".//PubmedArticle"):
        def txt(path: str) -> str:
            el = art.find(path)
            return clean("".join(el.itertext())) if el is not None else ""

        pmid = txt(".//MedlineCitation/PMID")
        authors = []
        for a in art.findall(".//AuthorList/Author"):
            ln, ini = a.findtext("LastName"), a.findtext("Initials")
            if ln:
                authors.append(f"{ln} {ini}".strip())
            elif a.findtext("CollectiveName"):
                authors.append(a.findtext("CollectiveName"))
        doi = ""
        # ⚠️ 只认本文自己的 ArticleIdList（PubmedData 下）：用 .//ArticleIdList 会抓到【参考文献】的 DOI
        for aid in art.findall("./PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = (aid.text or "").lower()
                break
        if not doi:
            for el in art.findall(".//Article/ELocationID"):
                if el.get("EIdType") == "doi":
                    doi = clean(el.text).lower()
                    break
        abst = " ".join(clean("".join(x.itertext())) for x in art.findall(".//Abstract/AbstractText"))
        pd = art.find(".//Journal/JournalIssue/PubDate")
        pub_date = ""
        if pd is not None:
            y = pd.findtext("Year") or ""
            m = (pd.findtext("Month") or "").strip()
            d = (pd.findtext("Day") or "").strip()
            if y:
                pub_date = f"{y}-{m or '01'}-{d or '01'}"
        out.append({
            "source": "pubmed", "pmid": pmid, "doi": doi,
            "title": txt(".//Article/ArticleTitle"), "abstract": abst, "authors": authors,
            "year": (pub_date[:4] if pub_date else ""), "pub_date": pub_date,
            "venue": txt(".//Journal/Title"), "citations": None,
            "is_oa": False, "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })
    return out


def search_openalex(query: str, start: str, end: str, n: int) -> list[dict]:
    """OpenAlex：覆盖最广（引用数 / OA 链接），摘要为倒排索引需还原。"""
    flt = f"from_publication_date:{start},to_publication_date:{end}"
    data = http_json(OPENALEX, {"search": query, "filter": flt, "per-page": n,
                                "sort": "publication_date:desc"})
    out = []
    for it in (data or {}).get("results") or []:
        inv = it.get("abstract_inverted_index")
        abst = ""
        if inv:
            pos = {}
            for w, idxs in inv.items():
                for i in idxs:
                    pos[i] = w
            abst = " ".join(pos[k] for k in sorted(pos))
        loc = it.get("primary_location") or {}
        src = loc.get("source") or {}
        out.append({
            "source": "openalex",
            "pmid": (it.get("ids") or {}).get("pmid", "").rsplit("/", 1)[-1],
            "doi": (it.get("doi") or "").replace("https://doi.org/", "").lower(),
            "title": clean(it.get("title")),
            "abstract": abst,
            "authors": [((a.get("author") or {}).get("display_name") or "") for a in (it.get("authorships") or [])],
            "year": it.get("publication_year") or "",
            "pub_date": it.get("publication_date") or "",
            "venue": src.get("display_name") or "",
            "citations": it.get("cited_by_count"),
            "is_oa": bool((it.get("open_access") or {}).get("is_oa")),
            "url": loc.get("landing_page_url") or it.get("id") or "",
        })
    return out


SOURCES = {"europepmc": search_europepmc, "pubmed": search_pubmed, "openalex": search_openalex}


# ---------------------------------------------------------------- merge / filter
def merge(records: list[dict]) -> list[dict]:
    """DOI > PMID > 归一化标题 三键合并；保留摘要最长者，并集 id / 源 / 引用数。"""
    buckets: dict[str, dict] = {}
    for r in records:
        keys = [k for k in ("doi:" + r["doi"] if r.get("doi") else "",
                            "pmid:" + str(r["pmid"]) if r.get("pmid") else "",
                            "t:" + norm_title(r.get("title"))) if k]
        if not keys:
            continue
        hit = next((k for k in keys if k in buckets), None)
        if hit is None:
            m = dict(r)
            m["sources"] = [r["source"]]
            buckets[keys[0]] = m
            for k in keys[1:]:
                buckets[k] = buckets[keys[0]]
        else:
            m = buckets[hit]
            m["sources"] = sorted(set(m.get("sources", []) + [r["source"]]))
            for f in ("doi", "pmid", "url", "venue", "pub_date"):
                if not m.get(f) and r.get(f):
                    m[f] = r[f]
            if len(r.get("abstract") or "") > len(m.get("abstract") or ""):
                m["abstract"] = r["abstract"]
            if (r.get("citations") or 0) > (m.get("citations") or 0):
                m["citations"] = r["citations"]
            m["is_oa"] = m.get("is_oa") or r.get("is_oa", False)
    seen, uniq = set(), []
    for m in buckets.values():
        if id(m) in seen:
            continue
        seen.add(id(m))
        uniq.append(m)
    return uniq


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def load_index() -> dict:
    p = ROOT / "index.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"updated": "", "seen": {}}


def index_keys(r: dict) -> list[str]:
    return [k for k in ("doi:" + r["doi"] if r.get("doi") else "",
                        "pmid:" + str(r["pmid"]) if r.get("pmid") else "",
                        "t:" + norm_title(r.get("title"))) if k]


def applies(record_text: str, cfg: dict) -> bool:
    """排除词过滤；命中 strong_keep 白名单可豁免。"""
    kws = cfg["keywords"]
    low = record_text.lower()
    if any(x.lower() in low for x in kws.get("exclude", [])):
        return any(x.lower() in low for x in kws.get("strong_keep", []))
    return True


def must_match(text: str, cfg: dict) -> bool:
    """骨架词硬门槛：标题+摘要至少命中一个，否则视为跨领域串味直接丢弃。"""
    terms = cfg["keywords"].get("must_match_any") or []
    if not terms:
        return True
    low = text.lower()
    return any(t.lower() in low for t in terms)


def relevance_hint(text: str, cfg: dict) -> int:
    low = text.lower()
    return sum(1 for k in cfg["keywords"].get("include", []) if k.lower() in low)


# ---------------------------------------------------------------- search cmd
def cmd_search(args) -> int:
    use_root(args.root)
    cfg = load_cfg()
    today = args.date or dt.date.today().isoformat()
    days = args.days or cfg["search"]["lookback_days"]["daily"]
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=days)).isoformat()
    pool = args.pool or cfg["search"]["candidate_pool_size"]
    queries = args.query or cfg["keywords"]["queries"]
    srcs = [s for s in (args.sources.split(",") if args.sources else cfg["search"]["sources"]) if s in SOURCES]
    per = max(6, pool // max(1, len(queries)))

    all_rec, errors = [], []
    for q in queries:
        for s in srcs:
            try:
                recs = SOURCES[s](q, start, today, per)
                print(f"  [{s:10s}] {len(recs):3d} 条  q={q[:52]}", file=sys.stderr)
                all_rec += recs
            except Exception as e:
                errors.append(f"{s}: {type(e).__name__}: {e}")
                print(f"  [{s:10s}] FAIL {type(e).__name__}: {e}", file=sys.stderr)

    merged = merge(all_rec)
    keep = [r for r in merged if applies(f"{r.get('title', '')} {r.get('abstract', '')}", cfg)
            and must_match(f"{r.get('title', '')} {r.get('abstract', '')}", cfg)]
    for r in keep:
        r["relevance_hint"] = relevance_hint(f"{r.get('title', '')} {r.get('abstract', '')}", cfg)
    keep.sort(key=lambda r: (r["relevance_hint"], r.get("pub_date") or "", r.get("citations") or 0), reverse=True)

    idx = load_index()
    seen = idx["seen"]
    fresh, dup = [], 0
    for r in keep:
        if any(k in seen for k in index_keys(r)):
            dup += 1
            continue
        r["uid"] = index_keys(r)[0]
        fresh.append(r)
    fresh = fresh[:pool]

    out = {"date": today, "window": [start, today], "days": days, "sources": srcs,
           "queries": queries, "raw_hits": len(all_rec), "merged": len(merged),
           "kept": len(keep), "already_seen": dup, "candidates": len(fresh),
           "errors": errors, "records": fresh}
    path = ROOT / "raw" / f"{today}_candidates.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n检索完成 {start} → {today}（{days} 天）")
    print(f"原始 {len(all_rec)} → 合并去重 {len(merged)} → 过滤后 {len(keep)} → 跨运行新文献 {len(fresh)}（历史已见 {dup}）")
    print(f"候选池: {path}")
    if errors:
        print("源失败: " + "; ".join(errors))
    print("-" * 130)
    for i, r in enumerate(fresh, 1):
        au = (r["authors"][0] if r["authors"] else "?")
        au = re.sub(r"\s.*", "", au)
        print(f"[{i:2d}] {r.get('pub_date') or r.get('year')} | {au} | {(r.get('venue') or '-')[:30]} "
              f"| cite={r.get('citations') if r.get('citations') is not None else '-'} | rel={r['relevance_hint']} "
              f"| src={','.join(r['sources'])}")
        print(f"     {r['title'][:150]}")
        print(f"     {(r.get('abstract') or '(无摘要)')[:260]}")
    print("-" * 130)
    print(f"候选 {len(fresh)} 条（无摘要 {sum(1 for r in fresh if not r.get('abstract'))} 条）")
    return 0 if fresh else 2


# ---------------------------------------------------------------- digest cmd
def render_digest(scored: dict, resolve, top: int) -> str:
    papers = sorted(scored["papers"], key=lambda p: p.get("score", 0), reverse=True)[:top]
    L = [f"📅 {scored['date']} 文献日报 | {scored.get('field_zh', '')}",
         f"候选池 {scored.get('candidates', '?')} → 精读 {len(papers)} | "
         f"窗口 {scored.get('window', ['', ''])[0]} ~ {scored.get('window', ['', ''])[1]}", ""]
    for rank, p in enumerate(papers, 1):
        r = resolve(p)
        au = r.get("authors") or []
        aus = (", ".join(au[:3]) + (" et al." if len(au) > 3 else "")) if au else "-"
        ids = " | ".join(x for x in [f"DOI: {r.get('doi')}" if r.get("doi") else "",
                                     f"PMID: {r.get('pmid')}" if r.get("pmid") else ""] if x)
        L += ["━━━━━━━━━━━━━━━━━━━━",
              f"🏅 #{rank} | {r.get('title')}",
              f"{r.get('venue') or '-'}, {r.get('year') or '-'} | {aus} | ⭐ {p['score'] / 10:.1f}/10 | "
              f"分流：{p.get('tier', '-')} | 阅读深度：{p.get('reading_depth', 'Abstract only')}",
              (ids or "") + (f" | {r.get('url')}" if r.get("url") else ""),
              "", f"💡 一句话：{p.get('takeaway', '')}",
              f"🔬 方法：{p.get('methods', '')}"]
        kr = p.get("key_results") or []
        L.append("📊 关键结果：")
        L += [f"  · {x}" for x in kr] if kr else ["  · (摘要未给具体数值)"]
        L += [f"🧭 点评：{p.get('commentary', '')}",
              f"📎 {r.get('url') or ('https://doi.org/' + r.get('doi', ''))}", ""]
    return "\n".join(L)


def write_note(p: dict, r: dict, cfg: dict, date: str) -> str:
    tier = p.get("tier", "E_暂存低优先")
    if tier not in cfg["tiers"]:
        tier = "E_暂存低优先"
    au = r.get("authors") or []
    first = re.sub(r"[^A-Za-z\-]", "", (au[0].split(",")[0] if au else "Anon").split()[0]) or "Anon"
    kws = "_".join([re.sub(r"[^\w\u4e00-\u9fa5]", "", t) for t in (p.get("tags") or ["文献"])[:3]])
    fname = f"{first}{r.get('year') or ''}_{kws}.md"
    d = ROOT / "notes" / tier
    d.mkdir(parents=True, exist_ok=True)
    path = d / fname
    if path.exists():
        path = d / f"{first}{r.get('year') or ''}_{kws}_{date.replace('-', '')}.md"
    ns = p.get("note_sections") or {}
    body = (f"---\n"
            f"title: \"{r.get('title', '')}\"\n"
            f"authors: \"{'; '.join(au[:3])}{' et al.' if len(au) > 3 else ''}\"\n"
            f"year: {r.get('year') or ''}\n"
            f"journal: \"{r.get('venue', '')}\"\n"
            f"doi: \"{r.get('doi', '')}\"\n"
            f"pmid: \"{r.get('pmid', '')}\"\n"
            f"classification: \"{tier}\"\n"
            f"score: {p.get('score', 0)}\n"
            f"reading_depth: \"{p.get('reading_depth', 'Abstract only')}\"\n"
            f"tags: [{', '.join(p.get('tags') or [])}]\n"
            f"date_read: {date}\n---\n\n"
            f"## 核心主张\n{ns.get('核心主张', p.get('takeaway', ''))}\n\n"
            f"## 方法\n{ns.get('方法', p.get('methods', ''))}\n\n"
            f"## 关键发现\n" + "\n".join(f"- {x}" for x in (p.get('key_results') or [])) + "\n\n"
            f"## 批判\n{ns.get('批判', '')}\n\n"
            f"## Connection to Research\n{ns.get('Connection to Research', '')}\n\n"
            f"## 下一步\n{ns.get('下一步', '')}\n")
    path.write_text(body, encoding="utf-8")
    return str(path.relative_to(ROOT)).replace("\\", "/")


def cmd_digest(args) -> int:
    use_root(args.root)
    cfg = load_cfg()
    cand_path = ROOT / "raw" / f"{args.date}_candidates.json"
    scored_path = ROOT / "raw" / f"{args.date}_scored.json"
    for p in (cand_path, scored_path):
        if not p.exists():
            print(f"[error] 缺少 {p}", file=sys.stderr)
            return 2
    cand = json.loads(cand_path.read_text(encoding="utf-8"))
    scored = json.loads(scored_path.read_text(encoding="utf-8"))
    records = {r["uid"]: r for r in cand["records"]}
    by_title = {norm_title(r.get("title")): r for r in cand["records"]}

    def resolve(p: dict) -> dict:
        """uid 优先，缺失或对不上时按归一化标题兜底（防源元数据漂移导致静默丢文献）。"""
        return records.get(p.get("uid")) or by_title.get(norm_title(p.get("title"))) or {}

    scored.setdefault("date", args.date)
    scored["window"] = cand.get("window", ["", ""])
    scored["candidates"] = cand.get("candidates", len(records))

    top = args.top or cfg["search"]["final_selection_count"]
    papers = sorted(scored["papers"], key=lambda p: p.get("score", 0), reverse=True)[:top]

    # 六维上限校验后重算总分（防打分虚高）
    W = cfg["scoring"]["weights"]
    for p in scored["papers"]:
        s = p.get("scores") or {}
        for k, cap in W.items():
            if s.get(k, 0) > cap:
                print(f"[warn] {p.get('uid')} 维度 {k}={s[k]} 超上限 {cap}，已截断", file=sys.stderr)
                s[k] = cap
        if s:
            p["score"] = sum(s.values())
        p["score"] = min(p.get("score", 0), 100)

    for p in papers:
        r = resolve(p)
        if r and p.get("tier"):
            p["note_file"] = write_note(p, r, cfg, args.date)

    digest = render_digest(scored, resolve, top)
    dpath = ROOT / "raw" / f"{args.date}_digest.md"
    dpath.write_text(digest, encoding="utf-8")

    idx = load_index()
    for p in scored["papers"]:
        r = resolve(p)
        entry = {"title": r.get("title", ""), "first_seen": args.date, "score": p.get("score"),
                 "tier": p.get("tier", ""), "doi": r.get("doi", ""), "pmid": r.get("pmid", ""),
                 "note": p.get("note_file", "")}
        for k in index_keys({"doi": r.get("doi"), "pmid": r.get("pmid"), "title": r.get("title")}):
            idx["seen"][k] = entry
    idx["updated"] = args.date
    (ROOT / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    with (ROOT / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"date": args.date, "mode": "manual", "window": cand["window"],
                            "raw_hits": cand["raw_hits"], "merged": cand["merged"],
                            "candidates": cand["candidates"], "scored": len(scored["papers"]),
                            "delivered": len(papers),
                            "digest": str(dpath.relative_to(ROOT)).replace("\\", "/"),
                            "errors": cand.get("errors", [])}, ensure_ascii=False) + "\n")

    print(f"日报: {dpath}")
    print("笔记: " + (", ".join(p.get("note_file", "") for p in papers if p.get("note_file")) or "(无)"))
    print(f"索引累计: {len(idx['seen'])} 个键")
    return 0


def cmd_status(args) -> int:
    use_root(args.root)
    idx = load_index()
    runs = []
    rp = ROOT / "runs.jsonl"
    if rp.exists():
        runs = [json.loads(x) for x in rp.read_text(encoding="utf-8").splitlines() if x.strip()]
    uniq = {json.dumps(v, sort_keys=True, ensure_ascii=False) for v in idx["seen"].values()}
    notes = list((ROOT / "notes").rglob("*.md")) if (ROOT / "notes").exists() else []
    print(f"库目录: {ROOT}")
    print(f"索引键 {len(idx['seen'])} → 去重后唯一文献 {len(uniq)} 篇（updated {idx['updated'] or '-'}）")
    print(f"笔记 {len(notes)} 篇 | 运行记录 {len(runs)} 次")
    for r in runs[-10:]:
        print(f"  {r['date']} 候选{r['candidates']:3d} 精读{r['delivered']} → {r['digest']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="文献追踪引擎（本地，无 MCP / 无 cron）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_root(p):
        p.add_argument("--root", default=None, help="库目录（默认取 LIT_TRACK_ROOT 或当前目录）")

    p = sub.add_parser("search")
    add_root(p)
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--pool", type=int, default=None)
    p.add_argument("--date", default=None)
    p.add_argument("--sources", default=None)
    p.add_argument("--query", action="append", default=None)
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("digest")
    add_root(p)
    p.add_argument("--date", required=True)
    p.add_argument("--top", type=int, default=None)
    p.set_defaults(fn=cmd_digest)

    p = sub.add_parser("status")
    add_root(p)
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())