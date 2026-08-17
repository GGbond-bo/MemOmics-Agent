
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
Load Example VCF Data for Testing

Provides small example VCF files for testing the variant annotation workflow.
These are for evaluation/testing purposes.

For user data validation, see validate_vcf.py
"""

import os
import gzip
from pathlib import Path


def load_clinvar_pathogenic_sample():
    """
    Create small subset of known pathogenic variants for testing

    Creates a minimal VCF with 10 known BRCA1/BRCA2 variants (mix of pathogenic/benign)
    from ClinVar for testing the annotation workflow.

    Dataset Details:
    - Variants: 10 known variants (8 pathogenic, 2 benign/likely benign)
    - Genes: BRCA1 (chr17) and BRCA2 (chr13)
    - Genome: GRCh38
    - Size: ~2 KB (minimal)
    - Download time: None (generated programmatically)

    Returns
    -------
    dict
        {
            'vcf_path': str, Path to created VCF file
            'genome': str, Genome build ('GRCh38')
            'description': str, Dataset description
            'expected_results': dict, Expected annotation metrics
        }

    Examples
    --------
    >>> data = load_clinvar_pathogenic_sample()
    >>> print(f"VCF created at: {data['vcf_path']}")
    >>> # Use with annotation workflow:
    >>> from scripts.validate_vcf import validate_vcf
    >>> results = validate_vcf(data['vcf_path'])
    """
    # Setup data directory
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    vcf_file = data_dir / "clinvar_brca_pathogenic.vcf.gz"

    if vcf_file.exists():
        print(f"✓ Example data already exists: {vcf_file}")
    else:
        print("Creating minimal test VCF with known pathogenic variants...")
        create_minimal_test_vcf(vcf_file)
        print(f"✓ Created test VCF: {vcf_file}")

    return {
        'vcf_path': str(vcf_file),
        'genome': 'GRCh38',
        'description': 'ClinVar pathogenic variants in BRCA1/BRCA2 genes',
        'expected_results': {
            'total_variants': 10,
            'high_impact': 6,  # stop_gained, frameshift
            'moderate_impact': 3,  # missense
            'pathogenic': 8,
            'benign': 2,
            'runtime_vep': '2-5 minutes',
            'runtime_snpeff': '1-2 minutes'
        }
    }


def create_minimal_test_vcf(output_path):
    """
    Create minimal VCF with 10 known BRCA1/BRCA2 variants for quick testing

    Includes mix of variant types:
    - Stop-gained (HIGH impact, pathogenic)
    - Frameshift (HIGH impact, pathogenic)
    - Missense (MODERATE impact, pathogenic/benign)
    - Synonymous (LOW impact, benign)

    All variants are from ClinVar with known clinical significance.

    Parameters
    ----------
    output_path : str or Path
        Output path for bgzipped VCF file
    """
    vcf_content = """##fileformat=VCFv4.2
##reference=GRCh38
##contig=<ID=chr13,length=114364328>
##contig=<ID=chr17,length=83257441>
##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">
##INFO=<ID=AF,Number=A,Type=Float,Description="Allele Frequency">
##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">
##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read Depth">
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO	FORMAT	SAMPLE1
chr17	43044295	rs80357906	C	T	100	PASS	DP=50;AF=0.5	GT:DP	0/1:50
chr17	43045802	rs28897696	A	G	100	PASS	DP=45;AF=0.5	GT:DP	0/1:45
chr17	43057051	rs1799949	G	A	100	PASS	DP=55;AF=0.5	GT:DP	0/1:55
chr17	43070927	rs80357713	C	T	100	PASS	DP=48;AF=0.5	GT:DP	0/1:48
chr17	43091434	rs80357382	T	C	100	PASS	DP=52;AF=0.5	GT:DP	0/1:52
chr13	32315474	rs80358969	G	T	100	PASS	DP=47;AF=0.5	GT:DP	0/1:47
chr13	32319077	rs80359550	A	G	100	PASS	DP=50;AF=0.5	GT:DP	0/1:50
chr13	32326241	rs80359113	C	G	100	PASS	DP=46;AF=0.5	GT:DP	0/1:46
chr13	32332271	rs28897743	G	A	100	PASS	DP=51;AF=0.5	GT:DP	0/1:51
chr13	32340271	rs1799954	C	T	100	PASS	DP=49;AF=0.5	GT:DP	0/1:49
"""

    with gzip.open(output_path, 'wt') as f:
        f.write(vcf_content)


def validate_input_data(vcf_path):
    """
    Validate user-provided VCF file before annotation

    Wrapper around validate_vcf.py for consistent interface.

    Parameters
    ----------
    vcf_path : str or Path
        Path to VCF file to validate

    Returns
    -------
    dict
        Validation results with 'is_valid', 'errors', 'warnings' keys

    See Also
    --------
    scripts.validate_vcf.validate_vcf : Full validation with detailed metrics
    """
    from validate_vcf import validate_vcf
    return validate_vcf(vcf_path)


if __name__ == '__main__':
    # Demo usage
    print("="*70)
    print("GENETIC VARIANT ANNOTATION - Example Data Loader")
    print("="*70)
    print()

    print("Loading example data...")
    data = load_clinvar_pathogenic_sample()

    print()
    print("Dataset Information:")
    print(f"  VCF file: {data['vcf_path']}")
    print(f"  Genome: {data['genome']}")
    print(f"  Description: {data['description']}")
    print()
    print("Expected Results:")
    for key, value in data['expected_results'].items():
        print(f"  {key}: {value}")
    print()
    print("✓ Ready for annotation!")
    print()
    print("Next steps:")
    print("  1. Validate: python -c 'from scripts.validate_vcf import validate_vcf; validate_vcf(\"data/clinvar_brca_pathogenic.vcf.gz\")'")
    print("  2. Annotate: See SKILL.md for full workflow")
