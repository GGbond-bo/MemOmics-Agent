# scTour 执行检查清单 — 详细参考

> 2026-07-08 会话教训整理。此文件记录 scTour 分析时必须遵守的 10 步执行链。

## 背景

2026-07-08 会话中，Agent 在未加载 `sctour-trajectory-inference` skill 的情况下直接写代码跑 scTour 分析，导致：
1. ❌ 结果目录路径错误（先放桌面，后放错 results/ 路径）
2. ❌ `log/` 目录完全缺失（无 analysis.log、debate_*.json、run_record_*.json）
3. ❌ `skill_evolution(action="record_run")` 未调用（事后补调）
4. ❌ `search_knowledge` 跳过（未查知识库）
5. ❌ `rail_review(pre/post)` 跳过
6. ❌ `debate_analysis` 跳过

**本清单是为了防止上述问题再次发生。**

## 10 步执行链（详细版）

### 步骤 1: search_knowledge

```python
# 必须调用，搜索物种+组织+方向+scTour 的相关参数
search_knowledge(
    species="human",  # 或用户指定的物种
    tissue="skeletal_muscle",  # 或用户指定的组织
    direction="aging",  # 或用户指定的方向
    query="scTour trajectory parameters"
)
```

**不跳过的原因**：知识库中可能已有同物种/同组织/同方向的 scTour 参数推荐，能直接复用省去调参时间。

### 步骤 2: skill_view（当前已加载 ✅）

```
skill_view(name="sctour-trajectory-inference")
```

**不跳过的原因**：此 SKILL.md 包含：
- 3 配置对比工作流（balanced/encoder/ODE）
- 参数范围（alpha_recon_lec, alpha_recon_lode, n_latent 等）
- 审查规则（rail_review pre/post）
- 目录结构（含 log/）
- 常见错误（SparseCSRView, dtype, OOM 等）

### 步骤 3: check_env

```python
check_env(
    packages=["sctour", "scanpy", "torch", "scikit-misc"],
    language="Python"
)
```

**注意**：`scikit-misc` 是隐式依赖（`flavor='seurat_v3'` 需要），scTour 不会自动安装。如果缺包，用 `pip install` 或 `uv pip install` 安装。

### 步骤 4: rail_review(pre)

```python
rail_review(
    phase="pre",
    module_id="sctour",
    required_packages=["sctour", "scanpy", "torch"]
)
```

前置审查检查：包是否齐、参数是否合理、数据是否准备好。

### 步骤 5: write_file

写脚本到 `results/<species>_<tissue>_<direction>_<date>/03_advanced/scTour/scripts/`

**结果基路径**：`results/`（项目根目录下的 `results/`，如 `MEMOMICS_HOME/results/`。**不是** `hermes-agent/results/`。2026-07-08 会话教训——memory 中误写导致日志放错位置，用户指出后才修正）

### 步骤 6: terminal

```bash
uv run python scripts/sctour_analysis.py
```

**禁止**：`&&` 连接多步骤。分步执行：预处理→训练→推断→可视化。

### 步骤 7: debate_analysis

```python
debate_analysis(
    topic="scTour multi-config comparison results",
    context="3 configs: balanced/encoder/ODE, KS test results, biological interpretation"
)
```

辩论内容：哪个配置最优？伪时间方向对不对？生物学结论合理吗？

### 步骤 8: rail_review(post)

```python
rail_review(
    phase="post",
    module_id="sctour",
    output_dir="results/.../scTour/"
)
```

**后置审查检查**：
- 图有没有生成？（每步至少 1 张，关键步骤 2-3 张）
- 图片是否空白/破损？（<5KB 或全白/全黑 → 重新出图）
- 伪时间数值范围是否合理？（[0, 1]）
- 结果是否与知识库一致？

### 步骤 9: skill_evolution（⚠️ 必须验证落盘，不可信任返回值）\n\n> **2026-07-08 会话教训**：6 次 `record_run` 调用中，前 4 次正常落盘，后 2 次返回 `{\"success\": true}` 但实际**未写文件**。用户追问\"为什么没有日志？\"后才被发现。**本步骤不可跳过，落盘验证不可跳过。**\n\n**通过时**（rail_review(post) 返回 passed=True）：

```python
skill_evolution(
    action="record_run",
    skill_name="sctour-trajectory-inference",
    script_name="sctour_analysis.py",
    species="human",
    tissue="skeletal_muscle",
    direction="aging",
    params_used="loss_mode=nb, n_top_genes=1000, 3 configs: balanced/encoder/ODE",
    result_summary="11,630 cells, scTour 3-config comparison completed",
    quality_score=8.5,
    notes="CPU mode works for 11k cells. Use GPU for >50k cells."
)
```

**失败时**（脚本报错）：

```python
skill_evolution(
    action="record_error",
    skill_name="sctour-trajectory-inference",
    script_name="sctour_analysis.py",
    species="human",
    tissue="skeletal_muscle",
    direction="aging",
    error_message="...",
    root_cause="...",
    fix_applied="..."
)
```

### 步骤 10: log/ 目录确认（⚠️ 双位置检查）\n\n执行完成后，**必须确认两个位置**都有日志文件：\n\n**位置 A — 分析结果目录（本次分析可追溯）：**\n\n```\nresults/.../scTour/\n└── log/\n    ├── analysis.log       # 分析全过程记录（手动写或自动生成）\n    ├── debate_*.json      # 辩论记录（debate_analysis 自动生成）\n    └── run_record_*.json  # 运行记录（skill_evolution 自动生成）\n```\n\n**位置 B — skill 的 `.run_logs/` 目录（跨分析复用）：**\n\n```\n~/.hermes/skills/bioinformatics/sctour-trajectory-inference/.run_logs/\n├── 脚本名_物种_组织_方向_日期.log       # record_run 记录\n└── 脚本名_物种_组织_方向_日期.err       # record_error 记录\n```\n\n> **2026-07-08 会话教训**：日志只放到了 `hermes-agent/results/.../log/`（错误路径），缺少 `results/.../log/`（正确路径）+ `.run_logs/` 中也缺少部分记录。用户两次追问（\"为什么没有自进化日志？\"\"日志不是要放到结果文件吗？\"）才补全。\n\n**缺任何一项 = 分析不完整，必须补写。**\n\n### 步骤 11（可选强化验证）：结果完整性自检\n\n分析完成后，在回复用户前执行一次快速验证：\n```bash\nls results/.../scTour/log/ && ls ~/.hermes/skills/bioinformatics/sctour-trajectory-inference/.run_logs/\n```

## 常见跳过原因及对策

| 跳过步骤 | 典型借口 | 实际后果 | 对策 |
|---------|---------|---------|------|
| search_knowledge | "我会写 scTour" | 参数可能不是最优 | 强制第一步，不可跳过 |
| skill_view | "SOUL.md 里看过" | 错过此 SKILL.md 的特定参数/坑 | 强制加载，SOUL.md 不包含技能细节 |
| rail_review(pre) | "包肯定装了" | 漏装的隐式依赖导致运行时错误 | 强制检查，不可跳过 |
| rail_review(post) | "图肯定生成了" | 图空白/破损/数量不够 | 强制检查，不可跳过 |
| debate_analysis | "结果很明显" | 生物学结论可能错误 | 强制辩论，不可跳过 |
| skill_evolution | "太麻烦了" | 下次分析无法复用本次经验 | 强制记录，不可跳过 |
| log/ 目录 | "忘了" | 分析不可追溯 | 强制创建，不可跳过 |