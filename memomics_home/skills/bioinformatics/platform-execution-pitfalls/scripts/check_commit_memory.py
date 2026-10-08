"""check_commit_memory.py — Windows 提交内存（commit）+ 进程占用体检探针

为什么需要它：
    物理内存 ≠ 可提交内存。Windows 上进程每次分配都要向 commit 记账，
    上限 = 物理 RAM + pagefile。commit 触顶时**十几 MB 的数组分配也会失败**，
    报错形态是 `MemoryError((2132, 1620), float32)` 或 `WinError 1455 页面文件太小`，
    极易被误判成"机器内存不够"，从而白改参数、白减数据规模。
    ⚠️ `wmic` 在 Windows 11 已被移除，不能用 `wmic OS get FreePhysicalMemory`。

用法（任何重任务/大批量分析开工前跑一次）：
    python check_commit_memory.py
    python check_commit_memory.py --top 20          # 看更多进程
    python check_commit_memory.py --kill-tree 60728 # 需要时按进程树清理（见文末警告）

判据：CommitTotal / CommitLimit > 85%  ⇒ 先降任务需求，不要硬跑
"""
import argparse
import ctypes
import sys


class PERF(ctypes.Structure):
    """Windows GetPerformanceInfo 结构体（commit 记账的核心来源）"""
    _fields_ = [
        ('cb', ctypes.c_ulong),
        ('CommitTotal', ctypes.c_size_t),
        ('CommitLimit', ctypes.c_size_t),
        ('CommitPeak', ctypes.c_size_t),
        ('PhysicalTotal', ctypes.c_size_t),
        ('PhysicalAvailable', ctypes.c_size_t),
        ('SystemCache', ctypes.c_size_t),
        ('KernelTotal', ctypes.c_size_t),
        ('KernelPaged', ctypes.c_size_t),
        ('KernelNonpaged', ctypes.c_size_t),
        ('PageSize', ctypes.c_size_t),
        ('HandleCount', ctypes.c_ulong),
        ('ProcessCount', ctypes.c_ulong),
        ('ThreadCount', ctypes.c_ulong),
    ]


def commit_info():
    p = PERF()
    p.cb = ctypes.sizeof(p)
    ok = ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p), p.cb)
    if not ok:
        raise OSError("GetPerformanceInfo failed")
    k = p.PageSize / 1e9
    return {
        "commit_total_gb": p.CommitTotal * k,
        "commit_limit_gb": p.CommitLimit * k,
        "commit_peak_gb": p.CommitPeak * k,
        "physical_total_gb": p.PhysicalTotal * k,
        "physical_avail_gb": p.PhysicalAvailable * k,
        "process_count": p.ProcessCount,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=12, help="列出 RSS 最高的 N 个进程")
    ap.add_argument("--kill-tree", type=int, default=None,
                    help="按进程树杀掉指定 PID（⛔ 先读 references/windows-commit-limit-and-memory-diagnosis.md 的警告）")
    args = ap.parse_args()

    try:
        import psutil
    except ImportError:
        print("需要 psutil：pip install psutil", file=sys.stderr)
        return 2

    c = commit_info()
    headroom = c["commit_limit_gb"] - c["commit_total_gb"]
    pct = 100 * c["commit_total_gb"] / c["commit_limit_gb"]
    v = psutil.virtual_memory()
    s = psutil.swap_memory()

    print("=== 提交内存（Windows commit）===")
    print(f"  CommitLimit   = {c['commit_limit_gb']:7.1f} GB")
    print(f"  CommitTotal   = {c['commit_total_gb']:7.1f} GB   ({pct:.1f}% of limit)")
    print(f"  CommitPeak    = {c['commit_peak_gb']:7.1f} GB")
    print(f"  余量 headroom = {headroom:7.1f} GB   <-- 真正的分配天花板")
    print(f"  物理内存      = total {c['physical_total_gb']:.1f} GB / avail {c['physical_avail_gb']:.1f} GB"
          f"  (psutil avail {v.available/1e9:.1f} GB, used {v.percent}%)")
    print(f"  Pagefile      = used {s.used/1e9:.1f} / total {s.total/1e9:.1f} GB ({s.percent}%)")
    print(f"  进程数        = {c['process_count']}")

    print("\n=== 判据 ===")
    if pct > 85:
        print(f"  ⛔ commit 已用 {pct:.1f}%（余量 {headroom:.1f} GB）—— 先降任务需求（worker 数 / HVG 子集 /")
        print("     释放 kernel 大对象），不要直接开跑重任务。")
    else:
        print(f"  ✅ commit 余量 {headroom:.1f} GB，尚可；仍建议估算任务峰值后再开跑。")
    print("  ⚠️ commit 触顶时『十几 MB 的数组分配也会失败』，报错形如")
    print("     MemoryError((n, m), float32) / WinError 1455 页面文件太小 —— 不是物理内存不足。")

    print(f"\n=== TOP {args.top} 进程 RSS ===")
    rows = []
    for q in psutil.process_iter(['pid', 'name', 'ppid']):
        try:
            rows.append((q.memory_info().rss / 1e9, q.pid, q.info['name'] or '', q.info['ppid']))
        except Exception:
            pass
    rows.sort(reverse=True)
    alive = {q.pid for q in psutil.process_iter()}
    print(f"{'RSS_GB':>8} {'PID':>8} {'PPID':>8}  NAME")
    for rss, pid, name, ppid in rows[:args.top]:
        flag = "  <-- PPID 已不存在（≠ 可杀！先查 CommandLine）" if ppid not in alive else ""
        print(f"{rss:8.2f} {pid:8d} {ppid:8d}  {name}{flag}")
    print(f"TOP{args.top} 合计 = {sum(r[0] for r in rows[:args.top]):.1f} GB ; 进程总数 = {len(rows)}")

    print("\n=== 提醒（本机实测教训）===")
    print("  · MemOmics server + kernel 池常驻 ~10 GB 属【正常占用】，不是残留垃圾。")
    print("  · PPID 已不存在 ≠ 进程可杀：server 的父启动器常已退出，杀其进程树会把自己的")
    print("    命令一起 SIGTERM（回执 exit 15、零输出）。先用 Get-CimInstance Win32_Process 查 CommandLine。")
    print("  · 内存不足优先『降任务自身需求』，不要拿平台基础设施开刀。")

    if args.kill_tree:
        pid = args.kill_tree
        try:
            proc = psutil.Process(pid)
            kids = proc.children(recursive=True)
            print(f"\n[kill-tree] PID {pid} ({proc.name()}) 子进程 {len(kids)} 个")
            for ch in kids:
                try:
                    print(f"   killing {ch.pid} {ch.name()}")
                    ch.kill()
                except Exception as e:
                    print(f"   kid kill failed {ch.pid}: {e}")
            proc.kill()
            print(f"[kill-tree] 已杀 {pid}")
        except Exception as e:
            print(f"[kill-tree] {pid} 处理失败: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())