# -*- coding: utf-8 -*-
"""统一系统提示后验证：heavy → light → heavy 交替，每轮首调用命中率"""
import asyncio, json, time
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"

MSGS = [
    # heavy：数据路径 + 执行关键词
    "用工具读一下 E:/骨骼肌锻炼/MF_AUCell_meta.csv 的前 5 行，报告列名。",
    # light：闲聊/知识问（无执行）
    "R 语言里 dplyr 的 filter 和 slice 有什么区别？一句话回答。",
    # heavy again：不同分析问题
    "统计 E:/骨骼肌锻炼/MF_AUCell_meta.csv 有多少列（用工具数），只回答数字。",
]

async def last_turn():
    path = r"E:\MemOmics-Agent\results\memomics-2274ab75\token_usage.jsonl"
    last = None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            last = json.loads(line)
    return last

async def main():
    async with websockets.connect(WS_URL, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "switch_session", "session_id": SID}, ensure_ascii=False))
        await asyncio.sleep(2)
        for i, text in enumerate(MSGS, 1):
            kind = "heavy" if i in (1, 3) else "light"
            print(f"===== ROUND {i} [{kind}]: {text[:36]}...", flush=True)
            await ws.send(json.dumps({"type": "chat", "session_id": SID, "message": text}, ensure_ascii=False))
            got = False
            deadline = time.time() + 420
            while time.time() < deadline and not got:
                try:
                    evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                except asyncio.TimeoutError:
                    continue
                if evt.get("type") == "complete":
                    got = True
            await asyncio.sleep(2)
            lt = await last_turn()
            d = (lt or {}).get("deltas") or {}
            billed = d.get("input_tokens", 0) + d.get("cache_read_tokens", 0) + d.get("cache_write_tokens", 0)
            hit = 100.0 * d.get("cache_read_tokens", 0) / billed if billed else 0
            calls = d.get("api_calls", 0) or 1
            per = billed // calls
            print(f"  done={got} | 回合总输入={billed:,} 未缓存={d.get('input_tokens',0):,} "
                  f"命中={hit:.0f}% api_calls={calls} 每调用≈{per:,}", flush=True)

asyncio.run(main())
