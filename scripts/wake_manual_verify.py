# -*- coding: utf-8 -*-
"""手动唤醒验证：wakeup API × 2（中间改 task_plan），对比唤醒命中率"""
import asyncio, json, time, urllib.request
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"
PLAN = r"E:\MemOmics-Agent\results\memomics-2274ab75\task_plan.md"

def wakeup(reason="progress", msg="manual test"):
    body = json.dumps({"reason": reason, "msg": msg}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8899/api/sessions/{SID}/wakeup",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def last_self_checks(n=3):
    path = r"E:\MemOmics-Agent\results\memomics-2274ab75\token_usage.jsonl"
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            if r.get("turn_kind") == "self_check":
                out.append(r)
    return out[-n:]

def fmt(r):
    d = r["deltas"]
    billed = d["input_tokens"] + d["cache_read_tokens"] + d["cache_write_tokens"]
    hit = 100.0 * d["cache_read_tokens"] / billed if billed else 0
    return "{} | 输入={:>8,} 缓存读={:>9,} 命中={:4.0f}% api={}".format(
        r["ts"][11:19], d["input_tokens"], d["cache_read_tokens"], hit, d.get("api_calls", 0))

async def main():
    n0 = len(last_self_checks(1000))
    print("当前 self_check 总数:", n0, flush=True)
    # W1：task_plan 现状下唤醒
    print("→ 触发唤醒 W1 (task_plan 现状)", flush=True)
    print("  ", wakeup(), flush=True)
    async with websockets.connect(WS_URL, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "switch_session", "session_id": SID}, ensure_ascii=False))
        await asyncio.sleep(2)
        # 等唤醒回合完成（观察 complete 或超时）
        deadline = time.time() + 240
        while time.time() < deadline:
            try:
                evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
            except asyncio.TimeoutError:
                continue
            if evt.get("type") in ("complete", "agent_done"):
                break
        await asyncio.sleep(3)
        sc1 = last_self_checks(1)
        print("W1:", fmt(sc1[-1]), flush=True)
        # 改 task_plan
        try:
            txt = open(PLAN, encoding="utf-8").read()
            open(PLAN, "w", encoding="utf-8").write(txt + "\n- [x] Phase1 完成 (2026-08-22 手动)\n- [ ] Phase2: 样本 B doubletfinder\n")
            print("→ task_plan 已更新", flush=True)
        except Exception as e:
            print("task_plan 更新失败:", e, flush=True)
        # W2：task_plan 更新后唤醒
        print("→ 触发唤醒 W2 (task_plan 已更新)", flush=True)
        print("  ", wakeup(), flush=True)
        deadline = time.time() + 240
        while time.time() < deadline:
            try:
                evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
            except asyncio.TimeoutError:
                continue
            if evt.get("type") in ("complete", "agent_done"):
                break
        await asyncio.sleep(3)
        sc2 = last_self_checks(1)
        print("W2:", fmt(sc2[-1]), flush=True)
        # W3：task_plan 不变再唤醒
        print("→ 触发唤醒 W3 (task_plan 不变)", flush=True)
        print("  ", wakeup(), flush=True)
        deadline = time.time() + 240
        while time.time() < deadline:
            try:
                evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
            except asyncio.TimeoutError:
                continue
            if evt.get("type") in ("complete", "agent_done"):
                break
        await asyncio.sleep(3)
        sc3 = last_self_checks(1)
        print("W3:", fmt(sc3[-1]), flush=True)

asyncio.run(main())
