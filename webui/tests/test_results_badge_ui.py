# -*- coding: utf-8 -*-
"""「分析结果栏红色提醒」—— 2026-10-23（用户要求）。

用户原话（要点）：分析的时候出图了，在「分析结果栏」标记显眼的红色提醒标识；
用户点击之后就消失，有新结果就出现红色提醒标注；只显示当前会话的结果
（两个会话都有结果时，分析结果栏只提醒当前会话的结果）。

验证：
1) 静态：侧栏「📊 分析结果」带红点容器与样式；出图/结果刷新/切会话/点开结果栏四处接线；
   中英文案；基线按会话持久化（localStorage）。
2) 行为：webui/tests/results_badge_frontend.cjs（抠真实角标函数 + 桩 localStorage/document）。
"""
import os
import shutil
import subprocess

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TESTS_DIR))
INDEX = os.path.join(REPO, "webui", "index.html")
SERVER = os.path.join(REPO, "webui", "server.py")

with open(INDEX, encoding="utf-8") as _f:
    HTML = _f.read()
with open(SERVER, encoding="utf-8") as _f:
    SERVER_SRC = _f.read()


class TestWiring:
    def test_nav_markup(self):
        assert 'id="nav-results-badge"' in HTML
        assert 'class="nav-red-badge"' in HTML
        # ⚠️ 侧栏文字会随语言重写 textContent → 文字必须在子 span 上，红点才不会被抹掉
        assert '<span data-i18n="nav_results">📊 分析结果</span><span class="nav-red-badge"' in HTML

    def test_css(self):
        assert ".nav-red-badge { display:inline-block;" in HTML
        assert ".nav-item.has-red-badge" in HTML

    def test_hooks(self):
        # 点开「分析结果」→ 红点消失
        assert "if (view === 'results') { _rsBadgeClear(); refreshResults(); }" in HTML
        # 切会话 → 先立基线、再按本会话重画
        assert "_rsBadgeEnsure(sid);" in HTML
        assert "refreshResults();\n  _rsBadgeScan" not in HTML  # 顺序：scan 在 refresh 内部，不是这里
        # 结果刷新 → 按 mtime 重算（只算当前会话；目录/子目录口径写死）
        assert "_rsBadgeScan(_lastFigItems, (currentPath.results ? [] : _lastResultItems));" in HTML
        # 出图事件 → 老图/回放不点亮（防「刚发问就亮」）；真新图才提醒（只提醒当前会话）
        assert "var _figIsOld = msg._replay || _rsFigKnown((msg.figure && msg.figure.name) || '') || _rsFigLooksOld(msg.figure);" in HTML
        assert "_rsBadgeNoteNewFigure(msg.figure, false);" in HTML

    def test_i18n(self):
        assert "'rs_badge_new':'有 {0} 个新分析结果，点击查看'" in HTML
        assert "'rs_badge_new':'{0} new analysis result(s) — click to view'" in HTML

    def test_baseline_is_per_session(self):
        assert "function _rsSeenKey(sid) { return 'memomics_res_seen_' + sid; }" in HTML
        assert "localStorage.setItem(_rsSeenKey(sid), String(ts))" in HTML


class TestFindNewAfterClick:
    """点开红点之后找得到「新更新的文件」：点开瞬间冻结清单 + 红色「新」标 + 一键筛选。"""

    def test_chip_and_markup(self):
        assert 'id="sort-new"' in HTML
        assert 'onclick="toggleNewFilter()"' in HTML
        assert ".sort-chip.new-chip" in HTML and ".file-new-tag" in HTML and ".fig-new-tag" in HTML
        assert ".file-item.file-new-item" in HTML and ".fig-thumb.fig-new-item" in HTML

    def test_batch_freeze_on_clear(self):
        assert "var _rsNewKeys = {};" in HTML
        assert "var _rsJustNew = {};" in HTML
        assert "var keys = _rsNewKeys[currentSid] || { files: [], figs: [] };" in HTML
        assert "_rsJustNewSave(currentSid);" in HTML
        assert "memomics_res_justnew_" in HTML

    def test_row_and_figure_marks(self):
        assert "var isNew = !f.is_dir && _rsJustNewHas(currentSid, 'file', f.path);" in HTML
        assert "var _isNewFig = _rsJustNewHas(currentSid, 'fig', f.name);" in HTML
        assert "file-new-item" in HTML and "fig-new-item" in HTML

    def test_filter(self):
        assert "function toggleNewFilter() {" in HTML
        assert "function _rsNewFilterOn() { return _showNewOnly && _rsJustNewCount() > 0; }" in HTML
        assert "if (_rsNewFilterOn()) out = out.filter(function(f) { return f.is_dir || _rsJustNewHas(currentSid, 'file', f.path); });" in HTML
        assert "var figsShown = _rsNewFilterOn() ? figs.filter(function(f) { return _rsJustNewHas(currentSid, 'fig', f.name); }) : figs;" in HTML

    def test_view_clears_and_decrements(self):
        # 点开看过一个 → 该项红色标识恢复正常；标记条数字同步减一
        assert "function _rsJustNewClearItem(kind, key) {" in HTML
        assert "if (host === 'results' && _rsJustNewClearItem('file', path)) {" in HTML
        assert "if (_rsJustNewClearItem('fig', name)) { _lastFiguresSig = ''; _renderSortBar(); loadFigures(); }" in HTML
        assert "if (_rsJustNewClearItem('fig', f.name)) { _lastFiguresSig = ''; _renderSortBar(); loadFigures(); }" in HTML
        assert "var newN = _rsJustNewCount();" in HTML
        assert "newEl.textContent = tf('rs_new_chip', newN);" in HTML

    def test_i18n(self):
        assert "'rs_new_chip':'🆕 最新文件 {0}'" in HTML
        assert "'rs_new_tag':'新'" in HTML
        assert "'rs_new_none':'这一层没有新的更新。'" in HTML
        assert "'rs_new_chip':'🆕 Latest files: {0}'" in HTML


class TestFakeNewFigureGuard:
    """用户反馈：刚发问就提示「有新的结果」，点开却没有 —— 两类假新图必须拦住。"""

    def test_old_figure_gates(self):
        assert "function _rsFigKnown(name) {" in HTML
        assert "function _rsFigLooksOld(fig) {" in HTML
        assert "function _rsBadgeNoteNewFigure(fig, replay) {" in HTML

    def test_event_branch_skips_old_and_replay(self):
        assert "if (!_figIsOld) {" in HTML
        assert "handleNewFigure(msg.figure);" in HTML

    def test_server_stops_resending_old_figures(self):
        # 每轮起始先把磁盘上已有的图登记为「已知」（否则每轮第一次扫描会把老图当新图重发）
        assert "_kf_base" in SERVER_SRC
        assert "上一轮/历史的图当「新图」重发" in SERVER_SRC


class TestHarness:
    def test_frontend_harness(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("本机没有 node")
        r = subprocess.run([node, os.path.join(TESTS_DIR, "results_badge_frontend.cjs")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        assert "0 fail" in out, out[-3000:]
        assert r.returncode == 0, out[-3000:]