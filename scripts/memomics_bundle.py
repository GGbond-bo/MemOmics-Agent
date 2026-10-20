# -*- coding: utf-8 -*-
"""MemOmics 资产包 CLI（跨机器转移用）。

用法::

    python scripts/memomics_bundle.py export --scopes kb,skills,memory --topic deg-analysis --out D:\\backup
    python scripts/memomics_bundle.py export --scopes kb,skills,memory --dry-run        # 只看命中
    python scripts/memomics_bundle.py preview D:\\backup\\memomics_bundle_xxx.zip
    python scripts/memomics_bundle.py import  D:\\backup\\xxx.zip --overwrite kb/a.yaml
    python scripts/memomics_bundle.py import  D:\\backup\\xxx.zip                       # 全部 skip（默认）
    python scripts/memomics_bundle.py activate --scopes kb,skills,memory
    python scripts/memomics_bundle.py rollback memomics_home\\backups\\20261020_xxx_pre_import
    python scripts/memomics_bundle.py list --out D:\\backup
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from memomics import bundle  # noqa: E402


def _p(obj, limit=4000):
    s = json.dumps(obj, ensure_ascii=False, indent=1)
    print(s[:limit] + ("\n…（截断）" if len(s) > limit else ""))
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="memomics_bundle", description="MemOmics 资产包（记忆/知识库/技能）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="打包导出")
    e.add_argument("--scopes", default="kb,skills,memory")
    e.add_argument("--topic", default=None, help="只导出某主题（逗号分隔多个关键词）")
    e.add_argument("--out", default=None, help="输出目录（默认 memomics_home/exports）")
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("--no-redact", action="store_true", help="不脱敏（默认脱敏：路径替换为占位符）")
    e.add_argument("--include-env", action="store_true", help="附带环境记录（cluster_envs/environment）")

    p = sub.add_parser("preview", help="预览包内容/冲突（不改任何文件）")
    p.add_argument("zip_path")

    i = sub.add_parser("import", help="导入（默认 skip 冲突）")
    i.add_argument("zip_path")
    i.add_argument("--overwrite", action="append", default=[], help="要覆盖的包内路径（可多次）")
    i.add_argument("--all-overwrite", action="store_true", help="全部冲突都覆盖")
    i.add_argument("--no-backup", action="store_true")
    i.add_argument("--no-activate", action="store_true")

    a = sub.add_parser("activate", help="重建索引/清缓存（内化）")
    a.add_argument("--scopes", default="kb,skills,memory")

    r = sub.add_parser("rollback", help="从备份回滚")
    r.add_argument("backup_dir")

    l = sub.add_parser("list", help="列出历史包")
    l.add_argument("--out", default=None)

    ns = ap.parse_args(argv)
    if ns.cmd == "export":
        out_dir = ns.out or os.path.join(bundle._home(), "exports")
        res = bundle.export_bundle(ns.scopes, out_dir, topic=ns.topic,
                                   redact=not ns.no_redact, include_env=ns.include_env,
                                   dry_run=ns.dry_run)
        if res.get("dry_run"):
            print(f"[dry-run] 命中 {res.get('total_files')} 个文件: {res.get('counts')}")
            return _p({"counts": res.get("counts"), "files": res.get("files")})
        if not res.get("ok"):
            return _p(res)
        print(f"✓ 已导出: {res['path']}  ({res['bytes'] / 1048576.0:.2f} MB)")
        print(f"  内容: {res.get('counts')}  | 脱敏替换 {res['manifest']['redactions_applied']} 处")
        if res["manifest"].get("locators_redacted"):
            print("  ⚠️ locator 已脱敏：导入后需本机复核证据定位")
        return 0
    if ns.cmd == "preview":
        res = bundle.preview_bundle(ns.zip_path)
        if res.get("ok"):
            print(f"包版本: {res.get('schema')} | 创建: {res.get('created_at')} | 主题: {res.get('topic') or '（全量）'}")
            print(f"内容: {res.get('counts')} | 记忆条目 {res.get('memory_entries')} | 脱敏: {res.get('redacted')}")
            print(f"新增 {len(res.get('new_files') or [])} 个 / 冲突 {len(res.get('conflicts') or [])} 个"
                  f" / 疑似密钥 {len(res.get('secrets_found') or [])} 个")
            if res.get("conflicts"):
                print("冲突（默认 skip，勾选才覆盖）：")
                for c in res["conflicts"][:40]:
                    print(f"  - {c['path']}  (本机 {c['local_mtime']}, {c['local_bytes']}B)")
        return _p(res)
    if ns.cmd == "import":
        pv = bundle.preview_bundle(ns.zip_path)
        ov = {}
        if ns.all_overwrite:
            ov = {c["path"]: "overwrite" for c in (pv.get("conflicts") or [])}
        for x in ns.overwrite:
            ov[x] = "overwrite"
        res = bundle.import_bundle(ns.zip_path, overrides=ov,
                                   backup=not ns.no_backup, activate_after=not ns.no_activate)
        if res.get("ok"):
            print(f"✓ 导入完成：写入 {len(res['written'])} 个 / 跳过 {len(res['skipped'])} 个"
                  f" / 记忆新增 {res['memory_added']} 条")
            print(f"  备份: {res.get('backup')}")
            for s in (res.get("activate") or {}).get("steps") or []:
                print(f"  [{ 'OK' if s.get('ok') else '!!' }] {s.get('step')}: {s.get('detail')}")
        return _p(res)
    if ns.cmd == "activate":
        return _p(bundle.activate(scopes=[x.strip() for x in ns.scopes.split(",") if x.strip()]))
    if ns.cmd == "rollback":
        return _p(bundle.rollback(ns.backup_dir))
    if ns.cmd == "list":
        items = bundle.list_bundles(ns.out)
        if not items:
            print("（没有历史包）")
            return 0
        for it in items:
            print(f"  {it['mtime']}  {it['mb']:>7.2f} MB  {it['name']}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
