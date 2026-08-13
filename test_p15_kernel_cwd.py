# -*- coding: utf-8 -*-
"""P1-5 working_dir 接线验证：持久 kernel 复用 worker 时 cwd 切换生效（真实 kernel）。"""
import os, sys, json, tempfile, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "hermes-agent"))
FAILED = []

def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)

from memomics.bio_tools.execute_r import execute_r
from memomics.bio_tools.execute_python import execute_python

d1 = tempfile.mkdtemp(prefix="p15_a_")
d2 = tempfile.mkdtemp(prefix="p15_b_")
tid = f"p15_{os.getpid()}"

try:
    # 1. R kernel：第一次 working_dir=d1，写文件 → 落在 d1
    r = execute_r(f'writeLines("hello1", "out.txt")\ncat(getwd(), "\\n")\n',
                  working_dir=d1, task_id=tid, timeout=120)
    d = json.loads(r)
    check("R 第一次 cwd=d1 生效", os.path.isfile(os.path.join(d1, "out.txt")),
          f"r={r[:120]!r} files_d1={os.listdir(d1)}")

    # 2. R kernel 复用：working_dir=d2 → setwd 切换后落在 d2
    r = execute_r(f'writeLines("hello2", "out.txt")\ncat(getwd(), "\\n")\n',
                  working_dir=d2, task_id=tid, timeout=120)
    d = json.loads(r)
    ok2 = os.path.isfile(os.path.join(d2, "out.txt"))
    check("R 复用 worker cwd 切换到 d2", ok2,
          f"r={r[:200]!r} files_d2={os.listdir(d2)} files_d1={os.listdir(d1)}")
    check("R d1 未被污染", not os.path.exists(os.path.join(d1, "out2.txt")) and
          os.path.isfile(os.path.join(d1, "out.txt")), "")

    # 3. Python kernel：复用 worker cwd 切换（execute_python 无 task_id 参数，用环境变量）
    os.environ["MEMOMICS_SESSION_ID"] = tid
    r = execute_python(
        f"import os\nopen('pyout.txt','w').write('p2')\nprint('cwd=', os.getcwd())\n",
        working_dir=d2, timeout=120)
    ok3 = os.path.isfile(os.path.join(d2, "pyout.txt"))
    check("Python kernel cwd 接线", ok3, f"r={r[:200]!r}")

finally:
    shutil.rmtree(d1, ignore_errors=True)
    shutil.rmtree(d2, ignore_errors=True)

print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败: {FAILED}")
    sys.exit(1)
print("✅ P1-5 全部通过")
