# -*- coding: utf-8 -*-
"""T3：验证 llm_ms 差分准确 + context_usage 带 last_turn"""
import asyncio, json, time
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"

async def main():
    async with websockets.connect(WS_URL, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "switch_session", "session_id": SID}, ensure_ascii=False))
        await ws.send(json.dumps({"type": "get_context_usage", "session_id": SID}, ensure_ascii=False))
        base = None
        deadline = time.time() + 30
        while time.time() < deadline and base is None:
            evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if evt.get("type") == "context_usage":
                base = evt.get("data") or {}
        print("BASELINE llm_ms:", (base or {}).get("session_stats", {}).get("llm_ms"), flush=True)
        await ws.send(json.dumps({"type": "chat", "session_id": SID,
                                  "message": "用一句话回答：1+1 等于几？（不要调用工具）"}, ensure_ascii=False))
        got = False
        deadline = time.time() + 300
        while time.time() < deadline and not got:
            try:
                evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            except asyncio.TimeoutError:
                continue
            if evt.get("type") == "complete":
                got = True
        print("TURN done:", got, flush=True)
        await ws.send(json.dumps({"type": "get_context_usage", "session_id": SID}, ensure_ascii=False))
        after = None
        deadline = time.time() + 30
        while time.time() < deadline and after is None:
            evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if evt.get("type") == "context_usage":
                after = evt.get("data") or {}
        ss = (after or {}).get("session_stats") or {}
        lt = ss.get("last_turn") or {}
        print("AFTER llm_ms:", ss.get("llm_ms"), flush=True)
        print("last_turn:", json.dumps({k: lt.get(k) for k in ("ts", "output_tokens", "llm_ms", "llm_seconds", "tokens_per_sec", "cache_read_tokens", "billed_input_tokens", "cache_hit_percent", "api_calls")}, ensure_ascii=False), flush=True)

asyncio.run(main())
