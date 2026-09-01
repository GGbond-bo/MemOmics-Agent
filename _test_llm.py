import asyncio, json, os, time
import httpx
import websockets

BASE = "http://localhost:8899"
WS = "ws://localhost:8899/ws"
HH = os.path.expanduser("~/memomics-test/MemOmics/hermes_home")

def get_key():
    import yaml
    with open(os.path.join(HH, "config.yaml"), encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    k = d.get("api_key") or ""
    return k, len(k), k[:5] == "sk-" and len(k) > 20

print("=== [0] 直连 DeepSeek 验证 key（不回显） ===")
k, klen, looks_ok = get_key()
print(f"  key len={klen}, 形态疑似有效: {looks_ok}")
if k and looks_ok:
    from openai import OpenAI
    c = OpenAI(api_key=k, base_url="https://api.deepseek.com/v1")
    try:
        r = c.chat.completions.create(model="deepseek-chat",
                                      messages=[{"role": "user", "content": "只回复两个字：正常"}],
                                      max_tokens=10, timeout=60)
        print("  LLM_DIRECT:", "OK |", r.choices[0].message.content or "", "- model:", r.model)
    except Exception as e:
        print("  LLM_DIRECT FAIL:", str(e)[:120])
else:
    print("  !! key 无效/缺失，跳过")

print("\n=== [1] CI 链路冒烟 ===")
with httpx.Client(timeout=20) as c:
    for path in ["/", "/api/health", "/api/update/check", "/api/env/check"]:
        r = c.get(BASE + path)
        print(f"  GET {path} -> {r.status_code}")

print("\n=== [2] WS 真实对话（全链路含流式） ===")
async def chat():
    async with httpx.AsyncClient(timeout=10) as c:
        s = await c.post(BASE + "/api/sessions/new")
        sid = s.json().get("id")
    events = []
    deltas = []
    async with websockets.connect(WS, max_size=2**24) as ws:
        await ws.send(json.dumps({"type": "chat", "message": "你好，请用一句话介绍你自己",
                                  "session_id": sid, "background": False, "images": []}, ensure_ascii=False))
        end = time.time() + 90
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                ev = json.loads(raw)
                t = ev.get("type")
                events.append(t)
                if t == "delta":
                    deltas.append(ev.get("delta") or ev.get("content") or "")
                if t in ("complete", "error", "cancelled"):
                    break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                events.append("CONN_ERR:" + str(e)[:50])
                break
    full = "".join(deltas)
    print(f"  events[{len(events)}]: {events[:14]}")
    print(f"  deltas[{len(deltas)}] 文本总长 {len(full)}")
    print(f"  首帧: {full[:60]!r}")
    print(f"  尾帧: {full[-60:]!r}")
    async with httpx.AsyncClient(timeout=10) as c:
        m = (await c.get(f"{BASE}/api/sessions/{sid}/messages?limit=100")).json()
        msgs = m.get("messages", [])
        print("  落库 roles:", [x["role"] for x in msgs], "| last len:", len(msgs[-1].get("content", "")) if msgs else 0)
    return sid, full

if __name__ == "__main__":
    sid, full = asyncio.run(chat())
    print("\nSID=" + sid)
    # 供后续复述/记忆测试复用
    with open("/tmp/memomics_llm_sid.txt", "w") as f:
        f.write(sid)
    with open("/tmp/memomics_llm_reply.txt", "w", encoding="utf-8") as f:
        f.write(full)