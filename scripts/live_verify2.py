# -*- coding: utf-8 -*-
"""Live 验证（真实会话 memomics-2274ab75）：
A) scripts 约定确认标记 + 按记忆召回 R 版本/库目录
B) 新脚本应该放哪里的链路回答
"""
import asyncio, json, sys, time
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"

MESSAGES = [
    "就用 scripts/ 的约定，并按记忆回答：R 版本和 R 库目录是什么？",
    "好，请按约定继续。再回答一个问题：本会话新写的分析脚本应该保存到哪里？（只答路径/目录即可）",
]

async def main():
    async with websockets.connect(WS_URL, max_size=64 * 1024 * 1024) as ws:
        # 先切会话拿快照
        await ws.send(json.dumps({"type": "switch_session", "session_id": SID}, ensure_ascii=False))
        for round_no, text in enumerate(MESSAGES, 1):
            print(f"\n===== ROUND {round_no} SEND =====", flush=True)
            print(text, flush=True)
            await ws.send(json.dumps({"type": "chat", "session_id": SID, "message": text}, ensure_ascii=False))
            texts = []
            types = {}
            deadline = time.time() + 300
            got_final = False
            while time.time() < deadline and not got_final:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=20)
                except asyncio.TimeoutError:
                    print(f"[round {round_no}] recv timeout 20s (still waiting)", flush=True)
                    continue
                try:
                    evt = json.loads(raw)
                except Exception:
                    continue
                t = evt.get("type", "?")
                types[t] = types.get(t, 0) + 1
                # 收集回复文本
                for key in ("text", "content", "message", "partial"):
                    v = evt.get(key)
                    if isinstance(v, str) and v.strip():
                        texts.append(v.strip())
                        break
                if t in ("assistant_message", "assistant", "final_reply", "turn_complete", "message_done"):
                    got_final = True
                # agent 完成标志（与 WebUI 一致的判定）
                if t == "agent_done" or (t == "status" and evt.get("status") == "done"):
                    got_final = True
            print(f"[round {round_no}] event types: {json.dumps(types, ensure_ascii=False)}", flush=True)
            if texts:
                joined = "\n---\n".join(texts)
                print(f"[round {round_no}] REPLY TEXT:\n{joined[:4000]}", flush=True)
            else:
                print(f"[round {round_no}] NO REPLY TEXT COLLECTED", flush=True)

asyncio.run(main())
