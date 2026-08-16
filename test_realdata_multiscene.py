# -*- coding: utf-8 -*-
"""真实数据多场景多意图集成测试（2026-08-17）。

覆盖意图（不依赖 LLM 网关，全部真实代码路径 + 真实数据）：
  A 环境检测意图：check_env 真检查（多库发现 + 诚实缺失）
  B 可视化意图（普通任务）：读 528MB 注释 RDS → DimPlot 出图；fread 30 万行 CSV
  C 执行审查意图：rail_review pre/post 真实端到端 + 门禁语义（11 项）
  D 长任务监督意图：task_class 升级 + 看门狗 working/frozen 判定（真 kernel）
  E 说而不做/意图路由：多意图文本检测
  F 完成停链意图：完成归档 + done 拦截 + 进行中对照
  G 单会话记忆：state.db 会话/消息完整性
  H 日志去重：同一事件只写一次

运行：venv python test_realdata_multiscene.py（约 3-5 分钟）
"""
import json
import os
import sys
import time
import threading

sys.path.insert(0, "E:/MemOmics-Agent")
sys.path.insert(0, "E:/MemOmics-Agent/hermes-agent")

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}", flush=True)


# ── A 环境检测意图 ─────────────────────────────────────────
def sA_env_check():
    from memomics.bio_tools.env_check import _r_lib_env, _check_r_packages
    env = _r_lib_env()
    libs = (env.get("R_LIBS", "") or "").split(";")
    ok_first = libs and libs[0].startswith("E:/R-libs/R-4.5.3")
    st = _check_r_packages(["Seurat", "ggplot2", "data.table", "harmony"])
    st2 = _check_r_packages(["pkg_nonexistent_xyz_123"])
    ok = ok_first and all(st.get(p) for p in ("Seurat", "ggplot2", "data.table")) \
        and st2.get("pkg_nonexistent_xyz_123") is False
    record("A 环境真检查(多库发现+诚实缺失)", ok,
           f"候选库{len(libs)}个 主力优先={ok_first} Seurat={st.get('Seurat')} harmony={st.get('harmony')} 假包=False")


# ── B 可视化意图（普通任务，真实数据） ─────────────────────
def sB_visualize():
    from tools.persistent_kernel import KERNEL_POOL
    import tempfile
    outdir = tempfile.mkdtemp(prefix="e2e-realdata-")
    rcode = (
        "suppressMessages(library(Seurat))\n"
        "suppressMessages(library(ggplot2))\n"
        "t0 <- Sys.time()\n"
        "obj <- readRDS('E:/骨骼肌锻炼/special_MF_annotation_umap.rds')\n"
        "cat(sprintf('obj dim=%dx%d subclusters=%d samples=%d\\n', nrow(obj), ncol(obj), "
        "length(unique(obj$subcluster)), length(unique(obj$samplename))), flush=TRUE)\n"
        "p <- DimPlot(obj, group.by='subcluster', label=TRUE, repel=TRUE, label.size=4.5)\n"
        f"ggsave('{outdir.replace(chr(92), '/')}/umap_annotation_e2e.png', p, width=9, height=7.5, dpi=300)\n"
        "cat(sprintf('PLOT DONE in %.1fs\\n', as.numeric(Sys.time()-t0)), flush=TRUE)\n"
    )
    t0 = time.time()
    r = KERNEL_POOL.execute(rcode, "e2e-realdata-vis", timeout=600, language="r", cwd=None)
    elapsed = time.time() - t0
    png = os.path.join(outdir, "umap_annotation_e2e.png")
    ok = r.get("status") == "ok" and os.path.isfile(png) and os.path.getsize(png) > 10000
    record("B 可视化(528MB RDS→注释UMAP)", ok,
           f"{elapsed:.0f}s status={r.get('status')} png={os.path.getsize(png) if os.path.isfile(png) else 0}字节")
    if not ok:
        print("   B 诊断:", str(r.get("output", ""))[-300:], str(r.get("error", ""))[:150], flush=True)
    # fread 30 万行
    r2 = KERNEL_POOL.execute(
        "suppressMessages(library(data.table)); x <- fread('E:/骨骼肌锻炼/MF_AUCell_meta.csv', nrows=300000, showProgress=FALSE); cat('fread', nrow(x), 'x', ncol(x), '\\n', flush=TRUE)",
        "e2e-realdata-fread", timeout=180, language="r", cwd=None)
    ok2 = r2.get("status") == "ok" and "fread 300000 x 58" in str(r2.get("output", ""))
    record("B2 CSV 30万行读取", ok2, str(r2.get("output", ""))[-60:])
    KERNEL_POOL.restart(task_id="e2e-realdata-vis")
    KERNEL_POOL.restart(task_id="e2e-realdata-fread")


# ── C 执行审查意图（真实 rail_review + 门禁语义） ──────────
def sC_review():
    from memomics.bio_tools.rail_review import rail_review
    # pre：真实包检测（环境修复后应通过）
    r_pre = json.loads(rail_review(phase="pre", module_id="visualize_umap",
                                   required_packages=["Seurat", "ggplot2"],
                                   skill_name="cns-visualization"))
    ok_pre = r_pre.get("should_proceed") is True
    # pre：不存在的包 → 应拦
    r_pre2 = json.loads(rail_review(phase="pre", module_id="x",
                                    required_packages=["pkg_nonexistent_xyz"], skill_name="s"))
    ok_pre2 = r_pre2.get("should_proceed") is False
    record("C1 rail_review(pre) 真包通过/假包拦截", ok_pre and ok_pre2,
           f"Seurat+ggplot2 → {r_pre.get('should_proceed')} | 假包 → {r_pre2.get('should_proceed')}")
    # 门禁语义 11 项（真实回调链）
    import subprocess
    p = subprocess.run([sys.executable, "E:/MemOmics-Agent/test_enforcement_block.py"],
                       capture_output=True, text=True, errors="replace")
    ok = p.returncode == 0 and "PASS 11" in p.stdout
    record("C2 门禁语义(11项)", ok, f"exit={p.returncode}")


# ── D 长任务监督意图 ───────────────────────────────────────
def sD_longtask():
    import webui.server as S
    from webui.runtime import run_gate
    import tempfile
    d = tempfile.mkdtemp(prefix="e2e-longtask-")
    sess = {"id": "e2e-longtask", "results_dir": d}
    run_gate.save_state(d, "pending", "t")
    assert run_gate.get_task_class(d) == "normal"
    S._mark_task_long_running(sess)
    ok1 = run_gate.get_task_class(d) == "long_running"
    record("D1 运行时证据→task_class 升级", ok1)

    # 看门狗 working（真 kernel 烧 CPU）
    from tools.persistent_kernel import KERNEL_POOL
    old_win = S._TRACKED_PROC_HIST_WINDOW
    S._TRACKED_PROC_HIST_WINDOW = 60
    sess2 = {"id": "e2e-realdata-burn", "results_dir": "", "_live_tool": "execute_r", "_proc_hist": []}
    res = {}
    rcode = ("suppressMessages(library(data.table))\n"
             "x <- fread('E:/骨骼肌锻炼/MF_AUCell_meta.csv', nrows=30000, showProgress=FALSE)\n"
             "num <- names(x)[sapply(x, is.numeric)]\n"
             "m <- as.matrix(x[, ..num]); m[!is.finite(m)] <- 0\n"
             "cat('matrix', nrow(m), 'x', ncol(m), '\\n', flush=TRUE)\n"
             "t0 <- Sys.time()\n"
             "while (as.numeric(Sys.time()-t0) < 50) { s <- svd(m[sample.int(nrow(m), 5000), ], nu=2, nv=2) }\n"
             "cat('BURN DONE\\n', flush=TRUE)\n")
    def run():
        res["r"] = KERNEL_POOL.execute(rcode, "e2e-realdata-burn", timeout=200, language="r", cwd=None)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    verdicts = []
    while t.is_alive():
        S._sample_task_procs(sess2)
        v, info = S._task_liveness(sess2)
        if v not in ("insufficient",) and (not verdicts or verdicts[-1] != v):
            verdicts.append(v)
        time.sleep(5)
    t.join()
    S._TRACKED_PROC_HIST_WINDOW = old_win
    ok2 = res.get("r", {}).get("status") == "ok" and "frozen" not in verdicts and "working" in verdicts
    record("D2 看门狗 working(真CPU燃烧50s)", ok2, f"verdicts={verdicts}")

    # 看门狗 frozen（真冻结）：sleep 需超过采样窗口，启动期 CPU 才会滑出窗口
    S._TRACKED_PROC_HIST_WINDOW = 30
    sess3 = {"id": "e2e-realdata-frozen", "results_dir": "", "_live_tool": "execute_r", "_proc_hist": []}
    res3 = {}
    def run3():
        res3["r"] = KERNEL_POOL.execute("Sys.sleep(60)", "e2e-realdata-frozen", timeout=150, language="r", cwd=None)
    t3 = threading.Thread(target=run3, daemon=True)
    t3.start()
    verdicts3 = []
    while t3.is_alive():
        S._sample_task_procs(sess3)
        v, info = S._task_liveness(sess3)
        if v not in ("insufficient",) and (not verdicts3 or verdicts3[-1] != v):
            verdicts3.append(v)
        time.sleep(5)
    t3.join()
    S._TRACKED_PROC_HIST_WINDOW = old_win
    ok3 = "frozen" in verdicts3
    record("D3 看门狗 frozen(真冻结45s)", ok3, f"verdicts={verdicts3}")
    KERNEL_POOL.restart(task_id="e2e-realdata-burn")
    KERNEL_POOL.restart(task_id="e2e-realdata-frozen")


# ── E 说而不做 / 意图路由 ──────────────────────────────────
def sE_promise():
    from webui.server import _detect_action_promise
    from webui.enforcement import detect_analysis_level
    cases_true = ["我现在去跑脚本生成热图，稍等",
                  "先并行扫描新文件，再对比数据",
                  "这就去读RDS对象检查barcode结构"]
    cases_false = ["我先看看结果再决定是否重跑",
                   "画一个 UMAP 给我看，谢谢",
                   "等你的指示再继续"]
    ok1 = all(_detect_action_promise(t, []) for t in cases_true)
    ok2 = all(not _detect_action_promise(t, []) for t in cases_false)
    lv = detect_analysis_level("你帮我把注释的umap画出来给我看")
    lv2 = detect_analysis_level("你好，今天天气不错")
    lv3 = detect_analysis_level("统计一下各组AUCell打分差异是否显著")
    ok3 = lv == "analysis" and lv2 == "chat" and lv3 in ("analysis", "statistical")
    record("E 说而不做+意图路由", ok1 and ok2 and ok3,
           f"真承诺{sum(_detect_action_promise(t, []) for t in cases_true)}/3 豁免{sum(not _detect_action_promise(t, []) for t in cases_false)}/3 意图={lv}/{lv2}/{lv3}")


# ── F 完成停链意图 ─────────────────────────────────────────
def sF_completion():
    import webui.server as S
    from webui.runtime import run_gate
    import tempfile
    calls = []
    _orig = S.asyncio.run_coroutine_threadsafe
    S.asyncio.run_coroutine_threadsafe = lambda coro, loop: calls.append(coro) or True
    class FakeLoop:
        def is_running(self): return True
    loop = FakeLoop()
    try:
        d = tempfile.mkdtemp(prefix="e2e-done-")
        os.makedirs(os.path.join(d, "figures"), exist_ok=True)
        with open(os.path.join(d, "figures", "out.png"), "w") as f:
            f.write("x")
        plan = ("# P\n## Goal\n画图\n## Phases\n### Phase 1\n- [x] 出图\n**Status:** complete\n\n"
                "产出: figures/out.png\n")
        with open(os.path.join(d, "task_plan.md"), "w", encoding="utf-8") as f:
            f.write(plan)
        sess = {"id": "e2e-done", "todos": [], "results_dir": d}
        S._schedule_self_check(sess, agent=object(), loop=loop)
        ok1 = run_gate.load_state(d).get("state") == "done" and os.path.exists(os.path.join(d, "task_plan.done.md")) and not calls
        d2 = tempfile.mkdtemp(prefix="e2e-active-")
        with open(os.path.join(d2, "task_plan.md"), "w", encoding="utf-8") as f:
            f.write("# P\n## Phases\n### Phase 1\n- [ ] 进行中\n**Status:** in_progress\n")
        sess2 = {"id": "e2e-active", "todos": [{"status": "in_progress", "title": "t"}], "results_dir": d2}
        calls.clear()
        S._schedule_self_check(sess2, agent=object(), loop=loop)
        ok2 = len(calls) == 1
        record("F 完成归档+停链 / 进行中续唤醒", ok1 and ok2,
               f"done归档={ok1} 进行中排唤醒={len(calls)}")
    finally:
        S.asyncio.run_coroutine_threadsafe = _orig


# ── G 单会话记忆 ───────────────────────────────────────────
def sG_memory():
    import sqlite3
    conn = sqlite3.connect(r"E:\MemOmics-Agent\hermes_home\state.db", timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT message_count FROM sessions WHERE id='memomics-0228a136'")
    row = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM messages WHERE session_id='memomics-0228a136'")
    nmsg = cur.fetchone()[0]
    conn.close()
    ok = row and row[0] == nmsg and nmsg >= 50
    record("G 单会话记忆持久化", ok, f"session.message_count={row[0] if row else None} messages表={nmsg}")


# ── H 日志去重 ─────────────────────────────────────────────
def sH_logdedup():
    import tempfile
    import webui.server as S
    d = tempfile.mkdtemp(prefix="e2e-log-")
    sess = {"id": "e2e-log", "results_dir": d}
    S._auto_system_log(sess, "execute_r", {"code": "x"}, "ok", tool_id="t1")
    S._auto_system_log(sess, "execute_r", {"code": "x"}, "ok", tool_id="t1")
    S._auto_system_log(sess, "execute_r", {"code": "y"}, "ok", tool_id="t2")
    log = os.path.join(d, "log", "system_log.jsonl")
    n = sum(1 for _ in open(log, encoding="utf-8"))
    record("H 日志同事件去重", n == 2, f"3 次调用(2 同 id) → {n} 行（期望 2）")


def main():
    print("=" * 70)
    print("真实数据多场景多意图集成测试")
    print("=" * 70)
    for fn in (sA_env_check, sB_visualize, sC_review, sD_longtask,
               sE_promise, sF_completion, sG_memory, sH_logdedup):
        try:
            fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
            record(fn.__name__, False, f"异常: {e}")
    fails = [r for r in RESULTS if not r[1]]
    print("=" * 70)
    print(f"总计 {len(RESULTS)} 项: PASS {len(RESULTS) - len(fails)} / FAIL {len(fails)}")
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
