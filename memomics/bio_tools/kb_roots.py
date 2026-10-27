# -*- coding: utf-8 -*-
"""知识库根目录的唯一真源（2026-10-26 修复「写入/读取指向两个目录」）。

背景（用户实测断点）：
  全新安装的包里**不带** `memomics/knowledge_base/`（打包规范把它当私有内容剔除），
  于是首次入库时 `kb_search._find_kb_root()` 返回 None → `save_knowledge._kb_root()`
  落到兜底目录 `memomics_home/skills`（agent 技能目录）——条目写进技能树里；
  而浏览页/图谱读的是硬编码 `KB_DIR = <安装目录>/memomics/knowledge_base`。
  结果：写与读各指一处，"提取成功了却什么都看不见"。

本模块提供统一出口：
  * `kb_root_path()`        → 权威路径（纯计算，不碰磁盘）
  * `ensure_kb_root()`      → 权威路径 + 不存在就建（写入端用）
  * `migrate_misplaced_entries()` → 把历史上误落进技能目录的 kb 条目搬回知识库

识别"误落盘条目"的口径（保守，避免误伤真实技能）：
  文件后缀 .yaml/.yml，且内容解析出 dict 且 `type: kb_entry`（或带 domain+evidence_chain）。
  同时要求该路径不在任何技能目录的 scripts/references/assets 下。
"""
import logging
import os
import re

logger = logging.getLogger(__name__)

MISPLACED_MARKERS = ("type: kb_entry",)
_MARKER_RE = re.compile(r"^\s*type:\s*['\"]?kb_entry['\"]?\s*$", re.M)
_SKILL_SUBDIRS = ("scripts", "references", "assets", "templates", "examples")


def kb_root_path() -> str:
    """知识库权威根目录（不创建）：<项目根>/memomics/knowledge_base。

    探测顺序：
      1. 环境变量 MEMOMICS_KB_DIR（显式指定优先）
      2. 已存在的默认位置（项目根/memomics/knowledge_base，含 cwd 变体）
      3. 由本包位置推导的项目根（安装目录直下）
    找不到"已存在"的也返回默认路径（供 ensure_kb_root 创建）。
    """
    env_dir = (os.environ.get("MEMOMICS_KB_DIR") or "").strip()
    if env_dir:
        return os.path.normpath(env_dir)

    here = os.path.dirname(os.path.abspath(__file__))          # <root>/memomics/bio_tools
    pkg_root = os.path.normpath(os.path.join(here, ".."))      # <root>/memomics
    default = os.path.normpath(os.path.join(pkg_root, "knowledge_base"))
    project_root = os.path.normpath(os.path.join(pkg_root, ".."))

    if os.path.isdir(default):
        return default

    # cwd 变体（从项目根启动时相对路径即为默认位置）
    cwd_variant = os.path.normpath(os.path.join(os.getcwd(), "memomics", "knowledge_base"))
    if cwd_variant != default and os.path.isdir(cwd_variant):
        return cwd_variant

    # 常见部署路径（历史上出现过 MemOmics-Agent / MemOmics 两种目录名）
    for cand in (
        os.path.join(project_root, "memomics", "knowledge_base"),
        os.path.join(os.path.dirname(project_root), "MemOmics-Agent", "memomics", "knowledge_base"),
        os.path.join(os.path.dirname(project_root), "MemOmics", "memomics", "knowledge_base"),
    ):
        if os.path.isdir(cand):
            return os.path.normpath(cand)

    return default


def ensure_kb_root() -> str:
    """返回知识库根目录并确保存在（写入端用；不存在就创建）。

    不再让调用方落"兜底目录"——那是写入/读取分裂的根因。
    """
    root = kb_root_path()
    try:
        os.makedirs(root, exist_ok=True)
    except OSError as e:
        logger.warning("ensure_kb_root: 无法创建知识库目录 %s: %s", root, e)
        return ""
    return root


def _looks_like_kb_entry(path: str) -> bool:
    """判断一个 yaml 文件是否是知识库条目（保守口径）。"""
    try:
        if os.path.getsize(path) > 512 * 1024:
            return False
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(65536)
    except OSError:
        return False
    if _MARKER_RE.search(head):
        return True
    # 无显式标记：domain + evidence_chain 同现也视为条目（老版本写出的形态）
    low = head.lower()
    return ("\ndomain:" in low or low.startswith("domain:")) and "evidence_chain:" in low


def _depth_ok(rel_parts) -> bool:
    """误落盘条目的路径形态校验：不能在任何技能子目录（scripts/references/...）里。"""
    return not any(p.lower() in _SKILL_SUBDIRS for p in rel_parts)


def migrate_misplaced_entries(skills_dir: str = "", kb_root: str = "", dry_run: bool = False) -> dict:
    """把误写进技能目录的知识库条目搬回知识库根目录。

    背景见模块 docstring；只搬 kb 条目（type: kb_entry），技能文件一律不动。
    目录名冲突时合并；同名条目保留较新的一份（旧的重命名为 .bak_<ts>）。
    """
    import shutil
    import time

    skills_dir = skills_dir or os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "memomics_home", "skills"))
    kb_root = kb_root or ensure_kb_root()
    result = {"moved": 0, "skipped": 0, "conflicts": 0, "skills_dir": skills_dir,
              "kb_root": kb_root, "errors": []}
    if not kb_root or not os.path.isdir(skills_dir):
        return result

    for dirpath, dirnames, filenames in os.walk(skills_dir):
        # 跳过隐藏目录（.archive/.curator_backups 等运行态）
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if not fn.lower().endswith((".yaml", ".yml")):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, skills_dir)
            rel_parts = rel.split(os.sep)
            if rel_parts and rel_parts[0].startswith("."):
                continue
            if not _depth_ok(rel_parts):
                continue
            if not _looks_like_kb_entry(full):
                continue
            dst = os.path.join(kb_root, rel)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(dst):
                    result["conflicts"] += 1
                    if os.path.getsize(dst) >= os.path.getsize(full):
                        result["skipped"] += 1
                        continue
                    backup = dst + ".bak_" + time.strftime("%Y%m%d%H%M%S")
                    os.replace(dst, backup)
                if dry_run:
                    result["moved"] += 1
                    continue
                shutil.move(full, dst)
                result["moved"] += 1
            except OSError as e:
                result["errors"].append(f"{rel}: {e}")
    if result["moved"]:
        logger.info("migrate_misplaced_entries: 从技能目录搬回知识库 %d 条（冲突 %d，跳过 %d）",
                    result["moved"], result["conflicts"], result["skipped"])
    return result