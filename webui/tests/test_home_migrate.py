# -*- coding: utf-8 -*-
"""hermes_home → memomics_home 覆盖升级迁移回归（2026-10-08 改名配套）。

锁死六条不变量：
1. 首次安装（无 hermes_home）→ noop，绝不碰文件系统；
2. 只有 hermes_home（既有安装）→ 整体改名，数据原地保留；
3. 双存在 + 新目录是产品空壳（更新包/fix_bundle 先造出来的）→ 缺失项搬进新目录，
   重名文件保留新目录版本（＝覆盖升级语义），旧目录退休为 .migrated_ 备份（不是删除）；
4. 双存在 + 两边都有用户数据 → 只返回 conflict，不动任何文件（防误合并）；
5. 检测依据是用户数据标记（config.yaml/state.db/memories/.install_path 等），
   单靠 .fix_bundle 之类运行标记不算"既有安装的数据"；
6. update_apply 在 _apply_overlay 之前调用同一迁移（源码级护栏，「先迁移、再覆盖」）。
"""
import os

import server

MIG = server.migrate_legacy_home


def _write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_first_install_noop_never_touches_fs(tmp_path):
    """首次安装：只有包内产品文件的新目录 → noop，不创建任何东西。"""
    new = tmp_path / "memomics_home"
    _write(str(new / "SOUL.md"))
    _write(str(new / "skills" / "demo" / "SKILL.md"))
    before = sorted(p.name for p in tmp_path.iterdir())
    assert MIG(str(new), str(tmp_path / "hermes_home")) == "noop"
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_rename_when_only_legacy_with_data(tmp_path):
    old = tmp_path / "hermes_home"
    _write(str(old / "config.yaml"), "plugins: {}\n")
    _write(str(old / "state.db"), "db")
    new = tmp_path / "memomics_home"
    assert MIG(str(new), str(old)) == "renamed"
    assert (new / "config.yaml").is_file() and (new / "state.db").is_file()
    assert not old.exists()


def test_merge_when_new_is_product_shell(tmp_path):
    old = tmp_path / "hermes_home"
    new = tmp_path / "memomics_home"
    _write(str(old / "config.yaml"), "cfg")
    _write(str(old / "memories" / "MEMORY.md"), "m")
    _write(str(old / "skills" / "mine" / "SKILL.md"), "user-skill")
    _write(str(old / "skills" / "product" / "SKILL.md"), "old-product")
    _write(str(old / ".fix_bundle"), "2026-08-16")  # 运行标记：不算数据，但会被搬走
    # 产品空壳：更新包铺进来的新目录
    _write(str(new / "skills" / "product" / "SKILL.md"), "new-product")
    _write(str(new / "SOUL.md"), "soul")
    res = MIG(str(new), str(old))
    assert res.startswith("merged:")
    assert (new / "config.yaml").read_text(encoding="utf-8") == "cfg"
    assert (new / "memories" / "MEMORY.md").is_file()
    assert (new / "skills" / "mine" / "SKILL.md").read_text(encoding="utf-8") == "user-skill"
    # 重名文件：新版赢（= 覆盖升级语义）
    assert (new / "skills" / "product" / "SKILL.md").read_text(encoding="utf-8") == "new-product"
    assert (new / "SOUL.md").is_file()
    # 旧目录退休为备份（不是删除），备份里只剩重名项
    left = list(tmp_path.glob("hermes_home.migrated_*"))
    assert len(left) == 1 and left[0].is_dir()
    assert (left[0] / "skills" / "product" / "SKILL.md").is_file()


def test_conflict_when_both_have_user_data(tmp_path):
    old = tmp_path / "hermes_home"
    new = tmp_path / "memomics_home"
    _write(str(old / "config.yaml"))
    _write(str(new / "state.db"))
    before_old = sorted(p.name for p in old.iterdir())
    before_new = sorted(p.name for p in new.iterdir())
    assert MIG(str(new), str(old)) == "conflict"
    assert sorted(p.name for p in old.iterdir()) == before_old
    assert sorted(p.name for p in new.iterdir()) == before_new
    assert not list(tmp_path.glob("hermes_home.migrated_*"))


def test_marker_detection_rules(tmp_path):
    """.install_path 算既有安装标记；只有 .fix_bundle 的空壳不算数据。"""
    old = tmp_path / "hermes_home"
    _write(str(old / ".fix_bundle"), "x")
    assert server._home_has_user_data(str(old)) is False
    _write(str(old / ".install_path"), "E:/MemOmics")
    assert server._home_has_user_data(str(old)) is True


def test_update_apply_migrates_before_overlay():
    """「先迁移、再覆盖」源码级护栏：迁移调用必须出现在 overlay 之前。"""
    src = open(os.path.join(os.path.dirname(server.__file__), "server.py"), encoding="utf-8").read()
    i = src.index("async def update_apply")
    j = src.index("_apply_overlay(extract_root, tops)", i)
    seg = src[i:j]
    assert "migrate_legacy_home(MEMOMICS_HOME_DIR, _legacy_home)" in seg
    assert "检测到覆盖升级" in seg