# -*- coding: utf-8 -*-
"""delegation 触发诊断冒烟：2 个应触发场景 + 回复内容 dump + 工具调用记录。"""
import json
import sqlite3
import sys
import time
import urllib.request

import websocket

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

BASE = "http://127.0.0.1:8899"
WS_URL = "ws://127.0.0.1:8899/ws"
STATE_DB = r"E:\MemOmics-Agent\hermes_home\state.db"
DATA = r"E:\MemOmics_test\results\human_skeletal_muscle_20260810"

SCENARIOS = [
    ("并行独立任务",
     "帮我分别调研：①Seurat 与 Scanpy 的整合流程差异 ②Monocle3 与 Slingshot 的拟时分析差异。两组调研互不依赖，内容都比较多，可以并行处理"),
    ("上下文隔离调研",
     "帮我调研 ArchR 和 SnapATAC 在 ATAC 分析上的差异，调研内容比较多，结论要详细"),
]


def http(method, url, data=None):
    req = urllib.request.Request(BASE + url, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def dump_session_activity(sid):
    conn = sqlite3.connect(STATE_DB)
    try:
        rows = conn.execute(
            "SELECT role, tool_name, substr(content,1,120) FROM messages "
            "WHERE session_id=? ORDER BY id", (sid,)
        ).fetchall()
        tools = [r for r in rows if r[1]]
        return tools
    finally:
        conn.close()


def main():
    sid = None
    ws = None
    try:
        r = http("POST", "/api/sessions/new?title=delegation-diag-%d" % int(time.time()))
        sid = r.get("id") or r.get("sid")
        assert sid, "no session id: %r" % r
        print("[session]", sid, flush=True)

        ws = websocket.create_connection(WS_URL, timeout=10)
        ws.send(json.dumps({"type": "switch_session", "session_id": sid}))
        time.sleep(0.5)

        for label, msg in SCENARIOS:
            print(f"\n=== {label} ===", flush=True)
            print("MSG:", msg[:80], flush=True)
            ws.send(json.dumps({"type": "chat", "session_id": sid, "message": msg}))
            ws.settimeout(2)
            deadline = time.time() + 240
            reply_parts = []
            done = False
            while time.time() < deadline:
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                except Exception:
                    break
                try:
                    m = json.loads(raw)
                except Exception:
                    continue
                t = m.get("type")
                if t == "delta":
                    reply_parts.append(m.get("content", "") or m.get("text", "") or "")
                elif t == "tool_start":
                    print("  TOOL:", m.get("tool_name") or m.get("name"), flush=True)
                elif t == "complete":
                    done = True
                    break
            used = any(t[1] == "delegate_task" for t in dump_session_activity(sid))
            print(f"  completed={done} used_delegate={used}", flush=True)
            reply = "".join(reply_parts)[-600:]
            print("  REPLY tail:", reply.replace("\n", " ")[:400], flush=True)

        tools = dump_session_activity(sid)
        print("\n=== ALL TOOL CALLS ===", flush=True)
        for role, tn, c in tools:
            print(f"  {role}: {tn} | {c}", flush=True)
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        # 保留会话供检查（不删）


if __name__ == "__main__":
    sys.exit(main())
