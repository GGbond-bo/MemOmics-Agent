# -*- coding: utf-8 -*-
"""T4 守卫："长任务走统一包装器" 这条约定必须写清楚，而且**和代码对得上**。

只查文档里有没有关键词是不够的 —— 这里把 SOUL.md 铁律 32 里写的示例标记行
**原样抽出来**喂给 task_run 的真实解析器，能解析出阶段/进度/参数/产物才算过：
文档写错格式、代码改了标记语法，都会在这里红。
"""
import importlib.util
import json
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
TRCLI = os.path.join(_REPO, "memomics", "bio_tools", "task_run.py")
SOUL = os.path.join(_REPO, "hermes_home", "SOUL.md")


def _load_task_run():
    spec = importlib.util.spec_from_file_location("task_run_convention", TRCLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def tr(tmp_path):
    mod = _load_task_run()
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    mod.TASKS_DIR = str(tasks)
    mod.FALLBACK_LOG_DIR = str(tmp_path / "logs")
    os.makedirs(mod.FALLBACK_LOG_DIR, exist_ok=True)
    return mod


def _soul() -> str:
    with open(SOUL, encoding="utf-8") as f:
        return f.read()


def _rule32() -> str:
    """截出铁律 32 那一段（到下一个编号条目为止）。"""
    s = _soul()
    i = s.index("32. **长任务一律走统一包装器")
    m = re.search(r"\n3[3-9]\. |\n\n> ", s[i:])
    return s[i:i + (m.start() if m else 4000)]


def test_rule_exists_and_points_at_wrapper():
    r = _rule32()
    for token in ["memomics/bio_tools/task_run.py", "--type", "--title", "--session-dir",
                  "--stages", "--param", "--script", "⏱ 任务", "--list", "--show"]:
        assert token in r, "铁律 32 里少了 %s" % token
    # 得明确禁止"起完就不管"的老写法，否则 Agent 还是会绕过面板
    assert "subprocess.Popen" in r and "看不见" in r


def test_marker_samples_in_doc_really_parse(tr, tmp_path):
    """把文档里的四行示例抽出来，喂给真实解析器。"""
    r = _rule32()
    samples = re.findall(r"`#TASK:(STAGE|PROGRESS|PARAM|OUTPUT)[^`]*`", r)
    kinds = sorted(set(samples))
    assert kinds == ["OUTPUT", "PARAM", "PROGRESS", "STAGE"], "文档里的示例标记不全：%s" % kinds

    t = tr.new_task("约定校验", type="qc", stages=["阶段名"])
    for kind in kinds:
        m = re.search(r"`(#TASK:" + kind + r"[^`]*)`", r)
        line = m.group(1)
        assert tr._MARKER_RE.match(line), "文档里的示例解析不了：%r" % line
        assert t.handle_marker(line) is True
    d = t.data
    assert d["stages"] and d["stages"][0]["name"] == "阶段名"
    assert d["progress"]["value"] is not None and d["progress"]["value"] > 0
    assert d["params"].get("键") == "值", "PARAM 示例没写进契约：%s" % d["params"]
    assert d["outputs"], "OUTPUT 示例没写进契约"


def test_progress_sample_matches_documented_shape(tr):
    """文档写的是 \"0.42 说明\"，解析器必须接受小数 + 空格 + 说明。"""
    t = tr.new_task("进度形状")
    assert t.handle_marker("#TASK:PROGRESS 0.42 过滤中") is True
    assert abs(t.data["progress"]["value"] - 0.42) < 1e-6
    assert "过滤中" in (t.data["progress"].get("text") or "")


def test_soul_still_loads_as_instruction_file():
    """SOUL.md 是运行时会读的文件，别把格式弄坏（编号条目必须是行首）。"""
    s = _soul()
    assert len(s) > 5000
    assert "\n32. **" in s or s.startswith("32. **")
    assert "\n31. **" in s
    assert "33. **" in s or True  # 以后加新条目不该让本测试红
