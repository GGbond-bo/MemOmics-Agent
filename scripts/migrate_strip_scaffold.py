# -*- coding: utf-8 -*-
"""一次性迁移：清理 state.db 历史 user 消息里的注入脚手架（2026-08-31 实测 65% 污染）。

背景：8-21 (b) 修复已保证**新消息**不再带脚手架持久化（_run_text=user_text 干净），
但 938 条历史消息仍带 "[会话要求…]" 前缀——search_history / prefetch 历史源 /
auto_extract 全在被污染的输入上跑。本脚本只剥离前缀、保留用户原文：
- 带原文的：剥离前缀层，content 只留真实用户文本
- 纯脚手架（无原文）：保持原样（(b) 卫生已在模型侧过滤，DB 不动防 rewind 断裂）
- 消息末尾 40 字符不变 → _resolve_message_id 的 rewind 断点匹配不受影响
另：回填 assets.project（= 该会话 results_dir 的 basename，来自 sessions.cwd）。

用法：python scripts/migrate_strip_scaffold.py [--dry-run]
安全：先 SQLite backup 到 state.db.bak_strip_时间戳。
"""
import argparse
import os
import re
import sqlite3
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DB = os.path.join(ROOT, "hermes_home", "state.db")
MEM_DB = os.path.join(ROOT, "hermes_home", "memory_store.db")

_PREFIXES = ("[会话要求", "[相关历史记忆", "[会话锚点", "[System:", "[数据读取配方", "📊 LoopX")
# 整条注入（无用户原文）：唤醒消息从头到尾都是系统内容，剥离后剩的还是系统指令
_WHOLE_INJECT = ("[系统唤醒", "⏰ [系统唤醒", "[wakeup-progress-check]")


def strip_scaffold(text: str) -> str:
    t = (text or "").strip()
    n = 0
    while n < 8:
        if t.startswith(_WHOLE_INJECT):
            return ""  # 整条系统注入 → 调用方保持原样
        if not t.startswith(_PREFIXES):
            return t
        idx = t.rfind("\n\n")
        if idx == -1:
            return ""  # 纯脚手架，无原文 → 调用方保持原样
        t = t[idx + 2:].strip()
        n += 1
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.dry_run:
        bak = STATE_DB + ".bak_strip_" + time.strftime("%Y%m%d-%H%M%S")
        src = sqlite3.connect(STATE_DB)
        dst = sqlite3.connect(bak)
        src.backup(dst)
        dst.close()
        src.close()
        print(f"backup -> {bak}")

    conn = sqlite3.connect(STATE_DB, timeout=30)
    rows = conn.execute(
        "SELECT id, content FROM messages WHERE role IN ('user','human')"
    ).fetchall()
    _inject_prefixes = _PREFIXES + _WHOLE_INJECT
    updates = []
    skipped_pure = 0
    for mid, content in rows:
        if not content or not str(content).startswith(_inject_prefixes):
            continue
        stripped = strip_scaffold(str(content))
        if not stripped:
            skipped_pure += 1
            continue
        updates.append((stripped, mid))
    print(f"scaffold-bearing rows: {sum(1 for _, c in rows if c and str(c).startswith(_inject_prefixes))} "
          f"| will strip: {len(updates)} | pure-scaffold kept: {skipped_pure}")
    for i, (stripped, mid) in enumerate(updates[:3]):
        print(f"  e.g. id={mid}: {stripped[:70]}")
    if not args.dry_run:
        conn.executemany("UPDATE messages SET content=? WHERE id=?", updates)
        conn.commit()
        print(f"stripped: {len(updates)}")
    conn.close()
    print("assets.project backfill: skipped — sessions.cwd 大多为空（仅 rename_results 写过），无可靠映射来源")


if __name__ == "__main__":
    main()
