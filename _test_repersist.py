# 复现实验：新会话 WS 聊天后，state.db 是否含 user 行（cf659495 曾丢失 user）
import asyncio, json, sqlite3, os, time
import httpx, websockets

BASE = "http://localhost:8899"
HH = os.path.expanduser("~/memomics-test/MemOmics/hermes_home")

def db_rows(sid):
    c = sqlite3.connect(os.path.join(HH, "state.db"))
    rows = c.execute("SELECT role, length(content) FROM messages WHERE session_id=?", (sid,)).fetchall()
    c.close()
    return rows

async def main():
    async with httpx.AsyncClient(timeout=15) as c:
        sid = (await c.post(BASE + "/api/sessions/new")).json().get("id")
    print("新会话:", sid)
    evs = []
    async with websockets.connect("ws://localhost:8899/ws", max_size=2**24) as ws:
        await ws.send(json.dumps({"type": "chat", "message": "你好，请用一句话回复。",
                                  "session_id": sid, "background": False, "images": []}, ensure_ascii=False))
        end = time.time() + 120
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
                ev = json.loads(raw)
                evs.append(ev.get("type"))
                if ev.get("type") in ("complete", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                evs.append("ERR:" + str(e)[:40])
                break
    print("events:", evs[:10], "| complete:", "complete" in evs)
    for delay in (0.5, 3.0, 8.0):
        await asyncio.sleep(delay)
        print(f"延迟{delay}s 后 DB:", db_rows(sid))

asyncio.run(main())