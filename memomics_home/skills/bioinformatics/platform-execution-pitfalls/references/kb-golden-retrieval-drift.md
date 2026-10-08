# KB 黄金检索集失败：数据漂移 vs 代码回归（含 2026-10-01 晚 **根因推翻重写**）

> 首次实测 2026-10-01（会话 memomics-afd2d418）。触发场景：**全量 `pytest` 门禁红了 1 条，而本次改动完全没碰检索链路**——
> 需要在不改测试、不改 ranker、不改数据的前提下，给出「是谁弄坏的」的可复现结论。
>
> 🔴 **2026-10-01 深夜更正**：本文档 §4 原写「根因 = `*_empirical.yaml` 淹了语料」，**当晚用决定性模拟证伪**——
> 排除全部 empirical 后目标文件只从第 8 名升到第 7 名，**仍不在 top5**。真实机制见新的 §4。
> 教训写在 §8：**别在跑到决定性实验之前就把根因断言出去**（我先报了错误根因，然后被自己的下一轮实验推翻）。

## 1. 现象

```
.venv/Scripts/python.exe -m pytest -q --no-header -rf
→ pytest_real_exit = 1
→ FAILED webui/tests/test_kb_retrieval_golden.py::test_golden_retrieval_cases
→ 其余 ~460 用例：进度条仅 . 与 s（1 个 F、2 skipped）
```

失败断言原文（test 打印，直接给出 query / total / top5，是归因的**起点证据**）：

```
黄金检索集: 23/24 通过; 已知覆盖缺口: ['kb-23', 'kb-25']
E  AssertionError: 黄金检索集未通过：
E    kb-15 query='差异表达分析 方法' total=79 top5=[
E      'homo_sapiens/liver/aging/03_测序方法/bulk/liver_bulk_key_findings.yaml',
E      'mus_musculus/liver/aging/03_测序方法/bulk/mouse_liver_bulk_key_findings.yaml',
E      'mus_musculus/liver/aging/01_生物学知识/gene_sets.yaml']
```

## 2. 该测试的判据（读代码，别猜）

`webui/tests/test_kb_retrieval_golden.py`（`pytestmark = pytest.mark.kb`）：

- fixture = `webui/tests/fixtures/kb_retrieval_golden.json`（`top_k: 5`，26 条意图查询）
- 期望按**意图目录前缀 / 文件名子串**写（`expect_prefix` / `expect_contains`），**不是把当前输出抄成快照**——
  设计意图是「问人骨骼肌衰老就该回到 `Homo_sapiens/skeletal_muscle/aging/`」，检索退化时测试会真的变红
- `known_gap: true` 的用例**只统计不断言**（本次 kb-23 / kb-25）
- 判分函数：`kb_search._search_kb(query, species, tissue, direction)` → 取 `results[:top_k]` 的 `file`，归一化后做前缀/子串匹配

本例 kb-15 = `query='差异表达分析 方法'`，`expect_contains: ["deg-", "deg_", "deg.yaml"]` —— **top5 内必须出现任一 `deg*` 文件名**。

## 3. 四步归因（缺一不可）

| 步 | 动作 | 本例实测 |
|---|---|---|
| ① | 从失败日志**读出期望口径**（期望哪个目录/文件名） | kb-15 期望 top5 含 `deg-*` / `deg_` / `deg.yaml` |
| ② | **复现真实排名**，看目标文件到底排第几 | `total=80`；`deg.yaml` **存在但排 8–11 名**（lung fibrosis / heart cardiomyopathy / skeletal_muscle aging / mouse skeletal_muscle），top5 被 liver bulk + mouse gene_sets 占满 ⇒ **是「被挤下去」，不是「检索崩了」** |
| ③ | **数候选污染源**与写入时间 | `rglob("*_empirical.yaml")` = **76 个**；当日新增 6 个（含 `skill_evolution_empirical.yaml` / `wakeup-progress-check_empirical.yaml`） |
| ④ | **代码侧是否被改** | `git status --porcelain memomics/bio_tools/kb_search.py webui/tests/test_kb_retrieval_golden.py webui/tests/fixtures/kb_retrieval_golden.json` → **三处全空** |

四条齐了才下结论：**数据侧漂移，不是代码回归**。汇报时四条证据一起给（只抛结论 = 用户无法复核）。

现成探针：`scripts/kb_retrieval_golden_diag.py`（一次打印排名 / deg 文件清单 / 今日写入量 / `*_empirical.yaml` 总数）。

## 3.5 ⭐ 决定性一步：在**内存里**模拟「排除污染源后的排名」（本步推翻了我的第一版结论）

只数出「有 76 个污染文件」**不足以说明它们就是元凶**。必须做一个**排除实验**：把候选按假设过滤掉，看判据是否恢复。

做法（全程只读、不碰 KB / ranker / 黄金集）：

1. 按路径加载模块（`memomics/bio_tools/__init__.py` 会拉起 hermes-agent 依赖，不能走包导入）：
   `spec_from_file_location(...)` + `spec.loader.exec_module(mod)` —— 与黄金测试同样的加载方式。
2. `mod._init_fts()` 后取模块全局 `mod._fts_conn` / `mod._fts_file_map`，**忠实复刻** `_search_kb` 的 FTS 打分循环
   （同 SQL：`SELECT rowid, rank FROM kb_fts WHERE kb_fts MATCH ? ORDER BY rank LIMIT 200`；同 `_structured_boost`；同 `max(0,-rank)*10 + boost + 4*short_hits`）。
3. 复制 `terms/short_terms` 的构造逻辑（含 `_CJK_STOPWORDS` 跳过、`<3` 字符降级为加分项、`_SHORT_WORD_BLACKLIST` 加引号）。
4. 跑两栏：`skip_empirical=False`（现状）/ `True`（模拟）。**自证**：现状那栏的 top15 必须与真实 `_search_kb` 输出逐条一致，否则复刻有误、结论无效。
5. 再看判据（本例 = top5 是否出现 `deg*`）、以及期望命中项的**名次变化**。

实测结果（决定性）：

| 场景 | 候选数 | top5 内 empirical | `deg.yaml` 最高名次 | 判据 |
|---|---:|---:|---:|---|
| 排除前（现状） | 80 | 1 个（rank 1，382.0 分） | 第 8 名 | 失败 |
| 排除后（模拟迁移/降权） | 61 | 0 个 | **第 7 名** | **仍失败** |

⇒ **「排除 empirical」不能修 kb-15**。「收紧自进化写 KB 落点 + 迁移历史 76 个文件」这条方案当场被证伪。

**判据**：拿到「疑似污染源计数」后，**下一步永远是排除实验**，不是写结论。排除后判据仍失败 ⇒ 污染源不是（唯一）主因。

## 4. 真实根因机制（2026-10-01 更正版）：**长 findings 正文的裸 BM25 压过规范方法文件**

分数构成（`score = bm25*10 + 路径加分 + 文件名加分 + 4*短词命中`）实测拆解（排除 empirical 后的前 8 名）：

| 总分 | bm25*10 | 路径加分 | 文件名加分 | 文件 |
|---:|---:|---:|---:|---|
| 223.3 | **208.3** | 15.0 | 0.0 | `Homo_sapiens/liver/aging/03_测序方法/Bulk/liver_bulk_key_findings.yaml` |
| 129.7 | 114.7 | 15.0 | 0.0 | `Mus_musculus/liver/aging/03_测序方法/Bulk/mouse_liver_bulk_key_findings.yaml` |
| 122.5 | 107.5 | 15.0 | 0.0 | `Mus_musculus/liver/aging/01_生物学知识/gene_sets.yaml` |
| 118.2 | 103.2 | 15.0 | 0.0 | `Homo_sapiens/liver/aging/03_测序方法/RNA/liver_aging_key_findings.yaml` |
| 113.1 | 98.1 | 15.0 | 0.0 | `Mus_musculus/liver/aging/03_测序方法/RNA/mouse_liver_aging_key_findings.yaml` |
| 111.2 | 81.2 | 30.0 | 0.0 | `Mus_musculus/liver/aging/03_测序方法/RNA/default_kb_method.yaml` |
| **110.3** | **20.3** | 30.0 | **60.0** | `Mus_musculus/lung/fibrosis/03_测序方法/RNA/deg.yaml` ← 期望命中项 |
| **110.3** | **20.3** | 30.0 | **60.0** | `Homo_sapiens/heart/cardiomyopathy/03_测序方法/RNA/deg.yaml` ← 期望命中项 |

机制：
- 查询扩展词 = `差异表达分析 方法 / 差异表 / 异表达 / 表达分 / 达分析 / deg / differential expression / 差异表达 / 差异基因 / marker / findmarkers`；
- **规范方法文件**（`deg.yaml`）正文只沾少量词 ⇒ **裸 bm25 仅 20.3**，全靠**文件名含 `deg`** 的 `+60`（`_structured_boost` 的 fname 项）才勉强到 110.3；
- **结论型长文**（`*_key_findings.yaml`）正文反复出现「差异表达 / 差异基因 / marker」⇒ **裸 bm25 81–208**，不需要任何路径/文件名加成即可碾压；
- 该查询**没有 <3 字符短词**（短词项为空）⇒ 不是旧版「短词导致整条查询退回 os.walk 词频」那条老路。

⚠️ empirical 确实占了一个位置——它是 **rank 1（382.0 分）**，但**只占 top5 一席**；把 76 个全排除也只是整体上移一名。
⇒ 「运行记录污染检索」是**真实的卫生问题**，但**不是本例的病因**。两件事必须分开写，别把计数当成因果。

## 5. 处置（**未获用户批准前一律不动**）

改任一处置都会削弱现有护栏，属用户拍板范围。给候选（附「对本例是否有用」+成本/风险）：

| 候选 | 做法 | 对本例（kb-15） | 影响 |
|---|---|---|---|
| ① 检索侧排除/降权 empirical | `kb_search` 对 `*_empirical.yaml` 降权或排除 | ❌ 实测无效（deg 仅 8→7） | 卫生价值；动产品代码 |
| ② 写入侧改落点 + 迁移历史 76 个 | `skill_evolution` 把经验写到独立目录，不进 `03_测序方法` | ❌ 同上（实测迁移无重名冲突，但修不了本案） | 治本**卫生**问题；不碰检索逻辑 |
| ④ 改打分 / 意图路由 | 给「方法类文件」加权、或给 `*_key_findings` 结论型长文降权、或按查询意图要求 top5 含同类文件 | ✅ **唯一能真修本例的方向** | 改 ranker 语义，需同步复核黄金集口径 |
| ③ 接受漂移 | 把 kb-15 标记 `known_gap: true` | 立刻变绿 | **削弱护栏**（检索真退化时不再报警）；且要写明「非 empirical 所致」 |

⛔ **禁止**：为让套件变绿顺手改黄金集期望值 / 改 KB 数据 / 调 BM25 权重——都是 drive-by 改动，超范围。

## 6. 汇报边界（容易被自己糊过去的一点）

本次被改文件是**技能目录下的脚本**，它**不在 pytest 覆盖面内**（全库检索该脚本名，唯一命中是二进制 `state.db-wal`）。
于是会出现：平台标记该文件 `unverified`，而唯一能跑的仓库级门禁又卡在**无关的既有失败**上。

**正确写法**：分成两栏如实写清——
1. 本改动的验证 = 功能测试（`py_compile` + 各分支实跑，PASS/FAIL 计数）+ 相关子集 pytest（真实退出码）；
2. 仓库级门禁 = 1 条**与本改动无关**的既有失败（四步归因证据）。

**⛔ 不要把「其余测试全绿」包装成「这个改动被 pytest 验证了」**；也说清为什么这条 `unverified` 清不掉（不在覆盖面 + 无关失败）。

## 7. 取证小坑（本轮实吃）

- **`cmd | tail -N; echo $?` 拿到的是 `tail` 的退出码（恒 0）** ⇒ 会伪造「pytest 通过」。
  正解：`pytest ... > log/x.log 2>&1; RC=$?; echo "pytest_real_exit=$RC"`（重定向到文件、先赋值再 echo）。
- **该仓库 pytest 的汇总行不进重定向日志**（末行常是 `-- Docs: ...`）。别为「拿到汇总行」重跑整套：
  ① `pytest_real_exit` 是权威判据；② 进度条字符类里**无 `F` / `E`** 即无失败/错误；③
  `awk '/^[.sFEx]+ +\[/{n+=length($1)} END{print n}' <log>` 数执行总数。
- **自己写模拟函数时，返回元组的字段顺序要与调用方解包一致**：`sorted(seen.items())` 天然是 `(file, score)`，
  调用方按 `(score, file)` 解包就会报 `AttributeError: 'float' object has no attribute 'endswith'`（本轮实吃一次）。
  写 `return [(_s, _f) for _f, _s in sorted(...)]` 显式转换，别依赖字典 items 的顺序直觉。
- **只读取证脚本别写 `rm` / `rmdir` / `shutil.rmtree`**：`execute_python` 的删除保护会**整段拒执行**（本轮一次
  execute_python 调用被拦、一行没跑），落文件走 terminal 才跑通。整理类任务一律只用 move。

## 8. 🔴 方法论教训：**根因不要在决定性实验之前说出口**

本轮真实时序：
1. 我数出 `*_empirical.yaml` = 76 个（一个**相关**事实），当轮汇报就写成「**这是根因**：自进化写 KB 污染了检索排名」；
2. 下一轮按 L1 辩论裁决的 `next_actions` 做了 §3.5 的排除模拟，**当场推翻**自己的结论（deg 8→7，仍失败）；
3. 于是不得不向用户更正根因——多烧一轮，且让用户先接收了一个错误结论。

三条纪律：
- **「相关」≠「因果」**：数出污染源只证明它*参与排名*，不证明它*决定了结果*。要么做排除实验，要么把措辞降级为
  「候选元凶，未验证」并显式标注。
- **裁决里的 `reopen_condition` 是要执行的**：本轮辩论裁决自己写了「*若模拟不能恢复 top5，禁止宣布②+迁移可绿*」——
  这条既是护栏也是任务，照它做就能在汇报前抓住错误。**收到裁决先读 `next_actions[].blocks` 与 `reopen_condition`**。
- **更正要显式**：根因变了就在同一轮把「先前说法不成立 + 新证据」写清楚（含进 task_plan 与记忆），
  不要让旧结论作为基线被后续轮次继承。