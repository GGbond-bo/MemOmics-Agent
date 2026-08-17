
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
Installation Helper for Annotation Tools

Provides automatic installation of SNPEff and VEP via conda.
"""

import subprocess
import sys
import shutil


def check_conda_available():
    """
    Check if conda is available.

    Returns
    -------
    bool
        True if conda is in PATH
    """
    return shutil.which('conda') is not None


def install_snpeff():
    """
    Install SNPEff via bioconda.

    This is a managed dependency (pre-built binary) that can be safely
    auto-installed in conda environments.

    Returns
    -------
    bool
        True if installation successful

    Raises
    ------
    RuntimeError
        If conda is not available or installation fails
    """
    if not check_conda_available():
        raise RuntimeError(
            "conda is not available. Please install conda first:\n"
            "  https://docs.conda.io/en/latest/miniconda.html\n\n"
            "Or install SNPEff manually:\n"
            "  conda install -c bioconda snpeff"
        )

    print("=" * 70)
    print("Installing SNPEff via bioconda...")
    print("=" * 70)
    print()
    print("This will install:")
    print("  - SNPEff (variant annotation tool)")
    print("  - Java runtime (bundled)")
    print()
    print("Installation size: ~250 MB")
    print("Time: ~2-5 minutes")
    print()

    cmd = [
        'conda', 'install',
        '-c', 'bioconda',
        '-y',  # Auto-confirm
        'snpeff'
    ]

    print("Running:", ' '.join(cmd))
    print()

    try:
        result = subprocess.run(
            cmd,
            check=True,
            text=True
        )

        print()
        print("=" * 70)
        print("✓ SNPEff installed successfully!")
        print("=" * 70)
        print()

        # Verify installation
        from run_snpeff import check_snpeff_installation
        is_installed, snpeff_path, version = check_snpeff_installation()

        if is_installed:
            print(f"  Location: {snpeff_path}")
            print(f"  Version: {version}")
            print()
            return True
        else:
            print("  WARNING: Installation completed but SNPEff not found in PATH")
            print("  You may need to restart your shell or activate your conda environment")
            return False

    except subprocess.CalledProcessError as e:
        print()
        print("=" * 70)
        print("✗ SNPEff installation failed")
        print("=" * 70)
        print()
        print("Please install manually:")
        print("  conda install -c bioconda snpeff")
        print()
        print("Or use VEP instead:")
        print("  conda install -c bioconda ensembl-vep")
        raise RuntimeError(f"SNPEff installation failed: {e}")


def install_vep():
    """
    Install Ensembl VEP via bioconda.

    Note: VEP cache must be installed separately (15-20 GB).

    Returns
    -------
    bool
        True if installation successful

    Raises
    ------
    RuntimeError
        If conda is not available or installation fails
    """
    if not check_conda_available():
        raise RuntimeError(
            "conda is not available. Please install conda first:\n"
            "  https://docs.conda.io/en/latest/miniconda.html\n\n"
            "Or install VEP manually:\n"
            "  conda install -c bioconda ensembl-vep"
        )

    print("=" * 70)
    print("Installing Ensembl VEP via bioconda...")
    print("=" * 70)
    print()
    print("This will install:")
    print("  - Ensembl VEP (variant annotation tool)")
    print("  - Perl dependencies")
    print()
    print("Installation size: ~500 MB")
    print("Time: ~5-10 minutes")
    print()
    print("NOTE: VEP cache must be installed separately (15-20 GB):")
    print("  vep_install -a c -s homo_sapiens -y GRCh38")
    print()

    cmd = [
        'conda', 'install',
        '-c', 'bioconda',
        '-y',  # Auto-confirm
        'ensembl-vep'
    ]

    print("Running:", ' '.join(cmd))
    print()

    try:
        result = subprocess.run(
            cmd,
            check=True,
            text=True
        )

        print()
        print("=" * 70)
        print("✓ VEP installed successfully!")
        print("=" * 70)
        print()

        # Verify installation
        from run_vep import check_vep_installation
        is_installed, vep_path, version = check_vep_installation()

        if is_installed:
            print(f"  Location: {vep_path}")
            print(f"  Version: {version}")
            print()
            print("NEXT STEP: Install VEP cache (required):")
            print("  vep_install -a c -s homo_sapiens -y GRCh38")
            print()
            return True
        else:
            print("  WARNING: Installation completed but VEP not found in PATH")
            print("  You may need to restart your shell or activate your conda environment")
            return False

    except subprocess.CalledProcessError as e:
        print()
        print("=" * 70)
        print("✗ VEP installation failed")
        print("=" * 70)
        print()
        print("Please install manually:")
        print("  conda install -c bioconda ensembl-vep")
        print()
        print("Or use SNPEff instead:")
        print("  conda install -c bioconda snpeff")
        raise RuntimeError(f"VEP installation failed: {e}")


def install_annotation_tool(tool='snpeff'):
    """
    Install the specified annotation tool.

    Parameters
    ----------
    tool : str
        Tool to install ('snpeff' or 'vep')

    Returns
    -------
    bool
        True if installation successful
    """
    if tool.lower() == 'snpeff':
        return install_snpeff()
    elif tool.lower() == 'vep':
        return install_vep()
    else:
        raise ValueError(f"Unknown tool: {tool}. Choose 'snpeff' or 'vep'")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Install variant annotation tools via conda'
    )
    parser.add_argument(
        'tool',
        choices=['snpeff', 'vep'],
        help='Tool to install'
    )

    args = parser.parse_args()

    try:
        success = install_annotation_tool(args.tool)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
