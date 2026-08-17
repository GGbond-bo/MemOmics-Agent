# 铁律：运行记录(query_logs)只是参考，不能跳过 rail_review/debate_analysis 审查

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
Ensembl VEP Wrapper Module

This module provides a Python interface for running Ensembl Variant Effect Predictor (VEP).
"""

import os
import subprocess
import sys
from pathlib import Path
import shutil


def check_vep_installation():
    """
    Check if VEP is installed and accessible.

    Returns
    -------
    tuple
        (is_installed, vep_path, version)
    """
    vep_path = shutil.which('vep')

    if not vep_path:
        return False, None, None

    try:
        result = subprocess.run(
            ['vep', '--help'],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Extract version from help text
        version = None
        for line in result.stdout.split('\n'):
            if 'ensembl-vep' in line.lower():
                version = line.strip()
                break

        return True, vep_path, version

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False, vep_path, None


def install_vep_cache(species="homo_sapiens", assembly="GRCh38", cache_dir=None):
    """
    Download and install VEP cache for a specific species and assembly.

    Parameters
    ----------
    species : str
        Species name (e.g., 'homo_sapiens', 'mus_musculus')
    assembly : str
        Genome assembly (e.g., 'GRCh38', 'GRCh37', 'GRCm39')
    cache_dir : str, optional
        Directory to install cache (default: ~/.vep)

    Returns
    -------
    str
        Path to installed cache directory
    """
    if cache_dir is None:
        cache_dir = Path.home() / ".vep"
    else:
        cache_dir = Path(cache_dir)

    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Installing VEP cache for {species} {assembly}...")
    print(f"Cache directory: {cache_dir}")
    print("This may take 10-30 minutes and requires 15-20 GB disk space.")

    cmd = [
        'vep_install',
        '--AUTO', 'c',
        '--SPECIES', species,
        '--ASSEMBLY', assembly,
        '--CACHEDIR', str(cache_dir),
        '--NO_UPDATE'
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"\n✓ VEP cache installed successfully to {cache_dir}")
        return str(cache_dir)

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Error installing VEP cache: {e}")
        print("\nManual installation:")
        print(f"  perl INSTALL.pl --AUTO c --SPECIES {species} --ASSEMBLY {assembly}")
        raise


def run_vep(
    input_vcf,
    output_vcf,
    genome="GRCh38",
    cache_dir=None,
    everything=True,
    vcf=True,
    force_overwrite=True,
    plugins=None,
    clinical_annotations=True,
    check_existing=True,
    max_af=None,
    fork=1,
    buffer_size=5000,
    additional_args=None
):
    """
    Run Ensembl VEP on a VCF file.

    Parameters
    ----------
    input_vcf : str
        Path to input VCF file
    output_vcf : str
        Path to output annotated VCF file
    genome : str
        Genome assembly (GRCh38, GRCh37, etc.)
    cache_dir : str, optional
        VEP cache directory (default: ~/.vep)
    everything : bool
        Use --everything flag (recommended)
    vcf : bool
        Output VCF format
    force_overwrite : bool
        Overwrite existing output file
    plugins : list, optional
        List of VEP plugins to use (e.g., ['CADD', 'dbNSFP,ALL'])
    clinical_annotations : bool
        Include ClinVar and other clinical annotations
    check_existing : bool
        Check for known variants in databases
    max_af : str, optional
        Add maximum allele frequency (e.g., 'gnomAD')
    fork : int
        Number of parallel processes (default: 1)
    buffer_size : int
        Number of variants to read at once (default: 5000)
    additional_args : list, optional
        Additional VEP command-line arguments

    Returns
    -------
    str
        Path to output annotated VCF file
    """
    # Check VEP installation
    is_installed, vep_path, version = check_vep_installation()
    if not is_installed:
        raise RuntimeError(
            "VEP is not installed or not in PATH.\n"
            "Install with: conda install -c bioconda ensembl-vep"
        )

    print(f"Using VEP: {vep_path}")
    if version:
        print(f"Version: {version}")

    # Set cache directory
    if cache_dir is None:
        cache_dir = Path.home() / ".vep"
    else:
        cache_dir = Path(cache_dir)

    if not cache_dir.exists():
        print(f"\nWarning: Cache directory not found: {cache_dir}")
        print("Run install_vep_cache() first or VEP will use online database (slower)")

    # Build command
    cmd = [
        'vep',
        '-i', str(input_vcf),
        '-o', str(output_vcf),
        '--assembly', genome,
        '--cache',
        '--dir_cache', str(cache_dir),
        '--fork', str(fork),
        '--buffer_size', str(buffer_size)
    ]

    # Add flags
    if everything:
        cmd.append('--everything')

    if vcf:
        cmd.append('--vcf')

    if force_overwrite:
        cmd.append('--force_overwrite')

    if clinical_annotations:
        cmd.extend(['--custom', 'ClinVar'])

    if check_existing:
        cmd.append('--check_existing')

    if max_af:
        cmd.extend(['--max_af', max_af])

    # Add plugins
    if plugins:
        for plugin in plugins:
            cmd.extend(['--plugin', plugin])

    # Add additional arguments
    if additional_args:
        cmd.extend(additional_args)

    # Print command
    print("\nRunning VEP command:")
    print(" ".join(cmd))
    print()

    # Run VEP
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )

        print(result.stdout)

        if result.stderr:
            print("VEP warnings/info:")
            print(result.stderr)

        print(f"\n✓ VEP annotation complete: {output_vcf}")
        return str(output_vcf)

    except subprocess.CalledProcessError as e:
        print(f"\n✗ VEP failed with error code {e.returncode}")
        print("\nStdout:")
        print(e.stdout)
        print("\nStderr:")
        print(e.stderr)
        raise RuntimeError(f"VEP annotation failed: {e}")


def run_vep_simple(input_vcf, output_vcf, genome="GRCh38", cache_dir=None):
    """
    Run VEP with default settings (simplified interface).

    Parameters
    ----------
    input_vcf : str
        Path to input VCF file
    output_vcf : str
        Path to output annotated VCF file
    genome : str
        Genome assembly (default: GRCh38)
    cache_dir : str, optional
        VEP cache directory (default: ~/.vep)

    Returns
    -------
    str
        Path to output annotated VCF file
    """
    return run_vep(
        input_vcf=input_vcf,
        output_vcf=output_vcf,
        genome=genome,
        cache_dir=cache_dir,
        everything=True,
        fork=4,
        buffer_size=5000
    )


def run_vep_clinical(input_vcf, output_vcf, genome="GRCh38", cache_dir=None):
    """
    Run VEP optimized for clinical analysis with pathogenicity predictions.

    Parameters
    ----------
    input_vcf : str
        Path to input VCF file
    output_vcf : str
        Path to output annotated VCF file
    genome : str
        Genome assembly (default: GRCh38)
    cache_dir : str, optional
        VEP cache directory (default: ~/.vep)

    Returns
    -------
    str
        Path to output annotated VCF file
    """
    return run_vep(
        input_vcf=input_vcf,
        output_vcf=output_vcf,
        genome=genome,
        cache_dir=cache_dir,
        everything=True,
        plugins=[
            'CADD',
            'REVEL',
            'dbNSFP,SIFT_pred,Polyphen2_HVAR_pred,MutationTaster_pred'
        ],
        clinical_annotations=True,
        check_existing=True,
        max_af='gnomAD',
        fork=4,
        buffer_size=5000
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run Ensembl VEP on VCF file')
    parser.add_argument('input_vcf', help='Input VCF file')
    parser.add_argument('output_vcf', help='Output annotated VCF file')
    parser.add_argument('--genome', default='GRCh38', help='Genome assembly (default: GRCh38)')
    parser.add_argument('--cache-dir', help='VEP cache directory (default: ~/.vep)')
    parser.add_argument('--fork', type=int, default=4, help='Number of parallel processes (default: 4)')
    parser.add_argument('--clinical', action='store_true', help='Use clinical annotation preset')
    parser.add_argument('--check', action='store_true', help='Check VEP installation only')

    args = parser.parse_args()

    # Check installation
    if args.check:
        is_installed, vep_path, version = check_vep_installation()
        if is_installed:
            print(f"✓ VEP is installed: {vep_path}")
            print(f"  {version}")
            sys.exit(0)
        else:
            print("✗ VEP is not installed")
            print("Install with: conda install -c bioconda ensembl-vep")
            sys.exit(1)

    # Run VEP
    if args.clinical:
        run_vep_clinical(
            args.input_vcf,
            args.output_vcf,
            genome=args.genome,
            cache_dir=args.cache_dir
        )
    else:
        run_vep_simple(
            args.input_vcf,
            args.output_vcf,
            genome=args.genome,
            cache_dir=args.cache_dir
        )
