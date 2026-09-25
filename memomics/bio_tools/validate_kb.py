# -*- coding: utf-8 -*-
"""知识库门禁：validate_kb —— 结构体检 + 回归基线（memomics/knowledge_base）。

为什么需要
----------
KB 里的 YAML 是**多来源、多代际**写进来的：早期 seed、literature 抽取、data_driven 经验回写
（skill_evolution）、chem/pathway 抽取器各有各的字段。结果是：
- 同一个语义字段四五种写法（source 25 种写法，其中 10+ 是自然语言长句）；
- name / 文件名 / auto_trigger 三者不一致，检索命中靠运气；
- evidence 里写着 DOI/PMID 但没结构化成字段，去重与引用回填无从下手；
- 个别文件出现过 YAML 列表「漏进」字符串字段（value 里带换行 + "- " 前缀）的脏数据。

这个脚本把上述问题变成**可枚举、可计数、可回归**的检查项：
ERROR 让命令非零退出（能当门禁用），WARN 只报告。
历史脏数据用基线文件（--baseline）冻结：只要不新增问题，门禁就是绿的。

用法
----
    python memomics/bio_tools/validate_kb.py                    # 体检，ERROR 则退出 1
    python memomics/bio_tools/validate_kb.py --json report.json
    python memomics/bio_tools/validate_kb.py --strict           # WARN 也失败
    python memomics/bio_tools/validate_kb.py --update-baseline  # 冻结当前 ERROR 为基线

注：这个文件**不依赖 hermes-agent**（只用标准库 + yaml），所以按文件路径直接跑即可。
若要用 `python -m memomics.bio_tools.validate_kb`，需要先把 `hermes-agent` 加进 sys.path
（包 __init__ 会 import 各工具模块并注册到 tools.registry）。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections import Counter, defaultdict

try:
    import yaml
except ImportError:  # pragma: no cover - 环境缺 yaml 时给明确指引
    yaml = None

DEFAULT_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_base")
DEFAULT_BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_kb_baseline.json")

#: 规范 source 取值。KB 里所有合法写入路径都应该落在这一组里。
CANONICAL_SOURCES = {"literature", "data_driven", "default_seed", "manual", "curated", "derived"}

#: 自然语言 source → 规范值（只用于给建议，不自动改写数据）。
SOURCE_SUGGESTIONS = (
    ("literature", ("literature", "literature-verified", "curated from", "literature-driven",
                    "paper", "pubmed", "literature search", "文献")),
    ("data_driven", ("data_driven", "data-driven", "empirical", "经验", "实测")),
    ("default_seed", ("memomics default kb", "default kb", "seed", "默认知识库")),
)

#: 元数据键：这些键只描述条目本身，不承载知识正文。
METADATA_KEYS = {"type", "name", "species", "tissue", "direction", "assay_type", "domain",
                 "chem_category", "category", "tags", "version", "source", "sources", "verified",
                 "quality", "auto_trigger", "evidence", "last_updated", "updated", "created",
                 "updated_at", "description", "title", "id", "kb_category", "pipeline_stage",
                 "notes", "doi", "pmid", "metadata"}
#: 兼容保留：早期版本按固定载荷键名判断。
PAYLOAD_KEYS = ("content", "resources", "pipeline", "entries", "items", "methods",
                "knowledge", "findings", "data", "sections", "summary", "results")

VALID_VERIFIED = {"verified", "partially_verified", "unverified"}
VALID_QUALITY = {"high", "medium", "low", "unknown"}

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'|,;)\]]+")
PMID_RE = re.compile(r"PMID[:\s]*([0-9]{6,9})", re.I)


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _flatten_strings(value, out, depth=0):
    """把嵌套结构里的字符串收集出来（evidence/content 可能是 list/dict）。"""
    if depth > 6:
        return
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _flatten_strings(v, out, depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _flatten_strings(v, out, depth + 1)


def suggest_source(raw: str) -> str:
    low = raw.strip().lower()
    for canon, needles in SOURCE_SUGGESTIONS:
        for n in needles:
            if n in low:
                return canon
    return ""


def check_file(path: str, root: str, strict: bool = False) -> list:
    """对单个 YAML 做检查，返回 findings 列表（每条含 rule/level/detail）。"""
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    out = []

    def add(rule, level, detail=""):
        out.append({"rule": rule, "level": level, "path": rel, "detail": detail})

    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except Exception as exc:  # YAML 语法错误 = 硬错误
        add("yaml_parse_error", "error", str(exc)[:200])
        return out

    if doc is None:
        add("empty_file", "error", "文件为空或只有注释")
        return out
    if not isinstance(doc, dict):
        add("not_mapping", "error", "顶层不是 mapping，而是 %s" % type(doc).__name__)
        return out

    stem = os.path.splitext(os.path.basename(path))[0]

    # --- 标识：type / name / auto_trigger ---
    if _is_blank(doc.get("type")):
        add("missing_type", "warn" if not strict else "error", "缺 type（不是 kb_entry）")
    name = doc.get("name")
    if _is_blank(name):
        add("missing_name", "warn" if not strict else "error", "缺 name")
    elif str(name) != stem:
        add("name_filename_mismatch", "warn" if not strict else "error",
            "name=%s 与文件名 %s 不一致" % (name, stem))

    trig = doc.get("auto_trigger")
    if _is_blank(trig):
        add("missing_auto_trigger", "warn", "缺 auto_trigger（检索/自动加载拿不到它）")
    elif not isinstance(trig, list):
        add("auto_trigger_not_list", "error", "auto_trigger 不是列表（%s）" % type(trig).__name__)
    else:
        vals = [str(x).strip() for x in trig if not _is_blank(x)]
        if not vals:
            add("missing_auto_trigger", "warn", "auto_trigger 为空列表")
        if name and str(name) not in vals:
            add("auto_trigger_name_mismatch", "warn",
                "auto_trigger %s 里没有 name（%s）" % (vals[:3], name))

    # --- source：脏值/自然语言 ---
    src = doc.get("source")
    if _is_blank(src):
        add("missing_source", "warn", "缺 source（无法追溯来源）")
    elif not isinstance(src, str):
        add("source_not_string", "error", "source 不是字符串（%s）" % type(src).__name__)
    else:
        if "\n" in src or src.lstrip().startswith("- "):
            add("source_multiline_leak", "error",
                "source 里漏进了 YAML 列表/换行（%r）" % src[:80])
        elif src.strip() not in CANONICAL_SOURCES:
            sug = suggest_source(src)
            add("source_noncanonical", "warn",
                "source=%r 非规范值%s" % (src[:60], ("，建议 %s" % sug) if sug else ""))

    # --- 时间/质量/可信度 ---
    lu = doc.get("last_updated")
    if _is_blank(lu):
        add("missing_last_updated", "warn", "缺 last_updated")
    elif isinstance(lu, (_dt.date, _dt.datetime)):
        add("last_updated_parsed_as_date", "warn",
            "last_updated 未加引号，被 YAML 解析成日期对象（%s）" % lu)

    ver = doc.get("verified")
    if _is_blank(ver):
        add("missing_verified", "warn", "缺 verified")
    elif str(ver) not in VALID_VERIFIED:
        add("verified_unknown_value", "warn", "verified=%s 不在 %s" % (ver, sorted(VALID_VERIFIED)))
    q = doc.get("quality")
    if _is_blank(q):
        add("missing_quality", "warn", "缺 quality")
    elif str(q) not in VALID_QUALITY:
        add("quality_unknown_value", "warn", "quality=%s 不在 %s" % (q, sorted(VALID_QUALITY)))

    # --- 内容与证据 ---
    # KB 里有三种合法「载荷」写法：content 文本、resources 资源表、pipeline 方法表。
    # 只有「一个载荷键都没有」才是硬错误——早期版本把 index.yaml / default_kb_method.yaml
    # 一律判成缺 content，是把异构 schema 误当脏数据。
    body = []
    payload_keys = [k for k, v in doc.items() if k not in METADATA_KEYS and not _is_blank(v)]
    payload_key = payload_keys[0] if payload_keys else ""
    if not payload_key:
        add("missing_payload", "error",
            "除元数据外没有任何正文键（只有 %s）——空条目进了 KB 会污染检索"
            % "/".join(sorted(doc.keys())[:6]))
    for key in (payload_key, "content", "evidence", "summary", "description"):
        if key:
            _flatten_strings(doc.get(key), body)
    blob = "\n".join(body)
    if payload_key == "content" and body and \
            set(x.strip().lower() for x in body[:40] if x.strip()) <= {"na", "n/a", "-", ""}:
        add("placeholder_content", "warn", "content 全是 na/占位符，没有可用信息")
    if _is_blank(doc.get("evidence")):
        add("missing_evidence", "warn", "缺 evidence（无法核对来源）")

    doi_field = doc.get("doi") or (doc.get("metadata") or {}).get("doi") if isinstance(doc.get("metadata"), dict) else doc.get("doi")
    doi_in_text = DOI_RE.findall(blob)
    if _is_blank(doi_field) and not doi_in_text:
        add("missing_doi", "warn", "全文没有 DOI（引用回填的候选）")
    if not PMID_RE.search(blob):
        add("missing_pmid", "warn", "全文没有 PMID")

    return out


def scan(root: str = DEFAULT_ROOT, strict: bool = False) -> dict:
    """扫描整个 KB，返回 {findings, stats, dup_doi}。"""
    findings, files = [], []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.endswith((".yaml", ".yml")):
                files.append(os.path.join(dirpath, fn))
    for p in files:
        findings.extend(check_file(p, root, strict=strict))

    # 结构化 DOI 字段的重复 = 错误（同一条记录写了两份）
    by_doi = defaultdict(list)
    for p in files:
        try:
            with open(p, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except Exception:
            continue
        if isinstance(doc, dict):
            md = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
            d = doc.get("doi") or md.get("doi")
            if isinstance(d, str) and d.strip():
                by_doi[d.strip().lower()].append(os.path.relpath(p, root).replace(os.sep, "/"))
    for doi, paths in sorted(by_doi.items()):
        if len(paths) > 1:
            for rel in paths[1:]:
                findings.append({"rule": "duplicate_record_doi", "level": "error", "path": rel,
                                 "detail": "DOI %s 已在 %s 出现" % (doi, paths[0])})

    stats = {
        "files": len(files),
        "by_rule": dict(Counter(f["rule"] for f in findings)),
        "by_level": dict(Counter(f["level"] for f in findings)),
        "with_doi_field": sum(len(v) for v in by_doi.values()),
    }
    return {"findings": findings, "stats": stats}


def _key(f) -> str:
    return "%s|%s" % (f["rule"], f["path"])


def load_baseline(path: str) -> set:
    if not path or not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return set(data.get("keys") or [])


def save_baseline(path: str, findings: list) -> None:
    keys = sorted({_key(f) for f in findings})   # 基线只冻结 ERROR，避免 WARN 抖动
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "note": "validate_kb 回归基线：只冻结 error 级问题；新出现的问题会让门禁失败。",
                   "keys": keys}, fh, ensure_ascii=False, indent=1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="知识库体检与门禁（validate_kb）")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--strict", action="store_true", help="warn 也算失败")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    report = scan(args.root, strict=args.strict)
    findings, stats = report["findings"], report["stats"]
    errors = [f for f in findings if f["level"] == "error"]
    warns = [f for f in findings if f["level"] == "warn"]

    if args.update_baseline:
        save_baseline(args.baseline, errors)
        print("已冻结基线: %s（%d 条 error）" % (args.baseline, len({_key(f) for f in errors})))
        return 0

    base = load_baseline(args.baseline)
    new_errors = [f for f in errors if _key(f) not in base]
    new_warns = [f for f in warns if _key(f) not in base]

    if not args.quiet:
        print("KB 体检: %d 个 YAML | error %d | warn %d" % (stats["files"], len(errors), len(warns)))
        for rule, n in sorted(stats["by_rule"].items(), key=lambda kv: -kv[1]):
            lvl = "ERROR" if any(f["rule"] == rule and f["level"] == "error" for f in findings) else "warn "
            print("  %s %-30s %4d" % (lvl, rule, n))
        if base:
            print("基线: %s（已冻结 %d 条）→ 新增 error %d" % (args.baseline, len(base), len(new_errors)))
        for f in new_errors[:20]:
            print("  [NEW-ERROR] %s: %s %s" % (f["path"], f["rule"], f["detail"][:110]))
        if args.strict:
            for f in new_warns[:20]:
                print("  [NEW-WARN ] %s: %s %s" % (f["path"], f["rule"], f["detail"][:110]))
        print("结论: %s" % ("不通过" if (new_errors or (args.strict and new_warns)) else "通过"))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"stats": stats, "new_errors": new_errors, "errors": errors,
                       "warnings": warns, "baseline_size": len(base)}, fh, ensure_ascii=False, indent=1)

    if new_errors or (args.strict and new_warns):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
