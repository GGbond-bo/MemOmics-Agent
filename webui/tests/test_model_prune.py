# -*- coding: utf-8 -*-
"""模型剪除/恢复逻辑的离线回归（2026-10-22 用户需求：「只保留联通的模型」）。

设计：**不复制实现**。直接从 webui/server.py 抽取 _prune_models_from_saved /
_restore_pruned_models 两个函数的源码，在受控命名空间里 exec 执行——这样测的
永远是真实实现，不存在「测试里的参照实现过期」问题（之前吃过一次亏）。
"""
import io
import json
import os
import re
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_PY = os.path.join(HERE, "..", "server.py")


def _extract_funcs():
    """从 server.py 抽取两个函数的源码（到下一个顶层 def/@app 或文件尾）。"""
    src = io.open(SERVER_PY, encoding="utf-8").read()
    out = {}
    for fn in ("_prune_models_from_saved", "_restore_pruned_models"):
        m = re.search(r"^def " + fn + r"\(.*?(?=^\S|\Z)", src, re.S | re.M)
        assert m, f"server.py 里找不到 {fn}"
        code = m.group(0)
        # 去掉行尾可能的 CRLF 残留（抽取时已按 \n 读取，这里防 CR）
        out[fn] = code.replace("\r", "")
    return out


def _namespace(path):
    """构造宿主命名空间：_provider_keys + _save_provider_keys 落到临时文件。"""
    ns = {
        "_provider_keys": {"demo": {
            "api_key": "sk-demo-key-123456",
            "models": [{"id": "m-ok-1"}, {"id": "m-ok-2"}, {"id": "m-bad-1"}, {"id": "m-bad-2"}],
            "models_source": "https://example.invalid/v1/models",
            "probe": {
                "results": {
                    "m-ok-1": {"id": "m-ok-1", "usable": True, "status": 200, "error": "", "ms": 100},
                    "m-ok-2": {"id": "m-ok-2", "usable": True, "status": 200, "error": "", "ms": 120},
                    "m-bad-1": {"id": "m-bad-1", "usable": False, "status": 400, "error": "协议不支持", "ms": 90},
                    "m-bad-2": {"id": "m-bad-2", "usable": False, "status": 402, "error": "端点停用", "ms": 80},
                },
                "known_ids": ["m-ok-1", "m-ok-2", "m-bad-1", "m-bad-2"],
            },
        }},
        "datetime": datetime,
    }
    ns["_save_provider_keys"] = lambda: io.open(path, "w", encoding="utf-8").write(
        json.dumps(ns["_provider_keys"], ensure_ascii=False, indent=2))
    return ns


def main():
    funcs = _extract_funcs()
    print("✅ 已从 server.py 抽取真实实现:",
          ", ".join(f"{k}({len(v.splitlines())} 行)" for k, v in funcs.items()))

    tmpdir = tempfile.mkdtemp(prefix="memomics_prune_")
    path = os.path.join(tmpdir, "provider_keys.json")
    ns = _namespace(path)
    for code in funcs.values():
        exec(compile(code, f"<server.py:{code.splitlines()[0][:40]}>", "exec"), ns)
    prune, restore = ns["_prune_models_from_saved"], ns["_restore_pruned_models"]

    print("\n=== 1) 剪除：实测不可用的摘掉，可用的保留 ===")
    removed = prune("demo", ns["_provider_keys"]["demo"]["probe"]["results"])
    print("  摘掉:", removed)
    assert removed == ["m-bad-1", "m-bad-2"], removed
    kept = [m["id"] for m in ns["_provider_keys"]["demo"]["models"]]
    print("  剩余:", kept)
    assert kept == ["m-ok-1", "m-ok-2"], kept
    pruned = ns["_provider_keys"]["demo"]["probe"]["pruned"]
    print("  pruned 记录:", pruned)
    assert pruned["ids"] == ["m-bad-1", "m-bad-2"] and pruned.get("at")

    print("\n=== 2) 再剪一次：清单里已没有它们，但仍须记进 pruned（恢复入口要可见）===")
    again = prune("demo", ns["_provider_keys"]["demo"]["probe"]["results"])
    print("  返回:", again)
    assert set(again) == {"m-bad-1", "m-bad-2"}, again
    assert ns["_provider_keys"]["demo"]["probe"]["pruned"]["ids"] == ["m-bad-1", "m-bad-2"]
    print("  ✅ 标记保持可见（本轮实测踩到的坑：丢了标记就没法恢复）")

    print("\n=== 3) 恢复：回到清单 + 带上次失败原因 ===")
    back = restore("demo")
    print("  恢复:", back)
    ids = [m["id"] for m in ns["_provider_keys"]["demo"]["models"]]
    print("  清单:", ids)
    assert set(ids) == {"m-ok-1", "m-ok-2", "m-bad-1", "m-bad-2"}
    errs = {m["id"]: m.get("_last_probe_error") for m in ns["_provider_keys"]["demo"]["models"]
            if m.get("_restored")}
    print("  失败原因回填:", errs)
    assert errs["m-bad-1"] == "协议不支持" and errs["m-bad-2"] == "端点停用"
    assert "pruned" not in (ns["_provider_keys"]["demo"]["probe"] or {})
    print("  ✅ pruned 标记已清除")

    print("\n=== 4) 边界：空结论 / 空清单不炸、不误删 ===")
    ns["_provider_keys"]["demo"]["probe"] = {}
    assert prune("demo", {}) == []
    assert restore("demo") == []
    ns["_provider_keys"]["nope"] = {"models": []}
    assert prune("nope", {"x": {"usable": False}}) == []
    print("  ✅ 边界安全")

    print("\n=== 5) 落盘可回读 ===")
    ns["_save_provider_keys"]()
    data = json.load(io.open(path, encoding="utf-8"))
    assert data["demo"]["models"] and "probe" in data["demo"]
    print("  ✅ OK:", os.path.basename(path))

    print("\n✅ 剪除/恢复离线回归全通过（用的是 server.py 的真实实现）")


if __name__ == "__main__":
    main()