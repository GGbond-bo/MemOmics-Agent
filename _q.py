import sqlite3, os
c = sqlite3.connect(os.path.expanduser("~/memomics-test/MemOmics/hermes_home/state.db"))
for sid in ("memomics-cf659495", "memomics-a2bd91e0", "memomics-e0b5c675"):
    rows = c.execute(
        "SELECT rowid, role, length(content), substr(content,1,36) FROM messages WHERE session_id=? ORDER BY rowid",
        (sid,)).fetchall()
    print(sid[:20], "->", [(r[1], r[2], r[3]) for r in rows])
# 顺便：消息表结构（确认 role 字段/是否有 deleted 标记）
cols = [r[1] for r in c.execute("PRAGMA table_info(messages)").fetchall()]
print("messages 列:", cols)
c.close()