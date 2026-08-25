# -*- coding: utf-8 -*-
"""ask_user — 澄清工具（DSH dsh-tool-ask-user 策略迁移，2026-08-25）。

背景：MemOmics 模型此前无法向用户澄清——用户意图不明确（如"检查"还是"修复并
继续"）时只能猜，而系统指令又引导它猜"修+跑"。本工具给模型一条"不确定就问"
的出路（配合 _EXECUTION_POLICY 第 5 条）。

机制（异步澄清，零阻塞）：
1. 模型调用 ask_user(question) → 工具把问题经 _session_emit 推给前端
   （type=question，同时发 notice 兜底展示），并存入 session["_pending_questions"]
2. 工具返回明确指示："问题已发送，请立即结束本回合，不要再调用任何工具"
3. 模型结束回合；用户回答成为下一条用户消息；模型从历史里看到自己的提问
   与用户回答，继续

注意：本工具不阻塞回合（Hermes 工具是同步返回），"结束回合等待"由模型执行
工具返回指示完成——这是把决策交给 LLM 的异步澄清模式。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

logger = logging.getLogger("memomics.ask_user")

_LOCK = threading.Lock()


def _session_context() -> tuple:
    """取当前线程的会话（sid, results_dir）：复用 debate_analysis 的线程上下文。"""
    try:
        from memomics.bio_tools.debate_analysis import get_session_sid
        sid = get_session_sid()
        if sid:
            return sid, ""
    except Exception:
        pass
    return os.environ.get("MEMOMICS_SESSION_ID") or "", ""


def ask_user(question: str, options: list = None) -> str:
    """向用户提问澄清（异步：发问题→结束回合→用户回答成为新消息）。

    options（可选）：选项列表 → 前端渲染选择按钮（无前端支持时文本降级
    "回复 1/2/3"），用户点选/回复后成为新消息。
    """
    q = (question or "").strip()
    if not q:
        return json.dumps({"ok": False, "error": "question 不能为空"}, ensure_ascii=False)
    if len(q) > 500:
        q = q[:500]
    opts = None
    if isinstance(options, (list, tuple)):
        opts = [str(o)[:80] for o in options][:6]  # 最多 6 个选项
        if not opts:
            opts = None
    sid, _rd = _session_context()
    delivered = False
    if sid:
        try:
            # 取已加载的 server 模块实例（conftest 以 "server" 名加载；
            # `import webui.server` 会重新执行模块 → 新实例、monkeypatch/会话落空）
            import sys as _sys
            _server = _sys.modules.get("server") or _sys.modules.get("webui.server")
            if _server is None:  # pragma: no cover - 常规运行经 webui.server 入口加载
                import webui.server as _server
            sess = _server._sessions.get(sid)
            if sess:
                _opt_txt = ""
                if opts:
                    _opt_txt = "\n" + "\n".join(f"{i+1}) {o}" for i, o in enumerate(opts))
                _server._session_emit(sess, {
                    "type": "question",
                    "content": f"❓ {q}",
                    "question": q,
                    "options": opts or [],
                    "session_id": sid,
                })
                _server._session_emit(sess, {
                    "type": "notice",
                    "content": f"❓ AI 需要确认：{q}{_opt_txt}"
                              + ("\n（点击选项或直接回复序号/内容）" if opts else "\n（请在输入框直接回答）"),
                    "session_id": sid,
                })
                pending = sess.setdefault("_pending_questions", [])
                with _LOCK:
                    pending.append({"question": q, "options": opts or [],
                                    "asked_at": time.strftime("%H:%M:%S")})
                    # 上限：只保留最近 20 条待确认问题（防模型连问导致无限累积）
                    if len(pending) > 20:
                        del pending[:len(pending) - 20]
                delivered = True
        except Exception as e:
            logger.warning(f"[ask_user] 发送失败: {e}")
    if not delivered:
        return json.dumps({"ok": False,
                           "error": "无法联系用户（会话不可用），请在回复中直接向用户提问"},
                          ensure_ascii=False)
    return json.dumps({
        "ok": True,
        "question": q,
        "options": opts or [],
        "instruction": ("❓ 问题已发送给用户。请立即结束本回合，不要再调用任何工具。"
                        "用户回答后会作为新消息发给你，届时再继续。"),
    }, ensure_ascii=False)


SCHEMA = {
    "name": "ask_user",
    "description": (
        "向用户提问澄清（不确定时用，不要猜）。适用场景：开工前关键信息缺失（数据在哪/"
        "物种组织/期望结果/是否继续旧任务）、用户意图不明确（例如只说'检查'没说'修复并"
        "继续'）、需要用户决定是否继续任务、需要确认数据/路径/参数。可带 options 选项数组"
        "（用户点选更省事）。调用后必须立即结束本回合等待用户回答；用户回答会成为下一条"
        "消息。仅在确实需要用户输入时使用，不要滥用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string",
                         "description": "向用户提出的澄清问题（简洁、具体）"},
            "options": {"type": "array", "items": {"type": "string"},
                        "description": "可选选项列表（最多 6 个，用户点选或回复序号）"}
        },
        "required": ["question"]
    }
}


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="ask_user",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: ask_user(args.get("question", ""),
                                                args.get("options")),
            emoji="❓",
            max_result_size_chars=1_200,
        )
    except Exception as e:
        logger.warning(f"ask_user register failed: {e}")


_register()
