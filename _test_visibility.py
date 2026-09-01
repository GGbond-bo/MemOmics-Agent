# 验证双实例可见性是缓存延迟还是真丢数据
import json, sqlite3, os, time, sys
import httpx

HH = os.path.expanduser("~/memomics-test/MemOmics/hermes_home")

def db_recent(limit=8):
    c = sqlite3.connect(os.path.join(HH, "state.db"))
    rows = c.execute(
        "SELECT session_id, role, substr(content,1,40) FROM messages "
        "WHERE session_id LIKE 'memomics-%' ORDER BY rowid DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    return rows

def list_sessions(port):
    with httpx.Client(timeout=10) as c:
        r = c.get(f"http://localhost:{port}/api/sessions")
        return r.json().get("sessions", []) if r.status_code == 200 else None

print("=== 双实例可见性复查（缓存 TTL 后） ===")
s8899 = list_sessions(8899)
print("8899 sessions:", len(s8899) if s8899 else None)
print("8898 还活着吗:", end=" ")
try:
    with httpx.Client(timeout=4) as c:
        r = c.get("http://localhost:8898/api/health")
        print("是" if r.status_code == 200 else "否")
except Exception as e:
    print("否（已按脚本结束被清理）", str(e)[:40])

rows = db_recent()
print("\nstate.db 最近消息（直查，不经过任何实例的内存）:")
for sid, role, head in rows:
    print(f"  {sid[:24]:26s} {role:9s} {head!r}")

# 关键：两条并发会话（并发测试A/B）是否都在库里、角色齐全
need = {"并发测试", "记住数字"}
present = {}
for sid, role, head in rows:
    for kw in ("并发测试A", "并发测试B"):
        if head and kw in head or (kw in (sid or "")):
            present.setdefault(kw, []).append((role, head[:20]))
print("\n并发会话消息核对:", present if present else "未在最近消息中出现(可能被中间测试淹没, 改查全库)")
if not present:
    c = sqlite3.connect(os.path.join(HH, "state.db"))
    rows2 = c.execute(
        "SELECT session_id, role, substr(content,1,60) FROM messages "
        "WHERE content LIKE '%并发测试%' OR content LIKE '%记住数字%'").fetchall()
    c.close()
    print("全库检索:", [(r[0][:20], r[1], r[2]) for r in rows2])