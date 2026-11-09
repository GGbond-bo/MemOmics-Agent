# -*- coding: utf-8 -*-
"""Unified evidence ledger for MemOmics evidence-chain adjudication.

The debate engine calls independent domain reviewers. This module turns their
outputs into one compact, auditable ledger instead of showing several long
role essays. It has no network or LLM dependencies and is deliberately kept
separate from the HTTP/orchestration layer.
"""
from __future__ import annotations

import json
import re

SCHEMA = "memomics.evidence-ledger.v1"
_DOMAIN_PREFIX = {
    "biology": "BIO",
    "statistics": "STAT",
    "bioinformatics": "METHOD",
    "history": "HIST",
    "design": "DESIGN",
    "reproducibility": "REPRO",
    "general": "GEN",
}
_VERIFICATION_RANK = {"missing": 0, "unverified": 1, "verified": 2}


def _clean(value, limit=400):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _list(value):
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _json_candidates(text):
    """Yield balanced JSON objects without executing arbitrary model output."""
    for start, ch in enumerate(text):
        if ch != "{":
            continue
        depth, in_string, escaped = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    in_string = False
                continue
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    yield text[start:i + 1]
                    break


def parse_role_payload(content):
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if not text or text.startswith("[reasoning草稿") or "辩论生成失败" in text:
        return {}
    text = text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    for candidate in [text] + list(_json_candidates(text)):
        try:
            obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return {}


def domain_for_role(label, explicit=""):
    if explicit:
        return str(explicit)
    name = str(label or "").lower()
    if "stat" in name:
        return "statistics"
    if "bioinfo" in name or "method" in name:
        return "bioinformatics"
    if "history" in name:
        return "history"
    if "design" in name:
        return "design"
    if "reproduc" in name:
        return "reproducibility"
    if "biology" in name:
        return "biology"
    return "general"


def _hypothesis(value):
    if isinstance(value, dict):
        return _clean(value.get("statement") or value.get("label") or value.get("name") or value.get("id"), 180)
    return _clean(value, 180)


def _hypotheses(value):
    out = []
    for item in _list(value):
        text = _hypothesis(item)
        if text and text not in out:
            out.append(text)
    return out


def _source(item, legacy=""):
    raw = item.get("source")
    source = dict(raw) if isinstance(raw, dict) else {}
    evidence = _clean(legacy or item.get("evidence"), 600)
    source_id = _clean(source.get("id") or source.get("source_id") or item.get("source_id")
                       or item.get("pmid") or item.get("doi") or evidence, 500)
    quote = _clean(source.get("quote_or_value") or source.get("quote") or source.get("value")
                   or item.get("quote_or_value") or item.get("quote") or evidence, 600)
    locator = _clean(source.get("locator") or source.get("location") or item.get("locator"), 240)
    source_type = _clean(source.get("type") or item.get("source_type"), 40)
    if not source_type:
        low = source_id.lower()
        if "pmid" in low or "doi" in low or "10." in low:
            source_type = "paper"
        elif "kb" in low or ".yaml" in low:
            source_type = "kb"
        elif "数据" in source_id or "data" in low or "run" in low:
            source_type = "data"
        elif "推理" in source_id:
            source_type = "reasoning"
        else:
            source_type = "unknown"
    verification = _clean(item.get("verification") or item.get("evidence_status"), 30).lower()
    if verification not in _VERIFICATION_RANK:
        verification = "unverified" if source_id and "推理" not in source_id else "missing"
    if not source_id:
        verification = "missing"
    return {
        "type": source_type,
        "id": source_id,
        "locator": locator,
        "quote_or_value": quote,
    }, verification


def _raw_evidence_items(payload, role):
    """Yield new-schema items and a compatibility conversion of legacy claims."""
    items = payload.get("evidence_items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                yield item, False
        return
    for claim in payload.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        converted = {
            "claim": claim.get("claim") or claim.get("statement"),
            "evidence": claim.get("evidence"),
            "verification": claim.get("verification"),
            "limitations": claim.get("limitations") or claim.get("risk_boundary"),
            "supports": claim.get("supports"),
            "against": claim.get("against"),
        }
        if not converted["supports"] and not converted["against"]:
            if str(role).startswith("pro_"):
                converted["supports"] = ["当前结论"]
            elif str(role).startswith("con_"):
                converted["against"] = ["当前结论"]
        yield converted, True


def _missing(payload):
    out = []
    raw = list(payload.get("missing_evidence") or []) + list(payload.get("needed_evidence") or [])
    for item in raw:
        if isinstance(item, dict):
            what = _clean(item.get("what") or item.get("missing") or item.get("evidence"), 260)
            how = _clean(item.get("how_to_obtain") or item.get("how") or item.get("action"), 320)
            distinguishes = _hypotheses(item.get("distinguishes") or item.get("hypotheses"))
        else:
            what, how, distinguishes = _clean(item, 300), "", []
        if what:
            out.append({"what": what, "how_to_obtain": how, "distinguishes": distinguishes})
    return out


def build_evidence_ledger(role_payloads, judge_obj=None, next_actions=None, decision=""):
    """Build one evidence ledger while preserving every source role.

    role_payloads: {role_label: raw_text | {"content": raw_text, "domain": optional}}
    judge_obj: parsed judge JSON, used only for the assessment fields.
    """
    hypotheses = []
    missing = []
    coverage = []
    merged = {}
    order = []

    for role, payload in (role_payloads or {}).items():
        explicit_domain = payload.get("domain", "") if isinstance(payload, dict) else ""
        raw = payload.get("content", "") if isinstance(payload, dict) else payload
        obj = parse_role_payload(raw)
        domain = domain_for_role(role, explicit_domain)
        role_count = 0
        for item, _legacy in _raw_evidence_items(obj, role):
            claim = _clean(item.get("claim") or item.get("statement"), 360)
            if not claim:
                continue
            source, verification = _source(item, item.get("evidence"))
            supports = _hypotheses(item.get("supports") or item.get("support"))
            against = _hypotheses(item.get("against") or item.get("oppose"))
            limitations = _clean(item.get("limitations") or item.get("risk_boundary"), 320)
            for hyp in supports + against:
                if hyp not in hypotheses:
                    hypotheses.append(hyp)
            key = (claim.casefold(), source["id"].casefold())
            if key not in merged:
                merged[key] = {
                    "domain": domain,
                    "claim": claim,
                    "supports": list(supports),
                    "against": list(against),
                    "source": source,
                    "verification": verification,
                    "limitations": limitations,
                    "source_roles": [],
                }
                order.append(key)
            entry = merged[key]
            entry["supports"] = list(dict.fromkeys(entry["supports"] + supports))
            entry["against"] = list(dict.fromkeys(entry["against"] + against))
            if _VERIFICATION_RANK[verification] > _VERIFICATION_RANK[entry["verification"]]:
                entry["verification"] = verification
            if limitations and limitations not in entry["limitations"]:
                entry["limitations"] = (entry["limitations"] + "；" + limitations).strip("；")[:500]
            if role not in entry["source_roles"]:
                entry["source_roles"].append(role)
            role_count += 1
        for hyp in _hypotheses(obj.get("hypotheses")):
            if hyp not in hypotheses:
                hypotheses.append(hyp)
        missing.extend(_missing(obj))
        coverage.append({"role": role, "domain": domain, "parse_ok": bool(obj),
                         "evidence_count": role_count})

    counters = {}
    items = []
    for key in order:
        entry = merged[key]
        domain = entry["domain"] if entry["domain"] in _DOMAIN_PREFIX else "general"
        prefix = _DOMAIN_PREFIX[domain]
        counters[prefix] = counters.get(prefix, 0) + 1
        entry = dict(entry)
        entry["evidence_id"] = f"{prefix}-{counters[prefix]:02d}"
        entry["domain"] = domain
        items.append(entry)

    # Deduplicate missing-evidence requests without hiding distinct obtaining methods.
    unique_missing = []
    seen_missing = set()
    for item in missing:
        marker = (item["what"].casefold(), item["how_to_obtain"].casefold())
        if marker not in seen_missing:
            seen_missing.add(marker)
            unique_missing.append(item)

    judge_obj = judge_obj if isinstance(judge_obj, dict) else {}
    raw_assessment = judge_obj.get("assessment") if isinstance(judge_obj.get("assessment"), dict) else {}
    verdict = str(judge_obj.get("verdict") or "").lower()
    label = str(raw_assessment.get("label") or "").lower()
    if label not in ("supported", "contradicted", "unresolved"):
        label = {"support": "supported", "ok": "supported", "modify": "contradicted"}.get(verdict, "unresolved")
    valid_ids = {item["evidence_id"] for item in items}
    requested = raw_assessment.get("because") or judge_obj.get("because") or []
    requested = [_clean(x, 40) for x in _list(requested) if _clean(x, 40)]
    because = [x for x in requested if x in valid_ids]
    dropped = [x for x in requested if x not in valid_ids]
    basis_status = "evidence_linked" if because else "missing_evidence_ids"
    if dropped and because:
        basis_status = "partial_evidence_ids"
    if requested and not because:
        basis_status = "invalid_evidence_ids"
        label = "unresolved"
    elif not requested and items:
        # A conclusion without traceable evidence IDs is not a completed adjudication.
        label = "unresolved"
    if not items:
        basis_status = "no_evidence"
        label = "unresolved"
    confidence = _clean(raw_assessment.get("confidence") or judge_obj.get("confidence"), 20).lower()
    preferred = _clean(raw_assessment.get("preferred_hypothesis") or judge_obj.get("preferred_hypothesis"), 220)
    if not preferred:
        preferred = ("暂不判断" if label == "unresolved"
                     else (hypotheses[0] if hypotheses else "未标注"))
    summary = _clean(raw_assessment.get("summary") or judge_obj.get("reasoning") or decision, 500)
    assessment = {
        "label": label,
        "preferred_hypothesis": preferred,
        "confidence": confidence or ("low" if label == "unresolved" else ""),
        "because": because,
        "dropped_references": dropped,
        "basis_status": basis_status,
        "summary": summary,
    }

    plan = []
    for action in next_actions or []:
        if isinstance(action, str):
            plan.append({"action": _clean(action, 400), "owner": "ai", "expected": "",
                         "tool": "", "input": "", "interpretation": "", "blocks": []})
            continue
        if not isinstance(action, dict):
            continue
        plan.append({
            "action": _clean(action.get("action") or action.get("step"), 400),
            "owner": _clean(action.get("owner") or "ai", 20),
            "expected": _clean(action.get("expected") or action.get("result"), 360),
            "tool": _clean(action.get("tool"), 100),
            "input": _clean(action.get("input"), 300),
            "interpretation": _clean(action.get("interpretation"), 400),
            "blocks": [_clean(x, 180) for x in _list(action.get("blocks")) if _clean(x, 180)],
        })

    return {
        "schema": SCHEMA,
        "hypotheses": hypotheses,
        "evidence_items": items,
        "missing_evidence": unique_missing,
        "role_coverage": coverage,
        "assessment": assessment,
        "verification_plan": plan,
        "counts": {
            "hypotheses": len(hypotheses),
            "evidence": len(items),
            "verified": sum(x["verification"] == "verified" for x in items),
            "unverified": sum(x["verification"] == "unverified" for x in items),
            "missing": len(unique_missing),
            "roles": len(coverage),
        },
    }


def attach_evidence_ledger(result, role_payloads, judge_obj=None):
    ledger = build_evidence_ledger(
        role_payloads,
        judge_obj=judge_obj,
        next_actions=result.get("next_actions") or [],
        decision=result.get("decision") or "",
    )
    result["evidence_ledger"] = ledger
    result["assessment"] = ledger["assessment"]
    return ledger


def evidence_ledger_prompt(ledger):
    """Compact JSON injected into the judge; IDs are stable within this debate."""
    payload = {
        "hypotheses": (ledger or {}).get("hypotheses") or [],
        "evidence_items": (ledger or {}).get("evidence_items") or [],
        "missing_evidence": (ledger or {}).get("missing_evidence") or [],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1)
