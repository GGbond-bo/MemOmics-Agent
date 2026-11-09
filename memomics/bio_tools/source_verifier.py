# -*- coding: utf-8 -*-
"""source_verifier — 文献来源核实（kb-evidence-v3 的 L1 门槛之一）。

只做一件事：判断一个 DOI 是否真实存在、标题是否对得上。
- 数据源：Crossref REST（免 key），必要时可回退 Europe PMC
- 返回三态：True（核实通过）/ False（明确不存在或标题对不上）/ None（无法判断：网络/接口不可用）
- **绝不把 None 当 True**：调用方拿到 None 必须按「未核实」处理（→ L0）
- 不写缓存文件，进程内 memo，避免污染用户目录

用法：
    from memomics.bio_tools.source_verifier import resolve_doi
    ok = resolve_doi("10.1038/s41591-024-03376-x", "An organotypic atlas of human vascular cells")
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

_MEMO = {}
_TITLE_STOP = {"a", "an", "the", "of", "in", "on", "for", "and", "to", "with",
               "from", "by", "at", "as", "is", "are", "human", "cells", "cell"}


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _TITLE_STOP and len(w) > 2}


def _title_match(want: str, got: str) -> bool:
    a, b = _tokens(want), _tokens(got)
    if not a or not b:
        return True  # 没给标题就只核存在性
    return len(a & b) / max(1, min(len(a), len(b))) >= 0.6


def _fetch_crossref(doi: str, timeout: float = 6.0):
    """返回 (status, title)；status ∈ {200, 404, None}。异常/超时 → (None, "")。"""
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "MemOmics-source-verifier/1.0 (mailto:noreply@example.com)",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        titles = (data.get("message") or {}).get("title") or []
        return 200, (titles[0] if titles else "")
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return 404, ""
        return None, ""
    except Exception:
        return None, ""


def resolve_doi(doi: str, title: str = "", *, timeout: float = 6.0, fetcher=None):
    """核实 DOI。True/False/None（None = 判断不了，按未核实处理）。"""
    doi = (doi or "").strip()
    if not doi:
        return False
    key = doi.lower()
    if key in _MEMO:
        return _MEMO[key]
    fetcher = fetcher or _fetch_crossref
    try:
        status, got_title = fetcher(doi, timeout)
    except Exception:
        _MEMO[key] = None
        return None
    if status is None:
        _MEMO[key] = None
        return None
    if status != 200:
        _MEMO[key] = False
        return False
    ok = _title_match(title, got_title)
    _MEMO[key] = ok
    return ok
