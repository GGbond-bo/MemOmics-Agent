#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""replay_reply_lint.py — 零 delta 唤醒轮「回复邀约」机械门

为什么存在
----------
SKILL.md 从 tick#22 起就写着「发前跑 `replay_reply_lint.py --ledger`」，
但该脚本**从未落地** ⇒ 规则连续三轮被同型违反（tick#22 / #24 / #27），
每轮都是「规则我写了，发的时候没跑门」。
本脚本把那句话变成可执行的门。

用法
----
    # 1) 检查一段草稿（最常用：先把结尾段贴进去）
    python scripts/replay_reply_lint.py --text-file draft.md
    echo "……结尾段……" | python scripts/replay_reply_lint.py

    # 2) 审计台账里记录过的历史轮次（找同型复犯）
    python scripts/replay_reply_lint.py --ledger
    python scripts/replay_reply_lint.py --ledger --session results/memomics-be17649b

退出码
------
    0 = 干净；1 = 命中禁串/邀约语义 ⇒ **删掉整个结尾段，禁改写成同义措辞**

⚠️ 只管【系统唤醒自主轮】。用户当轮主动提问 ⇒ 正常回答，不受本清单约束。
⚠️ 只做机械提示，不做语义裁决；命中不等于必然违规（例如在解释规则本身时会引用这些词），
   但默认应当成红灯去复核。
"""
import argparse
import glob
import os
import re
import sys

# ---------------------------------------------------------------- 规则
# 邀约：任何「要求用户做出选择 / 提供输入 / 点个头」的措辞。
INVITE = [
    r"需要你", r"待你(决定|确认|一句话|点头|回复)", r"待决定", r"待你选",
    r"等你(一句话|点头|确认|回复|选)", r"你说一声", r"你说句话", r"你说一句",
    r"说一句", r"说「", r"回复「", r"告诉我", r"点单", r"听你的",
    r"二选一", r"选一个", r"挑一个", r"你选", r"你确认", r"你来定",
    r"要不要", r"即可恢复", r"仍挂起", r"下一步你", r"想让我",
    r"给我(个|一个)?(DOI|篇名|路径|名单)", r"你给(个|一个)?(DOI|篇名|路径)",
    r"需要你一句话", r"由你决定", r"随你", r"等你答复",
]
# 重列挂起项：单纯指向 ledger 的「待决项见 notes.md」是合规模板，不算违规。
RELIST = [
    r"待决项(?!见|仅进|只进|已在|记录在)", r"挂起项(?!见|仅进|只进|已在)",
    r"待办清单", r"还缺", r"还差", r"剩(下)?(什么|两项|几项)(要|需|等)",
]


def compile_pats(pats):
    return [re.compile(p) for p in pats]


def scan(text, label):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        for kind, pats in (("邀约", INVITE), ("重列挂起", RELIST)):
            for p in compile_pats(pats):
                m = p.search(s)
                if m:
                    hits.append((label, i, kind, m.group(0), s[:140]))
                    break
    return hits


def report(hits):
    if not hits:
        print("✅ 干净：未命中禁串/邀约语义。")
        return 0
    print("⛔ 命中 %d 处 —— 删掉整个结尾段（禁改写＝换个说法继续邀约）：\n" % len(hits))
    for label, ln, kind, frag, ctx in hits:
        print("  [%s] %s:%d  命中=%r" % (kind, label, ln, frag))
        print("        %s" % ctx)
    print("\n合规结尾模板：三行核验表 + 「无待办：任务终态、无产物 delta、本轮零写入。待决项见 notes.md。」然后结束。")
    return 1


def ledger_files(session):
    if not session:
        cands = sorted(glob.glob(os.path.join("results", "*")), key=os.path.getmtime, reverse=True)
        session = next((c for c in cands if os.path.isdir(c)), "")
    if not session:
        print("（未找到会话目录：请用 --session results/<sid>）")
        return []
    out = []
    for name in ("notes.md", "task_plan.md"):
        p = os.path.join(session, name)
        if os.path.exists(p):
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description="零 delta 唤醒轮回复邀约扫描")
    ap.add_argument("--text-file", help="要检查的草稿文件")
    ap.add_argument("--text", help="要检查的文本（短文本可直接传）")
    ap.add_argument("--ledger", action="store_true", help="扫描台账（notes.md / task_plan.md）找历史同型违规")
    ap.add_argument("--session", default="", help="会话目录，如 results/memomics-be17649b")
    a = ap.parse_args()

    hits = []
    if a.ledger:
        files = ledger_files(a.session)
        if not files:
            return 2
        for f in files:
            hits += scan(open(f, encoding="utf-8", errors="ignore").read(), os.path.basename(f))
    elif a.text_file:
        hits += scan(open(a.text_file, encoding="utf-8", errors="ignore").read(), a.text_file)
    elif a.text:
        hits += scan(a.text, "arg")
    else:
        data = sys.stdin.read()
        if not data.strip():
            ap.print_help()
            return 2
        hits += scan(data, "stdin")
    return report(hits)


if __name__ == "__main__":
    sys.exit(main())