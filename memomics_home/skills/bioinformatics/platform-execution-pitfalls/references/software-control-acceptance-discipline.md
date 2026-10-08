# 软件操控 harness 的验收纪律（端到端实测 · 2026-10-04）

## 0. 适用场景
- 用户说「端到端验收测试」「实测一次真实软件操控」「验收这个 CLI/harness」「跑一遍给我原始 JSON」
- 任何改动 desktop-software harness（cli-anything 系列、自建 COM/ExtendScript 桥）之后的验证
- 用户给了「验收标准 1)…5)」这类清单，且要求按「命令 → 原始 JSON → 产物路径」逐条列

## 1. 被验对象在验收期间必须冻结 —— 修复只在「隔离副本」上验证

现场 hotfix 被验 harness 源码 = 测到的不是原 baseline + 原缺陷被掩盖。正确做法：

```bash
# 副本（原 baseline 一个字节都不改）
cp -r <原 harness 目录> <results>/<sid>/software_control/isolated_patch_harness
# 在副本上 patch，再用 PYTHONPATH 抢在 editable 安装之前加载副本
PYTHONPATH=<isolated_patch_harness> .venv/Scripts/python.exe -m cli_anything.<软件> --json <子命令>
```

- 失败现场（exit code + stderr + 源码行号）**完整留档**，不可覆盖；
- 副本拿到 `rc=0` 只证明「修法有效」，**不能**据此宣称「被验对象已通过」；
- 补丁以 `文件:行号 + 单行 diff` 交给用户拍板；改动 `pip install -e` 的 editable 树 = 变更已装基线，需授权。

## 2. 回复固定「命令 → 原始 JSON → 产物路径」三件套

用户明确要求过：**不要只说"成功"**。每条列清：

| 项 | 要求 |
|---|---|
| 命令 | 完整可复制（含 `--json` 位置、全部参数） |
| 原始 JSON | **原样粘贴**，含 `exit_code`；乱码也照贴（那本身是证据） |
| 产物路径 | 绝对路径 + **字节数**（多产物用一张表列全） |

失败项**同样**按三件套给 —— fake success 比失败严重得多。
一次批量取数，别逐张分轮核对（会被判循环失控，见 SKILL.md 坑 0）。

## 3. 导出图必须走「独立反证链」（对抗 rail_review 启发式误报）

PNG 只有几 KB 时 rail_review 判「图片太小 = 疑似空白图」，而**纯色图压缩后本就只有几 KB**。三件套反证：

1. `vision_describe` → 色彩分布 + OCR（置信度）+ ASCII 亮度图轮廓；
2. `sha256sum <源> <留档>` → 两份逐字节一致；
3. 原始 JSON 的断言字段：`png_exists` / `png_bytes` / `pathitems` / `textframes` / `pathitems`。

**绝不为了跨过体积阈值而放大分辨率或加噪重生成**（Goodhart 偏差，污染验收信号）。
`Output directory not found` 才是常见**真因**（目录没建）→ 先建目录再重跑 review。

## 4. 产物留档：`install -D` 一步建目录 + 复制

```bash
install -D -v "<临时产物路径>" "<results>/<sid>/software_control/cli_tests/<名字>"
```
`-D` 自动创建父目录 —— 省掉"复制进不存在的目录"的返工。命名带序号前缀（`01_doctor.json`、`02_probe.json`、
`03_gradient_probe_BASELINE_failed.json`、`04_gradient_probe_PATCHED_isolated.json`）便于一次性交代清楚。

## 5. 中文回显乱码 ≠ 渲染乱码

`--json` 返回的 `text` 字段中文可能乱码（COM→ExtendScript 的 GBK 空心），但**文档内渲染是正常的**。
判定以**导出产物 + OCR** 为准，禁止据回显断言"中文写坏了"。同一现象也出现在 ExtendScript 报错里：
`Error 2: viaCollection 未定义` 在中文 locale 下显示为乱码（`δ`），读报错要能还原真实变量名。

## 6. 实战证据链样例（可直接照抄格式）

```json
// doctor（exit 0）—— 附带安全信息：doc_count=0 表示无用户文档打开
{"bridge": true, "cscript": "C:\\WINDOWS\\system32\\cscript.EXE",
 "illustrator": {"doc_count": 0, "active_doc": null}}

// probe 隔离写测试（exit 0）
{"pathitems": 1, "textframes": 1, "text": "MemOmics ?ٿز?? 2026-10-04", "size": 14,
 "png": "C:\\...\\Temp/memomics_cli_probe.png", "png_exists": true, "png_bytes": 3088}
// 反证：400x300、5 色(#e0e0e0 60.9%/#e04040 33.5%/…)、OCR 1.0 读出文字、
//       sha256 源=留档=7eab1e2651dc58204c8c7b7c2131f0ef9cf204d175a72626e2b3ccda6a3df1a1

// gradient-probe 原 baseline（exit 2，缺陷留档）
{"error": "bridge failed rc=2: JS_FAIL|Error 2: viaCollection 未定义. Line: 73 -> ..."}
// 根因：illustrator_backend.py:331 使用 viaCollection 但全文件无声明（同段 applied/viaGradientColor 都有 var）
// 修法：在其前插一行  var viaCollection = false;

// 隔离副本补丁后（exit 0）
{"gradients_collection": 5, "swatch_typenames": ["Swatch"], "applied_via_swatch": false,
 "applied_via_collection": false, "applied_via_gradientcolor": true, "error": null, "pathitems": 1}
```

## 7. 跑这类验收一定会踩到的门禁副作用

| 现象 | 去哪查 |
|---|---|
| 并行多条 terminal，只有第一条放行 | 本 skill **坑 -1**（terminal→record_run→terminal 串行） |
| 一轮里 2~3 次同类只读核验 → 被判「循环失控」 | 本 skill **坑 0**（核验合并成一次） |
| 搜 harness 目录返回 0 命中（`results/` 被 gitignore） | 本 skill **坑 -2**（改用文件级 path 搜） |
| rail_review 判「图片太小/疑似空白」 | 本 skill **坑 -3** + 本文第 3 节 |
| `代码过短 (N 行)` | 审查器按分析脚本口径判的 → 如实说明口径不匹配，不补假代码 |