# -*- coding: utf-8 -*-
"""发布包文献库精选（批O5 2026-08-16）：只打包 N 篇样本文献供用户测试。

策略：
1. 固定精选清单（覆盖 翻译✓/摘要✓/知识✓ 的成品 + 人类/小鼠 + RNA/ATAC/spatial + 多方向），
   用户开箱即可逐个体验：📝提炼 / 🌐翻译 / ⇄对照 / 🧠知识 / 📎引用。
2. 每篇连带复制其全部衍生产物：markdown/<stem>.md、summaries/<stem>.md、
   translations/<stem>.zh.md、knowledge/<stem>.md。
3. .pdf_index.json 只保留选中条目，路径改写为可移植相对路径，清空 imported_from/by。
4. 运行态文件（.part.json/.binding.json/.bilingual.json）不进包。

用法: python scripts/select_release_papers.py <src_papers> <dst_papers> [N]
"""
import json
import os
import shutil
import sys

# 精选 5 篇（批O5d 用户拍板只带5篇；按体验价值排序，文件名与 .pdf_index.json 的 file 字段一致）
CURATED = [
    "10.1016_j.devcel.2026.03.010.pdf",            # ✅已翻译+摘要+知识（肌肉图谱 Dev Cell）
    "10.1038_s41467-025-56896-6.pdf",              # ✅已翻译+摘要（Nat Commun）
    "hotspot.pdf",                                  # ✅摘要+知识（方法学 Cell Systems）
    "lipid_signature_marks_in_human_muscle_aging.pdf",   # Nature Aging 2024 人骨骼肌脂质
    "s41588-024-01961-x.pdf",                       # Nature Genetics 空间转录组
]

DERIVED_DIRS = ("markdown", "summaries", "translations", "knowledge")


def select(src_papers: str, dst_papers: str, limit: int = 10) -> int:
    src_idx = os.path.join(src_papers, ".pdf_index.json")
    entries = []
    if os.path.isfile(src_idx):
        with open(src_idx, encoding="utf-8") as f:
            entries = json.load(f)
    by_file = {e.get("file"): e for e in entries}
    picked = []
    for fname in CURATED[:max(1, min(limit, len(CURATED)))]:
        if fname in by_file and os.path.isfile(os.path.join(src_papers, fname)):
            picked.append(fname)
        else:
            print(f"[warn] 源库缺失，跳过: {fname}")
    if not picked:
        # 兜底：前 limit 篇
        for e in entries:
            fname = e.get("file") or ""
            if fname and os.path.isfile(os.path.join(src_papers, fname)):
                picked.append(fname)
            if len(picked) >= limit:
                break
    print(f"[select] 选中 {len(picked)} 篇: {picked}")

    os.makedirs(dst_papers, exist_ok=True)
    # 清空目标（幂等）
    for name in os.listdir(dst_papers):
        p = os.path.join(dst_papers, name)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            os.remove(p)

    out_entries = []
    for fname in picked:
        shutil.copy2(os.path.join(src_papers, fname), os.path.join(dst_papers, fname))
        stem = os.path.splitext(fname)[0]
        for d, suffix in (("markdown", ".md"), ("summaries", ".md"),
                          ("translations", ".zh.md"), ("knowledge", ".md")):
            s = os.path.join(src_papers, d, f"{stem}{suffix}")
            if os.path.isfile(s):
                os.makedirs(os.path.join(dst_papers, d), exist_ok=True)
                shutil.copy2(s, os.path.join(dst_papers, d, f"{stem}{suffix}"))
        e = dict(by_file.get(fname) or {})
        e["file"] = fname
        e["path"] = f"hermes_home/papers/{fname}"
        e["imported_from"] = ""
        e["imported_by"] = ""
        out_entries.append(e)

    with open(os.path.join(dst_papers, ".pdf_index.json"), "w", encoding="utf-8") as f:
        json.dump(out_entries, f, ensure_ascii=False, indent=2)
    sz = sum(os.path.getsize(os.path.join(dst_papers, f)) for f in picked)
    print(f"[select] 文献库样本已就绪: {len(picked)} 篇 PDF, "
          f"{len(out_entries)} 条索引, {round(sz / 1048576, 1)} MB")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python scripts/select_release_papers.py <src_papers> <dst_papers> [N]")
        sys.exit(1)
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    sys.exit(select(sys.argv[1], sys.argv[2], limit))
