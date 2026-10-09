# -*- coding: utf-8 -*-
"""远端通配符展开助手（`_REMOTE_GLOB_PY`）的守卫测试 —— 2026-10-09。

事故：ssh23 上 `python` 是 **Python 2.7.5**（没有 python3），而助手原来写成
`[print(...) for p in ps]` —— py2 里 print 是语句，列表推导里直接 SyntaxError，于是
「pull/locate 带通配符」整条路报「远端没找到」（看起来像路径问题，其实是脚本没跑起来）。

这层测三件事：
1. 助手代码只含 py2/py3 都合法的写法（不许出现 print( 调用、f-string、async 等 py3 专属）；
2. **真跑**：用本机 python 执行同一个常量 + 同一套参数拼法，断言它按 `D/F:字节:路径` 输出；
3. 解析侧：喂 canned 远端输出（含目录行/文件行/垃圾行）给 `_locate_remote_glob`，断言 hits/errors 正确。
"""
import importlib.util
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
RC_PATH = os.path.join(REPO, "memomics", "bio_tools", "remote_cluster.py")

PY3 = sys.executable or shutil.which("python")
PY2 = shutil.which("python2") or shutil.which("python2.7")


def _load_rc():
    """按路径加载 remote_cluster（绕开包 __init__，和 test_large_cache 同一套路）。"""
    spec = importlib.util.spec_from_file_location("remote_cluster_glob_under_test", RC_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_helper_code_is_python2_safe():
    rc = _load_rc()
    code = rc._REMOTE_GLOB_PY
    assert "print(" not in code, "远端 python 可能只有 2.7：不能出现 print( 调用"
    assert "sys.stdout.write(" in code, "输出应走 sys.stdout.write（py2/py3 都合法）"
    assert "f'" not in code and 'f"' not in code, "不许用 f-string（py2 没有）"
    # py3 语法自证
    compile(code, "<remote-glob>", "exec")
    # 命令里 python3 优先、python 兜底（ssh23 只有 py2），且失败会报错不静默
    cmd_src = open(RC_PATH, encoding="utf-8").read()
    i = cmd_src.index("def _locate_remote_glob")
    j = cmd_src.index("for PY in python3 python", i)
    assert j > i
    assert "$PY -c '%s' %s && break" in cmd_src[i:i + 1200]


@pytest.mark.skipif(not PY3, reason="没有可用的 python 解释器")
def test_helper_runs_and_prints_machine_readable_lines(tmp_path):
    """真跑一遍常量：同一套 argv 拼法（shell 里带引号的 glob 由 python 展开）。"""
    rc = _load_rc()
    (tmp_path / "r-a_01.png").write_bytes(b"x" * 11)
    (tmp_path / "r-a_02.png").write_bytes(b"y" * 7)
    (tmp_path / "sub").mkdir()
    args = [str(tmp_path / "*.png"), str(tmp_path / "sub")]
    r = subprocess.run([PY3, "-c", rc._REMOTE_GLOB_PY] + args,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, "助手脚本本身跑挂了：%s" % r.stderr
    lines = [ln for ln in r.stdout.strip().splitlines() if ln]
    assert len(lines) == 3, lines
    kinds = {}
    for ln in lines:
        k, size, path = ln.split(":", 2)
        kinds[os.path.basename(path)] = (k, int(size))
    assert kinds["r-a_01.png"] == ("F", 11)
    assert kinds["r-a_02.png"] == ("F", 7)
    assert kinds["sub"][0] == "D", "目录行要以 D 开头"
    assert sorted(p for _, _, p in (ln.split(":", 2) for ln in lines)) == sorted(
        [str(tmp_path / "r-a_01.png"), str(tmp_path / "r-a_02.png"), str(tmp_path / "sub")])


@pytest.mark.skipif(not PY2, reason="本机没有 python2，跳过 py2 实测（ssh23 上靠 run 动作验收）")
def test_helper_actually_parses_under_python2(tmp_path):
    """本机有 py2 就真上一遍：py2 里 const 必须能编译+跑。"""
    rc = _load_rc()
    (tmp_path / "f1.png").write_bytes(b"z" * 5)
    r = subprocess.run([PY2, "-c", rc._REMOTE_GLOB_PY, str(tmp_path / "*.png")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, "py2 下助手脚本语法/运行错误：%s" % r.stderr
    assert r.stdout.strip().startswith("F:5:"), r.stdout


def test_locate_remote_glob_parses_canned_output(monkeypatch):
    """解析侧：py2 输出（含目录行与一行垃圾）要能吃下，垃圾进 errors 不进 hits。"""
    rc = _load_rc()
    canned = {
        "output": "F:17435:/s/plots/r-1_01.png\n"
                  "D:0:/s/plots/sub\n"
                  "F:500582:/s/plots/r-2_01.png\n"
                  "SyntaxError: invalid syntax\n",
        "exit_code": 0,
    }
    monkeypatch.setattr(rc, "_exec_env", lambda conn, cmd, timeout=60: canned)
    out = {"hits": [], "errors": []}
    rc._locate_remote_glob(None, ["/s/plots/*.png"], out)
    assert [h["path"] for h in out["hits"]] == ["/s/plots/r-1_01.png", "/s/plots/sub",
                                                "/s/plots/r-2_01.png"]
    assert out["hits"][0]["bytes"] == 17435 and out["hits"][1]["kind"] == "dir"
    assert any("SyntaxError" in e for e in out["errors"]), "远端报错要如实进 errors"


def test_locate_remote_glob_survives_py2_syntax_error(monkeypatch):
    """回归：老写法在 py2 上 SyntaxError 时，必须把远端理由带回来（不能再只说「没找到」）。"""
    rc = _load_rc()
    canned = {"output": 'File "<string>", line 1\nSyntaxError: invalid syntax\n', "exit_code": 0}
    monkeypatch.setattr(rc, "_exec_env", lambda conn, cmd, timeout=60: canned)
    out = {"hits": [], "errors": []}
    rc._locate_remote_glob(None, ["/x/*.png"], out)
    assert out["hits"] == []
    assert out["errors"], "远端错误没被带回来（用户会以为是路径写错了）"