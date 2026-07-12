#!/usr/bin/env python3
"""paper_dissector.py — 论文深度拆解管线 v2.0
================================================================
从 PDF → 全文提取 → Methods 段定位 → 双层提取（正则+LLM）→ YAML → Loop Gate

Pipeline:
  1. verify_pdf()          — magic bytes 验证真伪
  2. extract_fulltext()    — pymupdf 逐页提取
  3. locate_methods()      — 正则定位 Methods/材料与方法 段
  4. extract_layer1()      — 正则提取: 包/版本/参数/平台
  5. extract_layer2()      — LLM 严格模板（API 可用时）
  6. to_yaml()             — 标准化 YAML 输出
  7. loop_gate()           — 质量门禁 (methods≥2000字/版本≥5/包≥8)
  8. write_to_kb()         — 写入 memomics/knowledge_base/

用法:
    python paper_dissector.py <pdf_path> [--kb] [--force]
"""
import os, sys, re, json, yaml, argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# ── 常量 ──────────────────────────────────────────────────────
BIOINFO_PACKAGES = [
    # scRNA-seq
    'Seurat', 'Scanpy', 'scran', 'scuttle', 'DropletUtils', 'SoupX',
    'CellBender', 'DoubletFinder', 'Scrublet', 'scDblFinder', 'DoubletDecon',
    'SCTransform', 'sctransform', 'scater', 'scPipe',
    'Harmony', 'scVI', 'scGen', 'BBKNN', 'LIGER', 'fastMNN', 'SeuratWrappers',
    'Monocle', 'Slingshot', 'scVelo', 'velocyto', 'scTour', 'destiny',
    'CellRank', 'Palantir', 'PAGA', 'diffusionMap',
    'CellChat', 'NicheNet', 'CellPhoneDB', 'SingleCellSignalR', 'iTALK',
    'SCENIC', 'pySCENIC', 'RcisTarget', 'iRegulon', 'cisTopic', 'chromVAR',
    'Signac', 'ArchR', 'MOFA', 'MOFA2', 'SEURAT', 'WGCNA',
    'MAST', 'DESeq2', 'edgeR', 'limma', 'wilcox', 'SCDE', 'D3E',
    'clusterProfiler', 'fgsea', 'GSEA', 'ReactomePA', 'enrichR',
    'Cytoscape', 'STRINGdb',
    # Bulk RNA-seq
    'STAR', 'HISAT2', 'Bowtie', 'Bowtie2', 'Salmon', 'Kallisto', 'RSEM',
    'featureCounts', 'HTSeq', 'DESeq2', 'edgeR', 'limma-voom', 'sleuth',
    'ComBat', 'RUVSeq', 'sva', 'PEER',
    # ATAC-seq / ChIP-seq
    'MACS2', 'MACS', 'HOMER', 'MEME', 'FIMO', 'Genrich', 'ATACseqQC',
    'deepTools', 'bamCoverage', 'computeMatrix', 'plotHeatmap',
    # Spatial
    'SpaceRanger', 'Seurat', 'Giotto', 'SPATA2', 'SpatialDE', 'BayesSpace',
    'MERFISH', 'Vizgen', 'Xenium', 'CosMx',
    # Common OS tools
    'CellRanger', 'cellranger', 'SpaceRanger', 'spaceranger', 'samtools',
    'bedtools', 'picard', 'FastQC', 'MultiQC', 'TrimGalore', 'cutadapt',
    'fastp', 'Trimmomatic',
]

# Parameters patterns to extract
PARAM_PATTERNS = [
    (r'(?:n\s*features|nfeatures|n_genes)\s*[=:]\s*(\d+)', 'nfeatures'),
    (r'(?:min\s*\.?\s*cells|min_cells)\s*[=:]\s*(\d+)', 'min.cells'),
    (r'(?:min\s*\.?\s*genes|min_genes|min_features)\s*[=:]\s*(\d+)', 'min.genes'),
    (r'(?:resolution|res)\s*[=:]\s*(\d+\.?\d*)', 'resolution'),
    (r'(?:mitochondrial|MT\s*%|percent\s*\.?\s*mt?|mito_cutoff|MT_cutoff)\s*[<>=:]\s*(\d+\.?\d*)', 'MT_percent'),
    (r'(?:dims?\s*[=:]\s*(\d+)\s*[:：]\s*(\d+))', 'dims_range'),
    (r'(?:n\s*dims|npcs?|nPCs?)\s*[=:]\s*(\d+)', 'ndims'),
    (r'(?:regress|regress\.out|vars\.to\.regress)\s*[=:]\s*[c\(]?\s*"([^"]+)"', 'regress_vars'),
    (r'(?:seed|set\.seed|random\.seed|random_state)\s*[=\(]\s*(\d+)', 'seed'),
    (r'(?:FDR|p\s*\.?\s*adj|adjusted_p|padj|p_val_adj)\s*[<≤=:]\s*(\d+\.?\d*)', 'FDR'),
    (r'(?:log\s*2?\s*FC|logFC|lfc|log2FoldChange)\s*[>≥=:]\s*(\d+\.?\d*)', 'logFC'),
]


PROSE_PATTERNS = [
    (r'(?:first|top)\s+(\d+)\s+(?:principal components|PCs?|dimensions)', 'ndims'),
    (r'resolution\s*(?:of|[:=])\s*(\d+\.?\d*)', 'resolution'),
    (r'(\d+)\s*(?:principal components|PCs?)', 'nPCs'),
    (r'Bonferroni\s*correction', 'multiple_testing'),
    (r'log\s*2?\s*(?:fold.change|FC)\s*(?:cutoff|threshold|criterion)\s*(?:of|[:=<>])\s*(\d+\.?\d*)', 'logFC_threshold'),
    (r'FDR\s*(?:<|less than|≤|cutoff)\s*(\d+\.?\d*)', 'FDR_threshold'),
    (r'p\s*\.?\s*(?:val|value)?\s*(?:<|≤|cutoff|adjusted)\s*(\d+\.?\d*e?-?\d*)', 'pvalue_threshold'),
    (r'(\d+)\s*highly\s*variable\s*(?:genes|features)', 'nHVG'),
    (r'(\d+)\s*cells?\s*(?:per|/)\s*(?:sample|condition|group)', 'cells_per_group'),
]

SEQUENCING_PATTERNS = [
    r'(?:Illumina|NovaSeq|HiSeq|NextSeq|MiSeq)\s*(\d+)?',
    r'(?:10[xX]\s*(?:Genomics|genomics))',
    r'(?:Chromium)\s*(?:Single\s*Cell|Next\s*GEM)?\s*(?:v?(\d+))?',
    r'(?:NovaSeq\s*6000|HiSeq\s*4000|HiSeq\s*2500|NextSeq\s*550)',
    r'(\d+)\s*bp\s*(?:paired.end|PE|single.end|SE)',
    r'(\d+[,.Kk]*)\s*(?:reads|读长)/\s*cell',
]

# ── Step 1: PDF 验证 ──────────────────────────────────────────
def verify_pdf(path: str) -> Dict:
    """Magic bytes 验证 PDF 真伪"""
    if not os.path.exists(path):
        return {'valid': False, 'error': 'file not found', 'path': path}
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        header = f.read(8)
    is_pdf = header[:5] == b'%PDF-'
    is_html = b'<html' in header.lower() or b'<!DOC' in header
    return {
        'valid': is_pdf,
        'is_html': is_html,
        'size': size,
        'path': path,
        'warning': 'SCI-HUB HTML FAKE' if is_html else (None if is_pdf else 'unknown format')
    }

# ── Step 2: 全文提取 ──────────────────────────────────────────
def extract_fulltext(pdf_path: str, max_chars: int = 150000) -> str:
    """pymupdf 逐页提取全文"""
    try:
        import fitz
    except ImportError:
        return ""
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            pages.append(f"## Page {i+1}\n\n{text}")
    doc.close()
    return "\n\n".join(pages)[:max_chars]


# ── Step 3: Methods 段定位 ────────────────────────────────────
def locate_methods(fulltext: str) -> Optional[str]:
    """正则定位 Methods 段落"""
    # Multiple patterns for different journal formats
    patterns = [
        # Standard: "Methods" section header
        r'(?:^|\n)(?:M[Ee][Tt][Hh][Oo][Dd][Ss]|Methods|METHODS)\s*\n\s*\n(.+?)(?=\n(?:Results|Discussion|References|Supplementary|Acknowledgments|Figure|Table|Data availability|Code availability|Author contributions|Competing|Funding)\s*\n)',
        # Alternative: "Materials and Methods"
        r'(?:^|\n)(?:Materials?\s*(?:and|&)\s*[Mm]ethods?|MATERIALS?\s*(?:AND|&)\s*METHODS?)\s*\n\s*\n(.+?)(?=\n(?:Results|Discussion|References|Supplementary|Acknowledgments|Figure|Table)\s*\n)',
        # Chinese: 材料与方法 / 方法
        r'(?:^|\n)(?:材料与方法|方法|实验方法)\s*\n\s*\n(.+?)(?=\n(?:结果|讨论|参考文献|补充|致谢|图表)\s*\n)',
        # Online Methods (Nature format)
        r'(?:^|\n)(?:Online\s*[Mm]ethods?|ONLINE\s*METHODS?)\s*\n\s*\n(.+?)(?=\n(?:References|Data availability|Code availability|Author contributions)\s*\n)',
    ]
    for pat in patterns:
        m = re.search(pat, fulltext, re.DOTALL)
        if m and len(m.group(1).strip()) > 500:
            return m.group(1).strip()
    # Fallback: return all text
    return fulltext


# ── Step 4: Layer1 正则提取 ───────────────────────────────────
def extract_layer1(methods_text: str) -> Dict:
    """正则提取包/版本/参数/平台"""
    result = {
        'packages': [],
        'parameters': [],
        'platforms': [],
        'stats': {}
    }

    # 4a. 提取包 + 关联版本
    for pkg in BIOINFO_PACKAGES:
        # Find package mentions
        for m in re.finditer(rf'\b{re.escape(pkg)}\b', methods_text, re.I):
            pos = m.start()
            ctx = methods_text[max(0,pos-5):min(len(methods_text),pos+len(pkg)+100)]
            # Extract version near this mention
            ver_match = re.search(r'[Vv]\s*\.?\s*[\(\[]?\s*(\d+\.\d+(?:\.\d+)?)\)?\s*\)?', ctx)
            version = ver_match.group(1) if ver_match else None
            # Extract parameters near this mention
            nearby_params = []
            for pat, pname in PARAM_PATTERNS:
                for pm in re.finditer(pat, ctx):
                    nearby_params.append({'name': pname, 'value': pm.group(1)})
            result['packages'].append({
                'name': pkg,
                'version': version,
                'context': ctx.strip()[:200],
                'params': nearby_params[:5]
            })

    # Dedup packages (case-insensitive)
    seen = set()
    unique_pkgs = []
    for p in result['packages']:
        key = p['name'].lower()
        if key not in seen:
            seen.add(key)
            unique_pkgs.append(p)
    result['packages'] = unique_pkgs

    # 4b1. 代码风格参数提取
    for pat, pname in PARAM_PATTERNS:
        for m in re.finditer(pat, methods_text):
            result['parameters'].append({
                'name': pname,
                'value': m.group(1),
                'context': methods_text[max(0,m.start()-40):m.end()+40].strip()
            })

    # 4b2. Prose 风格参数提取（Nature/Cell 叙述性 Methods）
    for pat, pname in PROSE_PATTERNS:
        for m in re.finditer(pat, methods_text, re.I):
            result['parameters'].append({
                'name': pname,
                'value': m.group(1) if m.lastindex and m.lastindex >= 1 else 'yes',
                'context': methods_text[max(0,m.start()-40):m.end()+40].strip(),
                'source': 'prose'
            })

    # 4c. 测序平台
    for plat_pat in SEQUENCING_PATTERNS:
        for m in re.finditer(plat_pat, methods_text):
            result['platforms'].append(m.group(0).strip())

    # 4d. 统计量
    result['stats'] = {
        'methods_length': len(methods_text),
        'methods_lines': methods_text.count('\n'),
        'package_count': len(result['packages']),
        'version_count': sum(1 for p in result['packages'] if p.get('version')),
        'parameter_count': len(result['parameters']),
        'platform_count': len(result['platforms']),
    }
    return result


# ── Step 5: Layer2 LLM 严格模板 ────────────────────────────────
DISSECT_PROMPT = """You are a Nature Methods reviewer. Below is the Methods section of a paper. Extract PRECISE information into three tables. Every field must have EVIDENCE (verbatim quote from the text). Do NOT guess.

## Table 1: Bioinformatics Methods Detail

| Package | Version | Purpose | Key Parameters (exact values) | Command Line | Input/Output Format | Evidence (verbatim) |
|---------|---------|---------|------------------------------|-------------|---------------------|---------------------|
| Seurat | 4.0.4 | scRNA normalization | nfeatures=3000, vars.to.regress="percent.mt" | - | count matrix → SCT assay | "using the Seurat package (V. 4.0.4)…SCTransform with nfeatures=3000" |

Rules:
- Version MUST be exactly as written in the text — DO NOT guess
- Parameters MUST come from the text, not defaults
- No command line → write "-"
- One row per package/method

## Table 2: Biological Findings

| Finding | Evidence Level | Cell Type/Tissue | Genes/Markers | Source Paragraph |
|---------|---------------|-----------------|---------------|------------------|

## Table 3: Experimental Data Specifications

| Experiment | Species | Age/Condition | Sample Size | Platform | Depth | Evidence |
|-----------|---------|--------------|-------------|----------|-------|----------|

---

METHODS TEXT:
{methods_text}"""


def extract_layer2(methods_text: str, api_key: str = None, api_base: str = None, model: str = None) -> Dict:
    """LLM 严格模板提取（API 可用时）"""
    if not api_key:
        return {'status': 'skipped', 'reason': 'no API key'}
    import urllib.request
    prompt = DISSECT_PROMPT.format(methods_text=methods_text[:70000])
    try:
        req = urllib.request.Request(
            f"{api_base}/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 8000
            }).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read())
        return {
            'status': 'success',
            'output': result["choices"][0]["message"]["content"],
            'usage': result.get("usage", {}),
            'model': model
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


# ── Step 6: YAML 生成 ─────────────────────────────────────────
def to_yaml(layer1: Dict, layer2: Dict, metadata: Dict) -> Dict:
    """合并双层提取结果 → 标准化 YAML"""
    y = {
        'metadata': {
            'source': metadata.get('source', 'unknown'),
            'dissected_at': datetime.now().isoformat(),
            'pipeline_version': '2.0',
            'paper_title': metadata.get('title', ''),
            'doi': metadata.get('doi', ''),
            'pmid': metadata.get('pmid', ''),
            'extraction_method': 'regex_layer1' + ('+LLM_layer2' if layer2.get('status') == 'success' else ''),
        },
        'methods': {
            'packages': layer1.get('packages', []),
            'parameters': layer1.get('parameters', []),
            'platforms': list(set(layer1.get('platforms', []))),
            'stats': layer1.get('stats', {}),
        },
        'llm_extraction': layer2 if layer2.get('status') == 'success' else None,
    }
    return y


# ── Step 7: Loop Gate ─────────────────────────────────────────
def loop_gate(dissection: Dict) -> Tuple[bool, List[str]]:
    """质量门禁：检查提取完整性"""
    errors = []
    stats = dissection.get('methods', {}).get('stats', {})
    pkgs = dissection.get('methods', {}).get('packages', [])

    if stats.get('methods_length', 0) < 2000:
        errors.append(f"Methods too short: {stats['methods_length']} chars (min 2000)")
    if stats.get('version_count', 0) < 5:
        errors.append(f"Too few versions: {stats['version_count']} (min 5)")
    if stats.get('package_count', 0) < 8:
        errors.append(f"Too few packages: {stats['package_count']} (min 8)")

    passed = len(errors) == 0
    return passed, errors


# ── Step 8: 写入 KB ───────────────────────────────────────────
def write_to_kb(dissection: Dict, output_dir: str, paper_name: str, species: str, tissue: str, direction: str):
    """写入标准化 KB YAML"""
    kb_root = Path(output_dir) if output_dir else Path('memomics/knowledge_base')
    kb_dir = kb_root / species / tissue / direction / '03_测序方法' / 'RNA'
    kb_dir.mkdir(parents=True, exist_ok=True)

    out_path = kb_dir / f'{paper_name}_dissected.yaml'
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.dump(dissection, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"✅ KB written: {out_path} ({out_path.stat().st_size:,}B)")
    return str(out_path)


# ── Main Pipeline ──────────────────────────────────────────────
def dissect_paper(pdf_path: str, output_dir: str = None, api_key: str = None,
                  api_base: str = None, model: str = None, write_kb: bool = False,
                  species: str = None, tissue: str = None, direction: str = None,
                  force: bool = False) -> Dict:
    """主管线：PDF → 全文 → Methods → 双层提取 → YAML → Gate → KB"""
    print(f"📄 {os.path.basename(pdf_path)}")
    print("=" * 60)

    # Step 1: Verify
    v = verify_pdf(pdf_path)
    print(f"  [1/8] Verify: {'VALID' if v['valid'] else 'INVALID'} ({v['size']:,}B){' — '+v['warning'] if v.get('warning') else ''}")
    if not v['valid'] and not force:
        return {'status': 'rejected', 'reason': v.get('warning', 'invalid PDF'), 'stats': {'pdf_size': v['size']}}

    # Step 2: Extract fulltext
    fulltext = extract_fulltext(pdf_path)
    print(f"  [2/8] Fulltext: {len(fulltext):,} chars")
    if len(fulltext) < 1000 and not force:
        return {'status': 'rejected', 'reason': 'fulltext too short', 'stats': {'fulltext_chars': len(fulltext)}}

    # Step 3: Locate Methods
    methods = locate_methods(fulltext)
    print(f"  [3/8] Methods: {len(methods):,} chars")
    if len(methods) < 500 and not force:
        return {'status': 'rejected', 'reason': 'methods not found', 'stats': {'methods_chars': len(methods)}}

    # Step 4: Layer1 regex
    layer1 = extract_layer1(methods)
    print(f"  [4/8] Layer1: {layer1['stats']['package_count']} packages, {layer1['stats']['version_count']} versions, {layer1['stats']['parameter_count']} params")
    if layer1['stats']['version_count'] > 0:
        pkgs_with_ver = [p['name'] for p in layer1['packages'] if p.get('version')]
        print(f"         Versions: {', '.join(f'{pkg} {ver}' for pkg, ver in [(p['name'], p['version']) for p in layer1['packages'] if p.get('version')])}")

    # Step 5: Layer2 LLM
    layer2 = extract_layer2(methods, api_key, api_base, model)
    if layer2.get('status') == 'success':
        print(f"  [5/8] Layer2: LLM extracted ({layer2.get('usage',{}).get('total_tokens','?')} tokens)")
    else:
        reason = layer2.get('reason', layer2.get('error', 'skipped'))
        print(f"  [5/8] Layer2: {layer2.get('status', 'skipped')} — {reason[:80]}")

    # Step 6: YAML
    dissection = to_yaml(layer1, layer2, {'source': pdf_path})
    print(f"  [6/8] YAML: generated ({len(json.dumps(dissection)):,} chars)")

    # Step 7: Gate
    passed, errors = loop_gate(dissection)
    if passed:
        print(f"  [7/8] Gate: PASS")
    else:
        print(f"  [7/8] Gate: FAIL — {chr(10).join('    - '+e for e in errors)}")

    # Step 8: Write to KB
    if write_kb and (passed or force):
        paper_name = os.path.splitext(os.path.basename(pdf_path))[0].replace(' ', '_')[:60]
        out = write_to_kb(dissection, output_dir, paper_name,
                         species or 'Homo_sapiens', tissue or 'liver', direction or 'aging')
        print(f"  [8/8] KB write: {out}")

    dissection['status'] = 'passed' if passed else 'failed_gate'
    dissection['gate_errors'] = errors
    return dissection


# ── CLI ────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="paper_dissector — 论文深度拆解管线")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--kb", action="store_true", help="写入知识库")
    parser.add_argument("--force", action="store_true", help="绕过 Gate 强制写入")
    parser.add_argument("--species", default="Homo_sapiens")
    parser.add_argument("--tissue", default="liver")
    parser.add_argument("--direction", default="aging")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    api_base = os.environ.get("DEEPSEEK_BASE_URL", "https://dcsapi.dcs.cloud/api/aigress/unified/v1")
    model = os.environ.get("DEEPSEEK_MODEL", "glm-5.2")

    result = dissect_paper(
        pdf_path=args.pdf_path,
        output_dir=args.output_dir,
        api_key=api_key,
        api_base=api_base,
        model=model,
        write_kb=args.kb,
        species=args.species,
        tissue=args.tissue,
        direction=args.direction,
        force=args.force,
    )

    # Summary
    if result.get('status') == 'passed':
        s = result['methods']['stats']
        print(f"\n✅ PASS: {s['package_count']} packages, {s['version_count']} versions, {s['parameter_count']} params, {s['platform_count']} platforms")
    else:
        print(f"\n❌ {result['status']}: {result.get('reason', result.get('gate_errors', 'unknown'))}")
