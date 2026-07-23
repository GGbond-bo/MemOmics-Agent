"""
MemOmics Benchmarker — 多场景测试 skill/rail_review/debate 触发完整性

用法: python -m webui.benchmarker --scenario all
"""
import json, time, sys, os
from datetime import datetime

# 测试场景
SCENARIOS = {
    "chat_greeting": {
        "desc": "闲聊场景 — 应该被识别为 chat 级别",
        "messages": ["你好，介绍一下你自己", "今天天气怎么样"],
        "expect": {"analysis_level": "chat", "skills_loaded": False, "rail_pre": False, "rail_post": False, "debate": False},
    },
    "skill_only": {
        "desc": "仅查看 skill — 不触发分析",
        "messages": ["deg-analysis 这个 skill 怎么用？", "帮我看看 CellChat 的参数"],
        "expect": {"analysis_level": "chat", "skills_loaded": True, "rail_pre": False, "rail_post": False, "debate": False},
    },
    "analysis_new": {
        "desc": "新分析任务 — 应触发完整链路",
        "messages": ["帮我用 DESeq2 做差异分析，数据在 data/counts.csv"],
        "expect": {"analysis_level": "analysis", "skills_loaded": True, "rail_pre": True, "rail_post": True, "debate": True},
    },
    "analysis_repeat": {
        "desc": "重复分析 — 跑过的分析，仍需完整审查",
        "messages": ["刚才的差异分析再跑一次，换成 MAST 方法"],
        "expect": {"analysis_level": "analysis", "skills_loaded": True, "rail_pre": True, "rail_post": True, "debate": True},
    },
    "complex_analysis": {
        "desc": "复杂多步骤分析 — CellChat + 轨迹 + DEG",
        "messages": ["先做 DEG，再做 CellChat 细胞通讯，最后跑轨迹分析"],
        "expect": {"analysis_level": "analysis", "skills_loaded": True, "rail_pre": True, "rail_post": True, "debate": True},
    },
    "statistical_only": {
        "desc": "统计级操作 — 应有 pre/post 审查但无 debate",
        "messages": ["帮我做 t-test 统计检验，比较两组均值"],
        "expect": {"analysis_level": "statistical", "skills_loaded": True, "rail_pre": True, "rail_post": True, "debate": False},
    },
    "skip_detection": {
        "desc": "跳步检测 — 用户说'快点'，是否还会完整审查",
        "messages": ["快，直接跑 DESeq2，别查 skill 了"],
        "expect": {"analysis_level": "analysis", "skills_loaded": True, "rail_pre": True, "rail_post": True, "debate": True},
    },
}


def run_benchmark(api_base="http://localhost:8899"):
    """运行所有场景并收集结果"""
    import urllib.request

    results = []
    for name, scenario in SCENARIOS.items():
        print(f"\n{'='*60}")
        print(f"  Scenario: {name} — {scenario['desc']}")
        print(f"{'='*60}")

        for i, msg in enumerate(scenario["messages"]):
            print(f"\n  [{i+1}] 发送: {msg[:60]}...")
            # 这里需要实际的 WebSocket 发送逻辑
            # 简化版：记录预期结果
            pass

        results.append({
            "scenario": name,
            "desc": scenario["desc"],
            "expected": scenario["expect"],
            "actual": None,  # 需要实际运行后填充
            "passed": None,
        })

    return results


def verify_enforcement_state(session_id: str, api_base="http://localhost:8899"):
    """验证强制执行状态"""
    import urllib.request
    try:
        url = f"{api_base}/api/enforcement/{session_id}"
        r = urllib.request.urlopen(url)
        return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def check_conclusions(session_id: str, api_base="http://localhost:8899"):
    """检查结论目录"""
    import urllib.request
    try:
        url = f"{api_base}/api/results/{session_id}/tree"
        r = urllib.request.urlopen(url)
        data = json.loads(r.read())
        tree = data.get("tree", {})
        for child in tree.get("children", []):
            if child.get("name") == "conclusions":
                return child.get("children", [])
        return []
    except Exception as e:
        return [{"error": str(e)}]


if __name__ == "__main__":
    results = run_benchmark()
    print(json.dumps(results, indent=2, ensure_ascii=False))
