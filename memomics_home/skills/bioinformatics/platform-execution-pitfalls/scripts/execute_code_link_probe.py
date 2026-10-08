# execute_code 链路自检探针（2026-08-21 实测通过，user_score=10/10）
# 用途：怀疑 execute_code 沙箱/链路异常时，整体跑一遍确认。
# 预期输出（3 段）：
#   1) HELLO-STRESS  → status=ok
#   2) HELLO-STRESS  → status=ok（同命令原样第二次，验证确定性）
#   3) import 不存在的模块 → status=error + ModuleNotFoundError（cell 中断、后续不执行）
#      —— 然后把本脚本的 import 行改掉，改成 print('OK')，再跑 → status=ok
#
# 语义要点（已沉淀进 SKILL.md 坑表）：
#   - 沙箱把 import 错误当 cell 级致命错误，中断整个 cell，无部分副作用
#   - 缺失模块检测用独立 cell 验证，不要写在同一 cell 期待后续代码兜住

print('HELLO-STRESS')

# --- 第 3 段：故意 import 不存在的模块（预期 ModuleNotFoundError 中断 cell）---
import definitely_missing_module_xyz  # noqa: F401 — 预期报错，观察后删除/替换本行

# 修正版（替换上面 import 行后）：
# print('OK')
