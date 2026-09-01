import sqlite3, json, os
import httpx

BASE = "http://localhost:8899"
DB = os.path.expanduser("~/memomics-test/MemOmics/hermes_home/state.db")
SID = "memomics-fd5c39c8"

print("=== [1] state.db 里的消息行 ===")
c = sqlite3.connect(DB)
rows = c.execute("SELECT role, substr(content,1,60) FROM messages WHERE session_id=? ORDER BY rowid", (SID,)).fetchall()
print(f"  {len(rows)} rows:")
for r in rows:
    print(f"    [{r[0]}] {r[1]!r}")
# also show column names of messages table
cols = [x[1] for x in c.execute("PRAGMA table_info(messages)")]
print("  messages columns:", cols)

print("\n=== [2] 记忆写入测试（Linux 正确相对路径）===")
with httpx.Client(timeout=15) as cl:
    r = cl.get(BASE + "/api/memory")
    d = r.json()
    tok = d.get("api_token", "")
    print(f"  GET /api/memory -> entries={d.get('entries')}, token={bool(tok)}")
    # write
    w = cl.post(BASE + "/api/memory/write",
                headers={"X-Memory-Token": tok},
                json={"target": "MEMORY.md", "content": "- 测试记忆：用户偏好 Python", "mode": "append"})
    print("  POST write ->", w.status_code, w.text[:120])
    # read back
    r2 = cl.get(BASE + "/api/memory")
    d2 = r2.json()
    print("  GET /api/memory ->", json.dumps({k: v for k, v in d2.items() if k in ("memory", "entries")}, ensure_ascii=False)[:200])

print("\n=== [3] 记忆文件查看器路径对比（viewMemoryFile 用的路径 vs 后端给的路径）===")
with httpx.Client(timeout=15) as cl:
    d = cl.get(BASE + "/api/memory").json()
    if d.get("entries"):
        real_path = d["entries"][0]["path"]  # 后端返回的正确路径
        print(f"  后端返回的正确 path = {real_path!r}")
        # a) 前端硬编码的路径（bug）
        hard = "E:/MemOmics-Agent/hermes_home/memories/" + d["entries"][0]["name"]
        r1 = cl.get(BASE + "/api/file/read", params={"path": hard})
        print(f"  硬编码路径 ({hard!r}) -> HTTP {r1.status_code}: {r1.text[:80]}")
        # b) 正确路径（对比）
        r2 = cl.get(BASE + "/api/file/read", params={"path": real_path})
        print(f"  正确路径 ({real_path!r}) -> HTTP {r2.status_code}: {r2.text[:80]!r}")

print("\n=== [4] 服务是否还活着 ===")
import httpx as _h
try:
    rr = _h.get(BASE + "/api/health", timeout=5)
    print("  ", rr.text)
except Exception as e:
    print("  DOWN:", e)