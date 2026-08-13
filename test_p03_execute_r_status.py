# -*- coding: utf-8 -*-
"""P0-3 execute_r 失败语义验证：结构化 status JSON（真实 Rscript 运行）。"""
import os, sys, json, importlib

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "hermes-agent"))
# 注意：不要 insert ROOT/memomics —— 否则 import memomics.bio_tools 会解析到
# 嵌套旧副本 memomics/memomics/bio_tools/（真实隐患，与 server.py 的 sys.path 一致只插 ROOT）
FAILED = []

def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)

try:
    from memomics.bio_tools.execute_r import execute_r
except ImportError as e:
    sys.path.insert(0, os.path.join(ROOT, "hermes-agent"))
    from memomics.bio_tools.execute_r import execute_r

def parse(r):
    try:
        return json.loads(r)
    except Exception:
        return None

# 1. 成功路径（输出 print）
r = execute_r('cat("hello memomics\\n")\nx <- 1+1\ncat("x=", x, "\\n")\n', timeout=120)
d = parse(r)
check("成功返回 JSON", d is not None, f"raw={r!r}")
check("成功 status=success", d and d.get("status") == "success", f"d={d}")
check("成功 exit_code=0", d and d.get("exit_code") == 0, f"d={d}")
check("成功 output 含文本", d and "hello memomics" in str(d.get("output", "")), f"d={d}")

# 2. 失败路径（stop 非零退出）
r = execute_r('cat("before stop\\n")\nstop("custom failure message")\n', timeout=120)
d = parse(r)
check("失败返回 JSON", d is not None, f"raw={r!r}")
check("失败 status=error", d and d.get("status") == "error", f"d={d}")
check("失败 exit_code 非零", d and d.get("exit_code") != 0, f"d={d}")
check("失败 error 字段存在", d and bool(d.get("error")), f"d={d}")
check("失败 output 保留 [Exit code] 兼容标记", d and "[Exit code:" in str(d.get("output", "")), f"d={d}")

# 3. stderr 场景（warning 但退出码 0 → 仍算 success，stderr 在 output）
r = execute_r('warning("just a warning")\ncat("done\\n")\n', timeout=120)
d = parse(r)
check("warning 退出码0 → success", d and d.get("status") == "success", f"d={d}")

# 4. R 不存在场景（结构性 error）— 独立子进程（避开持久 kernel 缓存），PATH 清空
_code = r"""
import os, sys, json
sys.path.insert(0, ROOT)
from memomics.bio_tools.execute_r import execute_r
os.environ["PATH"] = "C:\\Windows\\System32"
r = execute_r('cat("x\\n")\n', timeout=30)
d = json.loads(r)
assert d.get("status") == "error", f"expected error, got {d}"
assert d.get("exit_code") is None, f"expected None exit_code, got {d}"
print("SUB_OK")
""".replace("ROOT", repr(ROOT))
import subprocess
_p = subprocess.run([sys.executable, "-c", _code], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=180)
check("R 缺失 status=error（子进程）", "SUB_OK" in _p.stdout, f"stdout={_p.stdout[-300:]!r} stderr={_p.stderr[-300:]!r}")

print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败: {FAILED}")
    sys.exit(1)
print("✅ P0-3 全部通过")
