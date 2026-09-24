# -*- coding: utf-8 -*-
"""check_env 的语言判定：R 里装了的包，不能因为在 Python 里 import 不到就被判 missing。

真实案例（2026-09-24，会话 memomics-ccdd8647）：聚类步骤 rail_review(pre) 传了
required_packages=[Seurat, harmony, ggplot2, patchwork, cluster]，check_env 返回
missing={"cluster": "R"}、should_proceed=false，把执行拦了两次；而 R 里
requireNamespace("cluster") 一直是 TRUE（R 基础推荐包，就在 E:/R-libs/R-4.5.3/cluster）。
根因：language 默认 "both" 时，凡是不在 PYTHON_PACKAGES_BIO / R_PACKAGES_BIO 名单里的
名字会被两种语言各查一遍 —— R 查到了进 installed，Python import 不到又进 missing，
rail_review 只认 missing 就会误拦。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from memomics.bio_tools import env_check as ec  # noqa: E402


def _isolate(monkeypatch, r_status, py_status, cache=None):
    monkeypatch.setattr(ec, "_ENV_CACHE", {"packages": dict(cache or {}), "paths": {}, "cached_at": 1}, raising=False)
    monkeypatch.setattr(ec, "_save_env_cache", lambda: None)
    monkeypatch.setattr(ec, "_check_r_packages", lambda pkgs: {p: r_status.get(p, False) for p in pkgs})
    monkeypatch.setattr(ec, "_check_python_packages", lambda pkgs: {p: py_status.get(p, False) for p in pkgs})
    monkeypatch.setattr(ec, "_install_r_package", lambda pkg: False)
    monkeypatch.setattr(ec, "_install_python_package", lambda pkg: False)


def test_r_only_package_not_flagged_missing(monkeypatch):
    """cluster 这种没登记在名单里的 R 包：R 里装了就算装了。"""
    _isolate(monkeypatch, {"cluster": True, "Seurat": True}, {"cluster": False})
    r = ec.check_env(["cluster", "Seurat"], auto_install=False)
    assert "cluster" not in r["missing"], r
    assert r["installed"]["cluster"] == "R"


def test_truly_missing_package_still_reported(monkeypatch):
    """两种语言都没有，才该进 missing（而且不能顺便把装了的包也列进去）。"""
    _isolate(monkeypatch, {"cluster": True, "GhostPkg": False}, {"GhostPkg": False})
    r = ec.check_env(["cluster", "GhostPkg"], auto_install=False)
    assert "GhostPkg" in r["missing"], r
    assert "cluster" not in r["missing"], r


def test_installed_and_missing_never_overlap(monkeypatch):
    """不变式：同一个包不许既 installed 又 missing —— rail_review 只看 missing。"""
    _isolate(monkeypatch, {"cluster": True}, {"cluster": False})
    r = ec.check_env(["cluster"], auto_install=False)
    assert not (set(r["installed"]) & set(r["missing"])), r


def test_python_only_package_checked_as_python(monkeypatch):
    """登记在 Python 名单里的包走 Python 检查，别被 R 分支吞掉。"""
    _isolate(monkeypatch, {"scanpy": False}, {"scanpy": True})
    r = ec.check_env(["scanpy"], auto_install=False)
    assert r["installed"].get("scanpy") == "Python", r
    assert "scanpy" not in r["missing"], r


def test_explicit_language_r_ignores_python(monkeypatch):
    """language="R" 时不查 Python（11:10 那次补救就是这个写法）。"""
    _isolate(monkeypatch, {"cluster": True}, {"cluster": False})
    r = ec.check_env(["cluster"], language="R", auto_install=False)
    assert r["installed"]["cluster"] == "R" and not r["missing"], r


def test_cache_hit_returns_installed(monkeypatch):
    """命中 24h 缓存就不再探测。"""
    _isolate(monkeypatch, {}, {}, cache={"cluster": "R"})
    r = ec.check_env(["cluster"], auto_install=False)
    assert r["installed"]["cluster"] == "R" and not r["missing"], r
