# -*- coding: utf-8 -*-
"""delegation 真实触发冒烟（真实 LLM × 4 场景）。

应触发: 并行独立任务 / 上下文隔离调研
不应触发: 辩论 / 单步小任务

每场景: ws 发消息 → 等 complete → 查 state.db 该会话是否出现 delegate_task 工具调用
"""
import json
import sqlite3
import sys
import time
import urllib.request

import websocket

BASE = "http://127.0.0.1:8899"
WS_URL = "ws://127.0.0.1:8899/ws"
STATE_DB = r"E:\MemOmics-Agent\hermes_home\state.db"

SCENARIOS = [
    # (label, expect_trigger, message)
    ("并行独立任务", True, "分别帮我跑一下样本A、样本B、样本C的marker分析，它们互不依赖，可以并行"),
    ("上下文隔离调研", True, "帮我调研一下 ArchR 和 SnapATAC 在 ATAC 分析上的差异，调研内容比较多"),
    ("辩论", False, "这个差异分析结论可信吗？来一场正反辩论"),
    ("单步小任务", False, "把热图配色改成蓝白色"),
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


def session_used_delegate(sid):
    """查 state.db：该会话是否有 delegate_task 工具调用记录。"""
    conn = sqlite3.connect(STATE_DB)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id=? AND (tool_name='delegate_task' OR tool_calls LIKE '%delegate_task%')",
            (sid,),
        ).fetchone()
        return int(row[0]) > 0
    except Exception:
        return False
    finally:
        conn.close()


def main():
    sid = None
    ws = None
    try:
        r = http("POST", "/api/sessions/new?title=delegation-smoke-%d" % int(time.time()))
        sid = r.get("id") or r.get("sid")
        assert sid, "no session id: %r" % r

        ws = websocket.create_connection(WS_URL, timeout=10)
        ws.send(json.dumps({"type": "switch_session", "session_id": sid}))
        time.sleep(0.5)

        results = []
        for label, expect, msg in SCENARIOS:
            ws.send(json.dumps({"type": "chat", "session_id": sid, "message": msg}))
            # 等 complete（超时 180s）
            ws.settimeout(2)
            deadline = time.time() + 180
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
                if m.get("type") == "complete":
                    done = True
                    break
                if m.get("type") == "error" and "cancel" in str(m).lower():
                    break
            used = session_used_delegate(sid)
            ok = (used == expect)
            results.append((label, expect, used, ok, done))
            print(f"[{label}] expect_trigger={expect} actual_used_delegate={used} "
                  f"{'PASS' if ok else 'FAIL'}" + ("" if done else " (timeout!)"), flush=True)

        print("=== SUMMARY ===", flush=True)
        for label, expect, used, ok, done in results:
            print(f"  {label}: {'PASS' if ok else 'FAIL'} (expect={expect}, used={used}, completed={done})", flush=True)
        passed = sum(1 for r in results if r[3])
        print(f"RESULT: {passed}/{len(results)} passed", flush=True)
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        if sid:
            http("DELETE", "/api/sessions/%s" % sid)
            print("[cleanup] deleted", sid, flush=True)


if __name__ == "__main__":
    sys.exit(main())
