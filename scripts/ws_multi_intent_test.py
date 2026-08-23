# -*- coding: utf-8 -*-
"""批K 多意图多场景测试：真实 agent 会话，观察不同意图下工具路由。"""
import json
import time
import urllib.request

import websocket

BASE = "http://127.0.0.1:8899"
WS = "ws://127.0.0.1:8899/ws"

TURNS = [
    ("方向2·入库意图", "帮我把文献库里的 10.1016_j.freeradbiomed.2024.07.026.pdf 提炼进知识库（调用 kb_extract_from_paper）。", "kb_extract_from_paper"),
    ("方向1·全文摘要意图", "总结文献库里 10.1016_j.freeradbiomed.2024.07.026.pdf 的研究思路，给出9项摘要（调用 summarize_paper）。", "summarize_paper"),
    ("查询意图", "文献库里还有哪些文章没有做全文提炼？只列文件名，不要提炼。", None),
]


def http_json(method, path, payload=None):
    data = json.dumps(payload or {}).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def log(msg):
    print(msg, flush=True)


def main():
    s = http_json("POST", "/api/sessions/new", {"title": "批K-多意图路由测试"})
    sid = s["id"]
    log("session: " + sid)
    state = {"tools": [], "done": False}

    def on_msg(ws, message):
        try:
            ev = json.loads(message)
        except Exception:
            return
        t = ev.get("type")
        if t == "tool_start":
            state["tools"].append(ev.get("tool"))
        if t == "complete":
            state["done"] = True

    ws = websocket.WebSocketApp(WS, on_message=on_msg)
    import threading
    th = threading.Thread(target=ws.run_forever, kwargs={"ping_interval": 20}, daemon=True)
    th.start()
    for _ in range(50):
        if ws.sock and ws.sock.connected:
            break
        time.sleep(0.2)
    ws.send(json.dumps({"type": "switch_session", "session_id": sid}, ensure_ascii=False))
    time.sleep(0.5)

    all_ok = True
    for label, msg, expect in TURNS:
        state["tools"] = []
        state["done"] = False
        ws.send(json.dumps({"type": "chat", "session_id": sid, "message": msg}, ensure_ascii=False))
        t0 = time.time()
        while time.time() - t0 < 240 and not state["done"]:
            time.sleep(1)
        tools = state["tools"]
        hit = expect in tools if expect else True
        all_ok = all_ok and hit
        log(f"{'PASS' if hit else 'FAIL'} | {label} | tools={tools[:8]}" + ("" if expect else " (仅观察)"))
        if not state["done"]:
            log("  ⚠️ 回合未在 240s 内完成")
            all_ok = False
        time.sleep(1)
    ws.close()
    log("RESULT: " + ("ALL PASS" if all_ok else "FAIL"))
    try:
        http_json("DELETE", f"/api/sessions/{sid}")
        log("test session deleted")
    except Exception as e:
        log("cleanup warn: " + str(e))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
