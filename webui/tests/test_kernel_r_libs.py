# -*- coding: utf-8 -*-
"""持久 kernel 的 R 库路径必须和 check_env 看到的一样宽（只差版本过滤）。

真机事故 11c-go-9000 / memomics-6cb793a7：execute_r 里 clusterProfiler 报
"there is no package called 'clusterProfiler'"，而同一个包 check_env 找得到 ——
因为 kernel 的 _r_lib_env 只注入了 environment.json 的 lib_user 就 return 了。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (ROOT, os.path.join(ROOT, "hermes-agent")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.persistent_kernel import KernelPool  # noqa: E402


def _env():
    return KernelPool._r_lib_env(dict(os.environ))


def _libs(e):
    return [p for p in (e.get("R_LIBS") or "").split(os.pathsep) if p.strip()]


def test_主力库仍然是第一顺位():
    libs = _libs(_env())
    assert libs, "R_LIBS 不能为空（否则 worker 用 R 默认库，Seurat 之类全找不到）"
    assert "R-libs" in libs[0] or libs[0].endswith("library")


def test_不收别的R版本的库():
    """混进 4.4.2/4.6.1 的库 = 14-cellchat 那次「sp 是用 R 4.4.3 建造的」的成因。"""
    from memomics.bio_tools.env_check import _r_lib_env as domain_env
    ver = ""
    try:
        sec = KernelPool._env_json_r_section()
        d = sec.get("default", "") or ""
        if d:
            ver = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(d))))
    except Exception:
        ver = ""
    if not ver:
        pytest.skip("拿不到本机 R 版本，跳过")
    for p in _libs(_env()):
        assert ver in p, "kernel 的 R_LIBS 混进了非 %s 的库：%s" % (ver, p)
    for p in _libs(domain_env()):
        if ver not in p and p not in _libs(_env()):
            continue  # 领域层允许更宽，kernel 不许


def test_领域层找得到的同版本库_kernel也要有():
    """本用例就是事故本体：用户自建库里装的包，kernel 必须也能看到。"""
    from memomics.bio_tools.env_check import _r_lib_env as domain_env
    ver = ""
    try:
        sec = KernelPool._env_json_r_section()
        d = sec.get("default", "") or ""
        if d:
            ver = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(d))))
    except Exception:
        ver = ""
    if not ver:
        pytest.skip("拿不到本机 R 版本，跳过")
    k = _libs(_env())
    same_ver = [p for p in _libs(domain_env()) if ver in p]
    missing = [p for p in same_ver if p not in k]
    assert not missing, "同版本库没并进 kernel：%s" % missing
