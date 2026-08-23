# -*- coding: utf-8 -*-
"""任务1：科研场景极端测试 — 小提琴图→打断→继续画图→混合场景，测命中率+脚本/环境复用"""
import asyncio, json, time
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"

# 场景序列（真实科研流：画图 → 打断问别的 → 继续画图 → 更多混合）
SCENARIOS = [
    ("heavy-violin-1", "用 E:/骨骼肌锻炼/MF_AUCell_meta.csv 画一张 LRP1B+ 亚群 AMPK_PGC1a 打分的小提琴图。先看 scripts/ 有没有现成脚本，有就直接复用改数据路径，没有就写新的。"),
    ("light-interrupt", "顺便问一下：R 里 factor 和 character 类型有什么区别？一句话。"),
    ("heavy-violin-2", "继续画图：再画一张 OTUD1+ 亚群 scoreAtrophy 的小提琴图，风格和上一张保持一致。"),
    ("heavy-other", "用同一个数据文件，统计一下 26 个 *_AUC 打分列的平均值，列个表。"),
    ("light-progress", "我刚才让你画的两张图都出来了吗？"),
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
        tools_seen = []
        for i, (kind, text) in enumerate(SCENARIOS, 1):
            print(f"===== SCENARIO {i} [{kind}] =====", flush=True)
            await ws.send(json.dumps({"type": "chat", "session_id": SID, "message": text}, ensure_ascii=False))
            got = False
            deadline = time.time() + 600
            while time.time() < deadline and not got:
                try:
                    evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                except asyncio.TimeoutError:
                    continue
                t = evt.get("type")
                if t == "tool_start":
                    tools_seen.append(evt.get("tool", "?"))
                if t == "complete":
                    got = True
            await asyncio.sleep(2)
            lt = await last_turn()
            d = (lt or {}).get("deltas") or {}
            billed = d.get("input_tokens", 0) + d.get("cache_read_tokens", 0) + d.get("cache_write_tokens", 0)
            hit = 100.0 * d.get("cache_read_tokens", 0) / billed if billed else 0
            calls = d.get("api_calls", 0) or 1
            print(f"  命中={hit:.0f}% 未缓存={d.get('input_tokens',0):,} 总={billed:,} api_calls={calls} llm_ms={d.get('llm_ms',0)}", flush=True)
        # 工具调用统计
        from collections import Counter
        cnt = Counter(tools_seen)
        print("=== 工具调用统计 ===", flush=True)
        for k, v in cnt.most_common(15):
            print(f"  {k}: {v}", flush=True)

asyncio.run(main())
