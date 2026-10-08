#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""已合并 store 的字段健康审计（重放轮顺手跑）。

用途：回执判「迟到重放」后，对 store 做一次便宜的字段健康扫描，抓出真正的内容缺陷
      （字段被截断 / 空值 / 占位符残留），同时用白名单滤掉合法短值。

配套阅读：references/merged-store-field-health-audit.md

用法：
    python audit_store_field_health.py <store.json> [--fields a,b,c] [--min-len 25]
    python audit_store_field_health.py cards.json
    python audit_store_field_health.py cards.json --key n        # 记录里用哪个键当 id

退出码：0 = 无缺陷；1 = 发现缺陷（清单打印在 stdout）。

设计要点（都是踩过的坑，别改）：
  * store 可能是 list[dict]（键在元素里）或 dict；形状先探再判，否则崩在 'list' has no 'items'。
  * 判据只用「字段长度 < min_len」。⛔ 不要用「结尾无句号」——中文卡片惯常不写句尾句号，
    实测该启发式报 54 处、真缺陷仅 1 处（96% 假阳性）。
  * 合法短值白名单必须先滤，否则「无量化评测」「未披露」（综述/观点文正当写法）全是假阳性。
"""
import argparse
import json
import os
import re
import sys

DEFAULT_FIELDS = [
    "architecture", "inputs", "outputs", "models",
    "benchmark", "validation", "key_claim", "novelty", "limitations",
]

# 综述/观点文天然合法的短值；按需扩充，扩的是「已知正当写法」而不是「看着像就行」
LEGIT_PATTERNS = [
    r"^无量化评测", r"^无$", r"^无（", r"^不适用", r"^未披露", r"^原文未报告$",
]


def load_store(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        # 容器形如 {"cards":[...], "evidence":[...]} → 取第一个 list 值
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v, f"dict→list({len(v)})"
        return [], "dict(空)"
    if isinstance(data, list):
        return data, f"list({len(data)})"
    return [], type(data).__name__


def records(store, key):
    """归一成 [(id, record_dict)]。key=None 时用序号。"""
    out = []
    for i, rec in enumerate(store):
        if not isinstance(rec, dict):
            continue
        rid = rec.get(key, i) if key else i
        out.append((str(rid), rec))
    return out


def is_legit(value):
    v = value.strip()
    return any(re.match(p, v) for p in LEGIT_PATTERNS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("store")
    ap.add_argument("--fields", default=",".join(DEFAULT_FIELDS))
    ap.add_argument("--min-len", type=int, default=25,
                    help="字段长度低于此值即视为可疑（默认 25）")
    ap.add_argument("--key", default=None, help="记录里作为 id 的键（如 n / id）")
    a = ap.parse_args()

    if not os.path.exists(a.store):
        print(f"[X] 不存在: {a.store}")
        return 2

    fields = [f.strip() for f in a.fields.split(",") if f.strip()]
    store, shape = load_store(a.store)
    recs = records(store, a.key)
    print(f"store : {a.store}")
    print(f"形状  : {shape}   有 id 的记录数: {len(recs)}")

    if not recs:
        print("[X] 没解析出记录 —— 形状没探对，先 print(type()/keys()) 再重跑")
        return 2

    # 字段名对不上是静默 0 命中，先把真实键打出来
    real_keys = sorted({k for _, r in recs for k in r})
    missing_fields = [f for f in fields if f not in real_keys]
    if missing_fields:
        print(f"[!] 字段名不在 store 里（会静默 0 命中，先核对）: {missing_fields}")
        print(f"    store 实际键: {real_keys}")

    print()

    # ① 逐字段长度分布
    suspects = []
    for f in fields:
        lens = sorted((len(str(r.get(f, "")).strip()), rid)
                      for rid, r in recs if f in r)
        if not lens:
            continue
        n = len(lens)
        stats = {
            "min": lens[0][0], "min_id": lens[0][1],
            "p25": lens[max(0, n // 4)][0],
            "median": lens[n // 2][0],
            "max": lens[-1][0], "max_id": lens[-1][1],
        }
        flag = "  ← min 离群" if stats["min"] * 4 < stats["p25"] else ""
        print(f"{f:<16} min={stats['min']:>5}(id={stats['min_id']}) "
              f"p25={stats['p25']:>5} median={stats['median']:>5} "
              f"max={stats['max']:>5}(id={stats['max_id']}){flag}")

    print()

    # ② 短字段清单（白名单过滤后）
    print(f"--- 短字段清单（< {a.min_len} 字）---")
    for rid, r in recs:
        for f in fields:
            if f not in r:
                continue
            s = str(r.get(f, "")).strip()
            if not s:
                suspects.append((rid, f, 0, "<空值>", False))
                continue
            if len(s) < a.min_len:
                legit = is_legit(s)
                suspects.append((rid, f, len(s), s, legit))

    real = [x for x in suspects if not x[4]]
    legit = [x for x in suspects if x[4]]

    for rid, f, L, s, _ in sorted(suspects, key=lambda x: (int(x[0]) if x[0].isdigit() else 0, x[1])):
        tag = "合法短值" if (rid, f, L, s, True) in suspects else "⛔ 缺陷"
        print(f"  [{tag}] id={rid:<4} {f:<14} {L:>4}字  {s[:70]!r}")

    print()
    print(f"合法短值 {len(legit)} 处（白名单命中，不是缺陷）")
    print(f"疑似缺陷 {len(real)} 处")
    if real:
        print("\n补齐方式（⛔ 别自己编）：回源全文 data/text/PMC<id>.txt 定位对应章节取原句；")
        print("  例：limitations → re.finditer(r'(?i)\\bLimitations?\\b') 命中偏移，读 §Limitations 段。")
        print("  ⛔ 改 store 前先读 references/merged-store-field-health-audit.md §五 ——")
        print("     冻结交付物只报告不擅自改（改 store 不重建 DOCX/HTML/md = 交付物自相矛盾）。")
        return 1
    print("✅ 未发现缺陷")
    return 0


if __name__ == "__main__":
    sys.exit(main())