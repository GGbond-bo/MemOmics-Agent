# 模式 C11 — 小批（N≤5）深度卡升级 + 指定落盘 + 单脚本机械门（2026-10-08 实测）

任务形态：`data/cards.json`（`list[dict]`，31 张薄卡）里**已有**卡，用户点名 n 列表
（本次 `n = 24, 26, 27, 29, 31`，全为「科研 AI agent」），要求**读全文升级成深读卡（中文，10 字段）**，
且**把结果写盘到指定 JSON 文件**、明确「**不要只回传内容**」。

## 交付配方（照抄）

```python
import json, os
out = {"cards": cards}                       # cards = {"24": {...10 字段...}, ...}
p = r"E:/MemOmics-Agent/results/<sid>/data/deep_cards_round2_t2.json"
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(os.path.getsize(p), p)                 # 本次 30096
assert json.load(open(p, encoding="utf-8"))["cards"].keys() == {"24","26","27","29","31"}
```

- 外层 key 固定 `"cards"`；卡键 = **原清单编号的字符串**。**另存新文件，不动 `cards.json`**（主代理合并）。
- 回复可贴同一份 JSON，但**不夹带方法论说明**（用户口径：「只输出我要的 JSON 字段」）。

## 落卡前单脚本机械门（一次断言全过再 dump）

```python
d = r".../data/text"; txt = {n: open(os.path.join(d, f"PMC{p}.txt"), encoding="utf-8").read()
                            for n, p in {24:"12936183",26:"11363023",27:"13345910",29:"12577674",31:"12847348"}.items()}
for n, c in cards.items():
    assert c["evidence_quote"] in txt[int(n)]     # 逐字可 grep（本次 5/5 True）
    assert len(c["architecture"]) >= 600          # 用户 brief 的字段下限
    assert len(c["limitations"]) >= 60
    assert len(c) == 10
```

本次实测长度（可作为「够不够深」的标尺）：architecture 912–1287、limitations 223–341、cards 各 10 字段。

## 读法：关键词偏移地图（对 90–580KB 长文最省调用）

```python
import re
for kw in ["patent similarity","coupling","TRL","Delphi","coverage","diversity",
           "benchmark","pass@","limitation","SWOT","FedAvg","Conclusion","Outlook"]:
    print(kw, [m.start() for m in re.finditer(kw, t)][:6])
# 再 print(t[a:b]) 定点读每段 ≤9500 字符
```
用途：定位 benchmark 指标（Table 1 五维）、limitations（4.6 Potential limitations / Conclusion and Outlook）、
模型版本清单、SWOT 等——**不用通读全文**。578KB 的 Chemical Reviews SDL 综述即靠此法定位到 Conclusion/Outlook。

## 本次 5 篇事实底稿（逐字数字 + 已校验 evidence_quote）

| n | 系统 | venue/year | 关键数字 | evidence_quote（`in txt`=True） |
|---|---|---|---|---|
| 24 | iDesignGPT | Nat Commun 2026 | 六挑战五维（中位）：LOI L2/L2/L3.5/L3；专利相似度 0.49/0.48/0.51/0.40；QFD-CR 61%/69%/93%/77%；TRL 5.5/5/5/4；耦合率 43%/37%/31%/28%；coverage 15.75→17.54(+11.4%)、diversity 0.92→1.09(+18.5%)、avg novelty 0.50→0.62；Delphi 6 专家 2 轮 Kendall's W；用户研究 n=11 与 n=37 | "Quantitative evaluations demonstrate that iDesignGPT systematically refines requirements, expands design spaces, and generates competitive design solutions with improved coverage, diversity, and novelty" |
| 26 | SDL 综述 | Chem Rev 2024 | **无量化评测**（综述）；软自主性 3 级 × 硬自主性 3 级 → Level 2–5；编排平台 ChemOS/Helao/AresOS/AiiDA/Fireworks/Snakemake；LLM agent Boiko/ChemCrow/CLAIRify/ORGANA | "Many Level 3 and 4 SDLs have already demonstrated impact in accelerating reaction process optimization, functional property refinement, and novel chemical and materials discovery" |
| 27 | Co-Scientist | Nature 2026 | Elo：203 goals（temporal buckets）+ 15 专家目标 vs o1/o3-mini-high/DeepSeek R1；盲评 11/15：rank 2.36、novelty 3.64、impact 3.09；湿实验 binimetinib IC50→2 nM、KIRA6 KG-1a 10 nM vs TK6 180 nM(18×)、CF 用 Chou–Talalay CI/HSA/Bliss、n=3 | "we introduce Co-Scientist, a multi-agent artificial intelligence (AI) system built on Gemini for structured scientific thinking and hypothesis generation" |
| 29 | MetaChat | Sci Adv 2025 | Stanford benchmark 101 题 5 类、pass@3、GPT-4o grader；AIM 消融 61.1/68.9/63.0/67.8/72.2/78.0/81.0%；LLM driver GPT-4o 81%、Llama3.3-70B 67.0%；FiLM WaveY-Net 30k 测试 MAE 0.055、400–700nm 0.098→0.043；7 模型版本见 Table 1 | "We introduce MetaChat, a multi-agentic design framework that can translate semantically described photonic design goals into high-performance, freeform device layouts in an automated, nearly real-time manner" |
| 31 | AAI+FL 农业 | Front Plant Sci 2025 | 全局 96.4%；DenseNet121 0.9526/MobileNetV2 0.9418；EfficientDet-D0 mAP@0.5 0.978/F1 0.961、YOLOv8 0.956/0.935；FedAvg 4 客户端 non-IID 20 轮；**无 LLM**（误用 agentic 标签） | "The federated global model achieved an accuracy of 96.4%, outperforming individual client models" |

## 要点提醒

- n=26 是**综述**：`benchmark`/`validation` 写「无/未做」，`models` 写「未披露（综述性质…盘点对象含 …）」，
  这套「不适用也要说明为什么」的填法见 SKILL.md C9 综述填法表。
- n=31 **无 LLM 而自称 agentic** ⇒ 在 `limitations` 的「可推断」段点名术语通胀（本赛道术语泛化的实例）。
- limitations 统一两段式：**「作者自陈：」+「可推断：」**（用户认第二段）。
- 事实全部来自 `data/text/PMC*.txt` 全文（**不要用 cards_source 里的截断预览字段**）。