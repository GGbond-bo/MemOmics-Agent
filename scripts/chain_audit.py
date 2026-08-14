# -*- coding: utf-8 -*-
"""chain_audit.py — MemOmics 各链路体检（2026-08-16，批L）。

检查面：
A. 注册表完整性（memomics 工具集声明 vs 实际注册、无重复、handler 可调用）
B. 文献库数据一致性（索引↔磁盘、空文件、引用库）
C. 知识库一致性（KB 目录、agent 写入条目的 YAML 合法性、search_knowledge 可检索）
D. 会话卫生（无测试残留会话、无 0 字节结果）
E. 配置健康（config.yaml 可解析、压缩阈值、模型配置）
F. 活服务器端点扫描（全部关键 API）
"""
import json
import os
import sys
import urllib.request

ROOT = r"E:\MemOmics-Agent"
os.environ.setdefault("HERMES_HOME", os.path.join(ROOT, "hermes_home"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "hermes-agent"))

PASS, FAIL, WARN = 0, 0, 0
results = []


def check(label, ok, detail=""):
    global PASS, FAIL, WARN
    PASS += bool(ok)
    FAIL += (not ok)
    results.append((("PASS" if ok else "FAIL"), label, str(detail)[:120]))


def warn(label, detail=""):
    global WARN
    WARN += 1
    results.append(("WARN", label, str(detail)[:120]))


# ── A. 注册表 ──
try:
    from tools.registry import registry
    import memomics.bio_tools  # noqa: F401
    import memomics.memomics_pipeline  # noqa: F401 (server.py 显式 import 注册)
    from toolsets import TOOLSETS  # type: ignore
except Exception as e:
    print("FATAL import:", e)
    sys.exit(2)

memomics_declared = set(TOOLSETS.get("memomics", {}).get("tools", []))

registered = set(registry.get_all_tool_names())
memomics_registered = set(registry.get_tool_names_for_toolset("memomics"))
check("registry: memomics 工具集已注册数", len(memomics_registered) > 10, len(memomics_registered))
missing = memomics_declared - registered
check("registry: 静态声明 vs 实际注册无缺失", not missing, sorted(missing))
# 关键工具存在
for t in ("scan_data", "save_knowledge", "kb_coverage", "literature_import",
          "kb_extract_from_paper", "summarize_paper", "save_reference",
          "memomics_pipeline", "rail_review", "debate_analysis", "generate_report",
          "vision_describe", "search_papers", "session_memory"):
    check(f"registry: 工具 {t}", t in registered)
# 重复注册检测（名称去重后数量一致）
all_names = registry.get_all_tool_names()
check("registry: 无重复工具名", len(all_names) == len(set(all_names)), len(all_names))
# handler 可调用性
bad = []
for n in memomics_registered:
    e = registry.get_entry(n)
    if e is None or not callable(getattr(e, "handler", None)):
        bad.append(n)
check("registry: 所有 memomics handler 可调用", not bad, bad[:5])

# ── B. 文献库一致性 ──
papers = os.path.join(ROOT, "hermes_home", "papers")
idx_path = os.path.join(papers, ".pdf_index.json")
idx = json.load(open(idx_path, encoding="utf-8")) if os.path.isfile(idx_path) else []
on_disk = {f for f in os.listdir(papers) if f.lower().endswith(".pdf")} if os.path.isdir(papers) else set()
in_idx = {e.get("file") for e in idx}
missing_files = [f for f in in_idx if not os.path.isfile(os.path.join(papers, f))]
orphan_files = sorted(on_disk - in_idx - {".pdf_index.json"})
empty_files = [f for f in on_disk if os.path.getsize(os.path.join(papers, f)) == 0]
check("文献库: 索引条目数", len(idx) > 0, len(idx))
check("文献库: 索引→磁盘无缺失文件", not missing_files, missing_files[:5])
check("文献库: 磁盘无孤儿 PDF（未入索引）", not orphan_files, orphan_files[:5])
check("文献库: 无 0 字节文件", not empty_files, empty_files[:5])
tagged = sum(1 for e in idx if e.get("tags"))
summed = sum(1 for e in idx if e.get("summary_done"))
kbed = sum(1 for e in idx if e.get("kb_done"))
check("文献库: 全部分类打标", tagged == len(idx), f"{tagged}/{len(idx)}")
print(f"  [info] 已全文提炼 {summed}/{len(idx)}，已入库 {kbed}/{len(idx)}")
refs = json.load(open(os.path.join(ROOT, "hermes_home", "references.json"), encoding="utf-8"))
check("引用库: references.json 条数 ≈ 索引条数", abs(len(refs) - len(idx)) <= 3, f"refs={len(refs)} idx={len(idx)}")
for ext in ("bib", "ris"):
    p = os.path.join(ROOT, "hermes_home", f"references.{ext}")
    check(f"引用库: references.{ext} 存在", os.path.isfile(p) and os.path.getsize(p) > 0)

# ── C. 知识库 ──
kb_root = os.path.join(ROOT, "memomics", "knowledge_base")
kb_files = []
for root, _dirs, fs in os.walk(kb_root):
    kb_files += [os.path.join(root, f) for f in fs if f.endswith(".yaml")]
import yaml
bad_yaml = []
for f in kb_files:
    try:
        yaml.safe_load(open(f, encoding="utf-8"))
    except Exception as e:
        bad_yaml.append((os.path.basename(f), str(e)[:60]))
check("知识库: YAML 全部可解析", not bad_yaml, bad_yaml[:3])
check("知识库: 条目数量", len(kb_files) > 0, len(kb_files))
try:
    from memomics.bio_tools.kb_search import search_knowledge
    r = json.loads(search_knowledge("exercise skeletal muscle signaling"))
    check("知识库: search_knowledge 可检索", "results" in r and r.get("total", 0) > 0,
          f"total={r.get('total')}")
except Exception as e:
    check("知识库: search_knowledge 可检索", False, e)

# ── D. 会话卫生（活服务器）──
BASE = "http://127.0.0.1:8899"
def get(p):
    return json.loads(urllib.request.urlopen(BASE + p, timeout=30).read())

try:
    sess = get("/api/sessions")
    sess = sess if isinstance(sess, list) else sess.get("sessions", [])
    test_titles = [s.get("title", "") for s in sess
                   if any(k in (s.get("title") or "") for k in ("批K", "批C冒烟", "批E冒烟", "诊断", "多意图"))]
    check("会话卫生: 无测试残留会话", not test_titles, test_titles[:5])
    running = [s.get("title", "") for s in sess if s.get("is_running")]
    check("会话卫生: 无卡死运行中会话", not running, running[:5])
    check("会话卫生: 会话总数", len(sess) > 0, len(sess))
except Exception as e:
    check("会话卫生: API 可用", False, e)

# ── E. 配置健康 ──
cfg = yaml.safe_load(open(os.path.join(ROOT, "hermes_home", "config.yaml"), encoding="utf-8"))
check("配置: config.yaml 可解析", cfg is not None)
check("配置: 压缩阈值 0.3（1M 窗口按 30% 触发）", cfg.get("compression", {}).get("threshold") == 0.3,
      cfg.get("compression"))
check("配置: model 已配置", bool(cfg.get("model")), cfg.get("model"))
check("配置: api_base 可用端点", "deepseek" in str(cfg.get("api_base") or "") or "opencode" in str(cfg.get("api_base") or ""),
      str(cfg.get("api_base"))[:50])

# ── F. 端点扫描 ──
endpoints = [
    ("/api/health", ["status"]),
    ("/api/version", ["version"]),
    ("/api/setup/status", ["needs_config"]),
    ("/api/env/check", ["python"]),
    ("/api/runtime", None),
    ("/api/resources", None),
    ("/api/kb", ["items"]),
    ("/api/kb/coverage", None),
    ("/api/kb/graph", None),
    ("/api/skills", ["total"]),
    ("/api/providers", None),
    ("/api/memory", ["entries"]),
    ("/api/literature/library", ["total"]),
    ("/api/literature/binding", None),
]
for path, keys in endpoints:
    try:
        d = get(path)
        ok = True
        if keys:
            ok = all(k in d for k in keys)
        check(f"端点 {path}", ok, str(d)[:80] if not ok else "")
    except Exception as e:
        check(f"端点 {path}", False, e)

# 写入型/参数型端点
try:
    d = get("/api/science/search?q=aging+muscle&source=arxiv&limit=2")
    check("端点 /api/science/search(arxiv)", bool(d.get("results")), len(d.get("results", [])))
except Exception as e:
    check("端点 /api/science/search(arxiv)", False, e)
try:
    d = get("/api/literature/summary?file_or_title=" + urllib.parse.quote("freeradbiomed"))
    check("端点 /api/literature/summary", d.get("ok") is not False, str(d)[:60])
except Exception as e:
    check("端点 /api/literature/summary", False, e)
try:
    d = get("/api/enforcement/memomics-00000000")
    check("端点 /api/enforcement/{sid}", isinstance(d, dict), str(d)[:60])
except Exception as e:
    check("端点 /api/enforcement/{sid}", False, e)

print()
print(f"=== 链路体检结果: {PASS} PASS / {FAIL} FAIL / {WARN} WARN ===")
for status, label, detail in results:
    if status != "PASS":
        print(f"  [{status}] {label} | {detail}")
sys.exit(1 if FAIL else 0)
