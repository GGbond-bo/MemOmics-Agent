# -*- coding: utf-8 -*-
"""extract_llm_json.py — 从 LLM / 子代理输出里健壮提取 JSON（裸引号 / 尾随逗号 / 截断 / 容器递归）。

用途：合并 delegate_task 子代理 summary、解析任何「本该是 JSON 但被中文裸引号和截断破坏」的输出。

CLI:
    python extract_llm_json.py <summary.txt>                 # 打印解析报告 + 顶层键概览
    python extract_llm_json.py <summary.txt> --out out.json  # 另存解析结果（审计留档）
    python extract_llm_json.py <summary.txt> --id-key n --name-key name   # 指定条目主键
    python extract_llm_json.py A.txt B.txt C.txt --out merged.json        # 多份合并去重

Import:
    from extract_llm_json import extract_items, extract_json_blocks, fix_bare_quotes
    items = extract_items(open(p, encoding="utf-8").read())   # -> list[dict]
"""
import json, re, sys, os

# ---------------------------------------------------------------- 解析核心
def fix_bare_quotes(s):
    """状态机：字符串内部的裸 ASCII 双引号 → 转义。

    判据：处于字符串中时遇到 " ，只有「其后第一个非空白字符 ∈ ,}]: 」
    才算字符串结束；否则判为正文里的裸引号（中文正文常拿 " 当强调号）。
    """
    out, i, n, in_str = [], 0, len(s), False
    while i < n:
        ch = s[i]
        if not in_str:
            if ch == '"':
                in_str = True
            out.append(ch); i += 1
        else:
            if ch == '\\':
                out.append(s[i:i + 2]); i += 2; continue
            if ch == '"':
                j = i + 1
                while j < n and s[j] in ' \t\r\n':
                    j += 1
                if j < n and s[j] in ',}]:':
                    in_str = False
                    out.append(ch); i += 1
                else:
                    out.append('\\"'); i += 1
            else:
                out.append(ch); i += 1
    return ''.join(out)


def strip_trailing_commas(s):
    return re.sub(r",\s*([}\]])", r"\1", s)


def extract_json_blocks(txt):
    """抽 ```json 围栏（正则含未闭合的最后一块）；无围栏 → 从 {"cards" 起截取兜底。"""
    blocks = [m.group(1).strip()
              for m in re.finditer(r"```json\s*(.*?)(?:```|\Z)", txt, re.S)]
    if not blocks:
        m = re.search(r"\{\s*\"(?:cards|items|results|data)\"", txt)
        if m:
            blocks.append(txt[m.start():])
        else:                       # 连顶层键都没有 → 全文抢救
            blocks.append(txt)
    return blocks


def salvage_objects(s):
    """深度扫描配平 {} 逐个顶层对象；解析失败的跳过。"""
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                frag = s[start:i + 1]
                for cand in (frag, fix_bare_quotes(frag),
                             strip_trailing_commas(fix_bare_quotes(frag))):
                    try:
                        out.append(json.loads(cand)); break
                    except Exception:
                        continue
                start = None
    return out


def try_parse(blk):
    """多重回退：原样 → 裸引号修复 → 去尾随逗号 → 截断补齐。返回 (obj, how)。"""
    fq = fix_bare_quotes(blk)
    for c in (blk, fq, strip_trailing_commas(fq), strip_trailing_commas(blk)):
        try:
            return json.loads(c), "ok"
        except Exception:
            pass
    t = strip_trailing_commas(fq)
    for cut in range(1, min(len(t), 8000)):           # 截断补齐
        frag = t[:-cut]
        for suf in ('"}]}', '"}]', '"]}', ']}', '}', ']'):
            try:
                return json.loads(frag + suf), "truncated_repair"
            except Exception:
                continue
    return None, "failed"


def _items_of(obj):
    """递归展开：dict 里的 cards/items/results/data/evidence 列表 → 迭代出条目。

    ⛔ 见 SKILL.md 坑「容器递归」：不递归就会返回 0 条且不报错。
    """
    if isinstance(obj, dict):
        for k in ("cards", "items", "results", "data", "evidence", "records", "rows"):
            v = obj.get(k)
            if isinstance(v, list):
                for x in v:
                    yield from _items_of(x)
                return
        yield obj                                  # 叶子 dict = 一条记录
    elif isinstance(obj, list):
        for x in obj:
            yield from _items_of(x)


def norm_key(v):
    """主键归一：'4' / 'n=9' / 4 → 4。"""
    if v is None:
        return None
    if isinstance(v, int):
        return v
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else str(v)


def extract_items(text, id_key="n"):
    """从文本提取条目列表（已去重：同 id 取字段最全者）。返回 (items, report)。"""
    items, report = [], []
    for bi, blk in enumerate(extract_json_blocks(text)):
        obj, how = try_parse(blk)
        got = []
        if obj is not None:
            got = list(_items_of(obj))
        if not got:                                # 解析成功但 0 条 → 抢救
            got = salvage_objects(blk)
            how = "salvaged" if obj is None else how + "+salvaged"
        if not got and obj is None:
            how = "failed"
        report.append({"block": bi, "how": how, "items": len(got), "chars": len(blk)})
        items += got

    by = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        k = norm_key(it.get(id_key))
        if k is None:
            k = norm_key(it.get("doi") or it.get("id") or it.get("name"))
        if k is None:
            by[id(object())] = it; continue
        if k not in by or len(json.dumps(it, ensure_ascii=False)) > \
                          len(json.dumps(by[k], ensure_ascii=False)):
            it[id_key] = k
            by[k] = it
    out = [by[k] for k in sorted(by, key=lambda x: (isinstance(x, str), x))]
    return out, report


def delta_report(new, store, fields, id_key="n"):
    """Δ 验证：与磁盘现有 store 逐字段比长度。Δ≈0 → 早已合并过，本轮不必重做。"""
    ex = {}
    for c in (store.get("cards") if isinstance(store, dict) else store) or []:
        ex[norm_key(c.get(id_key))] = c
    rows, tot_new, tot_old = [], 0, 0
    for c in new:
        k = norm_key(c.get(id_key))
        a = sum(len(str(ex.get(k, {}).get(f, ""))) for f in fields)
        b = sum(len(str(c.get(f, ""))) for f in fields)
        tot_old += a; tot_new += b
        rows.append({"id": k, "old": a, "new": b, "delta": b - a})
    return {"total_old": tot_old, "total_new": tot_new,
            "delta": tot_new - tot_old,
            "verdict": ("ALREADY_MERGED (Δ≈0，无需重复合并)" if abs(tot_new - tot_old) <= max(50, len(new) * 5)
                        else "HAS_NEW_CONTENT"),
            "rows": rows}


# ---------------------------------------------------------------- CLI
def main(argv):
    if not argv:
        print(__doc__); return 1
    out_path, files, id_key = None, [], "n"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out":
            out_path = argv[i + 1]; i += 2
        elif a == "--id-key":
            id_key = argv[i + 1]; i += 2
        else:
            files.append(a); i += 1

    all_items, all_report = [], []
    for f in files:
        t = open(f, encoding="utf-8", errors="replace").read()
        items, rep = extract_items(t, id_key=id_key)
        all_items += items
        all_report.append({"file": os.path.basename(f), "chars": len(t), "blocks": rep,
                           "items": len(items)})
        print(f"[{os.path.basename(f)}] chars={len(t)} items={len(items)} "
              f"how={[r['how'] for r in rep]}")

    # 多文件去重
    by = {}
    for it in all_items:
        k = norm_key(it.get(id_key))
        if k not in by or len(json.dumps(it, ensure_ascii=False)) > \
                          len(json.dumps(by[k], ensure_ascii=False)):
            by[k] = it
    merged = [by[k] for k in sorted(by)]

    print(f"\nTOTAL merged items: {len(merged)}  ids={[c.get(id_key) for c in merged]}")
    if merged:
        print("fields per item:", {k: sum(1 for c in merged if c.get(k)) for k in merged[0]})
    if out_path:
        json.dump({"items": merged, "parse_report": all_report},
                  open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("saved ->", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))