# -*- coding: utf-8 -*-
"""验证：特别指定语义 + 记忆精选后的请求瘦身"""
import asyncio, json, time
import websockets

SID = "memomics-2274ab75"
WS_URL = "ws://127.0.0.1:8899/ws"

async def main():
    async with websockets.connect(WS_URL, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "switch_session", "session_id": SID}, ensure_ascii=False))
        await asyncio.sleep(2)
        # 1) 发"特别指定"消息
        await ws.send(json.dumps({"type": "chat", "session_id": SID,
            "message": "特别重要：以后所有出图默认 300dpi 输出并附 SVG，不要用 150dpi。记住这一点。"}, ensure_ascii=False))
        got = False
        deadline = time.time() + 420
        while time.time() < deadline and not got:
            try:
                evt = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            except asyncio.TimeoutError:
                continue
            if evt.get("type") == "complete":
                got = True
        await asyncio.sleep(3)
        # 2) REQUIREMENTS 检查
        p = r"E:\MemOmics-Agent\results\memomics-2274ab75\REQUIREMENTS.md"
        txt = open(p, encoding="utf-8").read()
        print("=== REQUIREMENTS ===")
        for ln in txt.splitlines():
            if ln.strip():
                print(" -", ln[:90])
        print("(特别指定) 置顶:", txt.splitlines()[0].startswith("特别") or "(特别指定)" in (txt.splitlines()[0] if txt.splitlines() else ""))
        # 3) 回合 token 数据
        path = r"E:\MemOmics-Agent\results\memomics-2274ab75\token_usage.jsonl"
        last = None
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                last = json.loads(line)
        d = last["deltas"]
        billed = d["input_tokens"] + d["cache_read_tokens"] + d["cache_write_tokens"]
        hit = 100.0 * d["cache_read_tokens"] / billed if billed else 0
        print(f"回合: 总输入={billed:,} 未缓存={d['input_tokens']:,} 命中={hit:.0f}% (重启后首轮)")
        # 4) 跨会话 facts 检查
        import sqlite3
        db = sqlite3.connect(r"E:\MemOmics-Agent\hermes_home\memory_store.db")
        rows = db.execute(
            "SELECT content, trust_score FROM facts WHERE category='user_pref' AND content LIKE '%300dpi%'"
        ).fetchall()
        db.close()
        print("=== facts 跨会话检查 (300dpi) ===")
        for r in rows:
            print(" -", r[0][:70], "| trust:", r[1])

asyncio.run(main())
