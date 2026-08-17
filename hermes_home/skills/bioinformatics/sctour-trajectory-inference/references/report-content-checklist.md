# scTour 报告内容清单（必查项目）

> 2026-07-08 会话经验：用户明确要求“把辩论结果、参数怎么来的、结论辩论全都写上去”。
> 此 checklist 用于每次报告生成前后逐条验证，防止遗漏。

---

## 🔴 强制包含（缺一不可）

### 1. 参数来源表
```python
param_source_table = make_table(
    ["参数名", "值", "来源", "依据"],
    [
         # 每个参数一行，来源可选：知识库/技能模板/辩论debate_00X/官方默认
        ["训练轮数", "200", "辩论 debate_003", "反方胜：200轮后loss已平台"],
        ["HVG数", "1000", "辩论 debate_002", "正方胜：足够捕获骨骼肌marker"],
        ...
    ]
)
```

### 2. 配置裁决表
展示各配置的量化指标对比，标注胜出配置（符号⭐）：
- 平均KS统计量（越高越好）
- 衰老分离度（Young vs Old的KS值）
- 运动效应分离度（Pre vs Post的KS值）
- 伪时间变化敏感度（Δ均值，越敏感越好）
- 训练时间

### 3. 所有图集
- **图片引入策略**（2026-07-08 验证通过）：本地查看用 `file:///` 绝对路径引用；需分享时用 base64 嵌入
- 每种配置的 overview UMAP + vector field
- 平衡版额外图：组间箱线图、亚群箱线图、运动效应图、衰老梯度图
- 多配置对比图：箱线图对比、KS热力图、Delta均值对比
- **总量不少于 15 张**（3 配置各 2 张 + 平衡版额外 6 张 + 对比 3 张）
- 每张图文件大小 > 5KB（<5KB 视为异常图，需重新生成）

### 4. 辩论记录（每轮）
- 辩题（topic）
- 正方论点 × 3（方法学/生物学/统计学，各自独立）
- 反方论点 × 4（方法学/生物学/统计学/历史记录，各自独立）
- 裁判裁决：winner + pro_score + con_score + decision + reasoning + action

### 5. 结论辩论
- 对最终生物学结论（如"运动逆转衰老"）的正反方独立辩论
- 裁判裁决 → 限定声明（如"部分效应可能来自急性运动反应"）

### 6. 最终结论
- 经辩论验证的结论（含限定条件）
- 可标注辩论提醒：`<span style="color:#888;font-size:12px">[辩论确认：...]</span>`

### 7. 自进化日志表
- 列出每一步的 `run_record_*.json`：脚本名/步骤、质量评分、关键经验
- 表格中文件名用缩写格式 `...{序号:04d}_run.json`（如 `...0000_run.json`）

---

## 🟡 建议包含

### 统计表
- 分组统计（type组：count/mean/std/median/min/max）
- 亚群统计（subcluster组：count/mean/std/median）
- KS检验表（21对比 vs 3配置 × 7组对比）

---

## 生成后验证命令（增强版）

### 方法一：Python 脚本验证（推荐）
```python
import os, re

report = "scTour_Complete_Report.html"

# 1. 检查文件大小
size = os.path.getsize(report) / 1024
assert size > 15, f"报告太小 ({size}KB)，可能缺内容"

# 2. 读取内容
with open(report, encoding='utf-8') as f:
    html = f.read()

# 3. 结构验证
assert html.startswith("<!DOCTYPE html>"), "缺少 DOCTYPE"
assert "</html>" in html, "缺少 </html>"
assert "</body>" in html, "缺少 </body>"

# 4. 图片完整性
img_cnt = html.count('<img ')
assert img_cnt >= 15, f"图片不足 ({img_cnt}/15)"

# 5. 所有图片文件存在（非 base64 模式）
for ref in re.findall(r'<img[^>]+src="file:///([^"]+)"', html):
    exist = os.path.exists(ref.replace("/","\\"))
    assert exist, f"图片不存在: {ref}"

# 6. 辩论完整性
debate_cnt = html.count("辩论 #")
assert debate_cnt >= 5, f"辩论段不足 ({debate_cnt}/5)"

# 7. 裁判裁决
judge_cnt = html.count("⚖")
assert judge_cnt >= 5, f"裁判裁决不足 ({judge_cnt}/5)"

# 8. 章节完整性
for sec in ["分析流程", "参数来源", "配置裁决", "辩论记录", "结论辩论", "自进化日志"]:
    assert sec in html, f"缺少章节: {sec}"

# 9. 自进化日志
for i in range(6):
    assert f"...{i:04d}" in html, f"缺少自进化日志 #{i}"

# 10. 参数来源标签
assert any(t in html for t in ["tag-kb", "tag-debate", "参数来源"]), "缺少参数来源标记"

# 11. 正反方辩论框
assert html.count('debate-box pro') >= 5, "正方辩论框不足"
assert html.count('debate-box con') >= 5, "反方辩论框不足"

print(f"✅ 报告完整性验证通过 ({img_cnt}张图, {debate_cnt}段辩论, {judge_cnt}次裁决)")
```

### 方法二：快速 Shell 验证
```bash
grep -c '<img' scTour_Complete_Report.html      # 图片数
grep -c '辩论 #' scTour_Complete_Report.html     # 辩论段数
grep -co '⚖' scTour_Complete_Report.html         # 裁判裁决
du -h scTour_Complete_Report.html                 # 文件大小
```

### 验证失败的处理
| 问题 | 原因 | 修复 |
|------|------|------|
| 图片不足 | HTML 中缺少图引用 | 检查 `comparison/figures/` 和 `run*/figures/` 目录中 PNG 数量 |
| 辩论不足 | 辩论 JSON 未读取或未渲染 | 检查 `log/debate_*.json` 文件数量和格式 |
| 裁判裁决不足 | 最后一轮可能用了"⚖️ 裁判最终裁决"变体 | 用 `html.count("⚖")` 而非精确字符串匹配 |
| 缺少参数来源 | HTML 中缺少 `tag-*` CSS 类 | 确认参数来源表已写入 |
| 自进化日志缺失 | 记录名称格式不匹配 | 检查 HTML 文本中包含 `...0000` 到 `...0005` |

---