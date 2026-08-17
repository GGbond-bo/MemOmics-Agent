
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
Validate primer specificity using NCBI Primer-BLAST, local BLAST, or in-silico PCR.

This module checks primer specificity at three levels of rigor:

1. ``in_silico_pcr`` — exact/near-exact match against ONE supplied sequence.
   This is fast and offline but only checks the transcript you give it. It
   says nothing about the rest of the genome (paralogs, pseudogenes, other
   transcripts). This is the honest *default*.
2. ``check_specificity_local_blast`` — genome/transcriptome-wide search using a
   local BLAST+ database. Parses real ``blastn`` output and counts off-target
   hits. Only runs if ``blastn`` and a database are available.
3. ``check_primer_specificity`` — NCBI Primer-BLAST. A genome-wide check is NOT
   performed by this offline build; it returns an honest ``not_run`` status
   rather than a stub implying the primers passed.

Every specificity function returns a ``specificity_status`` field so downstream
reports (MIQE checklist, JSON records) can state exactly what was — and was not —
verified. See ``SPECIFICITY_STATUS`` for the controlled vocabulary.

**Pseudogene / paralog caveat:** Common reference genes (ACTB, GAPDH, B2M, ...)
have processed pseudogenes and paralog families. In-silico PCR against a single
transcript CANNOT detect these off-targets. ``flag_pseudogene_risk`` flags such
genes so the result is marked ``flagged_high_risk_unverified`` until a
genome-wide check (local BLAST or Primer-BLAST) is actually performed.
"""

import time
import requests
from typing import Dict, List
from xml.etree import ElementTree as ET


# Controlled vocabulary for the `specificity_status` field returned by the
# specificity functions. Downstream code (reports, exports) should treat any
# value other than these as unknown.
SPECIFICITY_STATUS = {
    # in-silico PCR matched only the single supplied transcript; genome NOT checked
    "in_silico_on_target_only": "in_silico_on_target_only",
    # local blastn ran and found no (or acceptable) off-target hits
    "local_blast_passed": "local_blast_passed",
    # local blastn ran and found off-target hits above threshold
    "local_blast_failed": "local_blast_failed",
    # NCBI Primer-BLAST ran and found the primers specific
    "primer_blast_passed": "primer_blast_passed",
    # target is a known pseudogene/paralog-prone gene AND only in-silico-on-target
    # was performed → off-targets are plausible but UNVERIFIED
    "flagged_high_risk_unverified": "flagged_high_risk_unverified",
    # no specificity check was actually performed
    "not_run": "not_run",
}


# Curated set of human genes with well-documented processed pseudogenes and/or
# large paralog families. Primers against a single transcript of these genes can
# silently co-amplify pseudogenes (often retained in genomic DNA) or paralogs.
# Keys are upper-cased gene symbols. Prefixes ending in '*' match any symbol
# starting with that stem (e.g. 'TUBB*' matches TUBB, TUBB2A, TUBB4B, ...).
_PSEUDOGENE_RISK_GENES = {
    # Classic high-copy reference genes with many processed pseudogenes
    "ACTB": "beta-actin: ~20 processed pseudogenes plus the ACTG1 paralog; "
            "amplicons commonly co-amplify pseudogenes from genomic DNA",
    "GAPDH": "GAPDH: dozens of processed pseudogenes (e.g. GAPDHP*) across the genome",
    "B2M": "beta-2-microglobulin: multiple processed pseudogenes",
    "HPRT1": "HPRT1: known processed pseudogenes",
    "YWHAZ": "14-3-3 zeta: multiple pseudogenes and a large 14-3-3 paralog family",
    "RPL13A": "ribosomal protein L13a: many ribosomal-protein pseudogenes",
    "PPIA": "cyclophilin A: numerous processed pseudogenes",
    "PGK1": "phosphoglycerate kinase 1: processed pseudogenes",
    "TBP": "TATA-box binding protein: pseudogenes reported",
    "SDHA": "succinate dehydrogenase A: several pseudogenes (SDHAP*)",
    "UBC": "polyubiquitin C: repetitive ubiquitin units / paralogs (UBB, UBA52, RPS27A)",
    "GUSB": "beta-glucuronidase: pseudogenes reported",
}

# Symbol-prefix families: any gene whose symbol starts with one of these stems is
# treated as high-risk (large paralog families and/or pseudogene-rich).
_PSEUDOGENE_RISK_PREFIXES = {
    "TUBB": "tubulin beta family: many paralogs (TUBB, TUBB2A/B, TUBB4A/B, ...) and pseudogenes",
    "TUBA": "tubulin alpha family: many paralogs and pseudogenes",
    "ACTG": "cytoplasmic/smooth-muscle actin family: paralogs and pseudogenes",
    "RPL": "60S ribosomal protein L family: hundreds of ribosomal-protein pseudogenes",
    "RPS": "40S ribosomal protein S family: hundreds of ribosomal-protein pseudogenes",
    "HSP90A": "HSP90 alpha family: paralogs (HSP90AA1/AB1) and pseudogenes",
}


def flag_pseudogene_risk(gene_symbol: str) -> Dict:
    """
    Flag genes that are prone to pseudogene / paralog co-amplification.

    Primers designed against a single transcript of these genes can silently
    amplify processed pseudogenes (frequently retained in genomic DNA) or close
    paralogs. In-silico PCR against one transcript CANNOT see those off-targets,
    so a genome-wide specificity check (local BLAST or Primer-BLAST) is required
    before trusting specificity.

    Parameters
    ----------
    gene_symbol : str
        Gene symbol (e.g. "ACTB", "GAPDH"). Case-insensitive. May be None/empty,
        in which case no risk is reported (we cannot assess an unnamed target).

    Returns
    -------
    dict
        - 'gene_symbol': normalized (upper-cased) symbol or None
        - 'high_risk': bool
        - 'reason': str explanation (empty if not high-risk / unknown)

    Example
    -------
    >>> flag_pseudogene_risk("ACTB")['high_risk']
    True
    >>> flag_pseudogene_risk("MYNOVELGENE1")['high_risk']
    False
    """

    if not gene_symbol or not str(gene_symbol).strip():
        return {'gene_symbol': None, 'high_risk': False, 'reason': ''}

    symbol = str(gene_symbol).strip().upper()

    # Exact match against curated set
    if symbol in _PSEUDOGENE_RISK_GENES:
        return {
            'gene_symbol': symbol,
            'high_risk': True,
            'reason': _PSEUDOGENE_RISK_GENES[symbol],
        }

    # Prefix-family match (e.g. TUBB2A starts with TUBB)
    for prefix, reason in _PSEUDOGENE_RISK_PREFIXES.items():
        if symbol.startswith(prefix):
            return {
                'gene_symbol': symbol,
                'high_risk': True,
                'reason': reason,
            }

    return {'gene_symbol': symbol, 'high_risk': False, 'reason': ''}


def _apply_pseudogene_flag(results: Dict, gene_symbol: str) -> Dict:
    """
    Downgrade an in-silico-on-target result to high-risk-unverified when the
    target is a known pseudogene/paralog-prone gene.

    Only escalates when the current status is ``in_silico_on_target_only`` (i.e.
    no genome-wide check was performed). A result that already passed local BLAST
    or Primer-BLAST is left unchanged. Mutates and returns ``results``.
    """

    risk = flag_pseudogene_risk(gene_symbol)
    results['gene_symbol'] = risk['gene_symbol']
    results['pseudogene_risk'] = risk['high_risk']
    results['pseudogene_risk_reason'] = risk['reason']

    if risk['high_risk'] and results.get('specificity_status') == \
            SPECIFICITY_STATUS['in_silico_on_target_only']:
        results['specificity_status'] = SPECIFICITY_STATUS['flagged_high_risk_unverified']
        # is_specific is no longer trustworthy from in-silico-on-target alone
        results['is_specific'] = None
        results['warning'] = (
            f"⚠ HIGH-RISK SPECIFICITY: '{risk['gene_symbol']}' is prone to "
            f"pseudogene/paralog co-amplification ({risk['reason']}). "
            "Only in-silico PCR against a single transcript was performed, which "
            "CANNOT detect pseudogene or paralog off-targets. Run a genome-wide "
            "check (check_specificity_local_blast with a genomic BLAST db, or NCBI "
            "Primer-BLAST) before trusting these primers."
        )
    return results


def check_primer_specificity(
    forward_primer: str,
    reverse_primer: str,
    organism: str,
    database: str = "refseq_representative_genomes",
    max_targets: int = 10,
    primer_specificity_database: str = None,
    gene_symbol: str = None
) -> Dict:
    """
    Check primer specificity using NCBI Primer-BLAST.

    **IMPORTANT — this offline build does NOT perform a genome-wide check.**
    A real Primer-BLAST query requires submitting a job to NCBI, polling for
    completion, and parsing the HTML/XML result (typically 30 s – several
    minutes per pair, subject to rate limits). That network workflow is not
    implemented here. Rather than return a stub that implies the primers passed,
    this function returns ``specificity_status == 'not_run'`` and a message
    explaining that the genome-wide check was not performed.

    To actually run a genome-wide check offline, use
    ``check_specificity_local_blast`` with a local genomic/transcriptomic BLAST
    database, or submit the primers to https://www.ncbi.nlm.nih.gov/tools/primer-blast/
    manually and record the result.

    **Rate limits (if you implement the network workflow):**
    - Without API key: max 3 requests/second
    - With API key: max 10 requests/second
    - Add a 3–5 second delay between calls to be safe.

    Parameters
    ----------
    forward_primer : str
        Forward primer sequence
    reverse_primer : str
        Reverse primer sequence
    organism : str
        Target organism name (e.g., "Homo sapiens", "Mus musculus")
    database : str
        NCBI database to search (e.g. "refseq_representative_genomes",
        "refseq_rna", "nr"). Default: "refseq_representative_genomes"
    max_targets : int
        Maximum number of targets to return. Default: 10
    primer_specificity_database : str, optional
        Organism-specific database for specificity checking
    gene_symbol : str, optional
        Target gene symbol, used to attach a pseudogene/paralog risk flag.

    Returns
    -------
    dict
        Specificity results including:
        - 'specificity_status': 'not_run' (genome-wide check not performed here)
        - 'is_specific': None (unknown — not checked)
        - 'on_target_hits' / 'off_target_hits': None
        - 'off_targets': []
        - 'validation_method': 'primer_blast_not_run'
        - 'note' / 'submit_url': how to run the check manually
        - 'pseudogene_risk' / 'pseudogene_risk_reason': from flag_pseudogene_risk

    Example
    -------
    >>> spec = check_primer_specificity("ATGC...", "CGTA...", "Homo sapiens")
    >>> spec['specificity_status']
    'not_run'
    """

    # Validate inputs
    forward_primer = forward_primer.upper().strip()
    reverse_primer = reverse_primer.upper().strip()

    if not all(base in 'ATCGN' for base in forward_primer + reverse_primer):
        raise ValueError("Primers must contain only A, T, C, G, or N")

    # Build the Primer-BLAST submission URL so the user can run it manually.
    base_url = "https://www.ncbi.nlm.nih.gov/tools/primer-blast/index.cgi"
    params = {
        'PRIMER_LEFT_INPUT': forward_primer,
        'PRIMER_RIGHT_INPUT': reverse_primer,
        'ORGANISM': organism,
        'PRIMER_SPECIFICITY_DATABASE': database,
        'TOTAL_PRIMER_SPECIFICITY_MISMATCH': 1,
        'TOTAL_MISMATCH_IGNORE': 6,
        'NUM_TARGETS_WITH_PRIMERS': max_targets,
        'HITSIZE': max_targets,
    }
    submit_url = base_url + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    print("⚠ Primer-BLAST genome-wide specificity check was NOT performed.")
    print("  This offline build does not submit jobs to NCBI.")
    print("  Run check_specificity_local_blast with a genomic BLAST db, or submit")
    print("  the primers to NCBI Primer-BLAST manually (URL in the returned dict).")

    results = {
        'specificity_status': SPECIFICITY_STATUS['not_run'],
        'is_specific': None,          # unknown — genome was NOT checked
        'num_products': None,
        'on_target_hits': None,
        'off_target_hits': None,
        'products': [],
        'off_targets': [],
        'validation_method': 'primer_blast_not_run',
        'organism': organism,
        'database': database,
        'submit_url': submit_url,
        'note': (
            "Genome-wide Primer-BLAST check was NOT performed by this offline "
            "build. Submit the primers manually via submit_url, or use "
            "check_specificity_local_blast with a local genomic database."
        ),
    }

    # Attach pseudogene/paralog risk info (does not escalate status here because
    # status is already 'not_run', which is honest on its own).
    risk = flag_pseudogene_risk(gene_symbol)
    results['gene_symbol'] = risk['gene_symbol']
    results['pseudogene_risk'] = risk['high_risk']
    results['pseudogene_risk_reason'] = risk['reason']
    if risk['high_risk']:
        results['warning'] = (
            f"⚠ HIGH-RISK SPECIFICITY: '{risk['gene_symbol']}' is prone to "
            f"pseudogene/paralog co-amplification ({risk['reason']}). A genome-wide "
            "specificity check is strongly recommended and was NOT performed."
        )

    return results


def check_specificity_local_blast(
    forward_primer: str,
    reverse_primer: str,
    blast_db_path: str,
    max_mismatches: int = 3,
    max_offtarget_hits: int = 0,
    gene_symbol: str = None
) -> Dict:
    """
    Check primer specificity using a local BLAST+ installation.

    Runs ``blastn -task blastn-short`` for both primers against a local database
    and PARSES the tabular (outfmt 6) output to count off-target hits. A hit is
    counted as a candidate binding site when its mismatch count is within
    ``max_mismatches``. The pair is judged specific when the number of distinct
    off-target subjects is at most ``max_offtarget_hits``.

    Requires BLAST+ (the ``blastn`` executable) and a formatted database. If
    either is missing, returns ``specificity_status == 'not_run'`` instead of a
    misleading "passed" placeholder.

    Parameters
    ----------
    forward_primer : str
        Forward primer sequence
    reverse_primer : str
        Reverse primer sequence
    blast_db_path : str
        Path to a local BLAST database (the prefix passed to ``-db``)
    max_mismatches : int
        Maximum mismatches for a hit to be considered a real binding site.
        Default: 3
    max_offtarget_hits : int
        Maximum number of distinct off-target subject sequences tolerated before
        the pair is flagged ``local_blast_failed``. Default: 0 (strict).
    gene_symbol : str, optional
        Target gene symbol, used to attach a pseudogene/paralog risk flag.

    Returns
    -------
    dict
        - 'specificity_status': 'local_blast_passed' | 'local_blast_failed' | 'not_run'
        - 'is_specific': bool | None
        - 'num_hits' / 'off_target_hits': counts (None if not run)
        - 'hits': parsed hit rows (list of dicts)
        - 'validation_method': 'local_blast' | 'local_blast_not_run'
        - 'note': explanation when not run
        - 'pseudogene_risk' / 'pseudogene_risk_reason': from flag_pseudogene_risk

    Example
    -------
    >>> spec = check_specificity_local_blast(
    ...     "ATGC...", "CGTA...", "/path/to/blastdb/human_genome"
    ... )
    >>> spec['specificity_status']
    'local_blast_passed'
    """

    import subprocess
    import shutil
    import tempfile
    import os

    forward_primer = forward_primer.upper().strip()
    reverse_primer = reverse_primer.upper().strip()

    base_result = {
        'validation_method': 'local_blast',
        'gene_symbol': None,
        'pseudogene_risk': False,
        'pseudogene_risk_reason': '',
        'max_mismatches': max_mismatches,
        'max_offtarget_hits': max_offtarget_hits,
    }

    # Honest 'not_run' when blastn is unavailable or no db was provided.
    if shutil.which('blastn') is None:
        result = dict(base_result)
        result.update({
            'specificity_status': SPECIFICITY_STATUS['not_run'],
            'is_specific': None,
            'num_hits': None,
            'off_target_hits': None,
            'hits': [],
            'validation_method': 'local_blast_not_run',
            'note': "blastn executable not found on PATH; genome-wide check NOT run.",
        })
        return _apply_pseudogene_flag(result, gene_symbol) if gene_symbol else result

    if not blast_db_path:
        result = dict(base_result)
        result.update({
            'specificity_status': SPECIFICITY_STATUS['not_run'],
            'is_specific': None,
            'num_hits': None,
            'off_target_hits': None,
            'hits': [],
            'validation_method': 'local_blast_not_run',
            'note': "No blast_db_path provided; genome-wide check NOT run.",
        })
        return _apply_pseudogene_flag(result, gene_symbol) if gene_symbol else result

    # Write primers to a temp FASTA
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.fasta') as f:
        f.write(f">forward\n{forward_primer}\n")
        f.write(f">reverse\n{reverse_primer}\n")
        primer_file = f.name

    try:
        # outfmt 6 columns: qseqid sseqid pident length mismatch gapopen
        #                   qstart qend sstart send evalue bitscore
        blast_cmd = [
            'blastn',
            '-query', primer_file,
            '-db', blast_db_path,
            '-task', 'blastn-short',
            '-outfmt', '6',
            '-max_target_seqs', '500',
        ]

        proc = subprocess.run(blast_cmd, capture_output=True, text=True)

        if proc.returncode != 0:
            result = dict(base_result)
            result.update({
                'specificity_status': SPECIFICITY_STATUS['not_run'],
                'is_specific': None,
                'num_hits': None,
                'off_target_hits': None,
                'hits': [],
                'validation_method': 'local_blast_not_run',
                'note': f"blastn failed (returncode {proc.returncode}): "
                        f"{proc.stderr.strip()[:300]}",
            })
            return _apply_pseudogene_flag(result, gene_symbol) if gene_symbol else result

        # Parse tabular output. Keep only hits within the mismatch tolerance.
        hits = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            cols = line.split('\t')
            if len(cols) < 12:
                continue
            try:
                mismatch = int(cols[4])
            except ValueError:
                continue
            if mismatch > max_mismatches:
                continue
            hits.append({
                'query': cols[0],
                'subject': cols[1],
                'pident': float(cols[2]),
                'length': int(cols[3]),
                'mismatch': mismatch,
                'sstart': int(cols[8]),
                'send': int(cols[9]),
                'evalue': float(cols[10]),
            })

        # Distinct subject sequences hit (the genome-wide off-target footprint).
        # We do not know the on-target subject id here, so we report the total
        # distinct subjects; specificity is judged against max_offtarget_hits,
        # which the caller can set to the number of legitimate on-target loci.
        distinct_subjects = sorted({h['subject'] for h in hits})
        off_target_count = max(0, len(distinct_subjects) - 1)

        is_specific = off_target_count <= max_offtarget_hits
        status = (SPECIFICITY_STATUS['local_blast_passed'] if is_specific
                  else SPECIFICITY_STATUS['local_blast_failed'])

        result = dict(base_result)
        result.update({
            'specificity_status': status,
            'is_specific': is_specific,
            'num_hits': len(hits),
            'distinct_subjects': distinct_subjects,
            'off_target_hits': off_target_count,
            'hits': hits[:50],  # cap to keep the record small
            'blast_db': blast_db_path,
            'note': (
                f"Local blastn found {len(hits)} hit(s) within {max_mismatches} "
                f"mismatch(es) across {len(distinct_subjects)} distinct subject(s)."
            ),
        })
        # Pseudogene flag does not override a real genome-wide result, but is
        # still attached for context.
        return _apply_pseudogene_flag(result, gene_symbol) if gene_symbol else result

    finally:
        if os.path.exists(primer_file):
            os.remove(primer_file)


def _hamming_match_positions(sequence: str, pattern: str, max_mismatches: int) -> List[int]:
    """
    Return all start positions where ``pattern`` matches ``sequence`` allowing up
    to ``max_mismatches`` substitutions (Hamming distance; no indels).

    Exact-match-equivalent when max_mismatches == 0. 'N' in either sequence is
    treated as a wildcard (never counts as a mismatch).
    """

    positions = []
    plen = len(pattern)
    if plen == 0 or plen > len(sequence):
        return positions

    for i in range(len(sequence) - plen + 1):
        mismatches = 0
        ok = True
        for j in range(plen):
            s = sequence[i + j]
            p = pattern[j]
            if s == p or s == 'N' or p == 'N':
                continue
            mismatches += 1
            if mismatches > max_mismatches:
                ok = False
                break
        if ok:
            positions.append(i)
    return positions


def in_silico_pcr(
    forward_primer: str,
    reverse_primer: str,
    sequence: str,
    max_product_size: int = 5000,
    max_mismatches: int = 0,
    gene_symbol: str = None
) -> List[Dict]:
    """
    Perform in-silico PCR against a SINGLE supplied sequence.

    This is a fast, offline check that finds where the primers would prime on the
    ONE sequence you pass in. It now honors ``max_mismatches`` via a Hamming
    (substitution-only) search at each candidate binding site, so you can model
    tolerant priming.

    **Scope / honesty:** This checks ONLY the supplied transcript. It does NOT
    look at the rest of the genome, so it cannot detect pseudogene or paralog
    off-targets. A clean result here means "specific to this transcript", NOT
    "genome-wide specific". For a genome-wide judgement use
    ``check_specificity_local_blast`` or NCBI Primer-BLAST.

    Parameters
    ----------
    forward_primer : str
        Forward primer sequence (5'->3')
    reverse_primer : str
        Reverse primer sequence (5'->3')
    sequence : str
        Target sequence to scan
    max_product_size : int
        Maximum PCR product size to report. Default: 5000
    max_mismatches : int
        Maximum substitution mismatches allowed per primer binding site.
        Default: 0 (exact match). Set >0 to model tolerant priming.
    gene_symbol : str, optional
        If provided, the returned summary (see ``in_silico_pcr_report``) can flag
        pseudogene/paralog risk. This function itself returns the product list;
        use ``in_silico_pcr_report`` for the status-bearing summary.

    Returns
    -------
    list of dict
        One entry per predicted product:
        - 'forward_start', 'reverse_start', 'product_size', 'sequence'
        - 'forward_mismatches', 'reverse_mismatches'

    Example
    -------
    >>> products = in_silico_pcr("ATGCG...", "CGTAT...", "ATGCG...CGTAT")
    >>> print(f"Found {len(products)} products")
    """

    from Bio.Seq import Seq

    products = []

    forward_primer = forward_primer.upper()
    reverse_primer = reverse_primer.upper()
    sequence = sequence.upper()

    # Reverse primer binds the template as its reverse complement.
    reverse_primer_rc = str(Seq(reverse_primer).reverse_complement())

    # Forward binding sites (allowing up to max_mismatches substitutions).
    forward_sites = _hamming_match_positions(sequence, forward_primer, max_mismatches)

    # Reverse binding sites: match the reverse-complement of the reverse primer.
    # We record (end_position, mismatches) so we can compute product size.
    reverse_sites = []
    for pos in _hamming_match_positions(sequence, reverse_primer_rc, max_mismatches):
        # recompute mismatch count at this site for reporting
        mm = sum(
            1 for j in range(len(reverse_primer_rc))
            if sequence[pos + j] != reverse_primer_rc[j]
            and sequence[pos + j] != 'N' and reverse_primer_rc[j] != 'N'
        )
        reverse_sites.append((pos + len(reverse_primer_rc), mm))

    # Per-forward-site mismatch counts for reporting.
    forward_mm = {}
    for f_pos in forward_sites:
        forward_mm[f_pos] = sum(
            1 for j in range(len(forward_primer))
            if sequence[f_pos + j] != forward_primer[j]
            and sequence[f_pos + j] != 'N' and forward_primer[j] != 'N'
        )

    # Pair forward (upstream) with reverse (downstream) within size limit.
    for f_pos in forward_sites:
        for r_end, r_mm in reverse_sites:
            if f_pos < r_end:
                product_size = r_end - f_pos
                if product_size <= max_product_size:
                    products.append({
                        'forward_start': f_pos,
                        'reverse_start': r_end,
                        'product_size': product_size,
                        'forward_mismatches': forward_mm[f_pos],
                        'reverse_mismatches': r_mm,
                        'sequence': sequence[f_pos:r_end],
                    })

    return products


def in_silico_pcr_report(
    forward_primer: str,
    reverse_primer: str,
    sequence: str,
    max_product_size: int = 5000,
    max_mismatches: int = 0,
    gene_symbol: str = None
) -> Dict:
    """
    Run ``in_silico_pcr`` and wrap the result in a status-bearing summary.

    This is the recommended entry point for validation pipelines: it returns the
    same product list plus a ``specificity_status`` field and, when
    ``gene_symbol`` is a known pseudogene/paralog-prone gene, escalates the status
    to ``flagged_high_risk_unverified`` with a prominent warning.

    Returns
    -------
    dict
        - 'specificity_status': 'in_silico_on_target_only' or
          'flagged_high_risk_unverified'
        - 'is_specific': bool (True iff exactly one on-target product) or None if
          flagged high-risk (because in-silico-on-target cannot confirm it)
        - 'num_products', 'on_target_hits', 'off_target_hits'
        - 'products': list from in_silico_pcr
        - 'validation_method': 'in_silico_pcr'
        - 'pseudogene_risk', 'pseudogene_risk_reason', 'gene_symbol'
        - 'warning': present iff flagged high-risk
    """

    products = in_silico_pcr(
        forward_primer, reverse_primer, sequence,
        max_product_size=max_product_size, max_mismatches=max_mismatches
    )

    num_products = len(products)
    # On the single supplied transcript, "specific" means exactly one product.
    on_target = 1 if num_products >= 1 else 0
    off_target = max(0, num_products - 1)

    results = {
        'specificity_status': SPECIFICITY_STATUS['in_silico_on_target_only'],
        'is_specific': num_products == 1,
        'num_products': num_products,
        'on_target_hits': on_target,
        'off_target_hits': off_target,
        'products': products,
        'validation_method': 'in_silico_pcr',
        'max_mismatches': max_mismatches,
        'note': (
            "In-silico PCR checked ONLY the supplied transcript. This does NOT "
            "detect pseudogene or paralog off-targets elsewhere in the genome."
        ),
    }

    # Escalate to high-risk-unverified for pseudogene-prone genes.
    return _apply_pseudogene_flag(results, gene_symbol)
