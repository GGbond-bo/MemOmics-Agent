# -*- coding: utf-8 -*-
"""交付件增量复审探针 —— 一个脚本跑完全部机械检查（防循环检测：一产物一探针）。

用法（先改顶部 CONFIG，再跑一次）：
    python audit_deliverable_round.py

输出 9 段：
  A docx 结构（段落/表格/内嵌图）+ word/media 字节数反查源图（对上未重出的源图 = 旧口径头号嫌疑）
  B 本版声称的改动是否真落位（CHECKS，独立复核；生成器自述不算证据）
  C 陈旧/风险字符串零命中（STALE，命中须为 0）
  D 摘要字数（细则 ≤300 字；报告含空格与不计空格两个数）
  E 附图形式（mode/size/dpi + 抽样彩色像素占比 → 专利附图一般须黑白线条图）
  F 形式项扫描（检索式/IPC/摘要附图/附图标记/发明人/申请号/优先权）
  G 权项与实施例覆盖计数
  H 数字回源重算（源表给列名即可复算；不给则跳过）
  I 附带检查摘要清单

⚠️ 全部路径与关键词都是本项目/本版的旋钮，换项目只改 CONFIG。
⚠️ 持久内核可能缺 python-docx/PIL/pandas → 在系统 Python 下跑；`import` 失败只跳过该段，不中断。
"""
import os, re, glob, sys, hashlib, zipfile

# ============ CONFIG（换项目只改这里）============
DOCX = r"E:/专利/技术交底书_已填写_附图版_v13.docx"
DELIV = r"E:/专利/交付_跨物种衰老可替代性专利"
FIG_DIRS = [os.path.join(DELIV, "figures"), r"E:/专利/patent/figures"]
# 源图目录（用于内嵌图字节反查；越全越好）

# B 段：本版声称的改动 → 独立复核（label: 返回 True 才算落位）
CHECKS = {
    "①旧因果句已删": lambda t: "门控保留的正是" not in t,
    "①新增不作承诺表述": lambda t: "不对被输出集合的整体生物学同向率作承诺" in t,
    "②p 改写 p<0.005": lambda t: "p<0.005" in t,
    "③置换统一 200 次": lambda t: "200 次" in t,
    "⑤摘要节存在": lambda t: "说明书摘要" in t,
    "⑥版本号已升": lambda t: "版本 v13" in t,
    "⑦失效边界段": lambda t: "失效边界" in t,
}

# C 段：陈旧/风险字符串（命中必须为 0）
STALE = [
    "说明门控保留的正是具有真实跨物种同向信号的元件", "保守单侧口径", "各 10,000 次",
    "×10,000 次", "（p=0.005）", "独立生物学重复数较多", "v12",
    "可作为替代模型", "可迁移的衰老脆弱元件", "双侧对称约束",
]
# 数字千分位陷阱：正文可能写 “10,000”，裸搜 "10000" 会漏

# F 段：形式项（交底书阶段缺失正常，报出来给代理人）
FORM_KEYS = ["检索报告", "检索式", "查新", "IPC", "分类号", "摘要附图",
             "发明人", "申请号", "优先权", "附图标记", "标记"]

# H 段：数字回源（源表 + 列名 + 复算式）。不需要就设 None
SRC = r"E:/专利/P3_L1_data/M2_repro_gene_conservation_all.csv"
COLS = dict(z1="Z_human", z2="Z_monkey", p2="p_monkey", same="same_direction")
# ================================================


def hr(t):
    print("\n" + "=" * 78); print("## " + t); print("=" * 78)


# ---------- 读 docx（段落 + 表格单元格，均须纳入） ----------
try:
    from docx import Document
    doc = Document(DOCX)
    paras = [p.text for p in doc.paragraphs]
    text = "\n".join(paras)
    for tb in doc.tables:
        for r in tb.rows:
            for c in r.cells:
                text += "\n" + c.text
except Exception as e:
    print("!! 无法读 docx（系统 Python 缺 python-docx？）:", e); sys.exit(1)

hr("A. docx 结构与内嵌图反查")
print(f"文件: {DOCX}  {os.path.getsize(DOCX):,} B")
print(f"段落 {len(paras)} / 表格 {len(doc.tables)} / 内嵌图 {len(doc.inline_shapes)}")
src_figs = {}
for d in FIG_DIRS:
    for f in glob.glob(os.path.join(d, "*.png")):
        src_figs[os.path.getsize(f)] = f
try:
    z = zipfile.ZipFile(DOCX)
    media = [n for n in z.namelist() if n.startswith("word/media/")]
    print(f"word/media/* 共 {len(media)} 个，字节 → 源图反查：")
    for m in media:
        b = z.read(m)
        hit = src_figs.get(len(b), "** 未匹配到源图（新出图 or 旧口径残留，逐个 vision_describe）**")
        print(f"   {m} {len(b):>10,} B md5={hashlib.md5(b).hexdigest()[:12]} → {hit}")
except Exception as e:
    print("!! zip/media 解析失败:", e)

hr("B. 本版声称的改动 —— 独立复核（自述 ≠ 证据）")
for k, f in CHECKS.items():
    print(f"   {'✅' if f(text) else '❌'} {k}")

hr("C. 陈旧/风险字符串扫描（命中须为 0）")
for s in STALE:
    n = text.count(s)
    print(f"   {'❌ 命中 %d 次' % n if n else '✅ 零命中'}: {s}")

hr("D. 摘要字数（细则 ≤300 字）")
try:
    i = next(i for i, p in enumerate(paras) if "说明书摘要" in p or p.startswith("零、"))
    body = paras[i + 1] if i + 1 < len(paras) else ""
    ns = len(re.sub(r"\s", "", body))
    print(f"   {len(body)} 字符(含空格) / {ns} 字符(不计空格) → {'✅ 合规' if ns <= 300 else '❌ 超限'}")
except Exception as e:
    print("   解析失败:", e)

hr("E. 附图形式（专利附图一般须黑白线条图）")
try:
    from PIL import Image
    for f in sorted(glob.glob(os.path.join(FIG_DIRS[0], "*.png"))):
        im = Image.open(f)
        px = list(im.convert("RGB").resize((160, 160)).getdata())
        colored = sum(1 for r, g, b in px if max(r, g, b) - min(r, g, b) > 12)
        print(f"   {os.path.basename(f):46s} mode={im.mode:5s} size={im.size} "
              f"dpi={im.info.get('dpi','?')} 彩色占比={colored/len(px):.1%}")
except Exception as e:
    print("   PIL 不可用:", e)

hr("F. 形式项扫描")
for k in FORM_KEYS:
    print(f"   {'在册' if k in text else '❌ 缺失'}: {k}")

hr("G. 权项与实施例覆盖")
print(f"   '权利要求' 字样 {text.count('权利要求')} 次；'实施例' {text.count('实施例')} 次")
for k in re.findall(r"权利要求\s*\d+", text):
    pass
claims = sorted({int(m) for m in re.findall(r"权利要求\s*(\d+)", text)})
print(f"   出现过的权项编号: {claims}")

hr("H. 数字回源重算")
if SRC and os.path.exists(SRC):
    try:
        import pandas as pd
        from scipy.stats import binomtest
        df = pd.read_csv(SRC, low_memory=False)
        print(f"   源表 {SRC}\n   行数 {len(df):,} 列 {list(df.columns)}")
        z1, p2, sd = COLS["z1"], COLS["p2"], COLS["same"]
        a = df[(df[z1].abs() >= 12) & (df[p2] < 0.05)]
        same = int(a[sd].sum()); opp = int((~a[sd].astype(bool)).sum())
        print(f"   |Z1|>=12 & p2<0.05: n={len(a)} 同向={same} 反向={opp} 同向率={same/max(len(a),1):.4f}")
        print(f"   二项检验 vs 0.5: p = {binomtest(same, len(a), 0.5).pvalue:.3e}")
        print(f"   全局同向率 = {df[sd].astype(bool).mean():.4f}")
        if COLS.get("z2"):
            print(f"   corr(|Z1|,|Z2|)={df[z1].abs().corr(df[COLS['z2']].abs()):.4f}  "
                  f"corr(Z1,Z2)={df[z1].corr(df[COLS['z2']]):.4f}")
    except Exception as e:
        print("   复算失败:", e)
else:
    print("   跳过（未配 SRC 或文件不存在）")

hr("I. 交付目录库存（时间戳 = 判本版/旧版最快的线索）")
for sub in ["", "scripts", "figures", "results"]:
    d = os.path.join(DELIV, sub)
    if os.path.isdir(d):
        fs = sorted(glob.glob(os.path.join(d, "*")), key=os.path.getmtime, reverse=True)[:12]
        print(f"   [{sub or '.'}]")
        for f in fs:
            import time
            print(f"      {time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(f)))}  "
                  f"{os.path.getsize(f):>12,} B  {os.path.basename(f)}")
print("\n=== 探针结束 ===")
