#!/usr/bin/env python3
"""verify_batch_replay.py — 判定一批子代理回执是「新工作」还是「迟到重放」。

背景
----
`[ASYNC DELEGATION BATCH COMPLETE]` 回执会**迟到重放**（同一批可被推两次，Dispatched 时间仍是旧的）。
照单全收会把早已合并的内容再合一遍 → 污染 store + 白烧一小时。本脚本把
delegation-orchestration SKILL.md §二 的 5 项检查一次跑完，看返回码再决定动不动手。

用法
----
python verify_batch_replay.py \
    --batch-json data/deep_cards_deleg_15d8b24b.json \
    --store      data/cards.json \
    --id-key     n \
    --expect-total 31 \
    --probes     probes.json \
    --size-dir   deliverables \
    --expect-size "MemOmics_科研AI_Agent领域定位报告.docx=769470" \
    --expect-size "MemOmics_科研AI_Agent领域定位报告.html=1180780" \
    --expect-size "positioning_full.md=246520" \
    --expect-size "evidence.csv=98行"

`--batch-json` 必须是**合并当时自己落盘的解析件**，不是 live transcript：后者会把 assistant
长回复截成 `…(+N chars)`（实测 26 KB log vs 80 KB 实际产出），做不了逐字比对。

`probes.json` 形如 `{"4": ["Experiment Design LLM", "11/20"], "45": ["OntoReaction"]}`，
大小写不敏感子串命中（注意 geNomad / GeNomad 这类陷阱，本脚本已 .lower()）。

返回码
----
  0 = ALREADY_MERGED  零差异 → 迟到重放，数据文件与交付物一个字节都不动
  3 = NEW_WORK        存在正差异 → 走字段级合并（新值非空才覆盖，旧值转存 *_v1）
  2 = 输入不可用      形状/键对不上 → 先查清楚形状，别硬写合并逻辑
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys


def load_shaped(path: str):
    """读取并**打印容器形状**：形状没确认前不要写合并/比对逻辑。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"[load] {path}")
    if isinstance(data, dict):
        print(f"       type=dict len={len(data)} first_keys={list(data)[:6]}")
    elif isinstance(data, list):
        e0 = data[0] if data else None
        print(f"       type=list len={len(data)} "
              f"elem0_type={type(e0).__name__} "
              f"elem0_keys={list(e0)[:8] if isinstance(e0, dict) else 'NA'}")
    else:
        print(f"       type={type(data).__name__} (不支持的类型)")
    return data


def unwrap_cards(data):
    """剥掉 `{"cards": ...}` 外壳（可多层），把四种实测形状归一成「卡片容器」。

    实测在磁盘上共存的形状（SKILL.md §二 0-ter）：:

        list[dict]                                     n 在元素里（store 常用）
        dict[id -> card]                               裸 dict，键就是 n
        {"cards": {"1": {...}, "2": {...}}}            dict-of-dict（用户点名落盘的补派件）
        {"cards": [ {...}, ... ], "evidence": [...]}   同前缀却是 list

    形状没归一前写比对逻辑 = 静默 0 条（不抛异常）。文件名前缀**不能**用来推断形状：
    `deep_cards_*` 下 dict-of-dict 与 list-of-dict 并存。
    """
    for _ in range(3):  # 至多剥 3 层，防病态嵌套死循环
        if isinstance(data, dict) and isinstance(data.get("cards"), (dict, list)) and data["cards"]:
            data = data["cards"]
            continue
        break
    return data


def to_map(data, id_key: str = "n") -> dict:
    """四种形状通吃，归一成 {int_id: card}。

    id 缺失时**回退取容器键**：dict-of-dict 形状的卡体常不带 `n`（键才是编号），
    只读卡体会把整批静默读成 0 条。
    """
    data = unwrap_cards(data)
    out: dict = {}
    items = data.items() if isinstance(data, dict) else enumerate(data)
    for k, v in items:
        if not isinstance(v, dict):
            continue
        raw = v.get(id_key, v.get("id"))
        if raw is None and isinstance(k, str) and k.strip().isdigit():
            raw = k
        if raw is None:
            continue
        kk = re.sub(r"^n=", "", str(raw).strip())
        if kk.isdigit():
            out[int(kk)] = v
    return out


def nz(s) -> str:
    """归一空白：不归一必然出假阳/假阴（纯换行差异会被判成内容差异）。"""
    return re.sub(r"\s+", "", s if isinstance(s, str) else "")


def sha16(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-json", required=True, help="合并时落盘的解析件（首选证据源）")
    ap.add_argument("--store", required=True, help="canonical store，如 data/cards.json")
    ap.add_argument("--id-key", default="n")
    ap.add_argument("--fields", default="",
                    help="逗号分隔；留空 = 取批次卡的全部非 id 字段")
    ap.add_argument("--probes", default="", help="probes.json: {id: [独有串...]}")
    ap.add_argument("--expect-total", type=int, default=0,
                    help="闭环不变量：store 应有的总卡数（Σ各批卡数）")
    ap.add_argument("--expect-size", action="append", default=[],
                    help='交付物指纹 "文件名=字节数" 或 "文件名=98行"，可重复')
    ap.add_argument("--size-dir", default="", help="交付物所在目录")
    a = ap.parse_args()

    batch_raw = load_shaped(a.batch_json)
    store_raw = load_shaped(a.store)
    batch, store = to_map(batch_raw, a.id_key), to_map(store_raw, a.id_key)
    if not batch:
        print("!! 批次解析件里没提取到任何卡 → 形状/键不对，先查清楚再判\n"
              "   （本脚本已内置四种形状通吃读法，见 SKILL.md §二 0-ter；仍为空说明是第五种形状，\n"
              "    先 print(type(x).__name__, len(x), list(x)[:5]) 再决定加分支，⛔ 不要改判据去凑）")
        return 2
    if not store:
        print("!! store 里没提取到任何卡 → 同上（先 print 形状，别硬写合并逻辑）"); return 2

    ids = sorted(batch)
    print(f"\n[batch] n={ids} count={len(batch)}")
    print(f"[store] count={len(store)}")

    if a.fields:
        FIELDS = [f.strip() for f in a.fields.split(",") if f.strip()]
    else:
        FIELDS = sorted({k for c in batch.values() for k in c} - {a.id_key, "id"})

    print(f"\n{'n':>4} {'一致':>7} {'字符Δ':>6}  差异字段")
    tot_ok = tot_bad = clean = dchar = 0
    for n in ids:
        c = store.get(n)
        if c is None:
            print(f"{n:>4}  ! store 缺失该卡"); tot_bad += len(FIELDS); continue
        bad = [f for f in FIELDS
               if batch[n].get(f) is not None and nz(batch[n][f]) != nz(c.get(f))]
        ok = len([f for f in FIELDS if batch[n].get(f) is not None]) - len(bad)
        dc = sum(abs(len(nz(batch[n][f])) - len(nz(c.get(f)))) for f in bad)
        tot_ok += ok; tot_bad += len(bad); dchar += dc; clean += (0 if bad else 1)
        print(f"{n:>4} {ok}/{ok + len(bad):<5} {dc:>6}  "
              f"{'OK 逐字段一致' if not bad else ','.join(bad)}")
    print(f"\n[字段比对] 一致 {tot_ok} / 不一致 {tot_bad} | "
          f"完全一致卡 {clean}/{len(ids)} | 总字符Δ {dchar}")

    probe_bad = 0
    if a.probes:
        probes = json.load(open(a.probes, encoding="utf-8"))
        hit = miss = 0
        for k, terms in probes.items():
            kk = re.sub(r"^n=", "", str(k).strip())
            card = store.get(int(kk)) if kk.isdigit() else None
            blob = json.dumps(card, ensure_ascii=False).lower() if card else ""
            for t in terms:
                if t.lower() in blob:
                    hit += 1
                else:
                    miss += 1; probe_bad += 1
                    print(f"  x 探针未命中 n={kk}: {t}")
        print(f"[独有串探针] {hit}/{hit + miss} 命中（大小写不敏感）")

    total_bad = 0
    if a.expect_total:
        ok = len(store) == a.expect_total
        total_bad += (0 if ok else 1)
        print(f"[闭环不变量] store {len(store)} vs 期望 {a.expect_total} -> {'OK' if ok else 'FAIL'}")

    size_bad = 0
    for spec in a.expect_size:
        name, _, want = spec.partition("=")
        p = os.path.join(a.size_dir, name) if a.size_dir else name
        want = want.strip()
        if not want or not os.path.exists(p):
            print(f"[交付物指纹] {name}: 文件不存在 -> 无法核验"); size_bad += 1; continue
        if want.endswith("行"):
            actual, exp = sum(1 for _ in open(p, encoding="utf-8", errors="replace")), want[:-1].strip()
        else:
            actual, exp = os.path.getsize(p), want
        ok = str(actual) == exp
        size_bad += (0 if ok else 1)
        print(f"[交付物指纹] {name}: {actual} vs {exp} -> {'OK' if ok else 'FAIL'}")

    print(f"\nsha256[:16]  store={sha16(a.store)}  batch={sha16(a.batch_json)}")

    clean_run = (tot_bad == 0 and probe_bad == 0 and total_bad == 0 and size_bad == 0)
    if clean_run:
        print("\n* 判定: ALREADY_MERGED（迟到重放：零差异）")
        print("  → 数据文件与交付物一个字节都不动；只把结论 + sha256 追加进 notes.md。")
        print("  → 汇报时注明 diff 的是「落盘解析件 <-> store」，不是回执原文/live log（会被截断）。")
        return 0
    print(f"\n* 判定: NEW_WORK（正差异：字段{tot_bad} 探针{probe_bad} 不变量{total_bad} 交付物{size_bad}）")
    print("  → 走字段级合并：新值非空才覆盖，旧值先转存 *_v1 备份键，再落盘。")
    return 3


if __name__ == "__main__":
    sys.exit(main())