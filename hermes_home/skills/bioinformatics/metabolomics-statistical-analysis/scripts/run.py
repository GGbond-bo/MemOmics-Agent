# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 代谢组学统计分析 — Python 入口脚本
# 调用 R 脚本执行完整 pipeline
# ============================================================

import subprocess
import sys
import os

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    r_script = os.path.join(script_dir, "statistical_analysis.R")
    
    cmd = ["Rscript", r_script]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print(result.stdout)
    if result.returncode != 0:
        print("ERROR:", result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

if __name__ == "__main__":
    main()