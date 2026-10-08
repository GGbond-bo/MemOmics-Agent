#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
asset_history_probe.py —— 「这个活到底干过没有」一步探针

用途：唤醒/中断轮重投了一条用户请求时，先用它查 log/system_log.jsonl 里该资产的处理史，
      而不是对着产物图反复复核（复核只能证明"现在是对的"，不能证明"活已干过"）。

用法：
    python asset_history_probe.py <会话目录> <关键词> [--n 40]
例：
    python asset_history_probe.py E:/MemOmics-Agent/results/memomics-afd2d418 44_MEF2C

输出：按时间排序的 工具调用时间线 + 关键行的摘要（write_file / execute_* / rail_review /
      skill_evolution.record_run 的 notes —— notes 就是上一轮自己写的"做了什么"）。
判读：出现 record_run(notes 覆盖本次请求) 且时间晚于上一条用户消息 ⇒ 任务已完成，汇报即可。
"""
import json
import os
import sys


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    sess, kw = argv[1], argv[2]
    n = 40
    if "--n" in argv:
        n = int(argv[argv.index("--n") + 1])

    log = os.path.join(sess, "log", "system_log.jsonl")
    if not os.path.isfile(log):
        print("!! 找不到 %s —— 会话目录给对了吗？" % log)
        return 2

    rows = []
    with open(log, encoding="utf-8", errors="ignore") as fh:
        for ln in fh:
            if kw not in ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            rows.append(d)

    print("命中 %d 条（关键词=%s）\n" % (len(rows), kw))
    flags = {"record_run": False, "rail_review": False}
    for d in rows[-n:]:
        ts = d.get("ts", "?")
        tool = d.get("tool", "?")
        a = d.get("args") or {}
        detail = ""

        if tool == "skill_evolution":
            act = a.get("action", "")
            detail = "action=%s" % act
            if act == "record_run":
                flags["record_run"] = True
                detail += " | notes=%s" % str(a.get("notes", ""))[:400]
        elif tool == "rail_review":
            flags["rail_review"] = True
            detail = "phase=%s output_dir=%s" % (a.get("phase"), a.get("output_dir"))
        elif tool in ("execute_python", "execute_r", "execute_code"):
            detail = "code[0:160]=%s" % str(a.get("code", ""))[:160].replace("\n", " ")
        elif tool == "write_file":
            detail = "path=%s (%d chars)" % (a.get("path"), len(str(a.get("content", ""))))
        elif tool == "vision_describe":
            detail = "image=%s" % a.get("image_path")
        else:
            detail = str(a)[:160]

        print("[%s] %-16s %s" % (ts, tool, detail))

    print("\n--- 判读 ---")
    print("record_run 出现过: %s   rail_review 出现过: %s" % (flags["record_run"], flags["rail_review"]))
    if flags["record_run"]:
        print("=> 有完成声明记录：比对 record_run.notes 里的改动是否已覆盖用户本次请求；是 ⇒ 已完成，直接汇报，勿重做。")
    else:
        print("=> 未见完成声明：该请求大概率还没做，正常执行。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))