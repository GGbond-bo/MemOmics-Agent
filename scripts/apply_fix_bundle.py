#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""start.bat 启动钩子：旧安装自动应用文件级修复（见 memomics/fix_bundle.py）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from memomics.fix_bundle import apply_fix_bundle
    res = apply_fix_bundle(os.path.join(ROOT, "hermes_home"))
    print("[FixBundle]", res)
    sys.exit(0)
except Exception as e:  # 迁移失败绝不阻塞启动
    print(f"[FixBundle] 跳过（不影响启动）: {e}")
    sys.exit(0)
