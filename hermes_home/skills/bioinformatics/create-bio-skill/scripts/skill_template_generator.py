#!/usr/bin/env python3
"""skill_template_generator.py — 生成标准 MemOmics 生信 skill 的 SKILL.md 文本。
    + 自动注册到 SOUL.md 技能匹配表。

用法:
    from skill_template_generator import generate_skill_md, register_to_soul_md

    # 1. 生成 SKILL.md
    content = generate_skill_md(
        name="sctour-trajectory-inference",
        description="scTour 轨迹推断...",
        tags=["trajectory", "scRNA-seq"],
        difficulty="advanced",
        language="Python",
        category="transcriptomics",
        r_packages=[],
        python_packages=["sctour", "scanpy"],
        title="scTour 轨迹推断",
        overview="使用 scTour 进行单细胞轨迹推断...",
        when_to_use="...",
        pipeline=[("Step 1", "加载数据"), ...],
        parameters=[("param1", "默认值", "说明"), ...],
        references=["Author et al. 2024"],
    )
    # 2. 注册到 SOUL.md 技能匹配表
    register_to_soul_md(
        skill_name="sctour-trajectory-inference",
        step_name="scTour 轨迹",
        description="VAE 深度潜在时间推断+向量场，无监督",
        trigger_keywords="scTour/深度伪时间/VAE轨迹/神经ODE",
        soul_md_path="hermes_home/SOUL.md",
    )
"""

# ============================================================
# 标准铁律头（写入每个新 skill 的脚本开头）
# ============================================================

IRON_RULE_HEADER = '''# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", script_name="本脚本名",
#      species="物种", tissue="组织", direction="方向")
#      → 查同类运行日志，有则参考已有参数和经验，无则按原脚本执行
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
#   2. 如果通过 → skill_evolution(action="record_run",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", params_used="参数JSON", result_summary="结果",
#      quality_score=8, notes="经验总结")
#      → 记录成功运行日志，供后续同类型分析参考
#   3. 如果失败 → skill_evolution(action="record_error",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", error_message="报错", root_cause="根因",
#      fix_applied="修复方案")
#      → 记录错误日志，修正后重跑
#
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
#   ★ 强制: 图片空白/NA/过小 → 重新出图 | 图片不够 → 补图 | 代码未分段 → 重写
#   ★ 强制: 有参数有结论 → debate_analysis 辩论
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================
'''


# ============================================================
# 标准强制规则块（写入每个新 skill 的 SKILL.md）
# ============================================================

ENFORCED_RULES = '''## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。使用本 skill 前，必须先通过 skill_view 加载本文件。以下规则覆盖所有默认行为。

### 规则1: 写代码前 → 必须先 search_knowledge + skill_view
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 search_papers_by_context 搜文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 8步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. skill_view 加载本 SKILL.md（获取脚本模板+审查规则+参数范围）
3. check_env 检查环境（缺包自动安装）
4. rail_review(pre) 前置审查（参数合理吗？包齐了吗？数据准备好了吗？）
5. 写这一步的代码（基于 skill 模板，只写这一步，不写后续步骤）
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
8. rail_review(post) 后置审查（图有没有？结果合理吗？跟知识库对应吗？）
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时，**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式：正方（支持当前参数）vs 反方（质疑+替代方案）→ 裁判决断
- **不确定的参数就辩论**，不要自己拍脑袋
- **辩论最多 3 轮**：3 轮后选最优参数结果

### 规则5: 执行后审查（强化版）
- 每步执行完调 `rail_review(post)` 审查，审查内容**全部强制**：
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
    - 通过 → 创建目录存储(figures/results/scripts/data) → 下一步

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
'''


def generate_skill_md(
    name: str,
    description: str,
    tags: list,
    difficulty: str,
    language: str,
    category: str,
    r_packages: list,
    python_packages: list,
    title: str,
    overview: str,
    when_to_use: str,
    pipeline: list,
    parameters: list,
    common_issues: str = "",
    references: list = None,
    related_skills: list = None,
) -> str:
    """生成完整的 SKILL.md 文本。

    Args:
        name: skill 名称（如 "sctour-trajectory"）
        description: 一句话描述
        tags: 标签列表
        difficulty: beginner/intermediate/advanced
        language: R/Python/R+Python
        category: transcriptomics/epigenomics/spatial/proteomics/meta
        r_packages: R 依赖包列表
        python_packages: Python 依赖包列表
        title: 分析步骤标题
        overview: 功能概述
        when_to_use: 触发场景
        pipeline: [(step_name, step_desc), ...] 列表
        parameters: [(param_name, default_value, description), ...] 列表
        common_issues: 常见问题文本
        references: 文献引用列表
        related_skills: 相关 skill 列表

    Returns:
        完整的 SKILL.md 文本
    """
    related_skills = related_skills or []
    references = references or []

    # Frontmatter
    fm = f"""---
name: {name}
description: "{description}"
version: 1.0.0
author: MemOmics (auto-created)
license: MIT
platforms: [windows, linux, macos]
category: {category}
metadata:
  hermes:
    tags: {tags}
    difficulty: {difficulty}
    language: {language}
    category: {category}
prerequisites:
  r_packages: {r_packages}
  python_packages: {python_packages}"""
    if related_skills:
        fm += f"\nrelated_skills: {related_skills}"
    fm += "\n---\n\n"

    # 强制规则块
    rules = ENFORCED_RULES

    # 正文
    body = f"\n---\n\n# {title}\n\n{overview}\n\n"
    body += f"## When to Use\n\n{when_to_use}\n\n"

    # Pipeline
    body += "## Pipeline\n\n"
    for step_name, step_desc in pipeline:
        body += f"### {step_name}\n```\nTool: terminal\n{step_desc}\n```\n\n"

    # Parameters
    body += "## Parameters\n\n"
    body += "| 参数 | 默认值 | 说明 |\n|------|--------|------|\n"
    for p_name, p_default, p_desc in parameters:
        body += f"| {p_name} | {p_default} | {p_desc} |\n"
    body += "\n"

    # Proven Scripts
    # P2-15(2026-08-10): 必须生成有效 markdown 空表格（规则2.6）——
    # _record_success 用正则匹配 `|:----` 分隔行追加记录，纯列表会导致
    # record_run 静默失败。生成器之前只输出列表 → 所有新 skill 的
    # record_run 都静默丢。现在输出标准空表格。
    body += "## Proven Scripts\n\n"
    body += ("> 经实际运行验证成功的脚本记录。`skill_evolution(action=\"record_run\")` 自动追加至此表。\n"
             ">\n"
             "> 评分规则：`auto` 来自 rail_review 技术审查，`user` 来自用户认可。\n\n")
    body += "| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |\n"
    body += "|:----|:----|:----|:----:|:-----|:----:|:----:|:-:|\n"
    body += "| <!-- 首次运行后自动填充 --> | | | | | | | |\n\n"
    body += f"- `scripts/run.py` — 主脚本模板（含 MemOmics 审查辩论铁律头）\n"
    if language in ("R", "R+Python"):
        body += f"- `scripts/reference_script.R` — R 参考实现\n"
    if language in ("Python", "R+Python"):
        body += f"- `scripts/reference_script.py` — Python 参考实现\n"
    body += "\n"

    # Common Issues
    body += "## Common Issues\n\n"
    body += common_issues if common_issues else "（待补充）\n"
    body += "\n"

    # References
    body += "## References\n\n"
    for ref in references:
        body += f"- {ref}\n"

    return fm + rules + body


def generate_run_py(skill_name: str, language: str, steps: list) -> str:
    """生成 scripts/run.py 脚本模板。

    Args:
        skill_name: skill 名称
        language: R/Python/R+Python
        steps: [(step_name, step_desc), ...] 列表

    Returns:
        完整的 run.py 文本
    """
    header = IRON_RULE_HEADER

    if language == "R":
        lang_line = "#!/usr/bin/env Rscript"
    else:
        lang_line = "#!/usr/bin/env python3"

    title = f"# {skill_name} — Proven Analysis Script\n# Auto-generated by MemOmics create-bio-skill\n#"

    usage = "# USAGE: This script is loaded by MemOmics agent when the skill is triggered.\n# Parameters are adapted based on species, tissue, and condition.\n"

    steps_text = "# Steps:\n"
    for i, (step_name, step_desc) in enumerate(steps, 1):
        steps_text += f"# Step {i}: {step_name} — {step_desc}\n"

    params_section = "\n# ── Parameters (adapt before running) ────────────────────────────────\n# TODO: Fill in parameters based on data quality and literature\n"
    main_section = "\n# ── Main Pipeline ─────────────────────────────────────────────────────\n# TODO: Proven code will be saved here after successful execution + review\n"
    save_section = "\n# ── Save Results ──────────────────────────────────────────────────────\n# TODO: Export figures, results, and metadata\n"

    return f"{lang_line}\n{title}\n{usage}\n{steps_text}\n{header}\n{params_section}\n{main_section}\n{save_section}\n"


def generate_skill_json(skill_name: str) -> str:
    """生成 skill.json 文本（JSON 字符串）。

    ⚠️ 这很关键：skill_evolution(action="record_run") 的 _record_success 依赖
    skill.json 存储 proven_params。如果 skill.json 不存在，record_run 会静默失败。

    Args:
        skill_name: skill 名称

    Returns:
        格式化的 JSON 字符串
    """
    import json
    return json.dumps({
        "name": skill_name,
        "version": "1.0.0",
        "success_count": 0,
        "proven_script": "",
        "proven_params": []
    }, indent=2, ensure_ascii=False)


def generate_reference_script(skill_name: str, language: str, steps: list, example_code: str = "") -> str:
    """生成 scripts/reference_script.R 或 .py 参考脚本模板。

    Args:
        skill_name: skill 名称
        language: R/Python
        steps: [(step_name, step_desc), ...] 列表
        example_code: 从官方文档提取的示例代码

    Returns:
        完整的参考脚本文本
    """
    header = IRON_RULE_HEADER

    if language == "R":
        lang_line = "#!/usr/bin/env Rscript"
    else:
        lang_line = "#!/usr/bin/env python3"

    title = f"# {skill_name} — Reference Implementation\n# Auto-generated by MemOmics create-bio-skill\n# Based on official documentation and literature\n"

    steps_text = "# Steps:\n"
    for i, (step_name, step_desc) in enumerate(steps, 1):
        steps_text += f"# Step {i}: {step_name} — {step_desc}\n"

    code_section = f"\n# ── Reference Implementation ──────────────────────────────────────────\n# 以下代码基于官方文档示例，运行前必须根据数据调整参数\n\n{example_code if example_code else '# TODO: Paste example code from official documentation here'}\n"

    return f"{lang_line}\n{title}\n{header}\n{steps_text}\n{code_section}\n"


# ============================================================
# 🔴 SOUL.md 自动注册（新 skill 必须注册到技能匹配表）
# ============================================================

AUTO_SKILL_MARKER = "<!-- AUTO_SKILL_INSERT_MARKER"


def register_to_soul_md(
    skill_name: str,
    step_name: str,
    description: str,
    trigger_keywords: str = "",
    soul_md_path: str = "hermes_home/SOUL.md",
) -> dict:
    """在 SOUL.md 技能匹配表中注册新 skill。

    在 AUTO_SKILL_INSERT_MARKER 上方插入新行，格式：
    | **<step_name>** | <skill_name> | <description>。用户说"<trigger_keywords>"时触发 |

    Args:
        skill_name: skill 名称（如 "sctour-trajectory-inference"）
        step_name: 分析步骤中文名（如 "scTour 轨迹"）
        description: 一句话描述
        trigger_keywords: 触发关键词（用 / 分隔，如 "scTour/深度伪时间/VAE轨迹"）
        soul_md_path: SOUL.md 路径

    Returns:
        {"success": bool, "message": str, "skill_name": str}
    """
    import os

    if not os.path.exists(soul_md_path):
        return {
            "success": False,
            "message": f"SOUL.md 不存在: {soul_md_path}",
            "skill_name": skill_name,
        }

    with open(soul_md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 找到 AUTO_SKILL_INSERT_MARKER 所在行
    marker_idx = None
    for i, line in enumerate(lines):
        if AUTO_SKILL_MARKER in line:
            marker_idx = i
            break

    if marker_idx is None:
        return {
            "success": False,
            "message": f"未找到 {AUTO_SKILL_MARKER} 标记，请先在 SOUL.md 中添加该标记",
            "skill_name": skill_name,
        }

    # 检查是否已注册（避免重复）
    already_registered = False
    for line in lines:
        if f"| {skill_name} |" in line or f"| **{skill_name}**" in line:
            already_registered = True
            break

    if already_registered:
        return {
            "success": True,
            "message": f"skill '{skill_name}' 已在 SOUL.md 中注册，跳过",
            "skill_name": skill_name,
            "already_registered": True,
        }

    # 构造新行 — P2-16(2026-08-10): 必须用触发表管道式格式
    # 旧格式: | **名称** | skill | 描述。用户说"kw"时触发 |
    #   → agent 的触发解析不认！现有触发表全部是:
    #     | "kw1" / "kw2" / ... | `skill_view("skill-name")` |
    # 意图测试(verify_skill_trigger.py)实测旧格式无法命中关键词 → 改成管道式
    kw_list = " / ".join(f'"{k.strip()}"' for k in trigger_keywords.split("/") if k.strip()) if trigger_keywords else ""
    new_row = f'| {kw_list} | `skill_view("{skill_name}")` |\n'

    # 在 marker 上方插入
    lines.insert(marker_idx, new_row)

    # 写回
    with open(soul_md_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {
        "success": True,
        "message": f"skill '{skill_name}' 已注册到 SOUL.md 技能匹配表（{step_name}）",
        "skill_name": skill_name,
        "registered_at": f"第 {marker_idx + 1} 行（{AUTO_SKILL_MARKER} 上方）",
    }


def verify_registration(skill_name: str, soul_md_path: str = "hermes_home/SOUL.md") -> dict:
    """验证 skill 是否已注册到 SOUL.md 技能匹配表。

    Args:
        skill_name: skill 名称
        soul_md_path: SOUL.md 路径

    Returns:
        {"registered": bool, "line": int or None, "message": str}
    """
    import os

    if not os.path.exists(soul_md_path):
        return {
            "registered": False,
            "line": None,
            "message": f"SOUL.md 不存在: {soul_md_path}",
        }

    with open(soul_md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if skill_name in line and line.strip().startswith("|"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2 and parts[1] == skill_name:
                return {
                    "registered": True,
                    "line": i + 1,
                    "message": f"skill '{skill_name}' 已注册在第 {i + 1} 行",
                }

    return {
        "registered": False,
        "line": None,
        "message": f"skill '{skill_name}' 未在 SOUL.md 技能匹配表中找到！请调用 register_to_soul_md() 注册。",
    }


def register_and_verify(
    skill_name: str,
    step_name: str,
    description: str,
    trigger_keywords: str = "",
    soul_md_path: str = "hermes_home/SOUL.md",
) -> dict:
    """注册 + 验证一体化：注册后立即验证。

    Returns:
        {"success": bool, "registered": bool, "verified": bool, "message": str}
    """
    reg_result = register_to_soul_md(
        skill_name=skill_name,
        step_name=step_name,
        description=description,
        trigger_keywords=trigger_keywords,
        soul_md_path=soul_md_path,
    )

    if not reg_result["success"]:
        return {
            "success": False,
            "registered": False,
            "verified": False,
            "message": f"注册失败: {reg_result['message']}",
        }

    verify_result = verify_registration(skill_name, soul_md_path)

    if not verify_result["registered"]:
        return {
            "success": False,
            "registered": True,
            "verified": False,
            "message": f"注册完成但验证失败: {verify_result['message']}",
        }

    return {
        "success": True,
        "registered": True,
        "verified": True,
        "message": f"skill '{skill_name}' 注册+验证通过（{step_name}）",
    }
