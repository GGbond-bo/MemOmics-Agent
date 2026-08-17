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
SNPEff Wrapper Module

This module provides a Python interface for running SNPEff variant annotation.
"""

import os
import subprocess
import sys
from pathlib import Path
import shutil


def check_snpeff_installation():
    """
    Check if SNPEff is installed and accessible.

    Returns
    -------
    tuple
        (is_installed, snpeff_path, version)
    """
    snpeff_path = shutil.which('snpEff')

    if not snpeff_path:
        # Try alternative: snpEff (capitalized)
        snpeff_path = shutil.which('snpEff')

    if not snpeff_path:
        return False, None, None

    try:
        result = subprocess.run(
            ['snpEff', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )

        version = result.stdout.strip() or result.stderr.strip()

        return True, snpeff_path, version

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False, snpeff_path, None


def download_snpeff_database(genome, data_dir=None):
    """
    Download SNPEff database for a specific genome.

    Parameters
    ----------
    genome : str
        Genome identifier (e.g., 'GRCh38.105', 'GRCh37.75', 'GRCm39.105')
    data_dir : str, optional
        Directory to store databases (default: ~/.snpeff)

    Returns
    -------
    str
        Path to data directory
    """
    if data_dir is None:
        data_dir = Path.home() / ".snpeff"
    else:
        data_dir = Path(data_dir)

    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading SNPEff database for {genome}...")
    print(f"Data directory: {data_dir}")

    cmd = [
        'snpEff',
        'download',
        '-dataDir', str(data_dir),
        genome
    ]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )

        print(result.stdout)
        print(f"\n✓ SNPEff database downloaded successfully to {data_dir}")
        return str(data_dir)

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Error downloading SNPEff database: {e}")
        print("\nStderr:")
        print(e.stderr)
        print("\nAvailable genomes: snpEff databases")
        raise


def list_snpeff_databases(search_term=None):
    """
    List available SNPEff databases.

    Parameters
    ----------
    search_term : str, optional
        Search term to filter databases (e.g., 'human', 'GRCh38')

    Returns
    -------
    list
        List of available database names
    """
    cmd = ['snpEff', 'databases']

    if search_term:
        cmd.append(search_term)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        print(result.stdout)

    except subprocess.CalledProcessError as e:
        print(f"Error listing databases: {e}")
        raise


def run_snpeff(
    input_vcf,
    output_vcf,
    genome,
    data_dir=None,
    stats=None,
    csv_stats=None,
    format_eff=False,
    canon=True,
    hgvs=True,
    lof=True,
    no_downstream=False,
    no_upstream=False,
    no_intergenic=False,
    threads=1,
    additional_args=None
):
    """
    Run SNPEff on a VCF file.

    Parameters
    ----------
    input_vcf : str
        Path to input VCF file
    output_vcf : str
        Path to output annotated VCF file
    genome : str
        Genome database name (e.g., 'GRCh38.105')
    data_dir : str, optional
        SNPEff data directory (default: ~/.snpeff)
    stats : str, optional
        Path to HTML statistics file
    csv_stats : str, optional
        Path to CSV statistics file
    format_eff : bool
        Use old EFF format instead of ANN (not recommended)
    canon : bool
        Mark canonical transcripts (default: True)
    hgvs : bool
        Add HGVS notation (default: True)
    lof : bool
        Predict loss-of-function variants (default: True)
    no_downstream : bool
        Skip downstream gene variants
    no_upstream : bool
        Skip upstream gene variants
    no_intergenic : bool
        Skip intergenic variants
    threads : int
        Number of threads (default: 1)
    additional_args : list, optional
        Additional SNPEff arguments

    Returns
    -------
    str
        Path to output annotated VCF file
    """
    # Check SNPEff installation
    is_installed, snpeff_path, version = check_snpeff_installation()
    if not is_installed:
        raise RuntimeError(
            "SNPEff is not installed or not in PATH.\n"
            "Install with: conda install -c bioconda snpeff"
        )

    print(f"Using SNPEff: {snpeff_path}")
    if version:
        print(f"Version: {version}")

    # Set data directory
    if data_dir is None:
        data_dir = Path.home() / ".snpeff"
    else:
        data_dir = Path(data_dir)

    # Build command
    cmd = ['snpEff', 'ann']

    # Add options
    if data_dir:
        cmd.extend(['-dataDir', str(data_dir)])

    if stats:
        cmd.extend(['-stats', stats])

    if csv_stats:
        cmd.extend(['-csvStats', csv_stats])

    if format_eff:
        cmd.append('-formatEff')

    if canon:
        cmd.append('-canon')

    if hgvs:
        cmd.append('-hgvs')

    if lof:
        cmd.append('-lof')

    if no_downstream:
        cmd.append('-no-downstream')

    if no_upstream:
        cmd.append('-no-upstream')

    if no_intergenic:
        cmd.append('-no-intergenic')

    if threads > 1:
        cmd.extend(['-t', str(threads)])

    # Add additional arguments
    if additional_args:
        cmd.extend(additional_args)

    # Add genome and input
    cmd.append(genome)
    cmd.append(str(input_vcf))

    # Print command
    print("\nRunning SNPEff command:")
    print(" ".join(cmd))
    print()

    # Run SNPEff and redirect output to file
    try:
        with open(output_vcf, 'w') as outfile:
            result = subprocess.run(
                cmd,
                stdout=outfile,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

            if result.stderr:
                print("SNPEff info/warnings:")
                print(result.stderr)

        print(f"\n✓ SNPEff annotation complete: {output_vcf}")

        if stats:
            print(f"  Statistics: {stats}")

        return str(output_vcf)

    except subprocess.CalledProcessError as e:
        print(f"\n✗ SNPEff failed with error code {e.returncode}")
        print("\nStderr:")
        print(e.stderr)
        raise RuntimeError(f"SNPEff annotation failed: {e}")


def run_snpeff_simple(input_vcf, output_vcf, genome, data_dir=None):
    """
    Run SNPEff with default settings (simplified interface).

    Parameters
    ----------
    input_vcf : str
        Path to input VCF file
    output_vcf : str
        Path to output annotated VCF file
    genome : str
        Genome database name (e.g., 'GRCh38.105')
    data_dir : str, optional
        SNPEff data directory (default: ~/.snpeff)

    Returns
    -------
    str
        Path to output annotated VCF file
    """
    stats_file = str(output_vcf).replace('.vcf', '_stats.html')

    return run_snpeff(
        input_vcf=input_vcf,
        output_vcf=output_vcf,
        genome=genome,
        data_dir=data_dir,
        stats=stats_file,
        canon=True,
        hgvs=True,
        lof=True,
        threads=4
    )


def run_snpeff_coding_only(input_vcf, output_vcf, genome, data_dir=None):
    """
    Run SNPEff with focus on coding regions only (skip intergenic/upstream/downstream).

    Parameters
    ----------
    input_vcf : str
        Path to input VCF file
    output_vcf : str
        Path to output annotated VCF file
    genome : str
        Genome database name
    data_dir : str, optional
        SNPEff data directory (default: ~/.snpeff)

    Returns
    -------
    str
        Path to output annotated VCF file
    """
    stats_file = str(output_vcf).replace('.vcf', '_stats.html')

    return run_snpeff(
        input_vcf=input_vcf,
        output_vcf=output_vcf,
        genome=genome,
        data_dir=data_dir,
        stats=stats_file,
        canon=True,
        hgvs=True,
        lof=True,
        no_downstream=True,
        no_upstream=True,
        no_intergenic=True,
        threads=4
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run SNPEff on VCF file')
    parser.add_argument('input_vcf', nargs='?', help='Input VCF file')
    parser.add_argument('output_vcf', nargs='?', help='Output annotated VCF file')
    parser.add_argument('--genome', help='Genome database (e.g., GRCh38.105)')
    parser.add_argument('--data-dir', help='SNPEff data directory (default: ~/.snpeff)')
    parser.add_argument('--threads', type=int, default=4, help='Number of threads (default: 4)')
    parser.add_argument('--coding-only', action='store_true', help='Annotate coding regions only')
    parser.add_argument('--check', action='store_true', help='Check SNPEff installation only')
    parser.add_argument('--list-databases', action='store_true', help='List available databases')
    parser.add_argument('--download', help='Download database for specified genome')

    args = parser.parse_args()

    # Check installation
    if args.check:
        is_installed, snpeff_path, version = check_snpeff_installation()
        if is_installed:
            print(f"✓ SNPEff is installed: {snpeff_path}")
            print(f"  {version}")
            sys.exit(0)
        else:
            print("✗ SNPEff is not installed")
            print("Install with: conda install -c bioconda snpeff")
            sys.exit(1)

    # List databases
    if args.list_databases:
        list_snpeff_databases()
        sys.exit(0)

    # Download database
    if args.download:
        download_snpeff_database(args.download, data_dir=args.data_dir)
        sys.exit(0)

    # Run SNPEff
    if not args.input_vcf or not args.output_vcf or not args.genome:
        parser.error("input_vcf, output_vcf, and --genome are required for annotation")

    if args.coding_only:
        run_snpeff_coding_only(
            args.input_vcf,
            args.output_vcf,
            args.genome,
            data_dir=args.data_dir
        )
    else:
        run_snpeff_simple(
            args.input_vcf,
            args.output_vcf,
            args.genome,
            data_dir=args.data_dir
        )
