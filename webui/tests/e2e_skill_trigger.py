# -*- coding: utf-8 -*-
"""端到端 skill 触发测试 v2：真实 ws 链路 + 真实 LLM，多场景 × 多意图 × 多用户。

v1 教训：
- ws 事件推送只发给 attach 过的连接（chat 消息不 attach → 收不到 tool_start）
- _create_session 忽略传入 sid，生成随机 memomics-xxx → 无法用 sid 过滤
判定改用权威链路：state.db 的 messages 表（role=tool, tool_name=skill_view）。

用法（需 server 已启动 + 真模型）：
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe webui/tests/e2e_skill_trigger.py [--quick] [--only academic-paper-reviewer]
"""
import asyncio
import json
import sqlite3
import sys
import time
import uuid

import websockets

WS_URL = "ws://127.0.0.1:8899/ws"
DB = r"E:\MemOmics-Agent\hermes_home\state.db"
TIMEOUT = 120  # 每用例最长等待（秒）

# (期望skill, 场景, 用户表述)
CASES = [
    ("academic-paper-reviewer", "直白中文", "帮我审一下这篇论文"),
    ("academic-paper-reviewer", "英文", "Can you review this manuscript?"),
    ("academic-paper-reviewer", "口语", "这稿子质量怎么样，帮我评评"),
    ("nature-reviewer", "直白", "Nature 审稿，帮我预审一下"),
    ("nature-reviewer", "英文", "pre-submission review for Nature"),
    ("nature-response", "直白", "帮我写修回信"),
    ("nature-response", "英文", "write a rebuttal letter"),
    ("paper-polish", "直白", "帮我润色这段论文"),
    ("paper-polish", "口语", "这摘要读着像AI写的，改自然点"),
    ("idea-evaluator", "直白", "评估一下我这个研究想法"),
    ("idea-evaluator", "口语", "我有个新点子，你帮我看看靠不靠谱"),
    ("nature-paper-card", "直白", "帮我拆解这篇文献"),
    ("nature-paper-card", "场景", "拆一下这篇 Nature 衰老文章的证据链"),
    ("nature-reader", "直白", "帮我读这篇论文"),
    ("nature-reader", "场景", "精读这篇文献，中英对照翻译"),
    ("NONE", "干扰-闲聊", "今天天气怎么样"),
    ("NONE", "干扰-编程", "帮我写个 Python 脚本处理这个 CSV"),
]


def _db_skill_views(ts_from, ts_to=None):
    """查时间窗内所有会话的 skill_view 调用。"""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    if ts_to:
        rows = con.execute(
            "SELECT session_id, content FROM messages "
            "WHERE tool_name='skill_view' AND timestamp > ? AND timestamp <= ? ORDER BY timestamp",
            (ts_from, ts_to),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT session_id, content FROM messages "
            "WHERE tool_name='skill_view' AND timestamp > ? ORDER BY timestamp",
            (ts_from,),
        ).fetchall()
    con.close()
    out = {}
    for r in rows:
        try:
            d = json.loads(r["content"])
            name = d.get("name", "?")
        except Exception:
            name = r["content"][:60]
        out.setdefault(r["session_id"], []).append(name)
    return out


async def run_case(ws, skill, scene, text, results):
    start_ts = time.time()
    await ws.send(json.dumps({
        "type": "chat",
        "session_id": f"e2e-{uuid.uuid4().hex[:8]}",
        "message": text,
    }, ensure_ascii=False))
    deadline = start_ts + TIMEOUT
    # 等待 agent 完成：轮询 state.db，出现该用例时间窗内的 assistant 完整回复
    done_at = None
    last_tool_ts = None
    while time.time() < deadline:
        await asyncio.sleep(5)
        con = sqlite3.connect(DB)
        n = con.execute(
            "SELECT count(*) FROM messages WHERE role='assistant' "
            "AND length(content) > 20 AND timestamp > ?",
            (start_ts,),
        ).fetchone()[0]
        t = con.execute(
            "SELECT MAX(timestamp) FROM messages WHERE role='tool' AND timestamp > ?",
            (start_ts,),
        ).fetchone()[0]
        con.close()
        if n > 0:
            done_at = time.time()
            last_tool_ts = t
            # agent 回复后可能仍在工具循环（skill_view 常发生在回复后），
            # 等到连续 20s 无新工具调用才判定完成
            idle_start = time.time()
            while time.time() - idle_start < 20 and time.time() < deadline:
                await asyncio.sleep(5)
                con = sqlite3.connect(DB)
                t2 = con.execute(
                    "SELECT MAX(timestamp) FROM messages WHERE role='tool' AND timestamp > ?",
                    (start_ts,),
                ).fetchone()[0]
                con.close()
                if t2 and (not last_tool_ts or t2 > last_tool_ts):
                    last_tool_ts = t2
                    idle_start = time.time()
            break
    # 完成后再等 10s 缓冲窗收集延迟落库的 skill_view
    await asyncio.sleep(10)
    end_ts = (done_at + 30) if done_at else deadline
    # 只统计本用例时间窗 [start_ts, end_ts] 内新增的 skill_view 调用
    views = _db_skill_views(start_ts, end_ts)
    all_names = [n for names in views.values() for n in names]
    # 干扰项（skill=NONE）：只要求不触发 7 个新 skill（agent 调其他分析 skill 属正常）
    NEW7 = ["academic-paper-reviewer", "nature-reviewer", "nature-response",
            "paper-polish", "idea-evaluator", "nature-paper-card", "nature-reader"]
    expected_hit = skill != "NONE"
    if expected_hit:
        hit = any(skill in n for n in all_names)
        got_label = "HIT" if hit else "MISS"
    else:
        hit = not any(any(s in n for s in NEW7) for n in all_names)
        got_label = "NO_HIT" if hit else "HIT"  # hit=True=无新7件触发=正确
    results.append({
        "skill": skill, "scene": scene, "text": text,
        "expect": "HIT" if expected_hit else "NO_HIT",
        "got": got_label,
        "skill_views": all_names[:4],
    })
    mark = "✓" if hit == expected_hit else "✗"
    print(f"[{mark}] {skill or 'NONE':<24} {scene:<8} {text[:26]:<28} "
          f"skill_view={all_names[:4] if all_names else '（无）'}", flush=True)


async def main(quick=False, only=None):
    cases = CASES
    if only:
        cases = [c for c in cases if c[0] == only]
    elif quick:
        cases = [c for c in cases if c[1] in ("直白", "直白中文")]
    results = []
    # 每个用例独立连接（避免长跑断连），模拟多用户多会话
    for skill, scene, text in cases:
        try:
            async with websockets.connect(WS_URL, ping_interval=None) as ws:
                await run_case(ws, skill, scene, text, results)
        except Exception as e:
            print(f"[!] 用例异常 {skill}/{scene}: {e}", flush=True)
            results.append({
                "skill": skill, "scene": scene, "text": text,
                "expect": "HIT" if skill != "NONE" else "NO_HIT",
                "got": "ERROR", "skill_views": [],
            })
    print("\n===== 汇总 =====", flush=True)
    total = len(results)
    passed = sum(1 for r in results if r["expect"] == r["got"])
    for r in results:
        mark = "✓" if r["expect"] == r["got"] else "✗"
        print(f"{mark} {r['skill'] or 'NONE':<24} {r['scene']:<8} {r['text'][:24]:<26} "
              f"expect={r['expect']} got={r['got']}", flush=True)
    print(f"\n通过 {passed}/{total}", flush=True)
    return passed == total


if __name__ == "__main__":
    args = sys.argv[1:]
    quick = "--quick" in args
    only = None
    for a in args:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
    ok = asyncio.run(main(quick=quick, only=only))
    sys.exit(0 if ok else 1)
