# -*- coding: utf-8 -*-
"""桌面图标链路硬化（2026-10-13）。

用户反馈："换了节点后桌面图标点不开、启动.bat 正常"。根因是图标脚本
（scripts/launch_from_desktop.ps1）① 只看 netstat 端口占用（8899 被别的进程占了就误判
"已在运行"）② 端口写死 8899（服务自动换到 8890 后不跟）③ 失败静默。

本文件锁死硬化后的三条约束：
  * 只认 /api/health 返回 MemOmics 的监听；
  * 端口发现：runtime/port.txt → 环境变量 → 扫 8899..8909；
  * 失败写 log/desktop_launch.log 并弹提示框；
  * 保留原有"三层定位启动脚本"（ASCII start.bat / 中文名 / 内容特征）与 UTF-8 BOM。
"""
import os

import server

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAUNCHER = os.path.join(ROOT, "scripts", "launch_from_desktop.ps1")
ICON = os.path.join(ROOT, "scripts", "create_desktop_icon.ps1")


def _launcher_text() -> str:
    return open(LAUNCHER, "rb").read().decode("utf-8-sig")


def test_write_runtime_port_writes_port_file(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "MEMOMICS_HOME_DIR", str(tmp_path))
    server._write_runtime_port(8890)
    p = tmp_path / "runtime" / "port.txt"
    assert p.is_file(), "未写出 runtime/port.txt"
    assert p.read_text(encoding="utf-8").strip() == "8890"


def test_launcher_verifies_health_not_just_netstat():
    t = _launcher_text()
    assert "/api/health" in t, "必须用 /api/health 确认真是 MemOmics"
    assert "MemOmics" in t
    # 旧逻辑的裸 netstat 判断必须已移除（否则换节点后仍误判）
    assert "netstat -ano | Select-String" not in t, "残留旧的 netstat 判断"


def test_launcher_discovers_real_port():
    t = _launcher_text()
    assert "memomics_home\\runtime\\port.txt" in t, "必须优先读服务写下的真实端口"
    assert "8899..8909" in t, "必须扫描 8899..8909 兜底"
    assert "MEMOMICS_PORT" in t


def test_launcher_logs_and_pops_up_on_failure():
    t = _launcher_text()
    assert "desktop_launch.log" in t, "失败必须留痕"
    assert "Add-Content" in t
    assert "Popup" in t, "找不到启动脚本时要弹提示（不再静默）"


def test_launcher_keeps_three_layer_bat_detection():
    t = _launcher_text()
    assert "'start.bat'" in t, "① ASCII 名"
    assert "0x542F" in t, "② 中文名 启(0x542F)动.bat"
    assert "MemOmics-Agent" in t and "MEMOMICS_PORT" in t, "③ 内容特征兜底"


def test_launcher_has_bom_and_parses():
    raw = open(LAUNCHER, "rb").read()
    assert raw[:3] == b"\xef\xbb\xbf", "含中文的 .ps1 必须带 UTF-8 BOM（PS5.1 否则按 GBK 解析）"
    assert len(raw) > 1500


def test_icon_creator_links_to_launcher_with_bypass():
    t = open(ICON, "rb").read().decode("utf-8-sig")
    assert "launch_from_desktop.ps1" in t
    assert "-ExecutionPolicy Bypass" in t, "快捷方式必须显式 Bypass，避免策略拦下后静默失败"
    assert "Test-Path $launcher" in t