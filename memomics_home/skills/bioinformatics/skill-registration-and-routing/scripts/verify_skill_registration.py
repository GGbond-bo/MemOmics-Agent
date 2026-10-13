#!/usr/bin/env python
"""技能注册体检（8 项）— 新建/改动技能后收工前跑这个。

用法:
    python verify_skill_registration.py <skill-name>

退出码: 0 = 全过；1 = 有 FAIL；2 = 用法/路径错误。

设计说明:
  * 只读，不改任何文件。
  * 真实 matcher 检查在**子进程**里做（import webui.server 重，且会写模型日志），
    失败不影响其他项判定（标 SKIP）。
  * 判定口径以源码为准（见 references/skill-registration-pipeline.md §2）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# 本文件位于 <ROOT>/hermes_home/skills/bioinformatics/<skill>/scripts/
_HERE = Path(__file__).resolve()
HERMES_HOME = Path(os.environ.get("HERMES_HOME") or _HERE.parents[4])
ROOT = Path(os.environ.get("MEMOMICS_ROOT") or HERMES_HOME.parent)

SCANNED_ROOTS = [
    ROOT / "skills",
    HERMES_HOME / "skills" / "bioinformatics",
    HERMES_HOME / "skills" / "plotting",
]
INDEX = HERMES_HOME / "SKILLS_INDEX.md"
ROUTING = ROOT / "webui" / "tests" / "fixtures" / "skill_routing_matrix.json"

PLACEHOLDER_RE = re.compile(r"^(包名|英文功能词|中文功能描述|触发场景\d|缩写或变体|用户口语同义词)")


def _run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def find_skill_dir(name: str) -> Path | None:
    for root in SCANNED_ROOTS:
        cand = root / name
        if (cand / "SKILL.md").is_file():
            return cand
    # 兜底：全库搜（用于诊断「放错目录」）
    for p in (HERMES_HOME / "skills").rglob("SKILL.md"):
        if p.parent.name == name:
            return p.parent
    return None


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    name = argv[1]
    results: list[tuple[str, str, str]] = []   # (status, title, detail)

    d = find_skill_dir(name)
    if d is None:
        print(f"FAIL 找不到技能目录 '{name}'（在 {HERMES_HOME}/skills 下搜过了）")
        return 2

    # --- 1) 目录在被扫描的根下 ---
    in_scan = any(str(d).startswith(str(r)) for r in SCANNED_ROOTS)
    results.append((
        "PASS" if in_scan else "FAIL",
        "目录在被扫描的根下（否则 WebUI 选择器看不到）",
        str(d) if in_scan else f"{d} 不在 {[str(r) for r in SCANNED_ROOTS]} 之下 → 迁到 hermes_home/skills/bioinformatics/",
    ))

    # --- 2) skill.json 存在且触发词达标 ---
    sj_path = d / "skill.json"
    sj, kws, level = {}, [], None
    if sj_path.is_file():
        try:
            sj = json.loads(sj_path.read_text(encoding="utf-8"))
            raw = sj.get("trigger_keywords") or []
            kws = [str(k) for k in raw] if isinstance(raw, list) else \
                  [x.strip() for x in str(raw).split(",") if x.strip()]
            level = sj.get("trigger_level")
        except Exception as exc:  # noqa: BLE001
            results.append(("FAIL", "skill.json 可解析", f"{exc}"))
    else:
        results.append(("FAIL", "skill.json 存在", "缺 skill.json → 复制 templates/skill.json 改"))
    if sj_path.is_file():
        placeholder = [k for k in kws if PLACEHOLDER_RE.match(k)]
        n = len(kws)
        if placeholder:
            results.append(("FAIL", "触发词是真实内容（非模板占位）", f"占位词: {placeholder}"))
        elif n < 2:
            results.append(("FAIL", "触发词条数 ≥2（<2 会跌落名称派生）", f"只有 {n} 条"))
        elif n < 10:
            results.append(("WARN", "触发词条数建议 10–17", f"只有 {n} 条，命中面偏窄"))
        else:
            results.append(("PASS", "触发词条数", f"{n} 条"))
        results.append(("PASS" if level else "FAIL", "trigger_level 已设置",
                        str(level) if level else "缺 trigger_level（RED/YEL/GRN/WHT）"))

    # --- 3) 索引行：存在 + 关键词与 skill.json 一致 + 非名称派生 ---
    idx_kw, idx_lvl, idx_found = None, None, False
    if INDEX.is_file():
        for line in INDEX.read_text(encoding="utf-8", errors="replace").splitlines():
            if f"| {name} |" in line:
                cells = [c.strip() for c in line.split("|")]
                if len(cells) >= 3:
                    idx_kw, idx_lvl, idx_found = cells[-3], cells[-2], True
                break
    if not idx_found:
        results.append(("FAIL", "索引行存在", "缺 → 跑 python -m webui.skills_registry --build"))
    else:
        deriv = idx_kw and idx_kw == ", ".join(
            [name] + [t for t in re.split(r"[-_\s]+", name) if t])
        same = kws and all(k in (idx_kw or "") for k in kws[:3])
        if deriv:
            results.append(("FAIL", "索引关键词非名称派生",
                            f"索引='{idx_kw}' ← 被名称派生盖掉了，重写 skill.json 后 --build"))
        elif same:
            results.append(("PASS", "索引关键词与 skill.json 一致（前 3 条抽样）", str(idx_kw)[:110]))
        else:
            results.append(("WARN", "索引关键词与 skill.json 一致",
                            f"skill.json={kws[:3]} / 索引={(idx_kw or '')[:70]}"))
        lv_ok = bool(idx_lvl and "RED" in idx_lvl)
        results.append(("PASS" if lv_ok else "WARN", "索引级别",
                        f"{idx_lvl}（要 RED 必触发才是必触发）"))

    # --- 4) 真实 matcher（子进程；失败标 SKIP） ---
    if kws:
        sample = kws[0] if not kws[0].isascii() or " " not in kws[0] else kws[0]
        probe = f"帮我看看 {sample} 怎么用"
        code = (
            "import sys;sys.path.insert(0,%r);import server;"
            "print('HITS='+','.join(server._match_red_skill_triggers(%r)))"
            % (str(ROOT / "webui"), probe)
        )
        cp = _run([sys.executable, "-c", code], cwd=str(ROOT), timeout=300)
        m = re.search(r"HITS=(.*)", cp.stdout or "")
        if m is None:
            results.append(("SKIP", "真实 matcher 命中", "server 不可导入（本地缺依赖？）"))
        else:
            hits = [h for h in m.group(1).split(",") if h]
            results.append(("PASS" if name in hits else "FAIL", "真实 matcher 命中",
                            f"probe={probe!r} → {hits}"))

    # --- 5) 路由用例 / 豁免 ---
    if ROUTING.is_file():
        try:
            fx = json.loads(ROUTING.read_text(encoding="utf-8"))
            covered = any(name in (c.get("must_hit") or []) for c in fx.get("cases", []))
            exempt = name in (fx.get("coverage_exempt") or [])
            results.append(("PASS" if (covered or exempt) else "FAIL", "路由用例或豁免",
                            "已覆盖" if covered else ("已豁免" if exempt else
                            "缺 → fixtures/skill_routing_matrix.json 的 cases 补一条真实口语用例")))
        except Exception as exc:  # noqa: BLE001
            results.append(("SKIP", "路由用例", f"fixtures 不可解析: {exc}"))
    else:
        results.append(("SKIP", "路由用例", f"缺 {ROUTING}"))

    # --- 6) skill.json 已入 git ---
    cp = _run(["git", "ls-files", "--error-unmatch", str(sj_path)], cwd=str(ROOT))
    tracked = cp.returncode == 0
    results.append(("PASS" if tracked else "FAIL", "skill.json 已入 git",
                    "已跟踪" if tracked else "git add <技能目录>（只 add SKILL.md 不够）"))

    # --- 7) 索引可复现性提示 ---
    n_lines = len(INDEX.read_text(encoding="utf-8", errors="replace").splitlines()) if INDEX.is_file() else 0
    results.append(("INFO", "索引规模（重复 --build 应字节一致）",
                    f"{n_lines} 行 / {INDEX.stat().st_size} 字节" if INDEX.is_file() else "无索引"))

    # --- 8) 门禁提示 ---
    results.append(("INFO", "提交门禁", "提交前跑 python scripts/check_skills_gate.py（被拦=门禁未过）"))

    # ---- 输出 ----
    print(f"\n技能注册体检: {name}   ({d})")
    print("=" * 68)
    for status, title, detail in results:
        mark = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ ", "SKIP": "⏭ ", "INFO": "ℹ️ "}[status]
        print(f"{mark} {title}\n     {detail}")
    n_fail = sum(1 for s, _, _ in results if s == "FAIL")
    print("=" * 68)
    print(f"FAIL {n_fail} 项 / 共 {len(results)} 项 → {'PASS ✅' if n_fail == 0 else 'NOT READY ❌'}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))