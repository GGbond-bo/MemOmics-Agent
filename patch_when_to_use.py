#!/usr/bin/env python3
"""Auto-generate 'when_to_use' for all SKILL.md files from existing description.
For skills without description, generate from skill name using keyword patterns."""
import os, re, glob

SKILLS_DIR = 'hermes_home/skills/bioinformatics'

# Manual overrides for collision groups — differentiated by specific use case
COLLISION_OVERRIDES = {
    # survival 
    'survival-analysis': '患者生存数据(OS/PFS)有完整随访记录，需KM曲线+Cox回归+RFS/DSS分析，临床样本量>50',
    'survival-analysis-clinical': '已有survival-analysis结果，需进一步做临床分层(分期/分级/年龄)的高阶生存分析，或时间依赖ROC评估biomarker预测能力',

    # functional enrichment
    'functional-enrichment': '有差异基因(DEG)列表或pre-ranked基因排序，需GO/KEGG/Reactome/MSigDB通路富集，用clusterProfiler或gseapy',
    'functional-enrichment-from-degs': '已有DEG分析结果(从DESeq2/Seurat出来的logFC/p-value表)，需要从DEG表直接一键做功能富集，不手动整理基因列表',

    # scrna disease drug
    'scrna-disease-drug': '有疾病scRNA数据+公共遗传证据(Open Targets/GWAS/eQTL)，需为组织中靶细胞群排序候选药物靶点，输出优先级列表',
    'scrna-disease-drug-discovery': '需要完整药物发现pipeline：从scRNA数据→靶点识别→化合物筛选→已有药物重定位，输出候选药物+证据强度',

    # chip-atlas 
    'chip-atlas-diff-analysis': '有ChIP-Atlas实验组/对照组peak数据，需做差异peak分析，找出组间显著变化peak的基因组位置和邻近基因',
    'chip-atlas-peak-enrichment': '已有ChIP-Atlas peak列表(非差异)，需对peak做基因组区域注释+已知motif富集+GO/KEGG通路富集',
    'chip-atlas-target-genes': '有ChIP-Atlas peak坐标或transcription factor名，需查询这些peak调控的靶基因列表，输出TF→target调控表',

    # bulk RNA
    'bulk-rnaseq-differential-expression': '有bulk RNA-seq counts矩阵+实验设计表(treat vs control)，需做差异化(GO/KEGG/火山图/热图)',
    'bulk-rnaseq-counts-to-de-deseq2': '有raw counts矩阵(从featureCounts/HTSeq输出)，仅需用DESeq2做差异(不包含后续富集/可视化)，作为pipeline的第一步',
    'bulk-omics-clustering': '有bulk RNA表达矩阵(非counts)，需做样本聚类/降维(PCA/t-SNE/UMAP)看组间分群，或WGCNA共表达模块',

    # scRNA variants
    'scrna-seurat-core': '有scRNA数据(10X count矩阵)，需Seurat全流程：QC→归一化→PCA→聚类→UMAP→marker→注释',
    'scrnaseq-seurat-core-analysis': '同scrna-seurat-core，使用Seurat v5新版pipeline，包含SCTransform归一化+harmony整合+自动注释',
    'scrnaseq-scanpy-core-analysis': '同功能但用Python/Scanpy，适合>60万细胞的大规模数据或GPU环境用户',

    # paper
    'paper-download': '需要下载单篇论文PDF（DOI/PMID/arXiv ID），仅下载不分析',
    'paper-summary': '已有PDF或论文链接，需生成结构化的论文摘要（背景/方法/结果/结论），快速了解论文内容',
    'paper-translate': '已有英文PDF，需翻译成中文保留排版格式，用于阅读外文文献',

    # ppt
    'ppt-generator': '已有分析结果和图表，需生成汇报用PPT，自动排版图文',
    'ppt-html': '已有内容框架，需生成HTML格式的演示文稿（可转PPT），适合快速预览和分享',
    'ppt-master': '需要设计母版风格的完整PPT（公司/会议级），包含统一配色/字体/布局模板',
}

def generate_when_to_use(skill_id, description):
    """Generate when_to_use from description or skill name."""
    if description and description != '""' and len(description) > 5:
        return description.strip('"').strip()
    
    # Generate from skill name
    name_parts = skill_id.replace('-', ' ').replace('_', ' ')
    # Build a generic use-case description from name
    templates = {
        'query': f'需查询{name_parts}数据库获取信息',
        'analyze': f'需分析{name_parts}数据',
        'annotate': f'需对{name_parts}进行注释',
        'find': f'需查找/搜索{name_parts}',
        'design': f'需设计{name_parts}',
        'simulate': f'需模拟{name_parts}',
        'perform': f'需执行{name_parts}实验/分析',
        'get': f'需获取{name_parts}',
        'generate': f'需生成{name_parts}',
        'predict': f'需预测{name_parts}',
        'segment': f'需对{name_parts}进行分割/量化',
        'create': f'需创建{name_parts}',
        'detect': f'需检测{name_parts}',
        'retrieve': f'需检索{name_parts}',
        'reconstruct': f'需重建{name_parts}',
        'sample': f'需采样{name_parts}',
    }
    
    for prefix, tmpl in templates.items():
        if skill_id.startswith(prefix):
            return tmpl
    
    return f'需使用{name_parts}功能，适用于相关生信分析场景'

# Scan all SKILL.md files
patched = 0
generated = 0
overridden = 0

for sf in glob.glob(os.path.join(SKILLS_DIR, '*', 'SKILL.md')):
    skill_id = os.path.basename(os.path.dirname(sf))
    
    with open(sf, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if when_to_use already exists
    if re.search(r'^when_to_use:', content, re.MULTILINE):
        continue  # Already has it
    
    # Extract description
    desc_match = re.search(r'^description:\s*(.+)$', content, re.MULTILINE)
    description = desc_match.group(1).strip() if desc_match else ''
    
    # Use override if in collision groups
    if skill_id in COLLISION_OVERRIDES:
        wtu = COLLISION_OVERRIDES[skill_id]
        overridden += 1
    else:
        wtu = generate_when_to_use(skill_id, description)
        if description and description != '""' and len(description) > 5:
            generated += 0  # Using existing description
        else:
            generated += 1
    
    # Helper to insert when_to_use after name/description
    if desc_match:
        # Insert after description line
        insert_pos = desc_match.end()
        new_content = content[:insert_pos] + f'\nwhen_to_use: "{wtu}"' + content[insert_pos:]
    else:
        # Insert after name line
        name_match = re.search(r'^name:.*$', content, re.MULTILINE)
        if name_match:
            insert_pos = name_match.end()
            new_content = content[:insert_pos] + f'\nwhen_to_use: "{wtu}"' + content[insert_pos:]
        else:
            # Insert after first frontmatter ---
            fm_end = content.find('---', 3)
            if fm_end > 0:
                new_content = content[:fm_end] + f'when_to_use: "{wtu}"\n' + content[fm_end:]
            else:
                new_content = content  # Can't insert
    
    if new_content != content:
        with open(sf, 'w', encoding='utf-8') as f:
            f.write(new_content)
        patched += 1

print(f'Patched: {patched} skills')
print(f'  with override (collision groups): {overridden}')
print(f'  auto-generated from name: {generated}')
print(f'  using existing description: {patched - overridden - generated}')
