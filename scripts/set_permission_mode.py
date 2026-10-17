# -*- coding: utf-8 -*-
"""切换 MemOmics 权限档位（借鉴 DSH permission-presets）。

用法：
    python scripts/set_permission_mode.py                # 查看当前档位
    python scripts/set_permission_mode.py read-only      # 只读
    python scripts/set_permission_mode.py workspace-write
    python scripts/set_permission_mode.py danger-full-access
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from webui.runtime import permission_presets as pp  # noqa: E402


def main(argv):
    if not argv:
        print("当前档位:", pp.get_mode())
        print("可选:", " / ".join(pp.MODES))
        print("允许写入的根:", pp.allowed_roots({}))
        return 0
    mode = argv[0].strip().lower()
    if mode not in pp.MODES:
        print("非法档位:", mode, "| 可选:", " / ".join(pp.MODES))
        return 2
    ok = pp.set_mode(mode)
    print(("已切换为 " + mode) if ok else "切换失败（检查 memomics_home/config.yaml 可写）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
