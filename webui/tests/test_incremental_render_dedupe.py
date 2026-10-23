# -*- coding: utf-8 -*-
"""交互框增量渲染「重复输出」回归（2026-10-23，真机会话 memomics-f3cbef42）。

用户报告：长任务跑到一半，「交互框输出的内容一直在重复」—— 同一个回答气泡里，
早先的过程叙述被更长的版本一遍遍盖在下面，粘贴出来是层层包含的多份（实测 4 份）。

根因：`renderBubbleIncremental()` 在一次「内容没变」的渲染里（切会话重挂载
liveBubble / 节流定时器 flush / 进度重放）执行 `state.segs = segs`，而 `segs` 是
`splitMsgBlocks()` 现切出来、不带 `.node` 引用的新对象 → 之后的删除循环拿
`state.segs[r].node === undefined` 跳过删除，旧节点留在 DOM、新节点又追加进来
→ 同一段文字越积越多（实测 30 轮流式更新能膨胀到 11 份）。

修法（webui/index.html · renderBubbleIncremental）：
  ① 未变化的段继承（或按位置补回）node 引用；
  ② DOM 子节点数与 state.segs 失配（历史残留副本）→ 清空整块按当前文本重建；
  ③ 快照恢复回来的气泡（DOM 有渲染块、但没有 JS 状态）→ 复用它，不新挂第二个块。

本文件：① 静态约束（修法必须在）；② 行为测试走 incremental_render_frontend.cjs
（抠真实函数 + 桩 DOM，含事故时序复现）。
"""
import os
import shutil
import subprocess

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TESTS_DIR))
INDEX = os.path.join(REPO, "webui", "index.html")
HARNESS = os.path.join(TESTS_DIR, "incremental_render_frontend.cjs")

with open(INDEX, encoding="utf-8") as _f:
    HTML = _f.read()


class TestIncrementalRenderStatic:
    def test_renderer_exists(self):
        assert "function renderBubbleIncremental(bubble, text) {" in HTML

    def test_node_refs_preserved_on_unchanged_render(self):
        """未变化的段必须继承（或按位置补回）node 引用，否则后续删不掉旧节点。"""
        assert "segs[k].node = state.segs[k].node || kids[k] || null;" in HTML

    def test_desync_rebuilds_body(self):
        """DOM 子节点数与 state.segs 失配（历史残留副本）→ 清空整块重建。"""
        assert "state.content.children.length !== state.segs.length" in HTML
        assert "state.content.innerHTML = '';" in HTML

    def test_removal_has_position_fallback(self):
        """删除循环不能只信 node 引用（引用可能缺失）——按位置兜底。"""
        assert "var oldNode = state.segs[r].node || kids[r] || null;" in HTML

    def test_restored_body_is_reused(self):
        """快照恢复的气泡里已有渲染块 → 复用，不新挂第二个（否则旧内容留在上面）。"""
        assert "if (_pre) {" in HTML
        assert "_pre.innerHTML = ''; state.content = _pre;" in HTML

    def test_finalized_bubble_not_rerendered(self):
        """已「过程/结论分层」收尾的气泡（折叠块 + 结论，无渲染块）→ 直接放弃渲染。"""
        assert "else if (bubble.querySelector('.proc-block')) {" in HTML

    def test_restore_heals_duplicated_body(self):
        """恢复画面时：渲染块子节点数 ≠ 应有段数（历史副本）→ 立刻按全文重建一次。"""
        assert "var _healBody = currentBubble ? currentBubble.querySelector('.md-incremental-body') : null;" in HTML
        assert "_healBody.children.length !== splitMsgBlocks(fullText).length" in HTML

    def test_harness_uses_real_functions(self):
        """harness 必须抠真实函数跑，而不是重写一份逻辑。"""
        with open(HARNESS, encoding="utf-8") as f:
            src = f.read()
        assert "grab('renderBubbleIncremental')" in src
        assert "grab('splitMsgBlocks')" in src


class TestIncrementalRenderHarness:
    def test_harness_passes(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("本机没有 node")
        r = subprocess.run([node, HARNESS], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
        assert "0 fail" in (r.stdout or ""), r.stdout