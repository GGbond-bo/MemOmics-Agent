# -*- coding: utf-8 -*-
"""Repair scaffold user messages polluting session history (2026-08-31).

Problem: self-check wake path persisted [会话要求…]/[系统唤醒…] as role=user,
agent treats them as new user questions each turn (870 in cd677556).
Safe fix: soft-delete (active=0) — excluded from default history load,
does NOT touch FTS content; reversible via backup copy.

Usage:
  python scripts/repair_scaffold_user_messages.py --session memomics-cd677556            # dry-run
  python scripts/repair_scaffold_user_messages.py --session memomics-cd677556 --apply    # backup+apply
"""
import argparse
import datetime
import os
import shutil
import sqlite3
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="memomics-cd677556")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db", default="E:/MemOmics-Agent/hermes_home/state.db")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print("DB not found:", args.db)
        sys.exit(1)

    prefixes = ("[会话要求%", "[系统唤醒%", "[相关历史记忆%", "[会话锚点%", "[数据读取配方%")
    like = " OR ".join(["content LIKE ?"] * len(prefixes))

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    params = (args.session,) + tuple(prefixes)
    cur.execute(f"SELECT COUNT(*) FROM messages WHERE session_id=? AND role='user' AND ({like})", params)
    count = cur.fetchone()[0]
    print(f"[dry-run] scaffold user messages found: {count}")
    if not args.apply:
        print("  use --apply to soft-delete (active=0). run stops here.")
        conn.close()
        return

    bak = args.db + ".bak-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(args.db, bak)
    print(f"[backup] copied to {bak}")

    cur.execute(f"UPDATE messages SET active=0 WHERE session_id=? AND role='user' AND ({like})", params)
    conn.commit()
    print(f"[applied] soft-deleted {cur.rowcount} scaffold user messages (active=0)")
    conn.close()
    print("done")


if __name__ == "__main__":
    main()
