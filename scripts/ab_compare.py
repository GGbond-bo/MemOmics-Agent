# -*- coding: utf-8 -*-
"""MiMo 记忆模式 vs 逐字全量 —— 效果 A/B 对比（2026-08-21）

用法（由外部编排）：
  1. python scripts/ab_compare.py seed <sidA> <sidB>   # 造两个相同内容的 250 条长会话 + 记忆文件
  2. 重启服务：场景B 带 MEMOMICS_AGGRESSIVE_COMPACT=1 MEMOMICS_AGGRESSIVE_THRESHOLD=30000
  3. python scripts/ab_compare.py ask <sidA>           # 逐字全量 3 问
  4. 重启服务：默认
  5. python scripts/ab_compare.py ask <sidB>           # 压缩态 3 问
"""
import asyncio, json, os, sys, sqlite3, time, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HERMES_HOME", r"E:\MemOmics-Agent\hermes_home")

WS = "ws://127.0.0.1:8899/ws"
DB = r"E:\MemOmics-Agent\hermes_home\state.db"
RESULTS = r"E:\MemOmics-Agent\results"

QUESTIONS = [
    "按会话记忆回答：数据文件路径是什么？出图必须带什么统计量？各一行即可。",
    "按会话记忆回答：绘图脚本放哪个目录？配色要求是什么？",
    "用 execute_code 读取 data/summary.csv 并打印行数，只要结果。",
]
EXPECT = [("MF_AUCell_meta.csv", "P 值"), ("scripts", "蓝"), ("execute_code", "")]


def _messages():
    """确定性 250 条真实风格消息：DEG/画图/富集/轨迹 + 3 条记忆要求 + 数值结果。"""
    msgs = []
    i = 0
    # 早期：任务 + 第一条记忆要求（数据路径 + P 值）
    seed = [
        ("user", "帮我分析 E:/骨骼肌锻炼/MF_AUCell_meta.csv 的 AUCell 打分，先看看结构。"),
        ("assistant", "数据加载完成：382MB，22 个打分列，10 个亚群，6 组样本。先做个体级聚合统计。"),
        ("user", "记住：数据文件固定是 E:/骨骼肌锻炼/MF_AUCell_meta.csv，以后出图必须带 P 值标注。"),
        ("assistant", "已记住。开始按五效应轴（Aging/T2D/ExYoung/ExOld/ExT2D）做效应矩阵统计。"),
        ("user", "跑 DESeq2 差异分析，比较 O_Pre vs Y_Pre。"),
        ("assistant", "DEG 完成：共 220 个基因，其中 117 个显著（padj<0.05），上调 61、下调 56。"),
        ("user", "把效应矩阵画成热图，CNS 风格。"),
        ("assistant", "FigA1_effect_matrix 已生成：22×5 效应热图，红蓝 Cohen's d + 星号，逆转率条形图在右侧。"),
        ("user", "跑 GO/KEGG 富集分析。"),
        ("assistant", "富集完成：GO BP 前 20 条已出气泡图，KEGG 通路 12 条显著（padj<0.05）。"),
        ("user", "用 Seurat 做一次 UMAP 聚类看看亚群边界。"),
        ("assistant", "UMAP 完成：10 个亚群边界清晰，LRP1B+(I) 与 Pure Type I 部分重叠。"),
        ("user", "轨迹分析用 Monocle3 还是 slingshot？"),
        ("assistant", "建议 Monocle3：用 as.cell_data_set() 构建，preprocess 后 Seurat UMAP 覆盖。"),
        ("user", "帮我看看 scoreInflammatory 在 OTUD1+(I) 的表达分布。"),
        ("assistant", "小提琴图 FigC1_OTUD1_I_scoreInflammatory 已生成，中位数 0.040，vs Pure Type I d=0.10。"),
    ]
    msgs += seed
    i += len(seed)
    # 中期：更多任务 + 第二条记忆要求（脚本目录 + 配色）
    mid_seed = [
        ("user", "记住：绘图脚本统一放 scripts/ 目录，配色统一用蓝橙，不用其他色系。"),
        ("assistant", "已记住脚本目录与配色约定。继续出 FigC1 系列。"),
    ]
    msgs += mid_seed
    i += len(mid_seed)
    topics = ["小提琴图", "火山图", "热图", "ECDF 图", "箱线图", "散点图", "柱状图", "dotplot"]
    for k in range(28):
        t = topics[k % len(topics)]
        msgs.append(("user", f"把 {t} 改一下配色和字号，主刊风格，不要遮挡。"))
        msgs.append(("assistant",
                     f"已按蓝橙配色更新 {t}：FigC{i}_v{k}.png 生成（300dpi），Arial 7pt，无网格线，图例无遮挡。"))
        i += 2
    # 晚期：汇总 + 第三条记忆要求
    msgs.append(("user", "记住：最终图都要输出 PNG+PDF+TIFF 三格式。"))
    msgs.append(("assistant", "已记住三格式要求。当前 FigC1 系列均含三格式。"))
    msgs.append(("user", "把五效应矩阵的逆转率排序画出来。"))
    msgs.append(("assistant", "逆转率图完成：代谢轴中位数逆转率 +0.21，衰老-炎症轴 -0.07。"))
    for k in range(20):
        msgs.append(("user", f"再检查一下第 {k} 张图的轴标签和显著性星号。"))
        msgs.append(("assistant", f"第 {k} 张图检查完毕：轴标签完整，星号位置正确，无截断。"))
    # 填充到 250 条
    while len(msgs) < 250:
        n = len(msgs)
        msgs.append(("user", f"把 FigC1 系列的第 {n % 12} 张重新渲染一版，保持蓝橙配色。"))
        msgs.append(("assistant", f"已重渲染：FigC1_{n % 12}_v{n}.png，三格式齐全，P 值星号保留。"))
    return msgs[:250]


def seed_sid(raw_sid):
    """创建会话(ws discover 拿真实 id) → 写入 250 条消息 → seed 记忆文件。返回 (raw, real)。"""
    import websockets

    async def _discover():
        async with websockets.connect(WS, max_size=256*1024*1024, open_timeout=10) as ws:
            await ws.send(json.dumps({"type": "chat", "session_id": raw_sid,
                                      "message": "只用一句话回复 OK。"}, ensure_ascii=False))
            start = time.time()
            while time.time() - start < 40:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                ev = json.loads(raw)
                if ev.get("type") == "session" and ev.get("session_id"):
                    return ev["session_id"]
        return None

    real = asyncio.run(_discover())
    if not real:
        raise RuntimeError("discover failed")
    msgs = _messages()
    db = sqlite3.connect(DB)
    now = time.time()
    db.executemany(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
        [(real, r, c, now - (len(msgs) - i) * 30) for i, (r, c) in enumerate(msgs)])
    db.commit(); db.close()
    # seed 记忆文件（模拟真实提取结果）
    rd = os.path.join(RESULTS, real)
    os.makedirs(os.path.join(rd, "scripts"), exist_ok=True)
    os.makedirs(os.path.join(rd, "data"), exist_ok=True)
    with open(os.path.join(rd, "REQUIREMENTS.md"), "w", encoding="utf-8") as f:
        f.write("数据文件固定是 E:/骨骼肌锻炼/MF_AUCell_meta.csv，出图必须带 P 值标注\n"
                "绘图脚本统一放 scripts/ 目录，配色统一用蓝橙\n"
                "最终图都要输出 PNG+PDF+TIFF 三格式\n")
    with open(os.path.join(rd, "task_plan.md"), "w", encoding="utf-8") as f:
        f.write("# FigC1 系列出图任务\n\n## Status: in_progress\n\n## Phase 2: 出图\n- 蓝橙配色/三格式\n")
    for fn in ("fig_v1.py", "fig_v2.R"):
        with open(os.path.join(rd, "scripts", fn), "w", encoding="utf-8") as f:
            f.write("# script\n")
    with open(os.path.join(rd, "data", "summary.csv"), "w", encoding="utf-8") as f:
        f.write("score,d\nA,0.1\nB,0.2\nC,0.3\nD,0.4\nE,0.5\n")
    print(f"seeded {raw_sid} -> {real} ({len(msgs)} msgs)")
    return raw_sid, real


def ask(sid):
    """对 sid 跑 3 个问题，输出每问的工具/答案/耗时。"""
    import websockets

    async def _turn(ws, msg, timeout=180):
        t0 = time.time(); final, deltas, tools = None, [], []
        await ws.send(json.dumps({"type": "chat", "session_id": sid, "message": msg}, ensure_ascii=False))
        while time.time() - t0 < timeout:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=12)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
            ev = json.loads(raw)
            if ev.get("session_id") and ev.get("session_id") != sid:
                continue
            t = ev.get("type")
            if t == "tool_start":
                tools.append(ev.get("tool"))
            elif t == "delta":
                deltas.append(ev.get("content", ""))
            elif t == "complete":
                final = ev.get("content", "")
                break
            elif t in ("cancelled", "error"):
                final = f"[{t}]"
                break
        return round(time.time() - t0), "".join(deltas) or (final or ""), tools

    async def _run():
        out = []
        async with websockets.connect(WS, max_size=256*1024*1024, open_timeout=10) as ws:
            for q, exp in zip(QUESTIONS, EXPECT):
                el, text, tools = await _turn(ws, q)
                hit = [e for e in exp if e and e.lower() in text.lower()]
                out.append({"q": q[:30], "elapsed": el, "tools": tools, "hit": hit, "answer": text.strip()[:220]})
                print(json.dumps(out[-1], ensure_ascii=False))
        return out

    return asyncio.run(_run())


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "seed":
        seed_sid(sys.argv[2])
    elif mode == "ask":
        ask(sys.argv[2])
