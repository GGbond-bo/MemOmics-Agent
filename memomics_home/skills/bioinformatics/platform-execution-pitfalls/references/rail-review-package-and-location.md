# rail_review 包检查与环境推断：三个实测坑（2026-10-13）

> 触发场景：`rail_review(pre)` 报某包缺失但该包明明装了；或审查位置被推断成集群、与本机实际执行环境不符。

## 坑 1：`required_packages` 只列非基础包（base 包会被误报缺失）

| 传入 | 结果 |
|---|---|
| `required_packages=["pheatmap","gtable"]`（只列非基础包） | `should_proceed: true`、`missing_packages: []`、warnings 仅「✅ 包齐（本机）」 |
| 把 base 包（`grid`/`stats`/`utils`/`methods`）也列进去 | 实测被报成**缺失** —— 误报（检查跑在另一套解释器/库上，base 包不可能真的缺） |

**对策**：列包清单时**剔除 base / recommended 包**，只列真正需要安装的（pheatmap、ComplexHeatmap、openxlsx…）。
被误报时**不要**去装 base 包，也不要中止任务——base 包一定在。

## 坑 2：`location` 不传会被自动推断，且可能推断到错误的执行环境

实测一次 `rail_review` 输出：

```json
"location": "cluster",
"location_source": "inferred",
"node": "ssh23",
"env": "R4.41",
"location_basis": "自动推断：本机有常驻集群会话 s-20261009-154804-vf9s @ssh23（env=R4.41, 状态=active）"
```

即：**本机跑的脚本被按集群环境做包检查**（本机是 R 4.5.3，审查却按集群 R4.41 的包清单判）。

**对策**：**本机任务一律显式传 `location="local"`**。传了以后审查输出首行会回显：

```
📍 审查位置：本机 —— 显式指定（本机 R/Python 包清单）；依据：调用方显式指定 location=local
```

只有真在集群节点上跑时才用推断（或显式指定 cluster/env）。

## 坑 3：`warnings` ≠ 失败（判据只看 `passed`）

`rail_review(post)` 常见 warnings：

```json
"passed": true,
"warnings": ["No result files found in output directory",
             "No error handling in code (tryCatch/try)"]
```

- `No result files found in output directory` —— `output_dir` 传的目录名与实际产物目录不一致（或产物落在子目录）就会误报。**产物是否真落盘以磁盘实测为准**（`os.path.getsize` / `ls -l`）。
- `No error handling in code` —— 提示性，不是阻断。

**判据：只看 `passed` 字段。** 不要因为 warning 就重跑一遍分析；也不要把 warning 当"已验证通过"的替代品（图是否非空仍须自己实测）。

## 相关

- `rail_review(post)` 需要**完整脚本正文**才有意义（<200 字符会被判"过短"）；跑完 terminal 后用 `read_file` 取脚本全文再传入。
- 与 `rail_review` 相邻的门禁：terminal 串行（铁律 24）、`skill_evolution(record_run)` 必需——见本 skill 主文件的坑表。