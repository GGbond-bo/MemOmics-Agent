# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 代谢组学功能富集 — Python 入口脚本
# ============================================================
import subprocess, sys, os

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    r_script = os.path.join(script_dir, "functional_enrichment.R")
    result = subprocess.run(["Rscript", r_script], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print("ERROR:", result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

if __name__ == "__main__":
    main()