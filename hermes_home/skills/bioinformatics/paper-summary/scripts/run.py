#!/usr/bin/env python3
"""
paper-summary — PDF 全文提取 + 图表提取工具

Usage:
    python run.py extract --tier1 --pdf paper.pdf --out results/
    python run.py extract --tier2 --pdf paper.pdf --out results/
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


def extract_text_fitz(pdf_path: str) -> str:
    """Extract full text from PDF using PyMuPDF (fitz)."""
    try:
        import fitz
    except ImportError:
        print("[ERROR] pymupdf not installed. Run: pip install pymupdf", file=sys.stderr)
        return ""

    doc = fitz.open(pdf_path)
    pages_text = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip():
            pages_text.append(text)
    doc.close()
    return "\n\n".join(pages_text)


def extract_metadata_fitz(pdf_path: str) -> dict:
    """Extract PDF metadata: title, author, subject."""
    try:
        import fitz
    except ImportError:
        return {}

    doc = fitz.open(pdf_path)
    meta = doc.metadata
    page_count = doc.page_count
    doc.close()

    return {
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
        "page_count": page_count,
    }


def extract_figures_fitz(pdf_path: str, output_dir: str, max_figures: int = 3) -> list:
    """Extract embedded images from PDF pages. Returns list of saved image paths."""
    try:
        import fitz
    except ImportError:
        print("[ERROR] pymupdf not installed. Run: pip install pymupdf", file=sys.stderr)
        return []

    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    saved = []

    for page_num in range(len(doc)):
        if len(saved) >= max_figures:
            break
        page = doc[page_num]
        images = page.get_images(full=True)
        for img_idx, img in enumerate(images):
            if len(saved) >= max_figures:
                break
            xref = img[0]
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            img_ext = base_image["ext"]

            # Only save reasonably sized images (>10KB = likely a figure)
            if len(img_bytes) < 10 * 1024:
                continue

            img_name = f"fig_{page_num+1:02d}_{img_idx+1:02d}.{img_ext}"
            img_path = os.path.join(output_dir, img_name)
            with open(img_path, "wb") as f:
                f.write(img_bytes)
            saved.append(img_path)

    doc.close()
    return saved


def extract_figure_captions(text: str, max_captions: int = 10) -> list[dict]:
    """Extract figure captions from full text by regex matching."""
    # Match patterns like "Figure 1.", "Fig. 1:", "Figure 1 —"
    pattern = r'(?:Figure|Fig\.?)\s*(\d+)[\.:\s—–-]+\s*(.+?)(?=(?:Figure|Fig\.?)\s*\d+[\.:\s—–-]|References|Discussion|$|[\n]{3,})'
    matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
    captions = []
    for num, caption in matches[:max_captions]:
        captions.append({
            "figure_number": int(num),
            "caption": caption.strip()[:500],  # Truncate long captions
        })
    return captions


def extract_section(text: str, section_name: str) -> str:
    """Extract a named section from the full text."""
    pattern = rf'{section_name}\s*\n(.*?)(?=\n\s*(?:[A-Z][A-Za-z\s]+)\n|\Z)'
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()[:2000]
    return ""


def run_tier1(pdf_path: str, output_dir: str) -> dict:
    """Tier 1 extraction: text + 1-3 key figures + metadata."""
    os.makedirs(output_dir, exist_ok=True)
    figures_dir = os.path.join(output_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    print(f"[Tier 1] Extracting from: {pdf_path}")

    # 1. Extract text
    full_text = extract_text_fitz(pdf_path)
    text_path = os.path.join(output_dir, "fulltext.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"[Tier 1] Full text saved: {text_path} ({len(full_text)} chars)")

    # 2. Extract metadata
    metadata = extract_metadata_fitz(pdf_path)
    metadata["pdf_path"] = pdf_path
    metadata["text_length"] = len(full_text)

    # 3. Extract key figures (1-3)
    fig_paths = extract_figures_fitz(pdf_path, figures_dir, max_figures=3)
    metadata["extracted_figures"] = fig_paths
    print(f"[Tier 1] Extracted {len(fig_paths)} figures")

    # 4. Extract figure captions
    captions = extract_figure_captions(full_text, max_captions=5)
    metadata["figure_captions"] = captions

    # 5. Save metadata
    meta_path = os.path.join(output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"[Tier 1] Metadata saved: {meta_path}")

    result = {
        "text_path": text_path,
        "metadata": metadata,
        "figures": fig_paths,
        "captions": captions,
        "text_preview": full_text[:500],
    }
    return result


def run_tier2(pdf_path: str, output_dir: str) -> dict:
    """Tier 2 extraction: all figures + full text + full metadata."""
    os.makedirs(output_dir, exist_ok=True)
    figures_dir = os.path.join(output_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    print(f"[Tier 2] Extracting from: {pdf_path}")

    # 1. Extract full text
    full_text = extract_text_fitz(pdf_path)
    text_path = os.path.join(output_dir, "fulltext.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"[Tier 2] Full text saved: {text_path} ({len(full_text)} chars)")

    # 2. Extract metadata
    metadata = extract_metadata_fitz(pdf_path)
    metadata["pdf_path"] = pdf_path
    metadata["text_length"] = len(full_text)

    # 3. Extract ALL figures
    fig_paths = extract_figures_fitz(pdf_path, figures_dir, max_figures=50)
    metadata["extracted_figures"] = fig_paths
    print(f"[Tier 2] Extracted {len(fig_paths)} figures")

    # 4. Extract all figure captions
    captions = extract_figure_captions(full_text, max_captions=20)
    metadata["figure_captions"] = captions

    # 5. Save metadata
    meta_path = os.path.join(output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"[Tier 2] Metadata saved: {meta_path}")

    result = {
        "text_path": text_path,
        "metadata": metadata,
        "figures": fig_paths,
        "captions": captions,
        "text_preview": full_text[:500],
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="paper-summary PDF extractor")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # extract command
    extract_parser = subparsers.add_parser("extract", help="Extract from PDF")
    extract_parser.add_argument("--tier1", action="store_true", help="Tier 1: lightweight extraction")
    extract_parser.add_argument("--tier2", action="store_true", help="Tier 2: full extraction")
    extract_parser.add_argument("--pdf", required=True, help="Path to PDF file")
    extract_parser.add_argument("--out", default="./results", help="Output directory")

    args = parser.parse_args()

    if args.command == "extract":
        if not os.path.exists(args.pdf):
            print(f"[ERROR] PDF not found: {args.pdf}", file=sys.stderr)
            sys.exit(1)

        if args.tier2:
            result = run_tier2(args.pdf, args.out)
        else:
            result = run_tier1(args.pdf, args.out)

        # Print summary for consumption by LLM
        print("\n" + "=" * 60)
        print("EXTRACTION COMPLETE")
        print("=" * 60)
        print(f"Text length: {len(result['text_preview'])} chars (preview)")
        print(f"Full text: {result['text_path']}")
        print(f"Figures: {len(result['figures'])}")
        for f in result['figures']:
            print(f"  - {f}")
        print(f"Captions: {len(result['captions'])}")
        for c in result['captions']:
            print(f"  - Figure {c['figure_number']}: {c['caption'][:80]}...")
        print("=" * 60)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
