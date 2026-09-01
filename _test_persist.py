import asyncio, json, sys, time
import websockets
try:
    import httpx
except ImportError:
    httpx = None

BASE = "http://localhost:8899"
WS = "ws://localhost:8899/ws"

async def http_get(path):
    if httpx:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(BASE + path)
            return r.status_code, r.text
    return -1, ""

async def main(msg_text):
    # 1. 建会话
    sc, body = await http_get("/api/sessions/new") if False else (0, "")
    # /api/sessions/new 是 POST，分开处理
    sid = None
    if httpx:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(BASE + "/api/sessions/new")
            d = r.json()
            sid = d.get("id") or d.get("session_id")
    print(f"[1] session = {sid}")

    # 2. WS 发消息
    events = []
    async with websockets.connect(WS, max_size=2**24) as ws:
        await ws.send(json.dumps({"type":"chat","message":msg_text,"session_id":sid,"background":False,"images":[]}, ensure_ascii=False))
        end = time.time() + 25
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2)
                ev = json.loads(raw)
                t = ev.get("type")
                c = (ev.get("content") or ev.get("delta") or ev.get("message") or ev.get("error") or "")
                events.append((t, str(c)[:80]))
                if t in ("done","error","agent_done","stopped"):
                    break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                events.append(("CONN_ERR", str(e)[:80]))
                break

    print(f"[2] events ({len(events)}):")
    for t, c in events:
        print(f"    {t}: {c!r}")

    # 3. 查消息接口（模拟刷新回放）
    sc, body = await http_get(f"/api/sessions/{sid}/messages?limit=100")
    print(f"[3] GET messages -> HTTP {sc}")
    try:
        d = json.loads(body)
        msgs = d.get("messages", [])
        print(f"    total={d.get('total')} returned={len(msgs)}")
        for m in msgs:
            print(f"    [{m.get('role')}] {str(m.get('content'))[:60]!r}")
    except Exception as e:
        print("    parse err", e, body[:200])

    # 4. 直接查 state.db 里的消息条数
    sql = "SELECT COUNT(*) FROM messages"
    print(f"[4] state.db check (sid={sid})")

    return sid

if __name__ == "__main__":
    sid = asyncio.run(main("测试消息：你好，我叫小王，请记住这个名字"))
    print("SID=" + str(sid))
    # 把 sid 写到文件供下一步测试
    with open("/tmp/memomics_test_sid.txt", "w") as f:
        f.write(str(sid or ""))