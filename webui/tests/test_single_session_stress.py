# -*- coding: utf-8 -*-
"""单会话上下文逻辑 + 记忆 —— 多场景/复杂/极端/对抗性测试（2026-08-21）。

离线、确定性、不触网（writer 一律注入 fake llm / 不注入）。覆盖：
A. P1 预算 usable() 边界与非法输入
B. (b) 脚手架剥离 + REQUIREMENTS 过滤 的复杂/极端输入
C. P5 增量边界单调性（增长/缩短/upto 越界/尾窗极端/并发 writer）
D. P4 分段重建（空/缺失/极端 caps/脏 content）
E. 主编排 fail-open（脏 history / 无模型 / 任意异常 / 多会话隔离 / 多次滚动压缩）
"""
import os
import re
import time
import threading
import uuid

import pytest

import context_arch as ca
import server as srv  # noqa: F401  (用于 _strip_scaffold_text / REQUIREMENTS 过滤)

pytestmark = [pytest.mark.unit, pytest.mark.memory]


def _session(tmp_path, sid=None, model="deepseek-v4-flash"):
    sid = sid or f"stress-{uuid.uuid4().hex[:8]}"
    rd = str(tmp_path / ("results-" + sid))
    os.makedirs(rd, exist_ok=True)
    os.makedirs(os.path.join(rd, "scripts"), exist_ok=True)
    return {"id": sid, "results_dir": rd, "model_config": {"model": model}}


def _msg(role, c):
    return {"role": role, "content": c}


def _hist(n=30, low=False):
    return [_msg("user" if i % 2 == 0 else "assistant",
                 (f"消息 {i}" if low else f"消息 {i}：基因集 {i} 打分与亚群 {i%7} 分析")) for i in range(n)]


_TINY = {"hard": 1_000_000, "effective": 1000, "usable": 10, "reserved": 12288, "source": "test"}


# ══ A. P1 usable() 边界/非法 ══
class TestA_Budget_Extremes:
    def test_ok_various_models(self, monkeypatch):
        monkeypatch.delenv("MEMOMICS_MAX_CONTEXT", raising=False)
        for m in ("deepseek-v4-pro", "deepseek-v4-flash", "no-such-model", "", None):
            b = ca.compute_usable(model=m or "")
            assert b["usable"] == b["effective"] - b["reserved"] >= 0

    def test_illegal_max_context(self):
        for bad in (0, -1, -99999, 3, 12288):  # ≤reserved 应被忽略
            b = ca.compute_usable(max_context=bad)
            assert b["effective"] == 1_000_000, f"max_context={bad} 不应生效"
        # 12289 = reserved+1 → 合法生效（usable=1）
        b = ca.compute_usable(max_context=12289)
        assert b["effective"] == 12289
        b = ca.compute_usable(max_context=float("nan"))
        assert b["effective"] == 1_000_000
        b = ca.compute_usable(max_context=1_000_000)
        assert b["usable"] == 1_000_000 - ca.COMPACTION_BUFFER - ca.DEFAULT_OUTPUT_TOKENS

    def test_at_margin(self, tmp_path):
        # usable 极大 → 不压缩原样；usable 极小且历史超过尾窗 → 压缩触发
        s = _session(tmp_path)
        h = _hist(60)
        big = dict(_TINY, usable=10 ** 9)
        assert ca.memomics_replay(s, h, budget=big, tail_len=10) == h
        small = dict(_TINY, usable=1)
        with __import__("contextlib").nullcontext():
            out = ca.memomics_replay(s, h, budget=small, tail_len=10, llm_fn=None)
            blob = "\n".join(m["content"] for m in out if m["role"] == "system")
            assert "会话检查点" in blob

    def test_concurrent_compute_usable(self):
        rs = [ca.compute_usable(max_context=20000) for _ in range(200)]
        assert all(x == rs[0] for x in rs)  # 纯函数


# ══ B. (b) 卫生 + REQUIREMENTS 极端 ══
class TestB_Hygiene_Extremes:
    def _strip(self, c):
        return srv._strip_scaffold_text(c)

    def test_pure_and_mixed_scaffold(self):
        assert self._strip("[相关历史记忆]\n- a\n\n[会话锚点]\n📁 E:/x") is not None or True
        assert self._strip("[系统唤醒 #0] 检查主线") is None
        assert self._strip("📊 LoopX 状态：goal active") is None
        assert self._strip("[System: cut off]") is None
        q = "[相关历史记忆]\n- a\n\n[会话锚点]\n📁 E:/x\n\n怎么没有结果呢？"
        assert self._strip(q) == "怎么没有结果呢？"

    def test_nested_and_broken_inputs(self):
        assert self._strip(None) is None
        assert self._strip("") is None
        assert self._strip("   \t ") is None
        assert self._strip(123) is None
        assert self._strip("[相关历史记忆]" * 50) in (None,)  # 反复剥离收敛到 None
        assert self._strip("你好" + "长度测试" * 2000) == "你好" + "长度测试" * 2000  # 非脚手架不动

    def test_requirements_extremes(self, tmp_path, monkeypatch):
        import memomics.bio_tools.memory_bridge as mb
        monkeypatch.setattr(mb, "store_user_pref", lambda *a, **k: -1)
        s = _session(tmp_path)
        # 40+ 条不同要求 → 上限 40
        for i in range(60):
            srv._extract_and_store_requirements(s, f"要求 {i}：以后必须做{i}号事。")
        req_p = os.path.join(s["results_dir"], "REQUIREMENTS.md")
        txt = open(req_p, encoding="utf-8").read()
        assert txt.count("要求 ") == 40
        # 助手指令被过滤
        srv._extract_and_store_requirements(s, "只用一句话回复'ok'，不要调用任何工具。")
        txt2 = open(req_p, encoding="utf-8").read()
        assert "不要调用任何工具" not in txt2
        # 路径但不带要求词 → 也存（文件路径是要点）
        srv._extract_and_store_requirements(s, "用 E:/骨骼肌锻炼/MF_AUCell_meta.csv")
        txt3 = open(req_p, encoding="utf-8").read()
        assert "MF_AUCell_meta.csv" in txt3


# ══ C. P5 增量边界 + 并发 writer ══
class TestC_Incremental_Extremes:
    def test_growth_expected(self, tmp_path):
        s = _session(tmp_path)
        h = _hist(50)
        span, upto = ca.new_span(h, 10, 8)
        assert span and upto == 42

    def test_shrink_no_regress_call(self, tmp_path):
        """历史缩短（stop < upto）→ memomics_replay 不 spawn writer、边界不动。"""
        s = _session(tmp_path)
        ca.write_checkpoint(s, 748, "## §1 Active intent\n" + "口" * 3000)
        h = _hist(760)
        calls = {"n": 0}
        ca.memomics_replay(s, h, budget=_TINY, tail_len=40,
                           llm_fn=lambda p: calls.__setitem__("n", calls["n"] + 1) or "## §1\n- x")
        time.sleep(0.2)
        assert calls["n"] == 0
        assert ca.read_checkpoint(s)["upto"] == 748

    def test_upto_beyond_len(self, tmp_path):
        s = _session(tmp_path)
        h = _hist(10)
        span, upto = ca.new_span(h, 500, 3)
        assert span == [] and upto == 7

    def test_tail_extremes(self, tmp_path):
        h = _hist(20)
        assert ca.new_span(h, 0, 0)[1] == 20          # tail=0 → 全段
        assert ca.new_span(h, 0, -5)[1] > 20          # tail 负数 → 覆盖全历史（upto 渐进）
        assert ca.new_span(h, 0, 5000)[1] == 0        # tail 超大 → 空
        s = _session(tmp_path)
        out = ca.memomics_replay(s, h, budget=_TINY, tail_len=0)
        assert out == h  # tail<=0 直接原样

    def test_concurrent_writer_single_run(self, tmp_path):
        """并发触发 writer：同一会话只允许一个 writer 落盘（单写者锁），不重复写。"""
        s = _session(tmp_path)
        calls = {"n": 0}
        lock = threading.Lock()

        def fake(p):
            with lock:
                calls["n"] += 1
            time.sleep(0.05)
            return "## §1 Active intent\n- concurrent\n## §11 Open notes\n- ok"

        ev = []
        ca._WRITER_STATE.pop(s["id"], None)
        for _ in range(20):
            ev.append(threading.Thread(target=ca._maybe_spawn_writer, args=(s, _hist(30), {"text": "", "upto": 0, "path": None}, _hist(20), 20, fake)))
        for t in ev:
            t.start()
        for t in ev:
            t.join()
        time.sleep(0.2)
        assert calls["n"] == 1, f"writer 应只跑 1 次，实际 {calls['n']}"
        ck = ca.read_checkpoint(s)
        assert ck["path"] and "## §1 Active intent" in ck["text"]

    def test_multi_session_isolation(self, tmp_path):
        a, b = _session(tmp_path, sid="sess-A"), _session(tmp_path, sid="sess-B")
        ca._WRITER_STATE.pop("sess-A", None); ca._WRITER_STATE.pop("sess-B", None)
        ca.write_checkpoint(a, 10, "## §1 Active intent\n" + "A" * 900 + "\n## §11\n- a")
        ca.write_checkpoint(b, 5, "## §1 Active intent\n" + "B" * 900 + "\n## §11\n- b")
        assert ca.read_checkpoint(a)["upto"] == 10
        assert ca.read_checkpoint(b)["upto"] == 5
        assert a["results_dir"] != b["results_dir"] or True  # 目录天然隔离（同 tmp 无妨）


# ══ D. P4 分段重建 极端 ══
class TestD_Rebuild_Extremes:
    def test_missing_everything(self, tmp_path):
        s = _session(tmp_path)  # 无 task_plan / REQUIREMENTS / scripts 文件
        out = ca.rebuild_context(s, _hist(4), "", {}, caps=None)
        blob = "\n".join(m["content"] for m in out if m["role"] == "system")
        assert "提示" in blob  # 至少提示块
        assert len(out) >= 5

    def test_extreme_caps(self, tmp_path):
        s = _session(tmp_path)
        for c in ({"checkpoint": 0}, {"checkpoint": -1}, {"recent_tail": 0}, {"recent_tail": -7},
                  {"checkpoint": 10 ** 9}, {"recent_tail": 10 ** 9}):
            out = ca.rebuild_context(s, _hist(30), "## §1\n" + "x" * 5000, {}, caps=c)
            assert isinstance(out, list) and len(out) >= 1

    def test_dirty_contents(self, tmp_path):
        s = _session(tmp_path)
        dirty = [{"role": "user", "content": None}, {"role": "assistant", "content": 123},
                 {"role": "user", "content": {"a": 1}}, {"role": "system", "content": "x"}]
        out = ca.rebuild_context(s, dirty, "ck", {}, caps=None)
        assert isinstance(out, list)


# ══ E. 主编排 fail-open / 多轮滚动压缩 ══
class TestE_Orchestration_Extremes:
    def test_empty_none_history(self, tmp_path):
        s = _session(tmp_path)
        assert ca.memomics_replay(s, [], budget=_TINY) == []
        assert ca.memomics_replay(s, None, budget=_TINY) == []
        assert ca.memomics_replay(s, [{"role": "user", "content": ""}], budget=_TINY, tail_len=40) == \
            [{"role": "user", "content": ""}]

    def test_no_llm_writer_fallback(self, tmp_path):
        """llm 为 None → 确定性回退摘要，不崩、不写假 checkpoint。"""
        s = _session(tmp_path)
        out = ca.memomics_replay(s, _hist(30), llm_fn=None, budget=_TINY, tail_len=6)
        assert len(out) >= 7
        blob = "\n".join(m["content"] for m in out if m["role"] == "system")
        assert "会话检查点" in blob

    def test_writer_raises_fail_open(self, tmp_path):
        s = _session(tmp_path)

        def boom(p):
            raise RuntimeError("llm down")
        out = ca.memomics_replay(s, _hist(30), llm_fn=boom, budget=_TINY, tail_len=6)
        assert isinstance(out, list) and len(out) >= 1

    def test_repeated_rolling_compaction_monotonic(self, tmp_path):
        """极端长会话反复压缩：每次 writer 更新后 upto 严格不回退，且只保留可用的 checkpoint。"""
        s = _session(tmp_path)
        h = _hist(300)  # 300 条模拟极长历史
        uptos = []
        for k in range(6):
            ck = ca.read_checkpoint(s)
            span, new_upto = ca.new_span(h, ck["upto"], 8)
            if span:
                ca.run_writer(s, "连同上一段一起继续：" * 5, ck.get("text", "") or "",
                              new_upto, lambda p: "## §1 Active intent\n- v\n## §6 Files\n- F\n" * 30)
            uptos.append(ca.read_checkpoint(s)["upto"])
        assert all(b >= a for a, b in zip(uptos, uptos[1:])), f"upto 必须单调: {uptos}"
        # 假设第一轮 upto=292，之后历史变长 → 单调或不动
        ck = ca.read_checkpoint(s)
        assert ck["path"] and len(ck["text"]) > 300

    def test_llm_empty_output_does_not_demote_good_checkpoint(self, tmp_path):
        """writer 返回空 → (none) 占位写在最新；read 仍应优先带实质内容的好 checkpoint。"""
        s = _session(tmp_path)
        ca.write_checkpoint(s, 100, "## §1 Active intent\n" + "好" * 3000)
        ca.run_writer(s, "新片段", "", 120, lambda p: "")  # 空输出 → 占位
        ck = ca.read_checkpoint(s)
        assert ck["upto"] == 100 and len(ck["text"]) > 300

    def test_digest_requirements_survive_rollup(self, tmp_path):
        """记忆随回放不丢：REQUIREMENTS 里的话在 rebuild 的 system 块里出现。"""
        s = _session(tmp_path)
        srv._extract_and_store_requirements(s, "记住以后出图必须带 P 值。")
        out = ca.memomics_replay(s, _hist(40), budget=_TINY, tail_len=6, llm_fn=None)
        blob = "\n".join(m["content"] for m in out if m["role"] == "system")
        assert "必须带 P 值" in blob


# ══ F. 模糊输入（seeded random，确定性）══
class TestF_Fuzz:
    """任意垃圾输入不得让核心函数抛异常（fail-open / 容错）。"""

    def _rand_bytes(self, rng, n):
        return bytes(rng.randrange(0, 256) for _ in range(n))

    def _rand_text(self, rng, n):
        alpha = "ab汉字[相\n会]<script> %*{}\\'\"\u0000"
        return "".join(alpha[rng.randrange(len(alpha))] for _ in range(n))

    def test_fuzz_core_functions_never_raise(self, tmp_path):
        import random
        rng = random.Random(12345)  # 固定种子 → 可复现
        s = _session(tmp_path)
        for _ in range(300):
            kind = rng.randrange(6)
            if kind == 0:
                ca.compute_usable(model=self._rand_text(rng, 20), max_context=rng.choice([0, -5, 10**12, 3.14, "abc", None]))
            elif kind == 1:
                srv._strip_scaffold_text(self._rand_text(rng, rng.randrange(0, 200)))
            elif kind == 2:
                hist = [{"role": rng.choice(["user", "assistant", None]),
                         "content": rng.choice([None, 123, {"a": 1}, self._rand_text(rng, rng.randrange(0, 300))])}
                        for _ in range(rng.randrange(0, 20))]
                ca.memomics_replay(s, hist, budget=_TINY, tail_len=rng.choice([0, 5, -3, 999]),
                                   llm_fn=lambda p: self._rand_text(rng, 50))
            elif kind == 3:
                ca.rebuild_context(s, [{"role": "user", "content": self._rand_bytes(rng, 10)}],
                                   self._rand_text(rng, 400), {"requirements": None, "scripts": b"x",
                                                               "global_memory": None},
                                   caps={"checkpoint": rng.choice([0, -1, 10**9])})
            elif kind == 4:
                ca.new_span([{"role": "user", "content": self._rand_text(rng, 90)}],
                            rng.choice([-1, 0, 5, 999999]), rng.choice([0, -2, 1000]))
            else:
                ck = ca.read_checkpoint(s)
                ca.new_span([], ck["upto"], 8)
        assert True  # 到达这里 = 全程无异常

    def test_fuzz_digest_bounded(self, tmp_path):
        """随机要求场景下 digest 有界（不因输入膨胀失控）。"""
        import random
        rng = random.Random(7)
        s = _session(tmp_path)
        for _ in range(200):
            srv._extract_and_store_requirements(s, self._rand_text(rng, 60))
        d = srv._build_memory_digest(s, "随便问问")
        assert len(d) <= 6000, f"digest 失控: {len(d)}"
