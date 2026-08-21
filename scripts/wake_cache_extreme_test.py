# -*- coding: utf-8 -*-
"""多轮多场景极端测试：唤醒上下文缓存固定化（task_plan 摘要尾部）

场景序列：
 A. 发起长任务（产生 task_plan + 后台 sleep）→ 等自动唤醒 W1
 B. 改 task_plan（模拟任务进展）→ 等唤醒 W2 → 验证前缀稳定（命中率应高）
 C. 连续唤醒 W3（task_plan 不变）→ 命中率应 95%+
 D. 主循环消息穿插（用户轮）→ 主循环 99% + 唤醒不受影响
"""
import asyncio, json, time
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"
PLAN = r"E:\MemOmics-Agent\results\memomics-2274ab75\task_plan.md"

def last_self_checks(n=6):
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
    return "{} | 输入={:>9,} 缓存读={:>10,} 命中={:4.0f}% api={}".format(
        r["ts"][11:19], d["input_tokens"], d["cache_read_tokens"], hit, d.get("api_calls", 0))

async def wait_turns(ws, timeout=900):
    got = False
    deadline = time.time() + timeout
    while time.time() < deadline and not got:
        try:
            evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        except asyncio.TimeoutError:
            continue
        if evt.get("type") == "complete":
            got = True
    return got

async def wait_new_self_check(baseline_n, timeout=1800):
    """等出现新的 self_check 回合"""
    start = time.time()
    while time.time() - start < timeout:
        sc = last_self_checks(3)
        if len(sc) > baseline_n:
            return sc
        await asyncio.sleep(15)
    return last_self_checks(3)

async def main():
    async with websockets.connect(WS_URL, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "switch_session", "session_id": SID}, ensure_ascii=False))
        await asyncio.sleep(2)
        base_sc = len(last_self_checks(100))

        # ── A. 发起长任务（写 task_plan + 后台进程）──
        print("===== A. 发起长任务 =====", flush=True)
        await ws.send(json.dumps({"type": "chat", "session_id": SID,
            "message": "新建一个后台任务：用 terminal 后台跑 `python -c \"import time; time.sleep(600)\"`（sleep 10 分钟），并写好 task_plan.md 记录这个任务。完成后只回复 OK。"}, ensure_ascii=False))
        await wait_turns(ws)
        print("  任务已发起，task_plan:", flush=True)
        try:
            print("  ", open(PLAN, encoding="utf-8").read()[:300].replace(chr(10), " | "), flush=True)
        except Exception as e:
            print("  (无 task_plan:", e, ")", flush=True)

        # ── 等 W1 ──
        print("===== 等待唤醒 W1 =====", flush=True)
        sc1 = await wait_new_self_check(base_sc)
        for r in sc1:
            print("  ", fmt(r), flush=True)

        # ── B. 修改 task_plan（模拟进展）──
        print("===== B. 修改 task_plan → 等唤醒 W2 =====", flush=True)
        try:
            txt = open(PLAN, encoding="utf-8").read()
            open(PLAN, "w", encoding="utf-8").write(txt + "\n- [x] Phase1 完成 (2026-08-22)\n- [ ] Phase2 启动: 样本 B\n")
            print("  task_plan 已更新", flush=True)
        except Exception as e:
            print("  更新失败:", e, flush=True)
        sc2 = await wait_new_self_check(len(last_self_checks(100)) + len(sc1) - len(sc1) if False else len(last_self_checks(100)))
        # 等新唤醒（比 W1 更多）
        while len(last_self_checks(100)) <= len(sc1):
            await asyncio.sleep(15)
        sc2 = last_self_checks(3)
        for r in sc2:
            print("  ", fmt(r), flush=True)

        # ── C. 再等一个唤醒 W3（task_plan 不变）──
        print("===== C. 等唤醒 W3（task_plan 不变）=====", flush=True)
        while len(last_self_checks(100)) <= len(sc2):
            await asyncio.sleep(15)
        sc3 = last_self_checks(2)
        for r in sc3:
            print("  ", fmt(r), flush=True)

        # ── D. 主循环穿插 ──
        print("===== D. 主循环消息（穿插唤醒）=====", flush=True)
        await ws.send(json.dumps({"type": "chat", "session_id": SID,
            "message": "后台任务还在跑吗？用 process 检查一下，一句话回答。"}, ensure_ascii=False))
        await wait_turns(ws)
        import os
        path = r"E:\MemOmics-Agent\results\memomics-2274ab75\token_usage.jsonl"
        last = None
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                last = json.loads(line)
        print("  主循环回合:", fmt(last), flush=True)

asyncio.run(main())
