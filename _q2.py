import sqlite3, os
c = sqlite3.connect(os.path.expanduser("~/memomics-test/MemOmics/hermes_home/state.db"))
rows = c.execute(
    "SELECT id, role, substr(content,1,24), length(api_content), active, compacted, timestamp "
    "FROM messages WHERE session_id=? ORDER BY rowid", ("memomics-cf659495",)).fetchall()
print("cf659495 全行:")
for r in rows:
    print("  ", r)
# 对比: 其他会话的 user 行是否正常带 content
rows2 = c.execute(
    "SELECT session_id, role, length(content), active, compacted, substr(content,1,20) "
    "FROM messages WHERE session_id LIKE 'memomics-%' AND role='user' ORDER BY rowid DESC LIMIT 5").fetchall()
print("\n最近 5 个 user 行:")
for r in rows2:
    print("  ", r)
c.close()