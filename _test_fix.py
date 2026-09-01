import asyncio, json, time
import httpx
import websockets

BASE = "http://localhost:8899"
WS = "ws://localhost:8899/ws"

print("=== [1] /api/file/read 路由已注册？ ===")
with httpx.Client(timeout=15) as c:
    o = c.get(BASE + "/openapi.json").json()
    paths = o.get("paths", {})
    print("  /api/file/read in paths:", "/api/file/read" in paths)
    if "/api/file/read" in paths:
        print("  methods:", list(paths["/api/file/read"].keys()))

    print("\n=== [2] 记忆写入 → 用服务端 path 读取（修复验证） ===")
    d = c.get(BASE + "/api/memory").json()
    tok = d.get("api_token", "")
    w = c.post(BASE + "/api/memory/write",
               headers={"X-Memory-Token": tok},
               json={"target": "MEMORY.md",
                     "content": "- 修复验证：记忆查看器现在能读到内容了", "mode": "append"})
    print("  write:", w.status_code)
    d2 = c.get(BASE + "/api/memory").json()
    entry = next((e for e in d2.get("entries", []) if e["name"] == "MEMORY.md"), None)
    print("  entry.path =", entry["path"] if entry else None)
    if entry:
        r = c.get(BASE + "/api/file/read", params={"path": entry["path"]})
        print("  GET /api/file/read?path=entry.path ->", r.status_code)
        body = r.json()
        print("  content contains 修复验证:", "修复验证" in (body.get("content") or ""))
        print("  truncated/size:", body.get("truncated"), body.get("size"))
    else:
        print("  !! MEMORY.md entry not found")

    print("\n=== [3] 旧硬编码 E:/ 路径应被拒（死路径已废） ===")
    r3 = c.get(BASE + "/api/file/read", params={"path": "E:/MemOmics-Agent/hermes_home/memories/MEMORY.md"})
    print("  HTTP", r3.status_code, "-", r3.text[:80])

    print("\n=== [4] 越权路径应 403（安全性未放宽） ===")
    r4 = c.get(BASE + "/api/file/read", params={"path": "/etc/passwd"})
    print("  HTTP", r4.status_code, "-", r4.text[:80])

print("\n=== [5] 聊天 WS 无回归（应与修复前同流程：事件到达 + 用户消息落库） ===")
async def ws_sanity():
    async with httpx.AsyncClient(timeout=10) as c:
        s = await c.post(BASE + "/api/sessions/new")
        sid = s.json().get("id")
    events = []
    async with websockets.connect(WS, max_size=2**24) as ws:
        await ws.send(json.dumps({"type": "chat", "message": "修复回归测试", "session_id": sid,
                                  "background": False, "images": []}, ensure_ascii=False))
        end = time.time() + 15
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2)
                ev = json.loads(raw)
                events.append(ev.get("type"))
                if ev.get("type") in ("done", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                events.append("CONN_ERR:" + str(e)[:40])
                break
    print("  event types:", events[:8])
    async with httpx.AsyncClient(timeout=10) as c:
        m = (await c.get(f"{BASE}/api/sessions/{sid}/messages?limit=100")).json()
        roles = [x["role"] for x in m.get("messages", [])]
        print("  persisted roles:", roles)
    return sid

sid = asyncio.run(ws_sanity())
print("\nSID=" + str(sid))