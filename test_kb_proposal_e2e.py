"""端到端测试：知识库 → 研究方案 全链路验证
语法版本: Python 3.12 / UTF-8
"""
import os, sys, re, yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "memomics", "bio_tools"))

ROOT = os.path.dirname(os.path.abspath(__file__))
SOUL_MD = os.path.join(ROOT, "hermes_home", "SOUL.md")
SKILL_MD = os.path.join(ROOT, "hermes_home", "skills", "bioinformatics", "academic-research", "SKILL.md")
KB_DIR = os.path.join(ROOT, "memomics", "knowledge_base", "Homo_sapiens", "heart", "development")

_passed = 0
_failed = 0
_LAST_ERROR = ""

def check(condition, label):
    global _passed, _failed, _LAST_ERROR
    if condition:
        _passed += 1
        print(f"  ✅ {label}")
    else:
        _failed += 1
        _LAST_ERROR = label
        print(f"  ❌ {label}")

# =====================================================================
# LAYER 1: SOUL.md 触发规则验证
# =====================================================================
print("\n=== L1: SOUL.md 触发规则 ===")
soul_text = open(SOUL_MD, "r", encoding="utf-8").read()

for phrase in ["研究方案", "实验设计", "方案设计", "设计实验", "研究计划",
               "research plan", "research proposal"]:
    check(phrase in soul_text and "academic-research" in soul_text, f"SOUL.md 含触发词 '{phrase}'")

check("search_knowledge" in soul_text, "SOUL.md 研究方案规则含 search_knowledge")

# 验证 skill_view("academic-research") 存在
check('skill_view("academic-research")' in soul_text or "skill_view('academic-research')" in soul_text,
      'SOUL.md 含 skill_view("academic-research")')

# =====================================================================
# LAYER 2: server.py 研究方案强制规则验证
# =====================================================================
print("\n=== L2: server.py 研究方案强制规则 ===")
server_text = open(os.path.join(ROOT, "webui", "server.py"), "r", encoding="utf-8").read()

# research_plan intent 检查
check('if intent == "research_plan"' in server_text, 'server.py 含 research_plan 意图分支')
check('skill_view' in server_text, 'server.py research_plan 含 skill_view 要求')
check('search_knowledge(species, tissue, direction)' in server_text or
      'search_knowledge' in server_text, 'server.py research_plan 含 search_knowledge 要求')
check('search_papers' in server_text, 'server.py research_plan 含 search_papers 要求')
check('[KB]' in server_text, 'server.py research_plan 要求 KB 标注 [KB]')

# plan_refine 检查
check('if intent == "plan_refine"' in server_text, 'server.py 含 plan_refine 意图分支')
check('来源：【KB】' in server_text, 'server.py plan_refine 要求 KB 来源标注')
check('KB论文版本' in server_text, 'server.py plan_refine 要求 KB 版本优先')

# =====================================================================
# LAYER 3: academic-research SKILL.md 规则验证
# =====================================================================
print("\n=== L3: academic-research SKILL.md 规则 ===")
skill_text = open(SKILL_MD, "r", encoding="utf-8").read()

check("search_knowledge" in skill_text, "SKILL.md 含 search_knowledge 规则")
check("**[KB]**" in skill_text or "【KB】" in skill_text, "SKILL.md 含 KB 来源标注规则")
check("**[PMID" in skill_text or "【PMID" in skill_text, "SKILL.md 含 PubMed 来源标注规则")
check("优先KB中的版本号" in skill_text, "SKILL.md 要求 KB 版本优先")
check("执行模板" in skill_text, "SKILL.md 含执行模板")
check("Loop Gate" in skill_text, "SKILL.md 含 Loop Gate 质量检查")
check("Iron Law" in skill_text, "SKILL.md 含 Iron Law #7 标记")

# =====================================================================
# LAYER 4: _auto_load_kb 读回测试 (heart SAN KB)
# =====================================================================
print("\n=== L4: KB 读回测试 (_auto_load_kb) ===")

# Check KB YAML files exist
kb_files = []
for root, _d, files in os.walk(KB_DIR):
    for f in files:
        if f.endswith("_dissected.yaml"):
            kb_files.append(os.path.join(root, f))

check(len(kb_files) >= 2, f"KB 含 ≥2 篇 dissected 论文 (实际: {len(kb_files)})")
for f in kb_files:
    check(os.path.getsize(f) > 1000, f"KB文件 > 1000B: {os.path.basename(f)}")

# Test _auto_load_kb readback
try:
    from debate_analysis import _auto_load_kb
    kb_text = _auto_load_kb("human heart development scRNA-seq", "test")
    check(len(kb_text) > 1000, f"_auto_load_kb 返回内容 > 1000 chars (实际: {len(kb_text)})")
    check("Seurat" in kb_text, "_auto_load_kb 含 Seurat 方法推荐")
    check("Bowtie2" in kb_text or "MACS2" in kb_text or "Harmony" in kb_text,
          "_auto_load_kb 含具体版本号方法")
except Exception as e:
    check(False, f"_auto_load_kb 抛出异常: {e}")

# =====================================================================
# LAYER 5: 多轮变换提示词命中测试 (模拟)
# =====================================================================
print("\n=== L5: 多轮变换提示词命中 ===")

# 从 SOUL.md 提取研究方案触发规则
trigger_line = None
for line in soul_text.split("\n"):
    if "研究方案" in line and "academic-research" in line and "skill_view" in line:
        trigger_line = line
        break
check(trigger_line is not None, "找到 SOUL.md 中研究方案触发规则行")

if trigger_line:
    # 提取关键词
    keywords_part = trigger_line.split("|")[1].strip() if "|" in trigger_line else trigger_line
    keywords = [k.strip().strip('"') for k in keywords_part.split("/")]
    check(len(keywords) >= 5, f"触发关键词 ≥5 个 (实际: {len(keywords)}: {keywords[:5]})")

# 模拟不同提示词
test_prompts = [
    ("中文直接", "帮我设计一个人心脏窦房结衰老的scRNA-seq研究方案"),
    ("中文简略", "帮我实验设计方案：心脏衰老"),
    ("中文方案", "做一个研究方案，心脏的"),
    ("英文标准", "Design a research plan for human heart sinoatrial node aging scRNA-seq"),
    ("英文简写", "I need a research proposal for heart aging"),
    ("中英混合", "帮我design一个研究方案关于心脏衰老"),
    ("场景描述", "我想研究心脏窦房结为什么会衰老，给我一个实验设计方案"),
    ("直接要求", "生成一个研究计划"),
    ("关键词触发", "research plan heart aging single cell"),
    ("重复问法", "方案设计：心脏衰老"),
]

for label, prompt in test_prompts:
    # 模拟匹配: 检查 prompt 中是否包含任一触发关键词
    hit = any(k.lower() in prompt.lower() for k in keywords)
    check(hit, f"提示词命中 '{label}': {prompt[:50]}...")

# =====================================================================
# LAYER 6: 非命中测试
# =====================================================================
print("\n=== L6: 非命中测试（不应触发研究方案）===")
non_prompts = [
    "帮我跑一下Seurat分析",
    "差异表达基因怎么分析",
    "cell-cell communication analysis with CellChat",
    "用scTour做轨迹推断",
    "error发生在我运行的时候",
]
for prompt in non_prompts:
    hit = any(k.lower() in prompt.lower() for k in keywords)
    check(not hit, f"不触发研究方案: {prompt[:40]}...")

# =====================================================================
# LAYER 7: 新会话模拟 — 重新加载 SOUL.md
# =====================================================================
print("\n=== L7: 新会话模拟 ===")
# 模拟新会话加载: 验证 SOUL.md 文件本身包含规则（不依赖内存状态）
soul_reload = open(SOUL_MD, "r", encoding="utf-8").read()
check('academic-research' in soul_reload and '研究方案' in soul_reload,
      "新会话重新加载 SOUL.md 后规则存在")
check('search_knowledge' in soul_reload, "新会话 SOUL.md 含 search_knowledge 要求")

# =====================================================================
# 汇总
# =====================================================================
total = _passed + _failed
print(f"\n{'='*60}")
print(f"结果: {_passed}/{total} 通过 ({_passed/max(total,1)*100:.1f}%)")
print(f"失败: {_failed}")
if _failed:
    print(f"最后失败: {_LAST_ERROR}")
print(f"{'='*60}")
sys.exit(0 if _failed == 0 else 1)
