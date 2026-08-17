
# ============================================================
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


"""
Tool Selection Module for Variant Annotation

This module provides logic for automatically selecting between Ensembl VEP
and SNPEff based on organism, use case, resources, and annotation priorities.
"""


def select_annotation_tool(organism, use_case, resources, annotation_priorities):
    """
    Automatically select VEP or SNPEff based on use case and requirements.

    Parameters
    ----------
    organism : str
        Target organism ('human', 'mouse', 'rat', 'zebrafish', 'drosophila',
        'celegans', or other)
    use_case : str
        Primary analysis purpose ('clinical', 'population', 'cancer', 'research')
    resources : str
        Available computational resources ('high-performance', 'standard', 'limited')
    annotation_priorities : list
        List of required annotation types (e.g., ['clinical_significance',
        'pathogenicity_predictions', 'regulatory_impacts'])

    Returns
    -------
    str
        'vep' or 'snpeff' with reasoning

    Examples
    --------
    >>> select_annotation_tool('human', 'clinical', 'high-performance',
    ...                        ['clinical_significance', 'pathogenicity_predictions'])
    'vep'

    >>> select_annotation_tool('zebrafish', 'research', 'limited', ['basic'])
    'snpeff'
    """
    model_organisms = ['human', 'mouse', 'rat', 'zebrafish', 'drosophila', 'celegans']

    # Non-model organism → SNPEff (38,000+ genomes)
    if organism.lower() not in model_organisms:
        return 'snpeff'

    # Limited resources → SNPEff (faster, smaller cache)
    if resources == 'limited':
        return 'snpeff'

    # Clinical use case with comprehensive annotations → VEP
    if use_case == 'clinical' and 'clinical_significance' in annotation_priorities:
        return 'vep'

    # Regulatory annotations important → VEP (ENCODE integration)
    if 'regulatory_impacts' in annotation_priorities:
        return 'vep'

    # Multiple pathogenicity predictors needed → VEP (more plugins)
    pathogenicity_tools = ['pathogenicity_predictions', 'protein_domains', 'conservation_scores']
    if len([p for p in pathogenicity_tools if p in annotation_priorities]) >= 2:
        return 'vep'

    # Default: VEP for human (most comprehensive), SNPEff otherwise
    return 'vep' if organism.lower() == 'human' else 'snpeff'


def get_vep_recommended_config(use_case, annotation_priorities):
    """
    Get recommended VEP configuration based on use case.

    Parameters
    ----------
    use_case : str
        Primary analysis purpose
    annotation_priorities : list
        Required annotation types

    Returns
    -------
    dict
        Recommended VEP parameters
    """
    config = {
        'everything': True,
        'vcf': True,
        'force_overwrite': True,
        'fork': 4,
        'buffer_size': 5000
    }

    # Clinical use case
    if use_case == 'clinical':
        config['plugins'] = ['CADD', 'dbNSFP,ALL', 'REVEL']
        config['clinical_annotations'] = True
        config['check_existing'] = True

    # Add specific plugins based on priorities
    if 'conservation_scores' in annotation_priorities:
        if 'plugins' not in config:
            config['plugins'] = []
        config['plugins'].extend(['Conservation', 'Blosum62'])

    if 'regulatory_impacts' in annotation_priorities:
        config['regulatory'] = True

    # Population frequencies
    if 'population_frequencies' in annotation_priorities:
        config['max_af'] = 'gnomAD'

    return config


def get_snpeff_recommended_config(use_case):
    """
    Get recommended SNPEff configuration based on use case.

    Parameters
    ----------
    use_case : str
        Primary analysis purpose

    Returns
    -------
    dict
        Recommended SNPEff parameters
    """
    config = {
        'stats': 'snpeff_summary.html',
        'csv_stats': 'snpeff_stats.csv',
        'format_eff': False,  # Use ANN format
        'canon': True,
        'hgvs': True,
        'threads': 4
    }

    # Clinical/research: focus on coding regions
    if use_case in ['clinical', 'research']:
        config['lof'] = True
        config['no_downstream'] = True
        config['no_upstream'] = True
        config['no_intergenic'] = True

    return config


def compare_tools(organism='human', use_case='clinical'):
    """
    Generate comparison summary between VEP and SNPEff for given context.

    Parameters
    ----------
    organism : str
        Target organism
    use_case : str
        Primary analysis purpose

    Returns
    -------
    dict
        Comparison summary with pros/cons for each tool
    """
    comparison = {
        'vep': {
            'pros': [
                'Comprehensive clinical annotations (ClinVar, COSMIC, HGMD)',
                'Multiple pathogenicity predictions (SIFT, PolyPhen, CADD, REVEL)',
                'Extensive regulatory annotations (ENCODE)',
                'Quarterly updates',
                'VCF output compatible with most tools'
            ],
            'cons': [
                'Large cache files (~15-20 GB for human)',
                'Slower than SNPEff',
                'More complex setup'
            ]
        },
        'snpeff': {
            'pros': [
                'Fast annotation speed',
                'Lightweight setup (~2-3 GB for human)',
                'Simple installation',
                '38,000+ genome databases',
                'Excellent GATK integration'
            ],
            'cons': [
                'Fewer pathogenicity predictors',
                'Less comprehensive clinical databases',
                'Limited regulatory annotations'
            ]
        }
    }

    # Context-specific notes
    if organism.lower() not in ['human', 'mouse', 'rat']:
        comparison['snpeff']['pros'].insert(0, f'Excellent support for {organism}')
        comparison['vep']['cons'].append(f'Limited support for {organism}')

    if use_case == 'clinical':
        comparison['vep']['recommended'] = True
    elif use_case == 'research':
        comparison['snpeff']['recommended'] = True

    return comparison
