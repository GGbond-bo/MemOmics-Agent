# -*- coding: utf-8 -*-
"""KB 尾部注入缓存验证：连续两轮 heavy 分析消息，看第二轮命中率"""
import asyncio, json, time
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"

MSGS = [
    "帮我分析这个文件的结构：E:/骨骼肌锻炼/MF_AUCell_meta.csv。只做一件事：用工具读取文件头部并报告列名和前3行内容，不要跑完整分析。",
    "接着这个数据：E:/骨骼肌锻炼/MF_AUCell_meta.csv。统计一下总共有多少行数据（用工具数一下），只回答数字。",
]

async def last_turn():
    """读 jsonl 最后一行 deltas"""
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
            print(f"===== ROUND {i}: {text[:40]}...", flush=True)
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
            print(f"  done={got}", flush=True)
            await asyncio.sleep(2)
            lt = await last_turn()
            d = (lt or {}).get("deltas") or {}
            billed = d.get("input_tokens", 0) + d.get("cache_read_tokens", 0) + d.get("cache_write_tokens", 0)
            hit = 100.0 * d.get("cache_read_tokens", 0) / billed if billed else 0
            print(f"  ts={lt.get('ts')} 未缓存={d.get('input_tokens',0):,} 缓存读={d.get('cache_read_tokens',0):,} "
                  f"命中={hit:.0f}% api_calls={d.get('api_calls',0)} llm_ms={d.get('llm_ms',0)}", flush=True)

asyncio.run(main())
