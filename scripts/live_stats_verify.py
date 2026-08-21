# -*- coding: utf-8 -*-
"""验证新统计：基线 get_context_usage → 跑一轮 → 再取对比"""
import asyncio, json, time
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"

def show(tag, ss):
    print(f"[{tag}]", flush=True)
    if not ss:
        print("  (no session_stats)", flush=True)
        return
    for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
              "billed_input_tokens", "cache_hit_percent", "api_calls", "llm_ms",
              "llm_seconds", "tokens_per_sec", "turns"):
        print(f"  {k} = {ss.get(k)}", flush=True)

async def main():
    async with websockets.connect(WS_URL, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "switch_session", "session_id": SID}, ensure_ascii=False))
        # 基线
        await ws.send(json.dumps({"type": "get_context_usage", "session_id": SID}, ensure_ascii=False))
        base = None
        deadline = time.time() + 30
        while time.time() < deadline and base is None:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            evt = json.loads(raw)
            if evt.get("type") == "context_usage":
                base = evt.get("data") or {}
        show("BASELINE", (base or {}).get("session_stats"))
        # 跑一轮
        await ws.send(json.dumps({"type": "chat", "session_id": SID,
                                  "message": "只用一句话回答：按记忆，本机 R 版本和 R 库目录是什么？（不要调用工具）"},
                                 ensure_ascii=False))
        got = False
        deadline = time.time() + 300
        while time.time() < deadline and not got:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
            except asyncio.TimeoutError:
                continue
            evt = json.loads(raw)
            if evt.get("type") == "complete":
                got = True
        print(f"[TURN] done={got}", flush=True)
        # 回合后统计
        await ws.send(json.dumps({"type": "get_context_usage", "session_id": SID}, ensure_ascii=False))
        after = None
        deadline = time.time() + 30
        while time.time() < deadline and after is None:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            evt = json.loads(raw)
            if evt.get("type") == "context_usage":
                after = evt.get("data") or {}
        show("AFTER", (after or {}).get("session_stats"))

asyncio.run(main())
