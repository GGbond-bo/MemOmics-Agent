# -*- coding: utf-8 -*-
"""
专利交付件形式规范验收器（机器可读，替代肉眼核对）
配套：references/patent-deliverable-hygiene.md §F（权项形式规范）

覆盖的静默漂移点：
  F1 权项连续编号 / 无小数编号残留 / 引用范围同步
  F4 发明名称三处一致
  F6 docx 表5 权项数 == claims.md 权项数
  + docx 结构计数（段落/标题/表/图）、口径数字在册、旧口径零命中

用法（Windows 示例）：
  python validate_patent_deliverables.py \
      --claims   "E:/专利/交付_xxx/claims.md" \
      --disclosure "E:/专利/交付_xxx/disclosure.md" \
      --docx     "E:/专利/技术交底书_v11.docx" \
      --expect-title "一种跨物种衰老染色质可及性核心元件的筛选方法" \
      --expect-claims 14 \
      --forbid "12.3,95.5%"

依赖：python-docx（仅当传 --docx 时需要）。
退出码：0 = 全通过；1 = 有 FAIL（可直接用于 CI / 收尾门禁）。
"""
import argparse
import os
import re
import sys

OK, BAD = [], []


def chk(cond, msg):
    (OK if cond else BAD).append(msg)
    print(("  [PASS] " if cond else "  [FAIL] ") + msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", help="claims.md 路径")
    ap.add_argument("--disclosure", help="disclosure.md 路径")
    ap.add_argument("--docx", help="交底书 docx 路径")
    ap.add_argument("--expect-title", default="", help="发明名称应含的关键子串（三处一致）")
    ap.add_argument("--expect-claims", type=int, default=0, help="期望权项总数（0=跳过）")
    ap.add_argument("--forbid", default="", help="禁用子串，逗号分隔（如旧口径 '12.3,95.5%'）")
    ap.add_argument("--require", default="", help="必须在册的子串，逗号分隔（口径数字台账）")
    ap.add_argument("--claim-range-to", default="", help="独权引用范围形如 '1 至 13'，用于校验最后一项独立权项")
    a = ap.parse_args()

    claims_txt = disc_txt = docx_txt = ""

    if a.claims:
        print("=" * 70 + "\n[1] claims.md\n" + "=" * 70)
        claims_txt = open(a.claims, encoding="utf-8").read()
        if a.expect_title:
            chk(a.expect_title in claims_txt, "claims.md 含完整发明名称（F4 三处一致）")
        chk("草案" in claims_txt or "v1" in claims_txt or "v" in claims_txt, "claims.md 有版本标识（F5）")
        # F1 小数编号残留
        chk(not re.search(r"##\s*权利要求\s*\d+\.\d+", claims_txt),
            "无 10.1/10.2 之类小数编号残留（F1）")
        nums = re.findall(r"##\s*权利要求\s*(\d+)（", claims_txt)
        nums_int = [int(x) for x in nums]
        chk(nums_int == list(range(1, len(nums_int) + 1)),
            f"权项编号连续从 1 起（实得 {nums_int}；F1）")
        if a.expect_claims:
            chk(len(nums_int) == a.expect_claims,
                f"claims.md 权项数 == {a.expect_claims}（实得 {len(nums_int)}；F6）")
        if a.claim_range_to:
            chk(f"权利要求 1 至 {a.claim_range_to}" in claims_txt,
                f"装置独权引用范围 = '权利要求 1 至 {a.claim_range_to}'（F1 连带改动）")

    if a.disclosure:
        print("=" * 70 + "\n[2] disclosure.md\n" + "=" * 70)
        disc_txt = open(a.disclosure, encoding="utf-8").read()
        if a.expect_title:
            chk(a.expect_title in disc_txt, "disclosure.md 含同一发明名称（F4）")
        chk(not re.search(r"^#+\s*六、效果对照小结", disc_txt, re.M) or "八、效果对照小结" in disc_txt,
            "章节编号在插入新章后已顺延（无重号）")
        chk("附图说明" in disc_txt, "含「附图说明」章节（F3 相邻：独权需图支持）")
        chk("存储介质" in disc_txt and "程序产品" in disc_txt,
            "含「装置与存储介质实施例」且覆盖程序产品载体（F3）")

    if a.docx:
        print("=" * 70 + "\n[3] docx\n" + "=" * 70)
        try:
            from docx import Document
        except ImportError:
            print("  [SKIP] 未安装 python-docx，跳过 docx 校验（pip install python-docx）")
            docx_txt = ""
        else:
            chk(os.path.exists(a.docx), "文件存在")
            print(f"  size = {os.path.getsize(a.docx):,} bytes")
            doc = Document(a.docx)
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            heads = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
            imgs = [r for r in doc.part.rels.values() if "image" in r.reltype]
            print(f"  非空段落 = {len(paras)} | 标题 = {len(heads)} | 表格 = {len(doc.tables)} | 图 = {len(imgs)}")
            chk(len(imgs) > 0, "有内嵌图（F3/交付完整性）")
            docx_txt = "\n".join(paras) + "\n" + "\n".join(
                c.text for t in doc.tables for r in t.rows for c in r.cells)
            if a.expect_title:
                chk(a.expect_title in docx_txt, "docx 含同一发明名称（F4 三处一致）")
            if a.expect_claims:
                t5 = [t for t in doc.tables if t.rows[0].cells[0].text.strip() == "权项"]
                chk(len(t5) == 1, "找到权项框架表（表5）")
                if t5:  # ⚠️ 切勿写成 `if chk(...)`：chk 返回 None，会让整个 F6 校验静默跳过
                    n = len(t5[0].rows) - 1
                    labels = [t5[0].rows[i].cells[0].text.strip() for i in range(1, len(t5[0].rows))]
                    print("    表5 权项行:", labels)
                    chk(n == a.expect_claims,
                        f"docx 表5 权项数 == {a.expect_claims}（实得 {n}；F6 最易漂移点）")

    blob = claims_txt + "\n" + disc_txt + "\n" + docx_txt

    if a.forbid:
        print("=" * 70 + "\n[4] 旧口径零命中\n" + "=" * 70)
        for s in [x.strip() for x in a.forbid.split(",") if x.strip()]:
            chk(s not in blob, f"禁用子串 '{s}' 零命中（旧口径已清除）")

    if a.require:
        print("=" * 70 + "\n[5] 口径数字台账在册\n" + "=" * 70)
        for s in [x.strip() for x in a.require.split(",") if x.strip()]:
            chk(s in blob, f"口径数字 '{s}' 在册（防静默丢失）")

    print("=" * 70)
    print(f"结果：PASS {len(OK)} | FAIL {len(BAD)}")
    if BAD:
        print("失败项：")
        for b in BAD:
            print("  -", b)
    print("=" * 70)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
