"""
Skill 自动注册工具
- 从 SKILL.md frontmatter 自动生成 skill.json
- 自动添加到 SKILLS_INDEX.md
- 可选：自动注册到 SOUL.md 必触发表
"""
import os, json, re, shutil
from pathlib import Path
from datetime import datetime

SKILLS_BIO_DIR = None  # Set by init
SKILLS_INDEX_PATH = None
SOUL_PATH = None


def init(skills_dir: str, index_path: str, soul_path: str):
    global SKILLS_BIO_DIR, SKILLS_INDEX_PATH, SOUL_PATH
    SKILLS_BIO_DIR = skills_dir
    SKILLS_INDEX_PATH = index_path
    SOUL_PATH = soul_path


def _registry():
    """按需导入 skills_registry（server.py 以 webui/ 为 sys.path，包方式则 from webui）。"""
    try:
        import skills_registry  # noqa: PLC0415 — 延迟导入，避免与 server.py 的 sys.path 顺序打架
        return skills_registry
    except Exception:
        try:
            from webui import skills_registry  # noqa: PLC0415
            return skills_registry
        except Exception:
            return None


def _parse_skill_md(skill_dir: str) -> dict:
    """从 SKILL.md frontmatter 提取元数据"""
    md_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(md_path):
        return {}
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # frontmatter 解析统一走 skills_registry._parse_frontmatter（同一套口径）：
    # 老实现是「逐行 key: value」，遇到 `description: >-` 块标量只取到字面量 `>-`，
    # 续行全丢 —— 生成出来的 skill.json 描述就是垃圾（2026-09 实测：'description': '>-'）。
    meta = {}
    reg = _registry()
    if reg is not None:
        try:
            meta = dict(reg._parse_frontmatter(content) or {})
        except Exception:  # noqa: BLE001 — 解析器异常时退回老逻辑，不能阻断注册
            meta = {}
    fm_match = None if meta else re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        # Parse simple key: value pairs
        for line in fm.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                key, _, val = line.partition(':')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if val.startswith('[') and val.endswith(']'):
                    # List
                    val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(',') if v.strip()]
                meta[key] = val
    
    # Extract first H1 as display name
    h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    display_name = h1_match.group(1).strip() if h1_match else ""
    
    # Extract description from metadata or first paragraph
    description = meta.get('description', '')
    if not description:
        desc_match = re.search(r'##\s*(?:简介|Overview|Description)\s*\n\s*(.+?)(?:\n|$)', content, re.DOTALL)
        if desc_match:
            description = desc_match.group(1).strip()[:200]
    
    # Determine category from metadata or tags
    category = meta.get('category', '')
    if not category:
        tags = meta.get('tags', [])
        cat_map = {
            'rna': 'transcriptomics', 'scrna': 'transcriptomics', 'scrnaseq': 'transcriptomics',
            'atac': 'epigenomics', 'chip': 'epigenomics',
            'spatial': 'spatial', '空间': 'spatial',
            'bulk': 'transcriptomics',
            'protein': 'proteomics', '蛋白': 'proteomics',
            'drug': 'drug_discovery', 'clinical': 'clinical', '药物': 'drug_discovery',
            'visualization': 'visualization', 'figure': 'visualization', '画图': 'visualization', '可视化': 'visualization',
            'literature': 'literature', '文献': 'literature', 'query': 'data_retrieval',
            'report': 'report', '报告': 'report',
            'multi-omics': 'multi_omics', '整合': 'multi_omics',
            'microbiology': 'microbiology', '植物': 'microbiology',
            'cloning': 'molecular_biology', '分子': 'molecular_biology', 'pcr': 'molecular_biology',
            'crispr': 'genome_editing',
            'histology': 'histology', '组织': 'histology',
            'cell': 'cell_biology', '细胞': 'cell_biology',
            'system': 'system',
        }
        for tag in (tags if isinstance(tags, list) else [tags]):
            tag_lower = tag.lower() if isinstance(tag, str) else ''
            for k, v in cat_map.items():
                if k in tag_lower:
                    category = v
                    break
            if category:
                break
        if not category:
            category = 'general'
    
    # Determine trigger level
    trigger_level = meta.get('trigger_level', '')
    if not trigger_level:
        trigger = meta.get('trigger', {})
        if isinstance(trigger, dict):
            when = trigger.get('when', [])
            if isinstance(when, list) and when:
                trigger_level = 'RED'
            else:
                trigger_level = 'YEL'
        else:
            trigger_level = 'YEL'
    
    # Extract trigger keywords
    trigger_keywords = []
    trigger_raw = meta.get('trigger_keywords', meta.get('trigger_keyword', []))
    if trigger_raw and isinstance(trigger_raw, list):
        trigger_keywords = trigger_raw
    elif trigger_raw and isinstance(trigger_raw, str):
        trigger_keywords = [k.strip() for k in trigger_raw.split(',')]
    else:
        # Try from when_to_use or description
        when = meta.get('when_to_use', '')
        if when:
            trigger_keywords = [w.strip().strip('"') for w in re.findall(r'"([^"]+)"', when)]
    
    return {
        'id': os.path.basename(skill_dir),
        'name': display_name or meta.get('name', os.path.basename(skill_dir)),
        'category': category,
        'description': str(description)[:200],
        'when_to_use': str(meta.get('when_to_use', '') or '')[:300],
        'trigger_level': 'RED' if trigger_keywords else trigger_level,
        'trigger_keywords': trigger_keywords,
        'tags': meta.get('tags', []) if isinstance(meta.get('tags'), list) else [],
        'language': meta.get('language', meta.get('platforms', 'Python')),
    }


def auto_generate_skill_json(skill_dir: str, force: bool = False) -> bool:
    """自动从 SKILL.md 生成 skill.json（如果不存在）"""
    json_path = os.path.join(skill_dir, "skill.json")
    if os.path.exists(json_path) and not force:
        return False
    
    meta = _parse_skill_md(skill_dir)
    if not meta:
        return False
    
    data = {
        "id": meta['id'],
        "name": meta['name'],
        "category": meta['category'],
        "language": str(meta.get('language', 'Python')),
        "description": str(meta.get('description', ''))[:200],
        "starting_prompt": f"使用 {meta['name']} 进行分析",
        "source_dir": f"skills/bioinformatics/{meta['id']}",
        "memomics_module": "",
        "chains_from": [],
        "chains_to": [],
        "tags": meta.get('tags', []) if isinstance(meta.get('tags'), list) else [],
        "aliases": [],
        "trigger_level": meta.get('trigger_level', 'YEL'),
        "trigger_keywords": meta.get('trigger_keywords', []),
    }
    # 从 SKILL.md 搬来的触发词/使用场景可能是长句、逗号粘连、分类水词，
    # 一律先过 skills_registry.normalize_meta()，保证写出来的 skill.json 与索引同一口径。
    reg = _registry()
    if reg is not None:
        old = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, encoding="utf-8") as f:
                    old = json.load(f) or {}
            except (OSError, ValueError):
                old = {}
        try:
            data = reg.normalize_meta(meta['id'], data, existing=old)
        except TypeError:   # 老版本 skills_registry 没有 existing 形参
            data = reg.normalize_meta(meta['id'], data)
        except Exception as e:  # noqa: BLE001 — 规范化失败也要能落盘
            print(f"[auto-register] normalize_meta failed ({e}); write raw metadata")
    
    with open(json_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[auto-register] Generated skill.json for {meta['id']}")
    return True


def auto_register_to_index(skill_dir: str) -> bool:
    """自动添加到 SKILLS_INDEX.md

    2026-09-23 起改为「整表重建」（webui/skills_registry.py）：旧实现只会在表尾追加
    一行，且表头 5 列 / 追加行 4 列导致错列，触发词回退成分类水词（rna, scrna…），
    355 个技能里有 82 个始终没有索引行。重建后索引 = 磁盘全量技能，新技能自动出现。
    下面的老追加逻辑保留为兜底（重建失败时才走）。
    """
    meta = _parse_skill_md(skill_dir)
    skill_name = meta.get('id') or os.path.basename(str(skill_dir).rstrip('/\\'))
    try:
        try:
            import skills_registry  # server.py 以 webui/ 为 sys.path 时
        except Exception:
            from webui import skills_registry  # 包方式导入
        index_path = SKILLS_INDEX_PATH or skills_registry.INDEX_PATH
        with open(index_path, 'r', encoding='utf-8') as f:
            # 新索引是 5 列编号行（| 12 | skill | ... |），老判定 | name | 匹配不到
            existed = bool(re.search(r'\|\s*(?:\d+\s*\|\s*)?' + re.escape(skill_name) + r'\s*\|', f.read()))
        # backfill_json=True：把 skill.json 里空/垃圾的 when_to_use、trigger_keywords、
        # trigger_level 用索引口径补齐（只补空，不覆盖人工填写值）。运行期写 skill.json 的
        # 路径不止一条（auto_generate_skill_json 会搬 SKILL.md frontmatter），不在这里收敛，
        # 那份脏值会一直躺在磁盘上并进下一次注册。
        skills_registry.build(write=True, backfill_json=True)
        print(f"[auto-register] Rebuilt SKILLS_INDEX.md "
              f"({'added' if not existed else 'refreshed'}: {skill_name})")
        return not existed
    except Exception as e:  # noqa: BLE001 — 兜底走老逻辑
        print(f"[auto-register] skills_registry rebuild unavailable ({e}); falling back to append")

    if not SKILLS_INDEX_PATH:
        print("[auto-register] SKILLS_INDEX_PATH 未初始化（未调用 init()），跳过索引注册")
        return False
    with open(SKILLS_INDEX_PATH, 'r', encoding='utf-8') as f:
        index = f.read()
    
    # Already registered?
    if re.search(r'\|\s*(?:\d+\s*\|\s*)?' + re.escape(skill_name) + r'\s*\|', index):
        return False
    
    # Determine category section
    category = meta.get('category', 'general')
    cat_section_map = {
        'transcriptomics': '01_RNA',
        'epigenomics': '02_ATAC',
        'spatial': '03_空间组',
        'proteomics': '05_蛋白',
        'drug_discovery': '07_药物临床',
        'clinical': '07_药物临床',
        'visualization': '08_报告',
        'report': '08_报告',
        'literature': '11_文献搜索',
        'data_retrieval': '11_文献搜索',
        'multi_omics': '10_多组学整合',
        'microbiology': '06_微生物植物',
        'molecular_biology': '12_分子生物学',
        'histology': '13_组织学病理',
        'cell_biology': '14_细胞生物学实验',
        'genome_editing': '15_CRISPR基因编辑',
        'system': '09_内置',
        'general': '08_报告',
    }
    section_name = cat_section_map.get(category, '08_报告')
    
    # Find the section
    section_marker = f'## {section_name}'
    section_pos = index.find(section_marker)
    if section_pos < 0:
        # Fallback: add to 08_报告
        section_pos = index.find('## 08_报告')
    if section_pos < 0:
        return False
    
    # Find end of section table (next ## or end of file)
    next_section = index.find('\n## ', section_pos + len(section_marker))
    if next_section < 0:
        next_section = len(index)
    
    # Build entry
    trigger_level = meta.get('trigger_level', 'YEL')
    trigger_display = {'RED': 'RED 必触发', 'YEL': 'YEL 讨论触发', 'GRN': 'GRN 按需触发', 'WHT': 'WHT 系统级'}.get(trigger_level, 'YEL 讨论触发')
    desc = meta.get('description', '')[:100]
    keywords = ', '.join(meta.get('trigger_keywords', meta.get('tags', []))[:10])
    
    entry = f'\n| {skill_name} | {desc} | {keywords} | {trigger_display} |'
    
    # Insert before next section
    index = index[:next_section] + entry + index[next_section:]
    
    # Update section count
    old_header = index[section_pos:index.find('\n', section_pos)]
    import re
    count_match = re.search(r'\((\d+) skills\)', old_header)
    if count_match:
        new_count = int(count_match.group(1)) + 1
        new_header = old_header.replace(count_match.group(0), f'({new_count} skills)')
        index = index[:section_pos] + new_header + index[section_pos + len(old_header):]
    
    with open(SKILLS_INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(index)
    print(f"[auto-register] Added {skill_name} to SKILLS_INDEX.md ({section_name})")
    return True


def auto_register_to_soul(skill_dir: str, trigger_keywords: list = None, skill_name: str = None) -> bool:
    """可选：自动注册到 SOUL.md 必触发表"""
    meta = _parse_skill_md(skill_dir)
    name = skill_name or meta['id']
    keywords = trigger_keywords or meta.get('trigger_keywords', [])
    
    if not keywords:
        return False
    
    with open(SOUL_PATH, 'r', encoding='utf-8') as f:
        soul = f.read()
    
    # Already registered?
    if f'skill_view("{name}")' in soul:
        return False
    
    # Build entry
    kw_str = ' / '.join(f'"{kw}"' for kw in keywords[:6])
    desc = meta.get('description', meta.get('name', name))[:80]
    entry = f'\n| {kw_str} | `skill_view("{name}")` → {desc} |'
    
    # Insert after the last trigger entry (before the LLM decision tree)
    tree_marker = '\n### LLM 决策树'
    tree_pos = soul.find(tree_marker)
    if tree_pos < 0:
        return False
    
    soul = soul[:tree_pos] + entry + soul[tree_pos:]
    
    with open(SOUL_PATH, 'w', encoding='utf-8') as f:
        f.write(soul)
    print(f"[auto-register] Registered {name} in SOUL.md with keywords: {keywords}")
    return True


def register_skill(skill_dir: str, 
                   trigger_keywords: list = None,
                   register_soul: bool = False) -> dict:
    """一键注册：skill.json + SKILLS_INDEX + (可选)SOUL.md
    
    Args:
        skill_dir: 技能目录名（如 'scipilot-figure-skill'）或完整路径
        trigger_keywords: 手动指定触发关键词
        register_soul: 是否同时注册到 SOUL.md
    """
    if not SKILLS_BIO_DIR:
        return {"ok": False, "error": "auto_register not initialized"}
    
    # Resolve path
    if os.path.isabs(skill_dir):
        full_path = skill_dir
    else:
        full_path = os.path.join(SKILLS_BIO_DIR, skill_dir)
    
    if not os.path.isdir(full_path):
        return {"ok": False, "error": f"Skill directory not found: {full_path}"}
    
    skill_name = os.path.basename(full_path)
    results = []
    
    # 1. Generate skill.json
    if auto_generate_skill_json(full_path):
        results.append("skill.json generated")
    
    # 2. Register to index
    if auto_register_to_index(full_path):
        results.append("SKILLS_INDEX registered")
    
    # 3. Register to SOUL (optional)
    if register_soul:
        if auto_register_to_soul(full_path, trigger_keywords, skill_name):
            results.append("SOUL.md registered")
    
    return {"ok": True, "skill": skill_name, "actions": results}


def rebuild_index_descriptions() -> dict:
    """重建 SKILLS_INDEX.md —— 统一委托 skills_registry，索引只有一个生成口径。

    历史实现是「就地补格」：重新解析 SKILL.md frontmatter，当索引单元格里的词数少于
    SKILL.md 里的 trigger_keywords 时，用**原始列表**整格覆盖写入，而且是默认文本模式
    （Windows 下变 CRLF）。实测后果：5 行被写成逗号粘连的长句（academic-paper-reviewer
    一格 19 个词：帮我审一下, 审一下这篇, ... review this, review the），全文 58802 字节，
    每次服务启动都会重犯 —— 这正是「注册触发场景没写好」的现场之一。

    现在整表交给 skills_registry.build()：触发词清洗 + 限长 + 等级与 SOUL 必触发表对齐后再
    渲染。返回键（ok / filled_desc / filled_keywords）保持不变，供启动日志继续使用。
    """
    if not SKILLS_BIO_DIR:
        return {"ok": False, "error": "not initialized"}
    reg = _registry()
    if reg is None:
        return {"ok": False, "error": "skills_registry unavailable"}
    try:
        info = reg.build(write=True, backfill_json=True)  # 同上：重建索引时顺手修掉 skill.json 里的垃圾字段
    except Exception as e:  # noqa: BLE001 — 启动期索引重建失败不能拖垮服务
        print(f"[auto-register] index rebuild failed: {e}", flush=True)
        return {"ok": False, "error": str(e)}
    rows = int(info.get("total") or 0)
    print(f"[auto-register] Index rebuilt via skills_registry: {rows} rows", flush=True)
    return {"ok": True, "filled_desc": 0, "filled_keywords": 0, "rows": rows}


def scan_and_register_all():
    """启动时扫描所有 skill 目录，补全缺失的 skill.json + 索引条目"""
    if not SKILLS_BIO_DIR:
        return {"ok": False, "error": "not initialized"}
    
    results = {"json_generated": 0, "index_added": 0}
    
    for d in sorted(os.listdir(SKILLS_BIO_DIR)):
        full = os.path.join(SKILLS_BIO_DIR, d)
        if not os.path.isdir(full) or d.startswith('.') or d.startswith('_'):
            continue
        
        # Generate skill.json if missing
        if not os.path.exists(os.path.join(full, "skill.json")):
            if auto_generate_skill_json(full):
                results["json_generated"] += 1
        
        # Add to index if missing
        with open(SKILLS_INDEX_PATH, 'r', encoding='utf-8') as f:
            index = f.read()
        if f'| {d} |' not in index:
            if auto_register_to_index(full):
                results["index_added"] += 1
    
    # 补全历史空描述条目（只追加不更新的历史缺陷）
    rebuild = rebuild_index_descriptions()
    results["desc_rebuilt"] = rebuild.get("filled_desc", 0)
    return results
