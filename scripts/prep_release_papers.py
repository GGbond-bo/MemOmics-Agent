# -*- coding: utf-8 -*-
"""发布包文献库清洗（批O5 2026-08-16）。

打包前对 hermes_home/papers 做脱敏与可移植化：
1. .pdf_index.json 里的绝对路径（打包机 E:/MemOmics-Agent/...）→ 相对可移植
   路径 "hermes_home/papers/<文件名>"（运行时代码有 _resolve_paper_path 兜底，
   即使不重写也能按文件名在库内找到 PDF）。
2. 清空 imported_from / imported_by（用户源路径与导入人标识不进包）。
3. 删除运行态文件：.binding.json（会话绑定）、*.part.json（断点续译进度）、
   *.bilingual.json（对照缓存，首开自动重建）。
用法: python scripts/prep_release_papers.py <pkg_dir>
"""
import json
import os
import re
import sys


def scrub(pkg_dir: str) -> int:
    papers = os.path.join(pkg_dir, "hermes_home", "papers")
    if not os.path.isdir(papers):
        print(f"[skip] {papers} 不存在")
        return 0
    removed = 0
    for root, _dirs, files in os.walk(papers):
        for f in files:
            if f == ".binding.json" or f.endswith(".part.json") or f.endswith(".bilingual.json"):
                p = os.path.join(root, f)
                os.remove(p)
                removed += 1
                print(f"[rm] {os.path.relpath(p, papers)}")
    idx = os.path.join(papers, ".pdf_index.json")
    if os.path.isfile(idx):
        try:
            with open(idx, encoding="utf-8") as fh:
                entries = json.load(fh)
            n = 0
            for e in entries:
                fname = e.get("file") or ""
                if fname:
                    e["path"] = f"hermes_home/papers/{fname}"
                    n += 1
                if "imported_from" in e:
                    e["imported_from"] = ""
                if "imported_by" in e:
                    e["imported_by"] = ""
            with open(idx, "w", encoding="utf-8") as fh:
                json.dump(entries, fh, ensure_ascii=False, indent=2)
            print(f"[scrub] .pdf_index.json: {len(entries)} 条，路径改写 {n} 条，"
                  f"imported_from/imported_by 已清空")
        except Exception as ex:
            print(f"[warn] index scrub failed: {ex}")
    else:
        print("[skip] .pdf_index.json 不存在")
    print(f"清洗完成：删除运行态文件 {removed} 个")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/prep_release_papers.py <pkg_dir>")
        sys.exit(1)
    sys.exit(scrub(sys.argv[1]))
