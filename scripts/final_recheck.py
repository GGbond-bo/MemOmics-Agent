# -*- coding: utf-8 -*-
"""最终复验：画图任务(不入库) → light → 检查 REQUIREMENTS 无污染 + 命中率"""
import asyncio, json, time
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"

MSGS = [
    "用 E:/骨骼肌锻炼/MF_AUCell_meta.csv 画一张 RP_high+ 亚群 scoreROS 的小提琴图，先看 scripts/ 有没有现成脚本。",
    "R 里 %>% 管道符是干什么的？一句话。",
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
            print(f"===== ROUND {i} =====", flush=True)
            await ws.send(json.dumps({"type": "chat", "session_id": SID, "message": text}, ensure_ascii=False))
            got = False
            deadline = time.time() + 600
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
            print(f"  done={got} | 命中={hit:.0f}% 未缓存={d.get('input_tokens',0):,} 总={billed:,} api_calls={d.get('api_calls',0)}", flush=True)

asyncio.run(main())
