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


def _ui_lang():
    """界面语言（zh / en）：问已加载的 server 模块要（前端切语言时会告知），拿不到就按 zh。"""
    try:
        import sys as _s
        _srv = _s.modules.get("server") or _s.modules.get("webui.server")
        if _srv is not None and hasattr(_srv, "_ui_lang"):
            return _srv._ui_lang()
    except Exception:
        pass
    return "zh"


def _ui(zh, en):
    """按界面语言取文案（P6-2：切英文时弹窗提示不能还是中文）。"""
    return en if _ui_lang() == "en" else zh


def _normalize_options(options) -> tuple:
    """选项规范化 → (labels, rich)。

    P3(2026-09-22): 支持 dict 选项 {"label","desc","recommended"} → 前端弹窗渲染
    勾选框 + 说明文字；纯字符串选项保持兼容。最多 8 项。
    """
    labels, rich = [], []
    if isinstance(options, (list, tuple)):
        for o in options[:8]:
            if isinstance(o, dict):
                lab = str(o.get("label") or o.get("title") or o.get("value") or "").strip()
                if not lab:
                    continue
                lab = lab[:120]
                labels.append(lab)
                rich.append({"label": lab,
                             "desc": str(o.get("desc") or o.get("description") or "")[:200],
                             "recommended": bool(o.get("recommended"))})
            else:
                lab = str(o).strip()[:120]
                if not lab:
                    continue
                labels.append(lab)
                rich.append({"label": lab, "desc": "", "recommended": False})
    return labels, rich


def _live_server(sid: str = ""):
    """拿"正在跑的那个" server 模块实例（多个候选时优先认识这个会话的那个）。

    2026-09-24 真机事故（memomics-c8aacf1e / 条目 06b-annot-9000）：生产是
    `python webui/server.py` 起来的 → 模块名是 __main__，既不是 "server" 也不是
    "webui.server"。老代码只认这两个名字，找不到就 `import webui.server` —— 那会**再执行一遍
    模块、造出第二个实例**，它的 _sessions 是空的 → ask_user 明明拿到了 sid，却查不到会话，
    于是静默返回「无法联系用户（会话不可用）」，意图确认表单永远弹不到前端
    （铁律 28/35 的"开工前必须弹确认表单"形同虚设）。
    测试里一直没暴露：conftest 恰好以 "server" 名字加载模块，命中老代码第一分支。
    """
    try:
        import sys as _sys
    except Exception:  # pragma: no cover
        return None
    cands = []
    for _name in ("server", "webui.server", "__main__"):
        _m = _sys.modules.get(_name)
        if _m is not None and hasattr(_m, "_sessions") and hasattr(_m, "_session_emit"):
            cands.append(_m)
    for _m in list(_sys.modules.values()):  # 兜底：入口名被改过也在所不惜
        if _m not in cands and hasattr(_m, "_sessions") and hasattr(_m, "_session_emit"):
            cands.append(_m)
    if not cands:
        return None
    if sid:
        for _m in cands:
            try:
                if sid in _m._sessions:
                    return _m
            except Exception:
                pass
    return cands[0]


def _unreachable_reason(sid: str, srv) -> str:
    """把"为什么联系不上用户"写清楚（下次出问题一眼看出是没 sid 还是实例不对）。"""
    if not sid:
        return _ui("会话上下文为空（没拿到 sid）", "no session id in context")
    if srv is None:
        return _ui("没找到正在运行的 server 模块实例", "running server instance not found")
    if sid not in getattr(srv, "_sessions", {}):
        return _ui("server 实例里没有这个会话（实例/入口名不匹配）",
                   "session not present in the server instance")
    return _ui("发送时异常", "emit failed")


def emit_form_for_session(sess, question: str, options: list = None, multi_select: bool = False,
                          allow_other: bool = True, header: str = "", kind: str = "clarify",
                          arm_gate: bool = True) -> tuple:
    """把确认表单直接发给指定会话（服务器侧确定性弹窗入口）→ (form_id, delivered)。

    P4(2026-09-22)：此前只有"模型调 ask_user"一条路 —— 弹不弹全看模型自觉。有些场景
    服务器自己就知道该问（例如用户只说"帮我改下脚本"，而记忆里正好有他的数据可以验证），
    这时由服务器直接弹窗，不依赖模型。ask_user 内部也走这里，一套逻辑两条入口。

    arm_gate=False：不置 P3 意图确认门禁（调用方自己有更精确的锁，如代码修改模式）。
    """
    q = (question or "").strip()
    if len(q) > 500:
        q = q[:500]
    opts, opts_rich = _normalize_options(options)
    if not opts:
        opts, opts_rich = None, None
    sid = str((sess or {}).get("id") or "")
    form_id = "form_" + time.strftime("%Y%m%d%H%M%S") + "_" + str(int(time.time() * 1000) % 1000)
    delivered = False
    if sid and q:
        try:
            # 取"正在跑的那个" server 实例：优先认识本会话的那个（见 _live_server 注释里的真机事故）
            _server = _live_server(sid)
            if _server is None:
                raise RuntimeError("没找到正在运行的 server 模块实例")
            if sess:
                _opt_txt = ""
                if opts:
                    _opt_txt = "\n" + "\n".join(f"{i+1}) {o}" for i, o in enumerate(opts))
                # P3(2026-09-22): 结构化确认事件（前端渲染勾选弹窗）
                _server._session_emit(sess, {
                    "type": "ask_form",
                    "form_id": form_id,
                    "kind": kind or "clarify",
                    "header": (header or (_ui("意图确认", "Confirm intent") if kind == "intent"
                                           else _ui("需要你确认", "Needs your confirmation")))[:60],
                    "question": q,
                    "options": opts or [],
                    "form_options": opts_rich or [],
                    "multi_select": bool(multi_select),
                    "allow_other": True if allow_other is None else bool(allow_other),
                    "content": f"❓ {q}",
                    "session_id": sid,
                })
                # 兼容旧通道（外部消费者/审计；前端不渲染旧的 question 事件）
                _server._session_emit(sess, {
                    "type": "question",
                    "content": f"❓ {q}",
                    "question": q,
                    "options": opts or [],
                    "form_id": form_id,
                    "session_id": sid,
                })
                _server._session_emit(sess, {
                    "type": "notice",
                    "content": (f"❓ {q}{_opt_txt}" if _ui_lang() == "en"
                                else f"❓ AI 需要确认：{q}{_opt_txt}")
                              + (_ui("\n（在弹窗里勾选后提交，或直接回复序号/内容）",
                                     "\n（Tick an option in the dialog and submit, or reply with the number/text）") if opts
                                 else _ui("\n（请在输入框直接回答）",
                                          "\n（Please answer directly in the input box）")),
                    "session_id": sid,
                })
                pending = sess.setdefault("_pending_questions", [])
                with _LOCK:
                    pending.append({"form_id": form_id, "question": q, "options": opts or [],
                                    "form_options": opts_rich or [],
                                    "multi_select": bool(multi_select),
                                    "allow_other": True if allow_other is None else bool(allow_other),
                                    "kind": kind or "clarify",
                                    "asked_at": time.strftime("%H:%M:%S"),
                                    "answered": False})
                    # 上限：只保留最近 20 条待确认问题（防模型连问导致无限累积）
                    if len(pending) > 20:
                        del pending[:len(pending) - 20]
                # P3: 意图确认门禁 —— 未答复前禁止执行类工具（硬约束，不靠模型自觉）
                if arm_gate:
                    try:
                        from webui import enforcement as _enf_a
                        _es_a = _enf_a.get_enforcement(sid)
                        _enf_a.set_awaiting_form(_es_a, form_id, q)
                    except Exception as _e_enf:
                        logger.warning(f"[ask_user] 门禁置位失败: {_e_enf}")
                delivered = True
        except Exception as e:
            logger.warning(f"[ask_user] 发送失败: {e}")
    if not delivered:
        return json.dumps({"ok": False,
                           "error": _ui("无法联系用户（会话不可用），请在回复中直接向用户提问",
                                        "Cannot reach the user (session unavailable); ask the user directly in your reply")},
                          ensure_ascii=False)
    return form_id, delivered


def ask_user(question: str, options: list = None, multi_select: bool = False,
             allow_other: bool = True, header: str = "", kind: str = "clarify") -> str:
    """向用户提问澄清 / 弹出意图确认表单（异步：发问题→结束回合→用户回答成为新消息）。

    options（可选）：字符串或 {label,desc,recommended} 列表 → 前端弹窗可勾选；
    multi_select=True 可多选；allow_other=True 提供"其他"自由填写。
    kind：clarify（澄清）| intent（开工前意图确认）| plan（方案选择）—— 仅用于标题与审计。
    """
    q = (question or "").strip()
    if not q:
        return json.dumps({"ok": False, "error": "question 不能为空"}, ensure_ascii=False)
    opts, _rich = _normalize_options(options)
    sid, _rd = _session_context()
    # 2026-09-24 真机修复：生产入口是 `python webui\server.py`（模块名 __main__），
    # 老写法只认 "server"/"webui.server"，找不到就 import webui.server → 第二个实例、空 _sessions
    # → 表单永远弹不出来。现在按"谁认识这个 sid"选实例。
    _srv = _live_server(sid) if sid else None
    form_id, delivered = "", False
    if sid and _srv is not None:
        try:
            form_id, delivered = emit_form_for_session(
                _srv._sessions.get(sid), q, options=options, multi_select=multi_select,
                allow_other=allow_other, header=header, kind=kind)
        except Exception as e:
            logger.warning(f"[ask_user] 发送失败: {e}")
    if not delivered:
        _why = _unreachable_reason(sid, _srv)
        logger.warning(f"[ask_user] 表单没能送达用户: {_why} (sid={sid or '空'})")
        return json.dumps({"ok": False,
                           "error": _ui("无法联系用户（会话不可用：%s），请在回复中直接向用户提问" % _why,
                                        "Cannot reach the user (session unavailable: %s); ask the user directly in your reply" % _why)},
                          ensure_ascii=False)
    return json.dumps({
        "ok": True,
        "form_id": form_id,
        "question": q[:500],
        "options": opts or [],
        "multi_select": bool(multi_select),
        "instruction": ("❓ 问题已发送给用户（前端弹窗可勾选）。请立即结束本回合，不要再调用"
                        "任何工具（执行类工具在用户答复前会被门禁拦下，白跑一趟）。"
                        "用户回答后会作为新消息发给你，届时再继续。"),
    }, ensure_ascii=False)


SCHEMA = {
    "name": "ask_user",
    "description": (
        "向用户提问澄清 / 弹出意图确认表单（不确定时用，不要猜）。必须用的场景："
        "①高代价任务（真实分析/集群投递/结果入库/出报告）开工前确认意图；"
        "②用户意图不明确（例如只说'检查'没说'修复并继续'）；"
        "③关键信息缺失（数据在哪/物种组织/期望结果/是否继续旧任务/参数与阈值）；"
        "④只改代码不跑（用户给你脚本让你改，记忆里有他的数据）——问「要不要用你的数据验证」。"
        "传 options 会渲染成可勾选弹窗（可用 dict 带 desc 说明与 recommended 推荐），"
        "multi_select=True 支持多选，allow_other=True 提供\"其他\"自由填写。"
        "调用后必须立即结束本回合等待用户回答（执行类工具在答复前会被门禁拦下）；"
        "用户回答会成为下一条消息。纯问答/只读查询不要问，别滥用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string",
                         "description": "向用户提出的问题（简洁、具体、一次问清）"},
            "options": {"type": "array",
                        "description": ("可选项（最多 8 个）：字符串，或对象 "
                                        "{\"label\":\"选项文字\",\"desc\":\"说明\",\"recommended\":true}"
                                        "；前端渲染成勾选框")},
            "multi_select": {"type": "boolean",
                             "description": "是否允许多选（默认 false=单选）"},
            "allow_other": {"type": "boolean",
                            "description": "是否提供\"其他\"自由填写（默认 true）"},
            "header": {"type": "string", "description": "弹窗标题（默认按 kind 生成）"},
            "kind": {"type": "string", "enum": ["clarify", "intent", "plan"],
                     "description": "clarify=澄清；intent=开工前意图确认；plan=方案选择"}
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
            handler=lambda args, **kw: ask_user(
                args.get("question", ""),
                args.get("options"),
                multi_select=bool(args.get("multi_select", False)),
                allow_other=args.get("allow_other", True),
                header=args.get("header", ""),
                kind=args.get("kind", "clarify"),
            ),
            emoji="❓",
            max_result_size_chars=1_200,
        )
    except Exception as e:
        logger.warning(f"ask_user register failed: {e}")


_register()
