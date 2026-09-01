# 复刻 CI linux-e2e-extreme 的持久内核复用测试（R + Python 变量跨调用存活）
import os, sys

os.environ.setdefault("PYTHONPATH", "" )
sys.path.insert(0, os.path.expanduser("~/memomics-test/MemOmics"))
sys.path.insert(0, os.path.expanduser("~/memomics-test/MemOmics/hermes-agent"))

from tools.persistent_kernel import KERNEL_POOL

r1 = KERNEL_POOL.execute('x <- 42; cat("defined x =", x, "\n")', 'e2e-r', timeout=120, language='r')
r2 = KERNEL_POOL.execute('cat("second call sees x =", x, "\n")', 'e2e-r', timeout=120, language='r')
rok = r1.get("status") == "ok" and r2.get("status") == "ok" and "42" in (r2.get("result") or "")
print("R_PERSISTENT:", "OK" if rok else "FAILED", "|", (r1.get("error") or r2.get("error") or "")[:120])
print("  r1:", r1.get("result"), "| r2:", r2.get("result"))

p1 = KERNEL_POOL.execute('x = 7\nprint("defined x =", x)', 'e2e-py', timeout=120, language='python')
p2 = KERNEL_POOL.execute('print("second call sees x =", x)', 'e2e-py', timeout=120, language='python')
pok = p1.get("status") == "ok" and p2.get("status") == "ok" and "7" in (p2.get("result") or "")
print("PY_PERSISTENT:", "OK" if pok else "FAILED", "|", (p1.get("error") or p2.get("error") or "")[:120])
print("  p1:", p1.get("result"), "| p2:", p2.get("result"))

# 依赖版本/OCR 探针（CI 冒烟项）
try:
    import rapidocr_onnxruntime
    print("OCR_LIB:", "OK", rapidocr_onnxruntime.__version__)
except Exception as e:
    print("OCR_LIB: MISSING:", str(e)[:80])