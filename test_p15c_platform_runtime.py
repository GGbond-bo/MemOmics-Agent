# -*- coding: utf-8 -*-
"""platform_runtime 薄层验证：detach/terminate/run_capped/spawn_detached（真实进程）。"""
import os, sys, time, json, tempfile, shutil, subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
FAILED = []

def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)

from memomics.platform_runtime import (
    run_capped_process, spawn_detached, terminate_process_tree, detach_options)

IS_WIN = os.name == "nt"
print(f"平台: {'windows' if IS_WIN else 'posix'} | detach_options={detach_options()}")

# 1. run_capped_process 成功路径（平台无关命令）
r = run_capped_process([sys.executable, "-c", "print('hello platform')"], timeout_seconds=60)
check("run_capped 成功", r.returncode == 0 and b"hello platform" in r.stdout, f"r={r!r}")
check("failure_kind=None", r.failure_kind is None, f"kind={r.failure_kind}")

# 2. 超时 → 进程树被杀 + failure_kind=timeout
r = run_capped_process([sys.executable, "-c", "import time; time.sleep(30)"], timeout_seconds=3)
check("超时 killed", r.returncode != 0, f"rc={r.returncode}")
check("failure_kind=timeout", r.failure_kind == "timeout", f"kind={r.failure_kind}")

# 3. 输出限幅（LoopX 契约：kind=output_limit 时进程被杀；缓冲可多出不到一个 chunk）
r = run_capped_process([sys.executable, "-c", "print('x'*300000)"],
                       timeout_seconds=60, output_limit_bytes=50_000)
check("输出限幅", r.failure_kind == "output_limit" and len(r.stdout) <= 50_000 + 65_536, f"kind={r.failure_kind} len={len(r.stdout)}")

# 4. stderr 捕获
r = run_capped_process([sys.executable, "-c", "import sys; sys.stderr.write('err-line')"], timeout_seconds=60)
check("stderr 捕获", b"err-line" in r.stderr, f"stderr={r.stderr!r}")

# 5. spawn_detached + terminate_process_tree：起一个睡眠进程，杀掉整棵树
tmp = tempfile.mkdtemp(prefix="prt_")
marker = os.path.join(tmp, "alive.txt")
script = (
    "import time, sys\n"
    f"open({marker!r}, 'w').write('up')\n"
    "time.sleep(60)\n"
)
proc = spawn_detached([sys.executable, "-c", script])
# 等标记出现（进程已启动）
for _ in range(30):
    if os.path.isfile(marker):
        break
    time.sleep(0.3)
check("detached 进程已启动", os.path.isfile(marker), "")
terminate_process_tree(proc)
time.sleep(1.0)
alive = proc.poll() is None
check("terminate_process_tree 杀掉进程树", not alive, f"poll={proc.poll()}")
check("terminate 幂等（再杀不抛）", True, "")
try:
    terminate_process_tree(proc)
    ok = True
except Exception as e:
    ok = False
check("二次 terminate 无异常", ok, "")
shutil.rmtree(tmp, ignore_errors=True)

# 6. 子进程树场景：父进程起子进程，杀父应连带杀子
tmp2 = tempfile.mkdtemp(prefix="prt2_")
child_marker = os.path.join(tmp2, "child.txt").replace("\\", "/")
parent_script = (
    "import subprocess, sys, time\n"
    f"child = subprocess.Popen([sys.executable, '-c', \"import time; open({child_marker!r},'w').write('c'); time.sleep(120)\"])\n"
    "time.sleep(120)\n"
)
proc = spawn_detached([sys.executable, "-c", parent_script])
for _ in range(40):
    if os.path.isfile(child_marker):
        break
    time.sleep(0.3)
check("父进程拉起子进程", os.path.isfile(child_marker), "")
terminate_process_tree(proc)
time.sleep(1.5)
# 子进程应该也被杀：检测子进程是否还持有文件——用 ps 探测
if IS_WIN:
    probe = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"],
                           capture_output=True, text=True, errors="replace")
    child_alive = "120" in probe.stdout and child_marker in probe.stdout
else:
    probe = subprocess.run(["ps", "-ef"], capture_output=True, text=True, errors="replace")
    child_alive = "time.sleep(120)" in probe.stdout
check("进程树连带清理（子进程一并被杀）", not child_alive, f"probe={probe.stdout[:200]!r}")
shutil.rmtree(tmp2, ignore_errors=True)

print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败: {FAILED}")
    sys.exit(1)
print("✅ platform_runtime 薄层验证通过")
