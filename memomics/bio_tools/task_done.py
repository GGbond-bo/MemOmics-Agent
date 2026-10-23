# -*- coding: utf-8 -*-
"""task_done：模型显式声明任务完成（2026-10-18，对齐 DSH 的 update_goal(complete)）。

背景：此前"任务是否完成"靠解析 task_plan.md 文本/关键词，模型说"没有未完成待办"也拦不住
唤醒调度器 → 完成任务后仍会被反复唤醒烧 token。改为**结构化调用**：
模型调用本工具 → 立即 mark_done + 暂停唤醒 + 清除 task_plan 残留（用户要求"彻底清除干净"）。
"""
import glob as _glob
import json
import os

SCHEMA = {
    "name": "task_done",
    "description": (
        "声明当前会话的任务已经完成。调用后：任务状态置为 done、停止一切自动唤醒、"
        "并清除 task_plan 等任务残留文件。仅在**任务确实交付完毕**时调用；"
        "还有未完成步骤时不要调用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "一句话说明完成依据（产出文件/结论/交付物）"},
            "results_dir": {"type": "string", "description": "可选：会话 results 目录（默认自动取上下文）"},
        },
        "required": [],
    },
}


def _purge(results_dir: str, reason: str) -> list:
    removed = []
    if not results_dir or not os.path.isdir(results_dir):
        return removed
    targets = [os.path.join(results_dir, "task_plan.md"), os.path.join(results_dir, "task_plan.done.md")]
    targets += _glob.glob(os.path.join(results_dir, ".wakeup*")) + _glob.glob(os.path.join(results_dir, ".self_check*"))
    for p in targets:
        try:
            if os.path.isfile(p):
                if os.path.basename(p).startswith("task_plan"):
                    try:
                        txt = open(p, encoding="utf-8", errors="replace").read()
                        log_dir = os.path.join(results_dir, "log")
                        os.makedirs(log_dir, exist_ok=True)
                        with open(os.path.join(log_dir, "task_purge.log"), "a", encoding="utf-8") as lf:
                            lf.write(f"purged {os.path.basename(p)} ({len(txt)} chars) reason={reason}\n")
                    except Exception:
                        pass
                os.remove(p)
                removed.append(os.path.basename(p))
        except Exception:
            continue
    return removed


def task_done(reason: str = "", results_dir: str = "") -> str:
    rd = str(results_dir or "").strip()
    if not rd:
        try:
            from memomics.bio_tools.debate_analysis import get_session_results_dir
            rd = get_session_results_dir() or ""
        except Exception:
            rd = ""
    if not rd:
        return json.dumps({"ok": False, "error": "拿不到会话 results_dir，请显式传 results_dir 参数"},
                          ensure_ascii=False)
    out = {"ok": True, "results_dir": rd, "reason": reason}
    try:
        from webui.runtime.run_gate import mark_done, disarm
        out["mark_done"] = bool(mark_done(rd, reason or "task_done 工具调用"))
        out["disarmed"] = bool(disarm(rd, "task_done: 任务已完成"))
    except Exception as exc:
        out["gate_error"] = str(exc)
    try:
        out["purged"] = _purge(rd, reason or "task_done")
    except Exception:
        out["purged"] = []
    return json.dumps(out, ensure_ascii=False, indent=2)


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="task_done",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: task_done(args.get("reason", ""), args.get("results_dir", "")),
        )
    except Exception:
        pass


_register()
