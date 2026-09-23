# -*- coding: utf-8 -*-
"""Skill 门禁（P0-1）：一条命令跑完「索引一致性 + 路由回归矩阵 + 注册表护栏」。

设计目标：把「技能面改动」的验收压成一条可被机器调用的命令，三处共用同一入口 ——
  · 人工：python scripts/check_skills_gate.py
  · 提交前：.githooks/pre-commit（只在暂存区涉及技能面文件时触发）
  · CI：.github/workflows/skills-gate.yml

它做两件事，任何一件不过就非零退出：
  1. webui/skills_registry.check()：SKILLS_INDEX.md 必须与磁盘 355 个技能逐字一致（只读，不写文件）；
  2. pytest 跑六份聚焦测试：注册表护栏、触发词矩阵、路由回归矩阵、触发词契约，
     加上 P0-3 命中可见性、P0-2d 置顶判定词边界（后两份是 P0-3/P0-2d 落地时补进门的，
     否则契约文件写了没人执行 —— 这两条正是「技能面改动」的验收面）；
  最后打印一行结论（含技能数/RED 数与耗时），便于 hook 与 CI 日志抓取。

为什么不用「全量 pytest」：全量 1253 例要跑十几分钟，提交前不可接受；技能面的风险
全部集中在上述三份测试里；改 server.py 其它部分时 CI 的全量工作流仍会兜底。

用法：
  python scripts/check_skills_gate.py            # 全量门禁
  python scripts/check_skills_gate.py --quiet    # 只打印结论行（hook 用）
  python scripts/check_skills_gate.py --list     # 只打印将要执行的检查项
退出码：0 通过；1 未通过（含环境缺 pytest / 索引漂移 / 测试失败）。
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_FILES = [
    os.path.join("webui", "tests", "test_skills_registry.py"),
    os.path.join("webui", "tests", "test_skill_trigger_matrix.py"),
    os.path.join("webui", "tests", "test_skill_routing_matrix.py"),
    os.path.join("webui", "tests", "test_skill_trigger_contract.py"),
    os.path.join("webui", "tests", "test_p0_3_skill_visibility.py"),
    os.path.join("webui", "tests", "test_p0_2d_trigger_boundary.py"),
    os.path.join("webui", "tests", "test_p1_1_goal_bar.py"),
]


def _load_registry():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from webui import skills_registry as reg  # noqa: E402
    return reg


def check_index(reg, quiet):
    """索引与磁盘一致性（只读）。返回 (ok, 说明)。"""
    try:
        problems = reg.check()
    except Exception as exc:  # noqa: BLE001 — 门禁自身出错按失败处理
        print("[skills-gate] x 索引检查自身失败: %r" % (exc,))
        return False, "索引检查异常: %r" % (exc,)
    if problems:
        print("[skills-gate] x SKILLS_INDEX.md 与磁盘不一致（%d 处）：" % len(problems))
        for p in problems[:20]:
            print("    . %s" % p)
        if len(problems) > 20:
            print("    . ...（还有 %d 处）" % (len(problems) - 20))
        print("[skills-gate]   修复：在 webui/ 目录执行 python -m webui.skills_registry --build，"
              "再重新提交（索引必须与磁盘同一次生成）")
        return False, "索引漂移 %d 处" % len(problems)

    entries = reg.scan_skills()
    info = reg.report(entries, verbose=False)
    levels = info.get("levels") or {}
    detail = "索引一致（%s 个技能：RED %s / YEL %s / GRN %s）" % (
        info.get("total"), levels.get("RED"), levels.get("YEL"), levels.get("GRN"))
    if not quiet:
        print("[skills-gate] OK %s" % detail)
    return True, detail


def _counts_from_junit(xml_path):
    """从 junit-xml 里取 (passed, failed, skipped)，拿不到就返回 None。"""
    if not os.path.isfile(xml_path):
        return None
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(xml_path).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is None:
            return None
        total = int(suite.get("tests") or 0)
        bad = int(suite.get("failures") or 0) + int(suite.get("errors") or 0)
        skip = int(suite.get("skipped") or 0)
        return (total - bad - skip, bad, skip)
    except Exception:  # noqa: BLE001 — 计数失败不影响门禁结论
        return None


def run_pytest(quiet, junit_path=None):
    """跑三份聚焦测试。缺 pytest 按失败处理（门禁不能因为「跑不起来」而放行）。"""
    missing = [f for f in TEST_FILES if not os.path.isfile(os.path.join(ROOT, f))]
    if missing:
        print("[skills-gate] x 测试文件缺失: %s" % missing)
        return False, "测试文件缺失"

    # 注意：pytest.ini 的 addopts 已经带了 -q + 标记过滤，这里不能再加 -q
    #（-qq 会让 pytest 连结论行都不打印，hook/CI 日志就抓不到计数）。
    # 计数以 junit-xml 为准（终端行只作兜底，避免受插件/编码影响）。
    xml_path = junit_path or os.path.join(tempfile.gettempdir(), "memomics_skills_gate.xml")
    if os.path.exists(xml_path):
        try:
            os.remove(xml_path)
        except OSError:
            pass
    cmd = [sys.executable, "-m", "pytest"] + TEST_FILES + [
        "-p", "no:warnings", "--no-header", "-rs", "--junitxml=" + xml_path]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=1800)
    except FileNotFoundError:
        print("[skills-gate] x 找不到 pytest：%s -m pytest" % sys.executable)
        return False, "缺 pytest"
    except subprocess.TimeoutExpired:
        print("[skills-gate] x 测试超时（>30 分钟）")
        return False, "测试超时"

    out = proc.stdout.decode("utf-8", "replace")
    passed = failed = skipped = 0
    counts = _counts_from_junit(xml_path)
    if counts:
        passed, failed, skipped = counts
    else:
        for line in reversed(out.splitlines()):
            if " passed" in line or " failed" in line or " error" in line:
                m = re.search(r"(\d+) passed", line)
                if m:
                    passed = int(m.group(1))
                m = re.search(r"(\d+) failed", line)
                if m:
                    failed = int(m.group(1))
                m = re.search(r"(\d+) skipped", line)
                if m:
                    skipped = int(m.group(1))
                break
    if proc.returncode != 0:
        print("[skills-gate] x 路由/注册表测试未通过（exit=%d）：" % proc.returncode)
        for line in out.strip().splitlines()[-25:]:
            print("    %s" % line)
        return False, "测试失败"
    detail = "测试通过（%s%s）" % (
        ("%d 例" % passed) if passed else "全部",
        ("，跳过 %d" % skipped) if skipped else "")
    if not quiet:
        print("[skills-gate] OK %s" % detail)
        if skipped:
            print("    （%d 例被跳过：多为本地缺 server 依赖，CI 环境会真跑）" % skipped)
    return True, detail


def main(argv=None):
    ap = argparse.ArgumentParser(description="MemOmics skill 门禁")
    ap.add_argument("--quiet", action="store_true", help="只打印最终结论行")
    ap.add_argument("--list", action="store_true", help="只打印检查项")
    ap.add_argument("--junit", metavar="PATH", default=None,
                    help="把 pytest 的 junit-xml 写到指定路径（CI 用来核对跳过数）")
    args = ap.parse_args(argv)

    if args.list:
        print("1. webui/skills_registry.check()：SKILLS_INDEX.md vs 磁盘（只读）")
        for f in TEST_FILES:
            print("2. pytest %s" % f.replace(os.sep, "/"))
        return 0

    started = time.time()
    reg = _load_registry()
    ok1, d1 = check_index(reg, args.quiet)
    if not ok1:
        print("[skills-gate] FAIL —— %s（%.1fs）" % (d1, time.time() - started))
        return 1
    ok2, d2 = run_pytest(args.quiet, args.junit)
    elapsed = time.time() - started
    if not ok2:
        print("[skills-gate] FAIL —— %s（%.1fs）" % (d2, elapsed))
        return 1
    print("[skills-gate] PASS —— %s · %s（%.1fs）" % (d1, d2, elapsed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
