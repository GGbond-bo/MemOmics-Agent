# -*- coding: utf-8 -*-
"""回归测试：更新包只覆盖代码，用户私有数据一律保留（2026-10-24 用户要求）

模拟一个装满私有数据的安装目录，用合成的 update 包（结构与真实包一致）跑真实
_apply_overlay，核验：
  1. 私有数据逐字节未变：配置(含各家 key) / 记忆 / 会话库 / 知识库 / 文献 / 分析结果 /
     DCS·集群配置 / 微信账号 / 日志 / .env
  2. 代码被更新：VERSION、webui/server.py、memomics/coding_plans.py
  3. 技能库随版本更新；结果目录不被触碰
  4. 无「多套一层」事故形态
"""
import hashlib
import io
import os
import shutil
import tempfile
import unittest

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server.py"))

USER_FILES = {
    "memomics_home/config.yaml": "custom_providers:\n  - id: mine\n    api_key: sk-my-secret\n",
    "memomics_home/provider_keys.json": '{"opencode-go": {"api_key": "oc_sk_secret"}}\n',
    "memomics_home/model_config.json": '{"model": "m1"}\n',
    "memomics_home/state.db": "SQLITE-FAKE\x00\x01",
    "memomics_home/memories/note.md": "# 我的记忆\n",
    "memomics_home/sessions/s1.json": '{"私密": true}\n',
    "memomics_home/papers/paper1.pdf": "PDF-FAKE\n",
    "memomics_home/papers/index.json": '{"papers": 1}\n',
    "memomics_home/references.json": '{"refs": ["我的文献"]}\n',
    "memomics_home/dcs_cloud.json": '{"pat": "dcs_pat_x"}\n',
    "memomics_home/cluster_envs.json": '{"hosts": ["h"]}\n',
    "memomics_home/weixin_account.json": '{"wxid": "w"}\n',
    "memomics/knowledge_base/Homo_sapiens/aging/x.md": "# 我的知识库\n",
    "results/s1/report.md": "# 我的结果\n",
    "log/server.log": "logs\n",
    ".env": "SECRET=1\n",
}
CODE_FILES = {"VERSION": "v2026-10-13\n", "webui/server.py": "# OLD\n"}
PKG_FILES = {
    "VERSION": "v2026-10-24\n",
    "webui/server.py": "# NEW\n",
    "memomics/coding_plans.py": "# NEW\n",
    "启动.bat": "@echo off\r\nREM NEW\r\n",
    "memomics_home/skills/x/SKILL.md": "new skill\n",
}


def _md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _write(root, files):
    for rel, content in files.items():
        p = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, "w", encoding="utf-8", newline="").write(content)


def _load(memomics_dir):
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


class TestUpdateKeepsUserData(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="keep_test_")
        self.install = os.path.join(self.tmp, "MemOmics")
        self.pkg = os.path.join(self.tmp, "pkg", "MemOmics")
        _write(self.install, USER_FILES)
        _write(self.install, CODE_FILES)
        _write(self.pkg, PKG_FILES)
        self.tops = ["MemOmics"]
        self.before = {r: _md5(os.path.join(self.install, r.replace("/", os.sep))) for r in USER_FILES}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_user_data_survives_and_code_updates(self):
        _, apply_overlay = _load(self.install)
        res = apply_overlay(self.pkg, self.tops)
        copied = res["copied"] if isinstance(res, dict) else res
        self.assertGreater(copied, 0)

        # 1) 私有数据逐字节未变
        for rel, before in self.before.items():
            after = _md5(os.path.join(self.install, rel.replace("/", os.sep)))
            self.assertEqual(after, before, f"私有数据被更新覆盖了：{rel}")

        # 2) 代码已更新
        for rel in ("VERSION", "webui/server.py", "memomics/coding_plans.py"):
            d = os.path.join(self.install, rel.replace("/", os.sep))
            s = os.path.join(self.pkg, rel.replace("/", os.sep))
            self.assertEqual(_md5(d), _md5(s), f"{rel} 未被更新")

        # 3) 技能库随版本更新（属于产品内容）
        sk = os.path.join(self.install, "memomics_home", "skills", "x", "SKILL.md")
        self.assertEqual(io.open(sk, encoding="utf-8").read(), "new skill\n")

    def test_keep_rules_for_private_paths(self):
        is_keep, _ = _load(self.install)
        must_keep = [
            "memomics_home/config.yaml", "memomics_home/provider_keys.json",
            "memomics_home/state.db", "memomics_home/memories/note.md",
            "memomics_home/sessions/s1.json", "memomics_home/papers/paper1.pdf",
            "memomics_home/references.json", "memomics_home/dcs_cloud.json",
            "memomics_home/cluster_envs.json", "memomics_home/weixin_account.json",
            "memomics/knowledge_base/Homo_sapiens/aging/x.md",
            "results/s1/report.md", ".env",
        ]
        for rel in must_keep:
            self.assertTrue(is_keep(rel), f"{rel} 必须保留（用户私有数据）")
        must_update = ["webui/server.py", "memomics/coding_plans.py", "VERSION",
                       "memomics_home/skills/x/SKILL.md", "启动.bat"]
        for rel in must_update:
            self.assertFalse(is_keep(rel), f"{rel} 必须允许更新")


if __name__ == "__main__":
    unittest.main(verbosity=2)