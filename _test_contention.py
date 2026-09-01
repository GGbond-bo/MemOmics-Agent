# 双进程共享 hermes_home/state.db 并发测试（模拟集群多节点/登录节点共享同一目录）
# 前置：守护进程在 8899（实例 A）；本脚本另起实例 B 在 8898，两者同一 HERMES_HOME
import asyncio, json, sqlite3, os, time
import httpx
import websockets

def db_rows(extra=""):
    conn = sqlite3.connect(os.path.expanduser("~/memomics-test/MemOmics/hermes_home/state.db"))
    n_sess = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    msgs = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    conn.close()
    return n_sess, msgs

async def chat_one(port, sid, text):
    evs = []
    async with websockets.connect(f"ws://localhost:{port}/ws", max_size=2**24) as ws:
        await ws.send(json.dumps({"type": "chat", "message": text, "session_id": sid,
                                  "background": False, "images": []}, ensure_ascii=False))
        end = time.time() + 120
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=6)
                ev = json.loads(raw)
                evs.append(ev.get("type"))
                if ev.get("type") in ("complete", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                evs.append("ERR:" + str(e)[:40])
                break
    return evs

async def main():
    print("=== 双进程共享 state.db 并发争抢测试（8899 守护 + 8898 第二实例） ===")
    # 起第二实例（同 HERMES_HOME）
    proc = await asyncio.create_subprocess_exec(
        "bash", "-lc",
        "cd ~/memomics-test/MemOmics && nohup env HERMES_HOME=$PWD/hermes_home "
        "PYTHONPATH=$PWD:$PWD/hermes-agent MEMOMICS_PORT=8898 "
        ".venv/bin/python webui/server.py > log/webui-8898.log 2>&1 & echo $! > /tmp/second.pid",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()
    # 等 8898 就绪
    ok = False
    for _ in range(40):
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get("http://localhost:8898/api/health")
                if r.status_code == 200:
                    ok = True
                    break
        except Exception:
            pass
        await asyncio.sleep(2)
    print("  8898 第二实例就绪:", ok)
    if not ok:
        print("  !! 第二实例没起来")
        return

    n0s, n0m = db_rows()
    print(f"  并发前 state.db: sessions={n0s} messages={n0m}")

    async with httpx.AsyncClient(timeout=15) as c:
        sid_a = (await c.post("http://localhost:8899/api/sessions/new")).json().get("id")
        sid_b = (await c.post("http://localhost:8898/api/sessions/new")).json().get("id")

    # 同时向两个实例各发一条，模拟双节点并发写
    ev_a, ev_b = await asyncio.gather(
        chat_one(8899, sid_a, "并发测试A：记住数字42"),
        chat_one(8898, sid_b, "并发测试B：记住数字7"),
    )
    print("  A events:", ev_a[:8])
    print("  B events:", ev_b[:8])

    await asyncio.sleep(2)
    n1s, n1m = db_rows()
    print(f"  并发后 state.db: sessions={n1s} messages={n1m}")

    # 两个实例各自回读对方写入的会话（跨进程可见性）
    async with httpx.AsyncClient(timeout=15) as c:
        al = await c.get("http://localhost:8899/api/sessions")
        bl = await c.get("http://localhost:8898/api/sessions")
    a_ids = {s["id"] for s in al.json().get("sessions", [])}
    b_ids = {s["id"] for s in bl.json().get("sessions", [])}
    print("  8899 可见会话数:", len(a_ids), "| 包含 B 的会话:", sid_b in a_ids)
    print("  8898 可见会话数:", len(b_ids), "| 包含 A 的会话:", sid_a in b_ids)
    print("  双向可见:", "OK" if (sid_b in a_ids and sid_a in b_ids) else "PARTIAL")

    # 停掉第二实例
    proc2 = await asyncio.create_subprocess_exec(
        "bash", "-lc", "kill $(cat /tmp/second.pid) 2>/dev/null; true",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc2.wait()

asyncio.run(main())