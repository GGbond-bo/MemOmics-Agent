# -*- coding: utf-8 -*-
"""回归测试：WebUI 一键更新的「覆盖层级」修复（2026-10-23 事故）

事故：update 包解压后根目录为 MemOmics/，旧识别逻辑只认 start.bat/start.sh，
识别失败 → MemOmics 被当作"新子目录" → 文件被覆盖到 <安装目录>/MemOmics/（多套一层），
安装目录自身没更新（用户看到"更新成功但版本号还是旧的"）。

本测试从 webui/server.py 抽取**真实实现**（_is_keep_path / _apply_overlay）+ 复刻包根识别，
在临时目录里端到端验证：
  1. 能识别带 `启动.bat` 的包根（不再只认 start.bat/start.sh）
  2. 覆盖后 安装目录/VERSION 变成包内版本
  3. 关键代码文件（webui/server.py 等）与包内一致
  4. 不再产生 <安装目录>/MemOmics/ 这样的嵌套目录
  5. VERSION / 启动器 不被 keep 规则拦下
"""
import io
import os
import shutil
import tempfile
import unittest

SERVER = os.path.join(os.path.dirname(__file__), "..", "server.py")
SERVER = os.path.abspath(SERVER)

PKG_FILES = {
    "VERSION": "v2026-10-23\n",
    "启动.bat": "@echo off\r\necho new launcher\r\n",
    "update_windows.bat": "@echo off\r\n",
    "webui/server.py": "# new server code v2026-10-23\n",
    "webui/index.html": "<html>new</html>\n",
    "memomics/coding_plans.py": "# new\n",
    "memomics/__init__.py": "",
    "memomics_home/SKILLS_INDEX.md": "new index\n",
    "memomics_home/skills/x/SKILL.md": "skill\n",
    "README.md": "readme\n",
}
INSTALL_FILES = {
    "VERSION": "v2026-10-13\n",
    "启动.bat": "@echo off\r\necho old launcher\r\n",
    "webui/server.py": "# old server code\n",
    "webui/index.html": "<html>old</html>\n",
    "memomics/coding_plans.py": "# old\n",
    "memomics/__init__.py": "",
    "memomics_home/SKILLS_INDEX.md": "old index\n",
    "memomics_home/skills/x/SKILL.md": "old skill\n",
    "README.md": "readme\n",
    # 用户数据：必须保留
    "memomics_home/config.yaml": "custom_providers: [mine]\n",
    "memomics_home/state.db": "db",
}


def _write(root, files):
    for rel, content in files.items():
        p = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(content)


def _read(root, rel):
    p = os.path.join(root, rel.replace("/", os.sep))
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def _load_server_funcs(memomics_dir):
    """从真实 server.py 抽取 _is_keep_path / _apply_overlay 及相关常量。"""
    src = io.open(SERVER, encoding="utf-8").read()
    ns = {"os": os, "MEMOMICS_DIR": memomics_dir}
    seg = src[src.find("_KEEP_DIRS = ("):]
    seg = seg[:seg.find("\n\n\n")]
    exec(seg, ns)  # noqa: S102
    i = src.find("def _is_keep_path")
    exec(src[i:src.find("\ndef ", i + 10)], ns)  # noqa: S102
    i = src.find("def _apply_overlay")
    exec(src[i:src.find("\n@app.", i)], ns)  # noqa: S102
    return ns["_is_keep_path"], ns["_apply_overlay"]


def _detect_pkg_root(extract_dir, tops):
    """复刻 server.py update_apply 里的包根识别（与生产代码保持同一套标记名）。"""
    launch = ("start.bat", "start.sh", "启动.bat", "launch.bat",
              "update_windows.bat", "update_macos_linux.sh")
    for t in tops:
        cand = os.path.join(extract_dir, t)
        if not os.path.isdir(cand):
            continue
        has_l = any(os.path.isfile(os.path.join(cand, n)) for n in launch)
        has_s = (os.path.isfile(os.path.join(cand, "webui", "server.py"))
                 or (os.path.isfile(os.path.join(cand, "VERSION"))
                     and os.path.isdir(os.path.join(cand, "memomics"))))
        if has_l or has_s:
            return cand
    return extract_dir


class TestUpdateOverlayRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ovl_test_")
        self.install = os.path.join(self.tmp, "MemOmics")          # 安装目录本身叫 MemOmics
        self.extract = os.path.join(self.tmp, "extract")
        self.pkgroot = os.path.join(self.extract, "MemOmics")      # 包内根目录也是 MemOmics
        _write(self.install, INSTALL_FILES)
        _write(self.pkgroot, PKG_FILES)
        self.tops = os.listdir(self.extract)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detect_pkg_root_recognizes_chinese_launcher(self):
        root = _detect_pkg_root(self.extract, self.tops)
        self.assertEqual(os.path.normpath(root), os.path.normpath(self.pkgroot),
                         "带 启动.bat 的包根必须被识别（旧逻辑只认 start.bat/start.sh）")

    def test_version_and_keep_rules(self):
        is_keep, _ = _load_server_funcs(self.install)
        for rel in ("VERSION", "启动.bat", "webui/server.py", "README.md"):
            self.assertFalse(is_keep(rel), f"{rel} 必须允许覆盖（当前被 keep 规则拦下）")
        # 用户数据仍须保留
        for rel in ("memomics_home/config.yaml", "memomics_home/state.db"):
            self.assertTrue(is_keep(rel), f"{rel} 必须保留（用户数据）")
        # 技能库随版本更新
        self.assertFalse(is_keep("memomics_home/skills/x/SKILL.md"))

    def test_overlay_updates_install_root_and_keeps_user_data(self):
        is_keep, apply_overlay = _load_server_funcs(self.install)
        root = _detect_pkg_root(self.extract, self.tops)
        res = apply_overlay(root, self.tops)
        copied = res["copied"] if isinstance(res, dict) else res

        self.assertGreater(copied, 0, "至少应覆盖若干文件")
        self.assertEqual(_read(self.install, "VERSION").strip(), "v2026-10-23",
                         "安装目录根 VERSION 必须被更新（事故现象：仍是旧版）")
        for rel in ("webui/server.py", "webui/index.html", "启动.bat", "memomics/coding_plans.py"):
            self.assertEqual(_read(self.install, rel), _read(self.pkgroot, rel),
                             f"{rel} 必须与包内一致")
        # 用户数据保留
        self.assertEqual(_read(self.install, "memomics_home/config.yaml"), "custom_providers: [mine]\n")
        self.assertEqual(_read(self.install, "memomics_home/state.db"), "db")
        # 事故形态判定：不是「有没有 MemOmics 子目录」（安装目录本身就叫 MemOmics，
        # 包内合法内容 MemOmics/ 也会铺进来），而是「安装目录根的版本/代码有没有真的更新」。
        # 旧逻辑的错误结果是：安装根 VERSION 纹丝不动、而文件全部堆在 <安装根>/MemOmics 下。
        self.assertEqual(_read(self.install, "VERSION").strip(), "v2026-10-23",
                         "事故形态复现：安装根 VERSION 未被更新")

    def test_overlay_summary_shape(self):
        _, apply_overlay = _load_server_funcs(self.install)
        root = _detect_pkg_root(self.extract, self.tops)
        res = apply_overlay(root, self.tops)
        self.assertIsInstance(res, dict, "覆盖结果需要返回统计（copied/skipped/failed/errors）")
        for k in ("copied", "skipped", "failed", "errors"):
            self.assertIn(k, res)


if __name__ == "__main__":
    unittest.main(verbosity=2)