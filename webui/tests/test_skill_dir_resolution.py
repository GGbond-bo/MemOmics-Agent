"""skill_evolution 技能目录解析（_get_skill_dir / resolve_skill_dir）回归测试。

背景：引擎原先把技能目录写死为 hermes_home/skills/bioinformatics/<名>，导致用户脚本库
的分类目录（plotting/ comparison/ statistics/ user-scripts/）无法被 record_run/record_error
识别（返回「尚未注册」并写出 action 记错的空壳归档）。

本测试锁定修复后的契约：
  主路径：prefixed / bare / top-level / bioinformatics(旧路径) / missing /
          wrong-prefix-unique / wrong-prefix-ambiguous / root-oserror /
          nonexistent-root / separators-and-whitespace / windows-case-ambiguity
  L2 裁决（code_engineering, verdict=modify）边界：nested>1 不命中 / 坏根 WARNING 可断言 /
          双根同名歧义 / 结构化诊断字段 / 指纹内容哈希（非 mtime）
  L1 复审补充：调用点消费 diagnosis（query_logs / update_script，含 ambiguous）/ 无静默
          bioinformatics 猜测 / _sync_to_hermes_home 尊重分类前缀 / CRLF·LF 指纹漂移 /
          读失败返回 unknown

纯本地文件系统操作，无外部依赖 → 默认 offline 集内可跑。
"""
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SE_PATH = ROOT / "memomics" / "bio_tools" / "skill_evolution.py"


def _load_engine():
    """按文件路径加载引擎模块（与 webui/enforcement.py 的动态加载方式一致）。"""
    spec = importlib.util.spec_from_file_location("se_under_test", SE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_module_from(path):
    """从任意路径加载引擎模块（指纹用例需要在临时副本上构造「同 mtime / 不同内容」）。"""
    spec = importlib.util.spec_from_file_location("se_under_test_tmp", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """把技能库根重定向到临时目录，构造真实分类结构。"""
    if not SE_PATH.is_file():
        pytest.skip(f"engine not found: {SE_PATH}")

    skills = tmp_path / "hermes_home" / "skills"
    (skills / "plotting" / "deg-updown-counts-by-subcluster").mkdir(parents=True)
    (skills / "plotting" / "deg-volcano-5comps-8sub-R").mkdir(parents=True)
    (skills / "statistics" / "cell-proportion-significance").mkdir(parents=True)
    (skills / "bioinformatics" / "deg-analysis").mkdir(parents=True)
    (skills / "top-level-skill").mkdir(parents=True)          # 顶层直放
    (skills / "plotting" / "not-a-dir.txt").write_text("x", encoding="utf-8")  # 非目录项

    mod = _load_engine()
    monkeypatch.setattr(mod, "_skill_roots", lambda: [str(skills)])
    return mod, skills


# ---------------------------------------------------------------- 主路径

def test_prefixed(engine):
    """带分类前缀 → 精确命中该分类。"""
    mod, skills = engine
    got = mod._get_skill_dir("plotting/deg-updown-counts-by-subcluster")
    assert got == str(skills / "plotting" / "deg-updown-counts-by-subcluster")


def test_bare(engine):
    """裸名 → 遍历一级分类目录命中（不再只认 bioinformatics）。"""
    mod, skills = engine
    assert mod._get_skill_dir("deg-updown-counts-by-subcluster") == \
        str(skills / "plotting" / "deg-updown-counts-by-subcluster")
    assert mod._get_skill_dir("cell-proportion-significance") == \
        str(skills / "statistics" / "cell-proportion-significance")


def test_top_level(engine):
    """顶层直放 → 直接命中。"""
    mod, skills = engine
    assert mod._get_skill_dir("top-level-skill") == str(skills / "top-level-skill")


def test_bioinformatics_legacy(engine):
    """向后兼容：旧 bioinformatics/ 路径仍可解析（带前缀与裸名两种写法）。"""
    mod, skills = engine
    assert mod._get_skill_dir("bioinformatics/deg-analysis") == \
        str(skills / "bioinformatics" / "deg-analysis")
    assert mod._get_skill_dir("deg-analysis") == \
        str(skills / "bioinformatics" / "deg-analysis")


def test_missing(engine):
    """不存在的 skill → None（不抛异常）。"""
    mod, _ = engine
    assert mod._get_skill_dir("不存在的名字") is None
    assert mod._get_skill_dir("") is None


def test_wrong_prefix_unique(engine):
    """前缀写错但末段唯一 → 退化为末段继续查找（兜底可用）。"""
    mod, skills = engine
    assert mod._get_skill_dir("wrongcat/deg-updown-counts-by-subcluster") == \
        str(skills / "plotting" / "deg-updown-counts-by-subcluster")


def test_wrong_prefix_ambiguous(engine):
    """跨分类同名 → 拒绝歧义匹配（返回 None，不静默取首匹配）。"""
    mod, skills = engine
    (skills / "statistics" / "deg-updown-counts-by-subcluster").mkdir(parents=True)
    assert mod._get_skill_dir("deg-updown-counts-by-subcluster") is None
    # 带精确前缀仍可消歧
    assert mod._get_skill_dir("plotting/deg-updown-counts-by-subcluster") == \
        str(skills / "plotting" / "deg-updown-counts-by-subcluster")


def test_root_oserror_isolated(tmp_path, monkeypatch):
    """单目录 listdir 抛 OSError（模拟无权限/坏 junction）→ 跳过并继续，不中断解析。"""
    if not SE_PATH.is_file():
        pytest.skip(f"engine not found: {SE_PATH}")

    skills = tmp_path / "hermes_home" / "skills"
    (skills / "plotting").mkdir(parents=True)
    (skills / "statistics" / "good-skill").mkdir(parents=True)

    mod = _load_engine()
    monkeypatch.setattr(mod, "_skill_roots", lambda: [str(skills)])

    real_listdir = os.listdir

    def fake_listdir(path):
        if os.path.basename(str(path)) == "plotting":
            raise PermissionError("simulated permission denied")
        return real_listdir(path)

    monkeypatch.setattr(mod.os, "listdir", fake_listdir)

    # 坏目录被跳过，好目录仍能解析出来
    assert mod._get_skill_dir("good-skill") == str(skills / "statistics" / "good-skill")


def test_nonexistent_root_isolated(tmp_path, monkeypatch):
    """根目录不存在 → 跳过，不抛异常。"""
    if not SE_PATH.is_file():
        pytest.skip(f"engine not found: {SE_PATH}")
    mod = _load_engine()
    monkeypatch.setattr(mod, "_skill_roots",
                        lambda: [str(tmp_path / "no-such-root"), str(tmp_path)])
    assert mod._get_skill_dir("whatever") is None


def test_separators_and_whitespace(engine):
    """反斜杠分隔符（Windows 习惯）/ 多余分隔符 / 前后空白 → 均应被规范化。"""
    mod, skills = engine
    want = str(skills / "plotting" / "deg-updown-counts-by-subcluster")
    assert mod._get_skill_dir("plotting\\deg-updown-counts-by-subcluster") == want
    assert mod._get_skill_dir("plotting//deg-updown-counts-by-subcluster") == want
    assert mod._get_skill_dir("  plotting/deg-updown-counts-by-subcluster  ") == want


def test_windows_case_insensitive_ambiguity(engine):
    """Windows/macOS 大小写不敏感：同名目录必须拒绝歧义，而不是静默取错。

    - 大小写敏感平台（Linux CI）：只有精确名命中 → 正常返回。
    - 大小写不敏感平台（Windows/macOS）：两个目录被视为同名 → 唯一命中失败 → None。
    两种情况都不允许「取到错的那个」。
    """
    mod, skills = engine
    (skills / "statistics" / "DEG-UPdown-counts-by-subcluster").mkdir(parents=True)
    got = mod._get_skill_dir("deg-updown-counts-by-subcluster")
    if os.path.normcase("A") == os.path.normcase("a"):
        assert got is None, f"大小写不敏感平台必须拒绝歧义，却返回 {got}"
    else:
        assert got == str(skills / "plotting" / "deg-updown-counts-by-subcluster")
    # 带精确前缀仍可消歧
    assert mod._get_skill_dir("plotting/deg-updown-counts-by-subcluster") == \
        str(skills / "plotting" / "deg-updown-counts-by-subcluster")


# ---------------------------------------------------------------- L2 裁决边界矩阵
# debate 裁决（code_engineering / verdict=modify）要求补齐：
# 嵌套>1 不命中、坏根 WARNING 可断言、双根同名歧义、结构化诊断字段、指纹内容哈希。


def test_nested_two_levels_not_hit(engine):
    """当前契约只扫「一级分类」：<根>/<分类>/<分类2>/<名> 不参与裸名匹配。

    显式带上两级相对路径仍应能命中（前缀分支按路径拼接，不限制层级）。
    """
    mod, skills = engine
    (skills / "plotting" / "nested" / "deep-skill").mkdir(parents=True)
    assert mod._get_skill_dir("deep-skill") is None
    assert mod._get_skill_dir("plotting/nested/deep-skill") == \
        str(skills / "plotting" / "nested" / "deep-skill")


def test_bad_root_logs_warning(caplog, tmp_path, monkeypatch):
    """坏根目录（无权限/坏 junction）必须被跳过 **且留下 WARNING** —— 不静默吞掉。"""
    if not SE_PATH.is_file():
        pytest.skip(f"engine not found: {SE_PATH}")

    good = tmp_path / "skills"
    (good / "statistics" / "good-skill").mkdir(parents=True)
    bad = tmp_path / "bad_root"
    bad.mkdir()

    mod = _load_engine()
    monkeypatch.setattr(mod, "_skill_roots", lambda: [str(bad), str(good)])

    real_listdir = os.listdir

    def fake_listdir(path):
        if os.path.basename(str(path)) == "bad_root":
            raise PermissionError("simulated permission denied")
        return real_listdir(path)

    monkeypatch.setattr(mod.os, "listdir", fake_listdir)

    with caplog.at_level("WARNING", logger="memomics.skill_evolution"):
        assert mod._get_skill_dir("good-skill") == str(good / "statistics" / "good-skill")

    assert any("跳过不可读根目录" in r.getMessage() for r in caplog.records), \
        f"坏根目录必须产生 WARNING，实际日志：{[r.getMessage() for r in caplog.records]}"


def test_ambiguous_detail_fields(engine):
    """多命中 → status='ambiguous' + candidates + searched_roots（可操作诊断，不再只是 None）。"""
    mod, skills = engine
    (skills / "statistics" / "deg-updown-counts-by-subcluster").mkdir(parents=True)
    d = mod.resolve_skill_dir("deg-updown-counts-by-subcluster")
    assert d["status"] == "ambiguous"
    assert d["path"] is None
    assert len(d["candidates"]) == 2
    assert d["searched_roots"] == [str(skills)]
    assert "同名" in d["reason"]


def test_not_found_detail_fields(engine):
    """0 命中 → status='not_found' + searched_roots(+prefix_attempted)，可区分「前缀错/不存在」。"""
    mod, skills = engine
    d = mod.resolve_skill_dir("no-such-skill")
    assert d["status"] == "not_found" and d["path"] is None
    assert d["searched_roots"] == [str(skills)]
    assert d["prefix_attempted"] is False
    d2 = mod.resolve_skill_dir("wrongcat/no-such-skill")
    assert d2["status"] == "not_found"
    assert d2["prefix_attempted"] is True
    assert d2["degenerated_prefix"] == "wrongcat"


def test_degenerated_prefix_recorded(engine):
    """前缀写错但末段唯一命中 → found，且保留退化前缀（便于定位前缀笔误）。"""
    mod, _ = engine
    d = mod.resolve_skill_dir("wrongcat/deg-volcano-5comps-8sub-R")
    assert d["status"] == "found"
    assert d["degenerated_prefix"] == "wrongcat"


def test_dual_root_same_name_ambiguous(tmp_path, monkeypatch):
    """两套根目录（skills/ 与 hermes_home/skills/）各有一处同名 → 必须拒绝歧义。"""
    if not SE_PATH.is_file():
        pytest.skip(f"engine not found: {SE_PATH}")
    old_root, new_root = tmp_path / "skills", tmp_path / "hermes_home" / "skills"
    (old_root / "plotting" / "same-name").mkdir(parents=True)
    (new_root / "statistics" / "same-name").mkdir(parents=True)
    mod = _load_engine()
    monkeypatch.setattr(mod, "_skill_roots", lambda: [str(old_root), str(new_root)])
    assert mod._get_skill_dir("same-name") is None
    assert mod.resolve_skill_dir("same-name")["status"] == "ambiguous"


def _fingerprint_sha(fp: str) -> str:
    """从指纹串中取 sha256 段（用于对比内容版本，忽略 mtime 等附件字段）。"""
    m = re.search(r"@sha256:([0-9a-f]{12})@", fp)
    assert m, f"指纹格式异常（应含 @sha256:<12hex>@）：{fp}"
    return m.group(1)


def test_fingerprint_is_content_hash_not_mtime(tmp_path):
    """指纹必须由**内容哈希**决定（mtime 判据在 checkout/打包/时钟回拨下会误判）。

    - mtime 变、内容不变 → sha256 不变
    - 内容变、mtime 与另一份相同 → sha256 必须变（这正是旧 mtime 判据失效的场景）
    """
    if not SE_PATH.is_file():
        pytest.skip(f"engine not found: {SE_PATH}")
    src = SE_PATH.read_text(encoding="utf-8")

    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        d.mkdir(parents=True, exist_ok=True)
        (d / "engine.py").write_text(src, encoding="utf-8")

    mod_a = _load_module_from(a / "engine.py")
    sha_a1 = _fingerprint_sha(mod_a._engine_fingerprint())

    os.utime(a / "engine.py", (10_000_000, 10_000_000))       # mtime 改、内容不变
    mod_a2 = _load_module_from(a / "engine.py")
    assert _fingerprint_sha(mod_a2._engine_fingerprint()) == sha_a1, \
        "mtime 变化不应改变内容哈希"

    mod_b = _load_module_from(b / "engine.py")
    assert _fingerprint_sha(mod_b._engine_fingerprint()) == sha_a1, \
        "同一份内容在不同路径下哈希应一致"

    (b / "engine.py").write_text(src + "\n# 内容变更\n", encoding="utf-8")
    os.utime(b / "engine.py", (10_000_000, 10_000_000))       # 与 a 同 mtime、内容不同
    mod_b2 = _load_module_from(b / "engine.py")
    assert _fingerprint_sha(mod_b2._engine_fingerprint()) != sha_a1, \
        "内容变化必须改变哈希（mtime 相同也不许判成同一版本）"


# ---------------------------------------------------------------- L1 复审补充
# debate 复审（verdict=modify）要求：调用点消费 diagnosis、无静默 fallback、
# 同步尊重分类前缀、CRLF/LF 指纹漂移、读失败可判。


def test_call_site_diagnosis_query_logs(engine):
    """query_logs 在解析失败时必须把诊断回传（不再只有一句「尚未注册」）。"""
    mod, skills = engine
    r = mod._query_logs("no-such-skill")
    assert r["diagnosis"]["status"] == "not_found"
    assert r["diagnosis"]["searched_roots"] == [str(skills)]
    assert r["diagnosis"]["prefix_attempted"] is False


def test_call_site_diagnosis_ambiguous(engine):
    """跨分类同名 → 调用点能拿到候选清单（诊断完整性）。"""
    mod, skills = engine
    (skills / "statistics" / "deg-updown-counts-by-subcluster").mkdir(parents=True)
    r = mod._query_logs("deg-updown-counts-by-subcluster")
    assert r["diagnosis"]["status"] == "ambiguous"
    assert len(r["diagnosis"]["candidates"]) == 2


def test_call_site_diagnosis_update_script(engine):
    """update_script 同样消费诊断（4 个调用点语义一致）。"""
    mod, _ = engine
    r = mod._update_script("no-such-skill", "x.R", "whatever")
    assert r["diagnosis"]["status"] == "not_found"
    assert "candidates" in r["diagnosis"]


def test_no_silent_path_guess(engine):
    """解析失败时**不得**静默拼一个 bioinformatics/<名> 路径当结果（旧 bug 的复发防护）。

    注意：用例名故意不含 "bioinformatics" 字样 —— pytest 的临时目录名会嵌入用例名，
    否则临时路径本身就会命中字符串断言（首版即栽在这里，引擎行为其实是对的）。
    """
    mod, _ = engine
    r = mod._query_logs("no-such-skill-xyz")
    assert r["diagnosis"]["status"] == "not_found"
    assert r["diagnosis"]["candidates"] == [], "失败时不该凭空造出候选路径"
    blob = json.dumps(r, ensure_ascii=False)
    assert "bioinformatics" not in blob, f"出现静默 bioinformatics 猜测：{blob}"
    assert not r.get("skill_dir") and not r.get("path")


def test_sync_respects_category_prefix(tmp_path, monkeypatch):
    """_sync_to_hermes_home：带分类前缀的新 skill 必须落到其分类目录，不搬去 bioinformatics/。"""
    if not SE_PATH.is_file():
        pytest.skip(f"engine not found: {SE_PATH}")
    mod = _load_engine()
    monkeypatch.setattr(mod, "_get_memomics_root", lambda: str(tmp_path))

    src = tmp_path / "src_skill"
    (src / "scripts").mkdir(parents=True)
    (src / "SKILL.md").write_text("# x", encoding="utf-8")
    (src / "scripts" / "s.R").write_text("1", encoding="utf-8")

    mod._sync_to_hermes_home("plotting/brand-new-skill", str(src))

    landed = tmp_path / "hermes_home" / "skills" / "plotting" / "brand-new-skill"
    assert landed.is_dir(), "带前缀的 skill 未落到分类目录"
    assert not (tmp_path / "hermes_home" / "skills" / "bioinformatics").exists(), \
        "不得回退到 bioinformatics/ 猜测"


def test_fingerprint_drifts_on_eol(tmp_path):
    """行尾（CRLF vs LF）不同 → 内容哈希必须不同。

    这条用例的意义：本仓库曾因 write_file 把 CRLF 改写成 LF 而产生 12 倍 diff 噪音，
    指纹对 eol 敏感，正是「eol 必须纳入版本管理（.gitattributes）」的直接依据。
    """
    if not SE_PATH.is_file():
        pytest.skip(f"engine not found: {SE_PATH}")
    lf = SE_PATH.read_bytes().replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")

    (tmp_path / "lf").mkdir()
    (tmp_path / "crlf").mkdir()
    (tmp_path / "lf" / "engine.py").write_bytes(lf)
    (tmp_path / "crlf" / "engine.py").write_bytes(crlf)

    sha_lf = _fingerprint_sha(_load_module_from(tmp_path / "lf" / "engine.py")._engine_fingerprint())
    sha_crlf = _fingerprint_sha(_load_module_from(tmp_path / "crlf" / "engine.py")._engine_fingerprint())
    assert sha_lf != sha_crlf, "行尾不同却给了同一个内容哈希 —— eol 未被纳入指纹"


def test_fingerprint_read_failure_returns_unknown(tmp_path):
    """文件读不到（指向目录 / 权限失败）→ 返回 'unknown'，不得抛异常打断 import。"""
    mod = _load_engine()
    mod.__file__ = str(tmp_path)          # 指向目录 → open 失败
    assert mod._engine_fingerprint() == "unknown"


def test_engine_version_self_attested_on_import():
    """启动期自证：import 后模块里必须可直接读到本进程加载的引擎版本（内容哈希）。"""
    if not SE_PATH.is_file():
        pytest.skip(f"engine not found: {SE_PATH}")
    mod = _load_engine()
    assert isinstance(getattr(mod, "ENGINE_VERSION", None), str)
    assert "@sha256:" in mod.ENGINE_VERSION
    assert mod.ENGINE_VERSION == mod._engine_fingerprint(), \
        "启动期自证值应与即时计算一致"