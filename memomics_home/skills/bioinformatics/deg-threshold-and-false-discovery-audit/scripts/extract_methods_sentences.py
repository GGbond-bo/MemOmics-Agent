#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 Europe PMC 开放获取全文里抽取「指定关键词」所在的原文句 —— 用于参数溯源。

用途：查「某个数值参数（阈值/分辨率/QC cutoff）到底有没有文献出处」时，
      必须拿到写该参数的那句话本身；摘要与标题不算证据。

用法：
    python extract_methods_sentences.py PMC8479118 PMC7705760 --kw "log2.*fold|threshold|FDR"
    python extract_methods_sentences.py --search 'TITLE:"hurdle model" AND TITLE:"single-cell"'

输出：每条 PMCID 命中的句子（打印到 stdout；可重定向落盘）。

设计约束（勿改）：
  * 不使用 __file__ —— 本脚本会被 execute_python 以 exec(open(...).read()) 方式跑，
    内核不注入 __file__（见 platform-execution-pitfalls）。
  * 只用标准库，无需联网依赖包。
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UA = {"User-Agent": "MemOmics/1.0 (research; parameter provenance)"}


def _get(url, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def search_pmc(query, n=8):
    """按 Europe PMC 检索式拿候选 PMCID。"""
    u = f"{EPMC}/search?query={urllib.parse.quote(query)}&format=json&pageSize={n}&resultType=core"
    d = json.loads(_get(u))
    out = []
    for r in d.get("resultList", {}).get("result", []):
        if r.get("pmcid"):
            out.append({"pmcid": r["pmcid"], "pmid": r.get("pmid"),
                        "year": r.get("pubYear"), "title": r.get("title", "")})
    return out


def fetch_sentences(pmcid, minlen=40):
    """抓全文 XML → 剥标签 → 切句。"""
    xml = _get(f"{EPMC}/{pmcid}/fullTextXML")
    # 去掉参考文献/附录，避免引用列表噪声
    xml = re.sub(r"<(ref-list|back|table-wrap|fig)[^>]*>.*?</\1>", " ", xml, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", xml)
    txt = re.sub(r"&#x[0-9A-Fa-f]+;", " ", txt)
    txt = re.sub(r"&[a-z]+;", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    # 按句切：句号/分号后接大写或括号才切，避免在 0.05 / et al. 处断得过碎
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(])", txt)
    return [p.strip() for p in parts if len(p.strip()) >= minlen]


def main():
    ap = argparse.ArgumentParser(description="Europe PMC 全文句子抽取（参数溯源用）")
    ap.add_argument("pmcids", nargs="*", help="PMCID 列表，如 PMC8479118")
    ap.add_argument("--search", default="", help="改用 Europe PMC 检索式拿候选 PMCID")
    ap.add_argument("--kw", default="", help="关键词正则（默认搜阈值类词）")
    ap.add_argument("--max", type=int, default=30, help="每条 PMCID 最多打印句数")
    ap.add_argument("--sleep", type=float, default=1.0, help="请求间隔秒")
    args = ap.parse_args()

    pat = re.compile(args.kw or
                     r"log2?\s*fold[\s-]*change|log2?FC|logFC|\bthreshold\b|\bcut[\s-]?off\b|"
                     r"adjusted\s*p|FDR|false\s*discovery|Benjamini|resolution|min\.?pct",
                     re.I)

    targets = [{"pmcid": p, "title": ""} for p in args.pmcids]
    if args.search:
        targets += search_pmc(args.search)
    if not targets:
        ap.error("给 PMCID 列表或 --search 检索式")

    seen = set()
    for t in targets:
        pmcid = t["pmcid"]
        if pmcid in seen:
            continue
        seen.add(pmcid)
        print(f"\n===== {pmcid} | PMID {t.get('pmid') or '-'} | {t.get('year') or '-'} =====")
        if t.get("title"):
            print("  ", t["title"][:150])
        try:
            sents = fetch_sentences(pmcid)
        except Exception as e:                      # noqa: BLE001 — 单篇失败不阻断整批
            print(f"  [skip] 抓取失败: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        hits = [s for s in sents if pat.search(s)]
        print(f"  [句子总数 {len(sents)} | 命中 {len(hits)}]")
        for s in hits[: args.max]:
            print("  -", s)
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()