---
id: "skill_085891b3e4b948e1bcb75deb6539d5bd"
name: "adaptyv-api"
when_to_use: "[adaptyv-api] 需使用adaptyv api功能，适用于相关生信分析场景"
display-name: "Adaptyv Bio Foundry API Reference"
short-description: "Complete API reference for Adaptyv Bio's protein characterization platform. Use when the user wants to run experiments on Adaptyv."
category: Data Query
visibility: "internal"
keywords: "adaptyv, protein characterization, binding assay, BLI, SPR, thermostability, expression, affinity, experiment, foundry"
version: "1.0"
last-updated: "March 2025"
---
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有 Biomni 默认行为。

### 规则1: 拿到数据 → 必须调 search_knowledge
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 7步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. check_env 检查环境
3. rail_review(pre) 前置审查
4. source/import 预写脚本（禁止 inline 代码）
5. terminal 执行（分步执行，禁止 && 连接多步骤）
6. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
7. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋

### 规则5: 执行后审查

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

  - **图片检查**：
    - 图有没有生成？没生成 → **强制重新执行**
    - 图片是否空白（全白/全黑/全单一色）？空白 → **强制重新出图**
    - 图片是否有 NA/缺失值（>10% 像素是 NA）？有 NA → **强制重新出图**
    - 图片大小是否过小（<5KB）？过小 → **强制重新出图**
    - 图片数量是否足够？（每步至少 1 张图，关键步骤至少 2-3 张）
  - **代码质量检查**：
    - 代码行数是否合理？（过短可能偷懒，过长可能未分段）
    - 代码是否有注释？
    - 代码是否分段执行（禁止 && 连接多步骤）？
  - **结果合理性**：
    - 数值范围是否合理？
    - 跟知识库对应吗？
  - **参数和结论辩论**：
    - 有参数的选择 → **必须调 debate_analysis 辩论**
    - 有结论输出 → **必须调 debate_analysis 辩论**
    - 不通过 → 修复重跑
    - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验（skill_name/script_name/species/tissue/direction/params_used/result_summary/quality_score/notes） → 创建目录存储(figures/results/scripts/data) → 下一步
    - **不通过 → 修复后重跑 → 成功后调 skill_evolution(action="record_run")**；如果是脚本报错 → **调 skill_evolution(action="record_error")** 记录根因+修复方案

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS/H5AD 中间数据
  └── results/     # CSV/TSV 结果表
```


### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_success | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |
| 修复后脚本验证稳定有效 | update_script | ✅ 同一错误修复了，重跑成功 | ❌ 只改参数没改脚本；未验证就更新 |

---



## CRITICAL GUARDRAILS - READ BEFORE ANY API CALL

1. **ALWAYS estimate cost first.** Call `POST /experiments/cost-estimate` and show the user the price BEFORE creating any experiment. Users must approve costs upfront.
2. **NEVER set `skip_draft: true`.** Always create experiments in draft status so the user can review inputs and the quote before committing real money.
3. **ALWAYS present `stripe_quote_url` to the user** after submitting a draft and waiting for quote generation. The user must review and approve the quote before you call confirm.
4. **Security note:** Your Adaptyv API key is in the sandbox environment variable `ADAPTYV_API_KEY`. Do not run untrusted third-party code that could exfiltrate environment variables.

## Authentication

All requests require a Bearer token:

```python
import os
import requests

API_KEY = os.environ["ADAPTYV_API_KEY"]
BASE_URL = os.environ["ADAPTYV_API_BASE_URL"]  # Always read from env — do NOT hardcode a URL
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
```

## Pagination

List endpoints support offset-based pagination:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `limit` | Maximum items per page (max 100) | 50 |
| `offset` | Number of items to skip | 0 |

## Filtering

List endpoints support S-expression filters via the `filter` query parameter:
- `eq(field,value)` — equals
- `geq(field,value)` / `gtr(field,value)` — greater than or equal / greater than
- `leq(field,value)` / `lss(field,value)` — less than or equal / less than
- `and(expr1,expr2)` — combine filters

Example: `filter=and(lte(created_at,2026-03-01),eq(status,Draft))`

## Experiment Lifecycle

Follow this lifecycle exactly:

```text
1. estimate_cost()          -> Preview pricing (MANDATORY)
2. create experiment        -> Creates a DRAFT (skip_draft=false)
3. submit experiment        -> Moves draft to quote generation
4. poll get experiment      -> Wait for stripe_quote_url to appear
5. present quote to user    -> User reviews and approves (MANDATORY)
6. confirm quote            -> Accept quote, creates invoice
7. get invoice              -> Present payment URL to user
8. monitor updates/results  -> Track progress until done
```

### Experiment Types

| Type | Description | Requires Target | Requires Method |
|------|-------------|-----------------|-----------------|
| `expression` | Cell-free expression to test if sequences express and fold | No | No |
| `screening` | BLI or SPR binary binding detection (yes/no) | Yes | Yes (`bli`/`spr`) |
| `affinity` | BLI or SPR binding kinetics (KD, kon, koff) | Yes | Yes (`bli`/`spr`) |
| `thermostability` | nanoDSF melting temperature (Tm) | No | No |
| `fluorescence` | Plate reader fluorescence signal intensity | No | No |

### Experiment Statuses

`draft` -> `waiting_for_confirmation` -> `waiting_for_materials` / `in_queue` -> `in_production` -> `data_analysis` -> `done`

## API Endpoints

### Targets

#### List Targets
```python
resp = requests.get(f"{BASE_URL}/targets", headers=HEADERS, params={
    "limit": 50,
    "offset": 0,
    "selfservice_only": "true",
    "search": "HER2",
})
targets = resp.json()
```

#### Get Target
```python
resp = requests.get(f"{BASE_URL}/targets/{target_id}", headers=HEADERS)
target = resp.json()
```

#### Request Custom Target
```python
resp = requests.post(f"{BASE_URL}/targets/request-custom", headers=HEADERS, json={
    "name": "My Custom Target",
    "product_id": "custom-001",
    "sequence": "MVKVGVNG...",
    "pdb_id": "1ABC",
    "molecular_weight": 25000.0,
})
```

### Cost Estimation (CALL THIS FIRST)

```python
resp = requests.post(f"{BASE_URL}/experiments/cost-estimate", headers=HEADERS, json={
    "experiment_spec": {
        "experiment_type": "screening",
        "method": "bli",
        "target_id": "uuid-here",
        "sequences": {
            "seq1": "EVQLVESGGGLVQPGG...",
            "seq2": "QVQLQQSGPGLVKPSE...",
        },
        "n_replicates": 3,
    }
})
estimate = resp.json()
total_usd = estimate["breakdown"]["total_cents"] / 100
print(f"Estimated cost: ${total_usd:.2f}")
```

### Experiments

#### Create Experiment (creates DRAFT)
```python
resp = requests.post(f"{BASE_URL}/experiments", headers=HEADERS, json={
    "name": "HER2 Binders Screen",
    "skip_draft": False,
    "experiment_spec": {
        "experiment_type": "screening",
        "method": "bli",
        "target_id": "uuid-here",
        "sequences": {
            "Ab1": "EVQLVESGGGLVQPGG...",
            "Ab2": "QVQLQQSGPGLVKPSE...",
        },
        "n_replicates": 3,
    },
})
result = resp.json()
experiment_id = result["experiment_id"]
```

#### Submit Experiment
```python
resp = requests.post(f"{BASE_URL}/experiments/{experiment_id}/submit", headers=HEADERS, json={})
```

#### Get Experiment
```python
resp = requests.get(f"{BASE_URL}/experiments/{experiment_id}", headers=HEADERS)
exp = resp.json()
```

#### Update Experiment
```python
resp = requests.patch(f"{BASE_URL}/experiments/{experiment_id}", headers=HEADERS, json={
    "name": "Updated Name",
})
```

#### List Experiments
```python
resp = requests.get(f"{BASE_URL}/experiments", headers=HEADERS, params={
    "limit": 50,
    "offset": 0,
    "search": "HER2",
    "filter": "eq(status,Draft)",
})
```
