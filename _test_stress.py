import asyncio, json, time
import httpx
import websockets

BASE = "http://localhost:8899"
WS = "ws://localhost:8899/ws"

async def new_sid(c):
    r = await c.post(BASE + "/api/sessions/new")
    return r.json().get("id")

async def chat(c, sid, text, timeout=150):
    """发一条消息，收集事件直到 complete/error，返回 (event_types, full_text)"""
    events, deltas = [], []
    async with websockets.connect(WS, max_size=2**24) as ws:
        await ws.send(json.dumps({"type": "chat", "message": text, "session_id": sid,
                                  "background": False, "images": []}, ensure_ascii=False))
        end = time.time() + timeout
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
                ev = json.loads(raw)
                events.append(ev.get("type"))
                if ev.get("type") == "delta":
                    deltas.append(ev.get("delta") or ev.get("content") or "")
                if ev.get("type") in ("complete", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                events.append("CONN_ERR:" + str(e)[:50])
                break
    return events, "".join(deltas)

print("=== [A] 记忆跨会话复述（症状③：经常忘记） ===")
async def memory_test():
    async with httpx.AsyncClient(timeout=15) as c:
        sid_a = await new_sid(c)
        ev_a, _ = await chat(c, sid_a, "请记住一条关于我的重要信息：我的研究主题是 ATAC 测序跨物种保守性比较。只回复“已记住”。")
        print(f"  会话A[记住] events={ev_a[:8]}  len={len(_)}")
        if "complete" not in ev_a:
            print("  !! 会话A 未完成"); return
        await asyncio.sleep(3)  # 给记忆落盘一点时间
        sid_b = await new_sid(c)
        ev_b, txt_b = await chat(c, sid_b, "根据你的长期记忆，我的研究主题是什么？只根据记忆回答，不要猜。")
        print(f"  会话B[复述] events={ev_b[:8]}")
        print(f"  会话B 回复: {txt_b[:200]!r}")
        hit = any(w in txt_b for w in ("ATAC", "保守", "跨物种", "转录"))
        print("  记忆复述命中:", "OK" if hit else "MISS")
        return sid_a, sid_b

print("=== [B] 流式稳定性：3 路并发对话（症状②：输出不稳定） ===")
async def streaming_test():
    async with httpx.AsyncClient(timeout=15) as c:
        sids = [await new_sid(c) for _ in range(3)]
        msgs = ["请用三句话介绍什么是单细胞测序。",
                "请列出基因表达差异分析的三种常用方法，一行一个。",
                "写一个 Python 函数：计算两个列表的交集，并说明用法。"]
        results = await asyncio.gather(*[chat(c, sid, m, timeout=180) for sid, m in zip(sids, msgs)])
    for i, (ev, txt) in enumerate(results):
        nd = sum(1 for e in ev if e == "delta")
        ok = "complete" in ev and len(txt) > 50
        print(f"  路{i+1}: complete={ok} deltas={nd} 总长={len(txt)}  events={ev[:10]}")
        if not ok:
            print(f"     !! 异常: {txt[:150]!r}")
    return results

sidA = sidB = None
try:
    dat = asyncio.run(memory_test())
    if dat:
        sidA, sidB = dat
except Exception as e:
    print("  [A] 失败:", str(e)[:150])
try:
    asyncio.run(streaming_test())
except Exception as e:
    print("  [B] 失败:", str(e)[:150])

print("\nSIDS", sidA, sidB)