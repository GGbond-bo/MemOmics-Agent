# -*- coding: utf-8 -*-
"""#2/#3 改造（2026-08-21）离线单测：
- #2 持久要求记忆：REQUIREMENTS.md 提取/去重/上限/digest 固定携带/rollup 同带
- #3 脚本落盘：scripts/ 清单提示
全部离线，不触发真实 memory_store 写入（autouse monkeypatch）。
"""
import os

import pytest

import server

pytestmark = [pytest.mark.unit, pytest.mark.memory]


@pytest.fixture(autouse=True)
def _no_real_memory_write(monkeypatch):
    import memomics.bio_tools.memory_bridge as mb
    monkeypatch.setattr(mb, "store_user_pref", lambda *a, **k: -1)


def _mk_session(tmp_path):
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    return {"id": "req-unit-test", "results_dir": str(tmp_path)}


class TestRequirementPersistence:
    def test_extract_path_and_requirement(self, tmp_path):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "以后做图必须带 P 值，数据路径 E:/骨骼肌锻炼/MF_AUCell_meta.csv。配色也统一一点。")
        p = os.path.join(str(tmp_path), "REQUIREMENTS.md")
        assert os.path.isfile(p)
        txt = open(p, encoding="utf-8").read()
        assert "必须带 P 值" in txt
        assert "E:/骨骼肌锻炼/MF_AUCell_meta.csv" in txt
        assert "统一" in txt

    def test_dedupe(self, tmp_path):
        s = _mk_session(tmp_path)
        for _ in range(3):
            server._extract_and_store_requirements(s, "记住输出必须带 P 值。")
        txt = open(os.path.join(str(tmp_path), "REQUIREMENTS.md"), encoding="utf-8").read()
        assert txt.count("必须带 P 值") == 1

    def test_read_requirements_paths(self, tmp_path):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "颜色统一。")
        server._extract_and_store_requirements(s, "路径 E:/data/x.csv 别忘了。")
        reqs = server._read_requirements(s, limit=8)
        assert reqs and any("E:/data/x.csv" in r for r in reqs)

    def test_digest_contains_requirements(self, tmp_path):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "记住每次出图都要带图注。")
        d = server._build_memory_digest(s, "随便")
        assert "会话要求" in d and "每次出图都要带图注" in d

    def test_chat_text_not_spam(self, tmp_path):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "你好呀")
        assert not os.path.isfile(os.path.join(str(tmp_path), "REQUIREMENTS.md"))

    def test_skip_assistant_directed_instructions(self, tmp_path):
        """回归(2026-08-21)：“发给助手的指令”不得污染持久要求。
        如自检消息('只用一句话回复…不要调用任何工具')带'不要/记住'本会命中标记，应被过滤；真要求照存。"""
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(
            s, "系统自检：只用一句话回复'通过'，不要调用任何工具。以后做图必须带 P 值。")
        txt = ""
        p = os.path.join(str(tmp_path), "REQUIREMENTS.md")
        if os.path.isfile(p):
            txt = open(p, encoding="utf-8").read()
        assert "只用一句话回复" not in txt, "助手指令不得入库"
        assert "不要调用任何工具" not in txt
        assert "必须带 P 值" in txt, "真正的用户要求应照存"

    def test_skip_question_sentences(self, tmp_path):
        """回归(压测发现 2026-08-21)：问句('你记得…吗?')即使含'记住/记得'也不是要求，不得入库。"""
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(
            s, "你记得本会话固定用的数据文件名是什么吗？记住数据文件在 data/gene_set_response_summary.csv。")
        txt = open(os.path.join(str(tmp_path), "REQUIREMENTS.md"), encoding="utf-8").read()
        assert "你记得本会话固定用的数据文件名是什么吗" not in txt, "问句不得入库"
        assert "gene_set_response_summary.csv" in txt, "陈述句要求应照存"

    def test_env_and_server_info_stored(self, tmp_path):
        """用户强调(2026-08-21)：服务器/环境情况(R版本、库路径)也要记入用户记忆([环境]节)。"""
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(
            s, "服务器上 R 是 4.5.3，库目录在 E:/R-libs/R-4.5.3。")
        txt = open(os.path.join(str(tmp_path), "REQUIREMENTS.md"), encoding="utf-8").read()
        assert "R-4.5.3" in txt and "R 是 4.5.3" in txt, "环境信息应入记忆"
        assert "R 是 4.5.3" in txt

    def test_confirm_marks_existing(self, tmp_path):
        """用户确认(2026-08-21)：'就用 E:/a.csv' → 已有条目标 (已确认)，下次以用户说明为主。"""
        s = _mk_session(tmp_path)
        p = str(tmp_path / "a.csv")
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        server._extract_and_store_requirements(s, f"数据文件是 {p}。")
        server._extract_and_store_requirements(s, f"就用 {p}，不用改。")
        txt = open(os.path.join(str(tmp_path), "REQUIREMENTS.md"), encoding="utf-8").read()
        assert "(已确认)" in txt, "确认过的条目应带标记"

    def test_digest_priority_strategy_line(self, tmp_path):
        """digest 应带执行策略：优先按用户说明执行+先核实。"""
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "记住数据文件在 E:/x.csv。")
        d = server._build_memory_digest(s, "随便")
        assert "优先按用户说明执行" in d and "先核实" in d, "digest 应含执行策略句"

    def test_confirmed_missing_path_strong_warning(self, tmp_path):
        """已确认但路径不存在 → 强警告(立即核实)。"""
        s = _mk_session(tmp_path)
        missing = os.path.join(str(tmp_path), "gone.csv")
        server._extract_and_store_requirements(s, f"数据文件是 {missing}，就用这个 (已确认)。")
        d = server._build_memory_digest(s, "随便")
        assert "已确认但路径不存在" in d, "已确认但缺失的路径应有强警告"

    def test_user_correction_removes_old(self, tmp_path):
        """用户纠正(2026-08-21)：'以前说必须带P值，其实改成带FDR' → 旧P值条目移除，新FDR条目在。"""
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "以后出图必须带 P 值。")
        server._extract_and_store_requirements(s, "其实以后出图改成带 FDR。")
        txt = open(os.path.join(str(tmp_path), "REQUIREMENTS.md"), encoding="utf-8").read()
        assert "P 值" not in txt, "被纠正的旧要求应移除"
        assert "FDR" in txt, "新要求应写入"

    def test_user_drop_removes(self, tmp_path):
        """用户作废(2026-08-21)：'那条 <路径> 的要求不用记了' → 旧条目移除。"""
        s = _mk_session(tmp_path)
        p = str(tmp_path / "data" / "a.csv")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        server._extract_and_store_requirements(s, f"记住固定数据文件在 {p}。")
        server._extract_and_store_requirements(s, f"那条 {p} 的要求不用记了。")
        txt = open(os.path.join(str(tmp_path), "REQUIREMENTS.md"), encoding="utf-8").read()
        assert "a.csv" not in txt, "已作废的要求应移除"

    def test_verify_warns_missing_path(self, tmp_path):
        """核实(2026-08-21)：要求里的路径不存在 → digest 带 ⚠️ 待核实标注；存在则无。"""
        # 会话1：只含不存在路径 → 有 ⚠️
        rd1 = str(tmp_path / "s1"); os.makedirs(rd1, exist_ok=True)
        s1 = {"id": "verify-1", "results_dir": rd1}
        missing = os.path.join(str(tmp_path), "data", "no_such_file.csv")
        server._extract_and_store_requirements(s1, f"记住数据文件在 {missing}。")
        d1 = server._build_memory_digest(s1, "随便")
        assert "⚠️" in d1 and "no_such_file.csv" in d1, "不存在的路径应被核实标注"
        # 会话2：只含存在路径 → 无 ⚠️
        rd2 = str(tmp_path / "s2"); os.makedirs(rd2, exist_ok=True)
        s2 = {"id": "verify-2", "results_dir": rd2}
        real = os.path.join(str(tmp_path), "data", "real.csv")
        os.makedirs(os.path.dirname(real), exist_ok=True)
        with open(real, "w", encoding="utf-8") as f:
            f.write("x")
        server._extract_and_store_requirements(s2, f"数据文件在 {real} 别忘了。")
        d2 = server._build_memory_digest(s2, "随便")
        # 注：digest 展示对行做 [:110] 截断，长 pytest 临时路径可能截掉文件名尾部 → 断言"行存在+无⚠️"
        assert "数据文件在" in d2 and "⚠️" not in d2, "存在的路径不应被标注"


class TestScriptsReuse:
    def test_scripts_digest_lists_existing(self, tmp_path):
        s = _mk_session(tmp_path)
        (tmp_path / "scripts" / "fig_v1.py").write_text("x", encoding="utf-8")
        (tmp_path / "scripts" / "fig_v2.R").write_text("y", encoding="utf-8")
        dig = server._build_scripts_digest(s, limit=5)
        assert "scripts/" in dig and ("fig_v1.py" in dig or "fig_v2.R" in dig)

    def test_scripts_digest_empty_when_none(self, tmp_path):
        s = _mk_session(tmp_path)
        assert server._build_scripts_digest(s, limit=5) == ""


class TestRollupCarriesRequirements:
    def test_checkpoint_has_requirements_section(self, tmp_path, monkeypatch):
        s = _mk_session(tmp_path)
        server._extract_and_store_requirements(s, "记住所有图必须用 CNS 配色。")
        hist = [{"role": "user", "content": f"消息 {i}"} for i in range(20)]
        monkeypatch.setenv("MEMOMICS_ROLLUP_BUDGET", "10")
        monkeypatch.setenv("MEMOMICS_ROLLUP_TAIL", "3")
        out = server._maybe_rollup_history(s, hist)
        assert any(m["role"] == "system" and "持久用户要求/路径" in m["content"] for m in out)
