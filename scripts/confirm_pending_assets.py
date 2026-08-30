# -*- coding: utf-8 -*-
"""幂等迁移：确认存量 pending 资产（路径真实存在 → confirmed；不存在 → 留 pending）。

2026-08-31 落地：资产确认链接线后，把历史遗留的 pending 资产一次性升级，
使 holographic 的「📌 会话资产清单」与 search_assets 立刻开始工作。

用法：python scripts/confirm_pending_assets.py [--dry-run]
安全：先 SQLite backup 一份（同目录 .bak_prewire_时间戳），再更新。
"""
import argparse
import os
import sqlite3
import time

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "hermes_home", "memory_store.db")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(DB):
        print(f"DB not found: {DB}")
        return

    if not args.dry_run:
        bak = DB + ".bak_prewire_" + time.strftime("%Y%m%d-%H%M%S")
        src = sqlite3.connect(DB)
        dst = sqlite3.connect(bak)
        src.backup(dst)
        dst.close()
        src.close()
        print(f"backup -> {bak}")

    conn = sqlite3.connect(DB, timeout=15)
    rows = conn.execute("SELECT asset_id, path FROM assets WHERE status='pending'").fetchall()
    confirmed = missing = 0
    for aid, path in rows:
        if os.path.isfile(path):
            if not args.dry_run:
                conn.execute(
                    "UPDATE assets SET status='confirmed', updated_at=CURRENT_TIMESTAMP WHERE asset_id=?",
                    (aid,),
                )
            confirmed += 1
            print(f"  confirm id={aid} {path}")
        else:
            missing += 1
            print(f"  keep-pending id={aid} {path} (file missing)")
    if not args.dry_run:
        conn.commit()
    conn.close()
    print(f"summary: confirmed={confirmed} missing={missing} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
