#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""非 JSON 形态（Markdown 摘要 + KB YAML）重放判定探针 —— 一次跑完 §二 ⓪-j / ⓪-k 的全部检查。

收到 [ASYNC DELEGATION BATCH COMPLETE] 回执、且该任务产物不是 cards.json 那类 JSON card store 时跑它。

覆盖：
  ① find 先行            —— 交付物真实位置（跨会话目录按名找，不靠猜层级）   ⓪-k ①
  ② 落盘件 mtime 时序    —— 该批全部子代理落盘件是否都早于交付物              ⓪-j ①
  ③ 交付物覆盖计数        —— 该批专有专名/数字在交付物里的命中次数（机械量）    ⓪-j ②
  ④ 反向封闭             —— mtime > 交付物 的未消费新件（排除 log/loopx）     ⓪-k ②
  ⑤ 指纹                 —— 字节 + sha256（权威）+ 行数（带 wc -l 口径标注）   ⓪-k ③
  ⑥ 台账                 —— 区分「派发行」与「核销行」，数 replay#N            ⓪-i
  ⑦ KB YAML 健康          —— 先 print 实际键再扫描（⛔ 别拿自编键名当必需字段） ⓪-j

退出码：0 = 判重放（零写入收场） 3 = 出现正差异，疑似新工作，走 §二 5 项 diff
用法：
  python probe_replay_nonjson.py --session-dir results/memomics-XXXX \
      --deliverable AI_agent_前沿工作解读.md \
      --batch-file results/memomics-XXXX/data/AI摘要_paper2Agent_CASSIA.md \
      --batch-file results/memomics-XXXX/Biomni_结构化摘要.md \
      --probe-terms Biomni,CASSIA,paper2Agent,DeepRare \
      --kb-dir memomics/knowledge_base/ai_agent
"""
from __future__ import annotations
import argparse, glob, hashlib, os, sys, time

VERDICT_REPLAY, VERDICT_NEW = 0, 3
SKIP_DIR_PARTS = ("/log/", "\\log\\", "/.loopx/", "\\.loopx\\", "/cache/", "\\cache\\")


def fp(path: str):
    """(bytes, sha256[:16], mtime_str, wc_l_lines) —— 行数按 wc -l 口径（数换行符）。"""
    b = open(path, "rb").read()
    nl = b.count(b"\n")
    return len(b), hashlib.sha256(b).hexdigest()[:16], \
        time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(path))), nl


def find_by_name(root: str, name: str):
    hits = []
    for dp, dn, fn in os.walk(root):
        if name in fn:
            hits.append(os.path.join(dp, name))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-dir", required=True, help="results/<sid>")
    ap.add_argument("--deliverable", required=True, help="交付物文件名（不含路径，探针自己 find）")
    ap.add_argument("--batch-file", action="append", default=[],
                    help="该批子代理落盘件（可重复；相对 --session-dir 或绝对路径）")
    ap.add_argument("--probe-terms", default="", help="该批专有专名/精确数字，逗号分隔")
    ap.add_argument("--kb-dir", default="", help="知识库域目录，如 memomics/knowledge_base/ai_agent")
    ap.add_argument("--root", default=".", help="find 的搜索根（默认当前目录）")
    a = ap.parse_args()

    S = os.path.abspath(a.session_dir)
    print(f"== 探针根: {S}\n")

    # ---- ① find 先行：一次 ls 的 MISSING 不是证据（⓪-k ①）
    dpath = os.path.join(S, a.deliverable)
    if not os.path.exists(dpath):
        hits = find_by_name(a.root, a.deliverable)
        print(f"!! 会话根没有 {a.deliverable} —— find 结果（{len(hits)} 条）:")
        for h in hits:
            print("   ", h)
        if not hits:
            print("   ⛔ 真的没有：这才叫「交付物不存在」；此前任何单层 ls 的 MISSING 都不算")
            return VERDICT_NEW
        dpath = hits[0]
        print(f"   ⇒ 采用 {dpath}（台账里务必写全这一层路径，避免下轮再踩）")
    dbytes, dsha, dmt, dlines = fp(dpath)
    dmt_epoch = os.path.getmtime(dpath)
    print(f"② 交付物 {os.path.relpath(dpath, a.root)}: {dbytes} B / sha256:{dsha} / "
          f"{dlines} 行 (wc -l，末行无换行则少 1 —— 口径差不是内容变化) @ {dmt}\n")

    # ---- ② 落盘件时序（⓪-j ①）
    verdict = VERDICT_REPLAY
    print("③ 落盘件时序（全部应 < 交付物 ⇒ 已消费）")
    if not a.batch_file:
        print("   (未给 --batch-file：跳过着装检查)")
    for p in a.batch_file:
        q = p if os.path.isabs(p) else os.path.join(S, p)
        if not os.path.exists(q):
            q = (find_by_name(a.root, os.path.basename(p)) or [None])[0]
        if not q:
            print(f"   MISSING {p}  ⇒ ⛔ 先 find 再定罪，别报「落盘件丢了」")
            verdict = VERDICT_NEW
            continue
        b, sh, mt, nl = fp(q)
        early = os.path.getmtime(q) < dmt_epoch
        print(f"   {'OK ' if early else 'LATE'} {b:>9} B @{mt}  {os.path.relpath(q, a.root)}")
        if not early:
            print("        ↑ 晚于交付物 ⇒ 交付物不可能含它，按新工作处置")
            verdict = VERDICT_NEW
    print()

    # ---- ④ 交付物覆盖计数（机械量，⛔ 别用语义词，见 §二 检查 3 口径卫生）
    terms = [t.strip() for t in a.probe_terms.split(",") if t.strip()]
    if terms:
        txt = open(dpath, encoding="utf-8", errors="ignore").read().lower()
        print("④ 交付物覆盖计数")
        for t in terms:
            n = txt.count(t.lower())
            print(f"   {t:24s} {n:>3} 次 {'OK' if n else '⛔ 0 命中 ⇒ 真缺口'}")
            if n == 0:
                verdict = VERDICT_NEW
        print()

    # ---- ⑤ 反向封闭：交付物之后有没有未消费新件（⓪-k ②）
    print("⑤ 反向封闭（交付物之后的新件；除 log/.loopx/cache 外应为空）")
    later = []
    for dp, dn, fn in os.walk(S):
        for f in fn:
            q = os.path.join(dp, f)
            if os.path.getmtime(q) <= dmt_epoch:
                continue
            if any(s in q or s.replace("/", os.sep) in q for s in SKIP_DIR_PARTS):
                continue
            later.append(q)
    for q in later:
        print("   ", os.path.relpath(q, a.root))
    print("   ⇒", "封闭成立（无未消费新件）" if not later else "⛔ 有后置新件，需逐个定性")
    if later:
        verdict = VERDICT_NEW
    print()

    # ---- ⑥ 台账：区分派发行 / 核销行（⓪-i）
    notes = os.path.join(S, "notes.md")
    if os.path.exists(notes):
        print(f"⑥ 台账 notes.md = {os.path.getsize(notes)} B")
        for i, l in enumerate(open(notes, encoding="utf-8", errors="ignore"), 1):
            if "deleg_" in l or "replay#" in l or "核销" in l:
                kind = "核销行" if ("核销" in l or "replay#" in l) else "派发行"
                print(f"   L{i:<4} [{kind}] {l.rstrip()[:140]}")
        print("   ⚠️ 只有『核销行』能一跳定案；命中派发行 ⇒ 退回 ⓪-j/⓪-k\n")
    else:
        print("⑥ notes.md 不存在 —— 台账缺失，本轮结论必须自己落账\n")

    # ---- ⑦ KB YAML 健康（先 print 键，再写逻辑 —— ⓪-j 踩点）
    if a.kb_dir:
        ys = []
        for ext in ("*.yaml", "*.yml"):
            ys += glob.glob(os.path.join(a.kb_dir, "**", ext), recursive=True)
        ys = sorted(set(ys))
        print(f"⑦ KB {a.kb_dir}: {len(ys)} 个 YAML（另有 00_INDEX.md 之类的非 YAML 件不在此列）")
        if ys:
            try:
                import yaml
            except ImportError:
                print("   (未装 pyyaml：跳过字段健康，⛔ 不要改用正则瞎扫)")
            else:
                print("   样本顶层键:", list(yaml.safe_load(open(ys[0], encoding="utf-8")).keys()))
                short = []
                for y in ys:
                    d = yaml.safe_load(open(y, encoding="utf-8")) or {}
                    c = len(d.get("content") or "")
                    e = len(d.get("evidence") or "")
                    if c < 800 or e < 40:
                        short.append((os.path.relpath(y, a.kb_dir), c, e))
                print(f"   content<800 或 evidence<40 的条目: {short or '无'}")
                if short:
                    verdict = VERDICT_NEW

    print(f"\n=== 判定: {'ALREADY_REPLAY（零写入；只追加台账行）' if verdict == VERDICT_REPLAY else 'NEW_WORK（走 §二 5 项 diff）'}")
    return verdict


if __name__ == "__main__":
    sys.exit(main())