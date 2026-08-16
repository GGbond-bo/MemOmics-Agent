#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MemOmics 任务进程监控与自愈链 E2E 验证（真数据 30 万行，不依赖 LLM 网关）。

设计（2026-08-16，用户要求多场景多角度真实验证）：
  S1  采样器正确性：自采样 alive/rss、CPU 燃烧增量检出、假 PID 无证据
  S2  真·冻结内核：R worker 跑 Sys.sleep(90)（零 CPU/IO = 冻结语义）→
      模拟 watchdog 逐 tick 采样 → 判定 frozen（窗口 60s 加速版）
  S3  真·30 万行长计算（>5 分钟，fread + 循环 SVD）→ 全程模拟 watchdog：
      5 分钟无事件后按进程证据决策，CPU 在动 → 永不中断、永不判 frozen
  S4  kernel PID 标记：计算期间 worker_snapshot 可见真实 R worker PID；
      结束后持久存活（热 kernel）；restart 后清空
  S5  完成停链（调用真实 _schedule_self_check，LLM 不参与）：
      5a 已完成普通任务 → 自动归档 task_plan.done.md + mark_done，不再排唤醒
      5b task_state=done → RunGate 第一道闸拦截
      5c registry paused+compute=0 → LoopX 闸拦截
      5d 进行中任务（对照组）→ 确实排下一次唤醒
      5e 重启播种判定 _task_plan_active：in_progress→True；完成+模板遗留→False
  S6  工具超时反馈：execute_r timeout=20 跑 Sys.sleep(60) → 返回 timeout 文本
      （工具层兜底生效，不是挂起）

运行：
  E:\\MemOmics-Agent\\.venv\\Scripts\\python.exe test_proc_watchdog_e2e.py
约 10 分钟（S3 是真实长计算）。
"""
import os
import sys
import time
import math
import json
import tempfile
import threading
import traceback

ROOT = r"E:\MemOmics-Agent"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "hermes-agent"))

RESULTS = []  # [(name, ok, detail)]


def record(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}", flush=True)


def _tick_decision(session, last_event_ts):
    """复刻 stall watchdog 的每 tick 决策（不含 emit/LLM/中断动作）。

    返回 (verdict, info, would_interrupt)：
      would_interrupt=True 仅当"无工具在飞 + 5 分钟无事件"（网关挂起路径）。
      工具在飞时只按 working/frozen 决策，frozen 才走"唤醒 AI 诊断"。
    """
    import webui.server as S
    S._sample_task_procs(session)
    live = str(session.get("_live_tool") or "").strip()
    now = time.time()
    if now - last_event_ts <= 300:
        return ("fresh", "", False)
    if live:
        verdict, info = S._task_liveness(session)
        if verdict == "frozen":
            return (verdict, info, False)  # 冻结 → 唤醒 AI 诊断（不是网关挂起中断）
        return (verdict, info, False)
    return ("no_tool_gateway_hang", "", True)


# ── S1 采样器正确性 ────────────────────────────────────────
def s1_proc_stats():
    from memomics.proc_stats import sample_process
    s = sample_process(os.getpid())
    assert s and s["alive"] and s["rss_bytes"] > 0, "self sample failed"

    def burn(dt):
        t0 = time.time()
        while time.time() - t0 < dt:
            math.sqrt(12345.678)

    a = sample_process(os.getpid())
    burn(0.5)
    b = sample_process(os.getpid())
    delta = b["cpu_seconds"] - a["cpu_seconds"]
    assert delta > 0.05, f"cpu delta too small: {delta}"
    assert sample_process(99999999) is None, "fake pid should be None"
    record("S1 proc_stats 采样", True,
           f"rss={s['rss_bytes'] / 1048576:.0f}MB cpu_delta={delta:.3f}s 假PID=None")


# ── S2 真·冻结内核 → frozen 判定（窗口加速版）──────────────
def s2_frozen_kernel():
    from tools.persistent_kernel import KERNEL_POOL
    import webui.server as S

    old_win = S._TRACKED_PROC_HIST_WINDOW
    S._TRACKED_PROC_HIST_WINDOW = 60  # 测试加速：窗口 60s（生产 300s）
    task_id = "memomics-e2e-frozen"
    session = {"id": task_id, "results_dir": "", "_live_tool": "execute_r",
               "_proc_hist": [], "_stall_notice_last": 0}
    res = {}

    def run():
        res["r"] = KERNEL_POOL.execute("Sys.sleep(90)", task_id, timeout=200,
                                       language="r", cwd=None)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t0 = time.time()
    verdicts = []
    try:
        while t.is_alive():
            S._sample_task_procs(session)
            v, info = S._task_liveness(session)
            if v not in ("insufficient",) and (not verdicts or verdicts[-1] != v):
                verdicts.append(v)
            time.sleep(5)
        t.join()
    finally:
        S._TRACKED_PROC_HIST_WINDOW = old_win
    status = (res.get("r") or {}).get("status")
    snap = KERNEL_POOL.worker_snapshot(task_id=task_id)
    print(f"    S2 verdicts={verdicts} kernel_status={status} workers={snap}", flush=True)
    ok = "frozen" in verdicts and status == "ok"
    record("S2 真冻结内核(零CPU/IO)→frozen 判定", ok,
           f"verdicts={verdicts}（启动期CPU 或早期 insufficient 属预期）")
    KERNEL_POOL.restart(task_id=task_id)


# ── S3 真·30 万行长计算（>5 分钟）全程不误判 ────────────────
def s3_real_data_long_run():
    from tools.persistent_kernel import KERNEL_POOL
    import webui.server as S

    data = "E:/骨骼肌锻炼/MF_AUCell_meta.csv"  # 正斜杠（R 代码内反斜杠+中文会触发 R 4.5.3 解析挂起，已由 execute_r 消毒）
    assert os.path.isfile(data), f"数据不存在: {data}"
    task_id = "memomics-e2e-real"
    rcode = (
        "suppressMessages(library(data.table))\n"
        "t0 <- Sys.time()\n"
        f"x <- fread('{data}', nrows=300000, showProgress=FALSE)\n"
        "cat(sprintf('loaded %d rows x %d cols in %.1fs\\n', nrow(x), ncol(x), "
        "as.numeric(Sys.time()-t0)), flush=TRUE)\n"
        "num <- names(x)[sapply(x, is.numeric)]\n"
        "stopifnot(length(num) >= 10)\n"
        "m <- as.matrix(x[, ..num])\n"
        "m[!is.finite(m)] <- 0\n"
        "cat(sprintf('numeric cols=%d dim=%dx%d\\n', length(num), nrow(m), ncol(m)), flush=TRUE)\n"
        "target <- t0 + 330\n"
        "i <- 0\n"
        "while (Sys.time() < target) {\n"
        "  i <- i + 1\n"
        "  idx <- sample.int(nrow(m), 50000)\n"
        "  s <- svd(m[idx, , drop=FALSE], nu=2, nv=2)\n"
        "  if (i %% 10 == 0) cat(sprintf('iter %d elapsed %.1fs\\n', i, as.numeric(Sys.time()-t0)), flush=TRUE)\n"
        "}\n"
        "cat(sprintf('DONE iters=%d total=%.1fs\\n', i, as.numeric(Sys.time()-t0)), flush=TRUE)\n"
    )
    session = {"id": task_id, "results_dir": "", "_live_tool": "execute_r",
               "_proc_hist": [], "_stall_notice_last": 0}
    res = {}

    def run():
        res["r"] = KERNEL_POOL.execute(rcode, task_id, timeout=1500,
                                       language="r", cwd=None)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t0 = time.time()
    last_event = t0  # 模拟"回合开始后无任何新事件"（最严苛）
    verdicts = []
    interrupts = []
    worker_pids = set()
    try:
        while t.is_alive():
            S._sample_task_procs(session)
            v, info = S._task_liveness(session)
            if v not in ("insufficient",) and (not verdicts or verdicts[-1] != v):
                verdicts.append(v)
            # 复刻 watchdog：5 分钟无事件后按证据决策
            if time.time() - last_event > 300:
                if v == "frozen":
                    interrupts.append(info)
                # working/insufficient/no_task → 都不中断（工具在飞）
            for w in KERNEL_POOL.worker_snapshot(task_id=task_id):
                if w.get("pid"):
                    worker_pids.add(int(w["pid"]))
            if int(time.time() - t0) % 60 < 5:
                print(f"    S3 t+{int(time.time() - t0)}s verdict={v} pids={sorted(worker_pids)}",
                      flush=True)
            time.sleep(5)
        t.join()
    except Exception:
        traceback.print_exc()
    out = (res.get("r") or {}).get("output", "")
    status = (res.get("r") or {}).get("status")
    elapsed = time.time() - t0
    ok = (status == "ok" and "DONE" in out and elapsed > 300
          and "frozen" not in verdicts and not interrupts and bool(worker_pids))
    record("S3 真30万行长计算(>5min)全程不误判",
           ok,
           f"耗时{elapsed:.0f}s verdicts={verdicts} 中断={len(interrupts)} pids={sorted(worker_pids)}")
    if not ok:
        print(f"    S3 诊断: status={status} out_tail={out[-300:]}", flush=True)
    return worker_pids


# ── S4 kernel PID 标记与生命周期 ───────────────────────────
def s4_worker_pid(pids):
    from tools.persistent_kernel import KERNEL_POOL
    from memomics.proc_stats import sample_process
    task_id = "memomics-e2e-real"
    snap = KERNEL_POOL.worker_snapshot(task_id=task_id)
    alive_after = any(w.get("pid") in pids and w.get("alive") for w in snap)
    rss_ok = False
    for p in pids:
        s = sample_process(p)
        if s and s.get("alive") and s.get("rss_bytes", 0) > 0:
            rss_ok = True
    record("S4 kernel PID 标记+完成后持久存活", bool(alive_after and rss_ok),
           f"pids={sorted(pids)} after_run_alive={alive_after} rss_sample={rss_ok}")
    KERNEL_POOL.restart(task_id=task_id)
    snap2 = KERNEL_POOL.worker_snapshot(task_id=task_id)
    record("S4b restart 后 worker 清空", not snap2, f"remaining={len(snap2)}")


# ── S5 完成停链：真实 _schedule_self_check 全链路 ──────────
def s5_completion_chain():
    import webui.server as S
    from webui.runtime import run_gate

    calls = []
    _orig_rtc = S.asyncio.run_coroutine_threadsafe
    S.asyncio.run_coroutine_threadsafe = lambda coro, loop: calls.append(coro) or True

    class FakeLoop:
        def is_running(self):
            return True

    loop = FakeLoop()

    def mkdir_scene(name, plan_text, state=None, outputs=(), registry=None):
        d = tempfile.mkdtemp(prefix=f"e2e-{name}-")
        with open(os.path.join(d, "task_plan.md"), "w", encoding="utf-8") as f:
            f.write(plan_text)
        for rel in outputs:
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
        if state:
            run_gate.save_state(d, state, "test")
        if registry:
            lp = os.path.join(d, ".loopx")
            os.makedirs(lp, exist_ok=True)
            with open(os.path.join(lp, "registry.json"), "w", encoding="utf-8") as f:
                json.dump(registry, f, ensure_ascii=False)
        return d

    try:
        # 5a 已完成普通任务 → 自动归档 + mark_done + 停链
        plan_done = (
            "# P\n## Goal\n画图\n\n## Phases\n"
            "### Phase 1: 执行用户任务\n- [x] 出图\n**Status:** complete\n\n"
            "产出: figures/out.png\n\n"
            "## Verification Checklist\n- [x] N/A 模板遗留\n"
        )
        d = mkdir_scene("5a-done", plan_done, outputs=["figures/out.png"])
        sess = {"id": "memomics-e2e-5a", "todos": [], "results_dir": d}
        calls.clear()
        S._schedule_self_check(sess, agent=object(), loop=loop)  # agent 必须 truthy（否则函数首行早退）
        st = run_gate.load_state(d)
        archived = os.path.exists(os.path.join(d, "task_plan.done.md"))
        reseed = S._task_plan_active(d)
        ok5a = st.get("state") == "done" and archived and not calls and reseed is False
        record("5a 完成→自动归档+mark_done+停链+重启不播种",
               ok5a, f"state={st.get('state')} archived={archived} 排唤醒={len(calls)} reseed={reseed}")

        # 5b task_state=done → RunGate 拦截
        d2 = mkdir_scene("5b-gate", "# P\n- [ ] 未完成", state="done")
        sess2 = {"id": "memomics-e2e-5b", "todos": [], "results_dir": d2}
        calls.clear()
        S._schedule_self_check(sess2, agent=object(), loop=loop)
        record("5b task_state=done→RunGate 拦截", not calls, f"排唤醒={len(calls)}")

        # 5c registry paused+compute=0 → LoopX 闸拦截
        reg = {
            "schema_version": "loopx_registry_v0",
            "goals": [{
                "id": "memomics-e2e-5c", "domain": "memomics", "status": "paused",
                "role": "primary", "repo": "x", "state_file": ".loopx/ACTIVE_GOAL_STATE.md",
                "authority_sources": [],
                "adapter": {"kind": "project_goal", "status": "paused"},
                "spawn_policy": {"mode": "sequential", "allowed": True, "max_children": 0,
                                 "allowed_domains": []},
                "coordination": {"write_scope": "repo", "requires_parent_approval": []},
                "execution_profile": {"mode": "interactive", "allowed": True,
                                      "default_effort": "normal", "allowed_efforts": ["normal"]},
                "quota": {"compute": 0, "window_hours": 24, "slot_minutes": 30,
                          "allowed_slots": 500, "spent_slots": 500},
                "guards": [],
            }]
        }
        plan_prog = ("# P\n## Phases\n### Phase 1\n- [ ] 进行中\n**Status:** in_progress\n")
        d3 = mkdir_scene("5c-paused", plan_prog, registry=reg)
        sess3 = {"id": "memomics-e2e-5c",
                 "todos": [{"status": "in_progress", "title": "t"}],
                 "results_dir": d3}
        calls.clear()
        S._schedule_self_check(sess3, agent=object(), loop=loop)
        record("5c registry paused→LoopX 闸拦截", not calls, f"排唤醒={len(calls)}")

        # 5d 进行中任务（对照组）→ 确实排下一次唤醒
        d4 = mkdir_scene("5d-active", plan_prog)
        sess4 = {"id": "memomics-e2e-5d",
                 "todos": [{"status": "in_progress", "title": "t"}],
                 "results_dir": d4}
        calls.clear()
        S._schedule_self_check(sess4, agent=object(), loop=loop)
        record("5d 进行中任务→排下一次唤醒(对照)", len(calls) == 1, f"排唤醒={len(calls)}")

        # 5e 重启播种判定
        d6 = mkdir_scene("5e-active", plan_prog)
        ok_active = S._task_plan_active(d6) is True
        d7 = mkdir_scene(
            "5e-done", "# P\n已完成\n## Phases\n### Phase 1\n- [x] 完成\n**Status:** complete\n\n"
            "## Verification Checklist\n- [ ] output_filtered.h5 存在\n\n## Errors Encountered\n")
        ok_done = S._task_plan_active(d7) is False
        record("5e 重启播种判定(_task_plan_active)", ok_active and ok_done,
               f"in_progress→{ok_active} 完成+模板遗留→{ok_done}")
    finally:
        S.asyncio.run_coroutine_threadsafe = _orig_rtc


# ── S6 工具超时反馈（工具层兜底，不是挂起）──────────────────
def s6_tool_timeout():
    from tools.persistent_kernel import KERNEL_POOL
    t0 = time.time()
    r = KERNEL_POOL.execute("Sys.sleep(60)", "memomics-e2e-to", timeout=20,
                            language="r", cwd=None)
    elapsed = time.time() - t0
    ok = r.get("status") == "timeout" and "timed out" in str(r.get("error", ""))
    record("S6 工具超时反馈(20s 上限)", ok,
           f"status={r.get('status')} 实际{elapsed:.0f}s 返回")
    KERNEL_POOL.restart(task_id="memomics-e2e-to")


# ── S7 反斜杠中文路径消毒回归（本次测试挖出的 R 解析挂起 bug）──
def s7_backslash_sanitize():
    from memomics.bio_tools.execute_r import _sanitize_r_backslashes, execute_r
    # 单元：非法转义 → 正斜杠；合法转义保留
    a = _sanitize_r_backslashes("x <- 'E:\\骨骼肌锻炼\\MF_AUCell_meta.csv'")
    assert a == "x <- 'E:/骨骼肌锻炼/MF_AUCell_meta.csv'", f"sanitize failed: {a}"
    b = _sanitize_r_backslashes("cat('a\\nb\\t')\ncat('\\\\')")
    assert "a\\nb\\t" in b and "\\\\" in b, f"legal escapes damaged: {b}"
    # 端到端：带反斜杠中文路径的代码经 execute_r 不再卡死（修复前 worker 永久挂起）
    t0 = time.time()
    r = execute_r(
        "x <- 'E:\\骨骼肌锻炼\\MF_AUCell_meta.csv'; cat('parsed ok len=', nchar(x), '\\n', sep='')",
        working_dir="", timeout=120, task_id="memomics-e2e-s7")
    elapsed = time.time() - t0
    ok = "success" in str(r) and "parsed ok len=" in str(r) and elapsed < 60
    record("S7 反斜杠中文路径→消毒后不挂起", ok,
           f"{elapsed:.1f}s 返回: {str(r)[:80]}")


def main():
    print("=" * 72)
    print("MemOmics 任务进程监控与自愈链 E2E 验证（真数据，无 LLM 依赖）")
    print(f"启动 {time.strftime('%H:%M:%S')}")
    print("=" * 72)
    try:
        s1_proc_stats()
        s2_frozen_kernel()
        pids = s3_real_data_long_run()
        s4_worker_pid(pids)
        s5_completion_chain()
        s6_tool_timeout()
        s7_backslash_sanitize()
    except Exception:
        traceback.print_exc()
        record("FATAL", False, "未捕获异常")
    print("=" * 72)
    fails = [r for r in RESULTS if not r[1]]
    print(f"总计 {len(RESULTS)} 项: PASS {len(RESULTS) - len(fails)} / FAIL {len(fails)}")
    for name, ok, _detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
