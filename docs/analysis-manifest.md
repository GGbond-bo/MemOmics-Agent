# 结果完成契约（analysis_manifest 协议）— v1

借鉴 OpenAI4S 的 `host.submit_output` 完成契约：分析结束时，agent 提交一份**结构化清单**，
结果面板据此展示版本、指标、溯源，而不是只看到一堆散文件。

## 文件位置

```
<results_dir>/
  analysis_manifest.json      # 最新清单（始终指向最新版本）
  analysis_manifest.v1.json   # 版本 1（历史保留，永不覆盖）
  analysis_manifest.v2.json   # 版本 2（每次提交版本号 +1）
```

## 字段定义

```json
{
  "schema": "memomics.analysis_manifest.v1",
  "version": 1,
  "title": "分析标题",
  "created_at": "2026-08-08 22:00:00",
  "model": {"provider": "deepseek", "model": "deepseek-v4-flash"},
  "provenance": {
    "data_paths": ["E:/data/raw/sample1.rds"],
    "params": {"species": "human", "min_cells": 3},
    "env": {"conda_env": "scanpy310", "packages": {"scanpy": "1.10.1"}},
    "git": {"commit": "dc83fb7e", "dirty": false}
  },
  "metrics": {"n_cells": 12345, "n_genes": 20000, "auc": 0.92},
  "artifacts": [
    {"path": "Figures/pca.png", "type": "figure", "size": 123456},
    {"path": "results.csv", "type": "table", "size": 2048}
  ],
  "notes": "分析说明"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema` | 自动 | 协议标识，服务端写入 |
| `version` | 自动 | 版本号，服务端递增 |
| `title` | 建议 | 分析标题（展示用） |
| `created_at` | 自动 | 提交时间（可覆盖） |
| `model` | 自动 | 提交时的模型（可覆盖） |
| `provenance.data_paths` | 建议 | 输入数据路径 |
| `provenance.params` | 建议 | 关键参数 |
| `provenance.env` | 建议 | conda 环境 + 关键包版本 |
| `provenance.git` | 自动 | 服务端 git commit + dirty（可覆盖） |
| `metrics` | 建议 | 关键数值指标（面板展示） |
| `artifacts` | 建议 | 产出文件清单 `[{path, type, size}]`，type ∈ figure/table/report/other |
| `notes` | 可选 | 分析说明 |

## 提交方式

- **API**：`POST /api/results/manifest`，body `{session_id, manifest}`，返回 `{ok, version, path}`
- **agent 工具**：`submit_output`（待接入，与 API 同语义）
- 服务端自动补全：`schema`/`version`/`created_at`/`model`/`provenance.git`

## 读取

- `GET /api/results?sid=<sid>&path=` 返回 `manifest`（最新）+ `manifest_versions`（全部版本号）
- 前端可展示版本切换（v1/v2/v3 对比）
