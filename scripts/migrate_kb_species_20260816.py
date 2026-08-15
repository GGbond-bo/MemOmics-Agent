# -*- coding: utf-8 -*-
"""kb 物种目录合并迁移（批O3 2026-08-16）

历史问题：不同时期的写入方用了不同物种目录名，导致同义目录分裂：
    human/  → Homo_sapiens/    （2 → 56 文件）
    mouse/  → Mus_musculus/    （1 → 35 文件）
    Macaca_mulatta/ → monkey/  （1 → 7 文件；检索端标准名是 monkey）
本脚本把源目录文件移动到标准目录；同名冲突时：内容一致→跳过，不一致→改名 _from_<src> 保留。
同时把批O 早期生成的 3 个 hotspot 条目从 other/other/other 迁到新域：
    paper_bioinfo_hotspot → common/general/03_测序方法/RNA/
    paper_qc_hotspot      → common/general/02_质控参数/RNA/
    paper_bio_hotspot     → 保留 other（无物种信息的生物学兜底）
幂等：可重复运行。
"""
import json
import os
import shutil
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "memomics", "knowledge_base")

MERGES = [
    ("human", "Homo_sapiens"),
    ("mouse", "Mus_musculus"),
    ("Macaca_mulatta", "monkey"),
]


def _move_file(src_path, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src_path))
    if os.path.exists(dst):
        with open(src_path, "rb") as f:
            a = f.read()
        with open(dst, "rb") as f:
            b = f.read()
        if a == b:
            print(f"  [dup-skip] {src_path}")
            os.remove(src_path)
            return
        stem, ext = os.path.splitext(os.path.basename(src_path))
        tag = os.path.basename(os.path.dirname(src_path))
        dst = os.path.join(dst_dir, f"{stem}_from_{tag}{ext}")
        print(f"  [collision] {src_path} → {dst}")
    else:
        print(f"  [move] {src_path} → {dst}")
    shutil.move(src_path, dst)


def _rm_empty_dirs(top):
    for dirpath, dirs, files in os.walk(top, topdown=False):
        if dirpath == top:
            continue
        if not os.listdir(dirpath):
            os.rmdir(dirpath)
            print(f"  [rmdir] {dirpath}")


def main():
    for src, dst in MERGES:
        src_dir = os.path.join(ROOT, src)
        if not os.path.isdir(src_dir):
            print(f"{src}/ 不存在，跳过")
            continue
        print(f"=== 合并 {src}/ → {dst}/ ===")
        for dirpath, dirs, files in os.walk(src_dir):
            rel = os.path.relpath(dirpath, src_dir)
            dst_dir = os.path.join(ROOT, dst, rel) if rel != "." else os.path.join(ROOT, dst)
            for f in files:
                if f.endswith((".yaml", ".yml", ".md", ".json")):
                    _move_file(os.path.join(dirpath, f), dst_dir)
        _rm_empty_dirs(src_dir)
        if os.path.isdir(src_dir) and not os.listdir(src_dir):
            os.rmdir(src_dir)
            print(f"  [rmdir] {src_dir}")

    # hotspot 早期条目迁到 common 域
    print("=== 迁移 hotspot 条目到 common 域 ===")
    old_base = os.path.join(ROOT, "other", "other", "other")
    moves = [
        (os.path.join(old_base, "03_测序方法", "RNA", "paper_bioinfo_hotspot.yaml"),
         os.path.join(ROOT, "common", "general", "03_测序方法", "RNA")),
        (os.path.join(old_base, "02_质控参数", "RNA", "paper_qc_hotspot.yaml"),
         os.path.join(ROOT, "common", "general", "02_质控参数", "RNA")),
    ]
    for src_path, dst_dir in moves:
        if os.path.isfile(src_path):
            os.makedirs(dst_dir, exist_ok=True)
            dst_path = os.path.join(dst_dir, os.path.basename(src_path))
            if os.path.exists(dst_path):
                os.remove(src_path)
                print(f"  [dup-skip] {src_path}")
            else:
                shutil.move(src_path, dst_path)
                print(f"  [move] {src_path} → {dst_path}")
        else:
            print(f"  [not-found] {src_path}")
    _rm_empty_dirs(old_base)
    print("迁移完成。")


if __name__ == "__main__":
    main()
