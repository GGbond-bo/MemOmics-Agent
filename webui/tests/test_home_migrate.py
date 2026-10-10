# -*- coding: utf-8 -*-
"""hermes_home → memomics_home 覆盖升级迁移回归（2026-10-08 改名配套）。

锁死八条不变量（2026-10-10 数据安全加固后）：
1. 首次安装（无 hermes_home）→ noop，绝不碰文件系统；
2. 只有 hermes_home（既有安装）→ 整体改名，数据原地保留；
3. 双存在 + 新目录是产品空壳（更新包/启动器先造出来的）→ 先安全并入再退休旧目录；
   重名文件保留新目录版本；旧版仍在退休目录里（零丢失），但不再另存上千个 .from_hermes_ 备份；
4. 双存在 + 两边都有用户数据 → **不再只告警**：安全并入（缺失项搬入、重名另存备份、
   旧目录退休 .migrated_）—— 修的就是"更新后会话/记忆看起来全没了"；
5. 启动器预生成的模板 config.yaml（占位符 YOUR_API_KEY_HERE / 与 config.yaml.example 一致）
   不算用户数据，且用户自己的 config.yaml 会顶掉它（模板另存 .default_ 备份）；
6. 检测依据是强标记（state.db/provider_keys.json/sessions 有文件/真 key 的 config.yaml），
   .fix_bundle、.install_path、cron 等程序自己会建的标记不算；
7. 任何分支都不删数据：旧目录一律退休为 hermes_home.migrated_<时间戳>，并写 MIGRATION_NOTICE.txt；
8. update_apply 在 _apply_overlay 之前调用同一迁移（源码级护栏，「先迁移、再覆盖」）。
"""
import os
import shutil

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
    # 重名文件：新版赢（= 覆盖升级语义）；2026-10-10 起产品空壳场景不再另存 .from_hermes_ 备份
    # （用户实测一次更新产生 2290 个垃圾备份）；旧版仍留在退休目录里可手工找回（零丢失）
    assert (new / "skills" / "product" / "SKILL.md").read_text(encoding="utf-8") == "new-product"
    assert not list((new / "skills" / "product").glob("SKILL.md.from_hermes_*"))
    assert (new / "SOUL.md").is_file()
    # 旧目录退休为备份（不是删除），备份里只剩重名项
    left = list(tmp_path.glob("hermes_home.migrated_*"))
    assert len(left) == 1 and left[0].is_dir()
    assert (left[0] / "skills" / "product" / "SKILL.md").is_file()


def test_conflict_merges_safely_never_loses_data(tmp_path):
    """两边都有用户数据 → 安全并入（2026-10-10 起；旧行为"只告警"会让用户以为数据丢了）。"""
    old = tmp_path / "hermes_home"
    new = tmp_path / "memomics_home"
    _write(str(old / "config.yaml"), "api_key: sk-olduser-abcdef123456\nmax_turns: 177\n")
    _write(str(old / "sessions" / "s1.json"), '{"marker": "OLD"}')
    _write(str(old / "sessions" / "s2.json"), '{"marker": "OLD2"}')
    _write(str(new / "state.db"), "db")
    _write(str(new / "sessions" / "s1.json"), '{"marker": "NEW"}')
    res = MIG(str(new), str(old))
    assert res.startswith("conflict-merged:")
    # 新目录自己的数据一律保留
    assert (new / "state.db").read_text(encoding="utf-8") == "db"
    assert (new / "sessions" / "s1.json").read_text(encoding="utf-8") == '{"marker": "NEW"}'
    # 旧目录缺失项搬入；重名项另存备份（零丢失）
    assert (new / "sessions" / "s2.json").read_text(encoding="utf-8") == '{"marker": "OLD2"}'
    assert list((new / "sessions").glob("s1.json.from_hermes_*"))
    # 用户旧配置在新目录缺失 → 直接搬入
    assert (new / "config.yaml").read_text(encoding="utf-8").startswith("api_key: sk-olduser-abcdef123456")
    # 旧目录退休为备份（不删除），并留下迁移通知
    assert len(list(tmp_path.glob("hermes_home.migrated_*"))) == 1
    assert (new / "MIGRATION_NOTICE.txt").is_file()


def test_template_config_replaced_by_user_config(tmp_path):
    """启动器预生成的模板 config.yaml 必须被用户自己的配置顶掉（模板另存 .default_）。"""
    old = tmp_path / "hermes_home"
    new = tmp_path / "memomics_home"
    tpl = "provider: openai\nmodel: deepseek-chat\napi_base: https://api.deepseek.com/v1\napi_key: YOUR_API_KEY_HERE\n"
    _write(str(old / "config.yaml"), "provider: openai\napi_key: sk-realolduser-abcdef123456\nmax_turns: 177\n")
    _write(str(old / "sessions" / "s1.json"), "{}")
    _write(str(new / "config.yaml"), tpl)
    _write(str(new / "config.yaml.example"), tpl)
    assert server._config_is_default(str(new)) is True
    res = MIG(str(new), str(old))
    assert res.startswith("merged:")
    cfg = (new / "config.yaml").read_text(encoding="utf-8")
    assert "sk-realolduser-abcdef123456" in cfg and "max_turns: 177" in cfg
    assert list(new.glob("config.yaml.default_*"))
    assert (new / "sessions" / "s1.json").is_file()


def test_marker_detection_rules(tmp_path):
    """强标记才算用户数据（2026-10-10 收紧）：程序自建标记/模板配置不算。"""
    old = tmp_path / "hermes_home"
    _write(str(old / ".fix_bundle"), "x")
    _write(str(old / ".install_path"), "E:/MemOmics")
    _write(str(old / "cron" / "jobs.json"), "[]")
    assert server._home_has_user_data(str(old)) is False
    # 模板 config.yaml（占位符）不算
    tpl = "api_key: YOUR_API_KEY_HERE\n"
    _write(str(old / "config.yaml"), tpl)
    _write(str(old / "config.yaml.example"), tpl)
    assert server._home_has_user_data(str(old)) is False
    # 真 key 的 config.yaml 才算
    _write(str(old / "config.yaml"), "api_key: sk-someone-abcdef1234567890\n")
    assert server._home_has_user_data(str(old)) is True
    # 只有空目录的 sessions 不算，含文件才算
    shutil.rmtree(str(old)); os.makedirs(str(old / "sessions"), exist_ok=True)
    assert server._home_has_user_data(str(old)) is False
    _write(str(old / "sessions" / "s1.json"), "{}")
    assert server._home_has_user_data(str(old)) is True


def test_update_apply_migrates_before_overlay():
    """「先迁移、再覆盖」源码级护栏：迁移调用必须出现在 overlay 之前。"""
    src = open(os.path.join(os.path.dirname(server.__file__), "server.py"), encoding="utf-8").read()
    i = src.index("async def update_apply")
    j = src.index("_apply_overlay(extract_root, tops)", i)
    seg = src[i:j]
    assert "migrate_legacy_home(MEMOMICS_HOME_DIR, _legacy_home)" in seg
    assert "检测到覆盖升级" in seg

def test_tidy_from_hermes_dupes_only_removes_identical(tmp_path):
    """2026-10-10：历史迁移留下的 .from_hermes_ 备份，只有与本体逐字节相同才清掉。"""
    import pytest
    fb = pytest.importorskip("memomics.fix_bundle")
    home = tmp_path / "memomics_home"
    _write(str(home / "a.txt"), "same")
    _write(str(home / "a.txt.from_hermes_20261010-170544"), "same")      # 相同 → 删
    _write(str(home / "b.txt"), "new")
    _write(str(home / "b.txt.from_hermes_20261010-170544"), "user-edit")  # 有差异 → 留
    _write(str(home / "c.txt.from_hermes_20261010-170544"), "orphan")     # 本体缺失 → 留
    removed, kept = fb._tidy_from_hermes_dupes(str(home))
    assert removed == 1 and kept == 2
    assert not (home / "a.txt.from_hermes_20261010-170544").exists()
    assert (home / "b.txt.from_hermes_20261010-170544").is_file()
    assert (home / "c.txt.from_hermes_20261010-170544").is_file()
