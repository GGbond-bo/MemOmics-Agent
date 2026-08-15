# -*- coding: utf-8 -*-
"""文献栏批O(2026-08-16)回归测试：
1) 引用格式专业化（GB/T 7714 顺序编码制/著者-出版年制 / APA 7 / NLM / MLA / BibTeX / RIS）
2) get_summary 九项摘要修复（从原始索引读取，不再为空；作者不再丢失）
3) DOI 清洗（WILEY 水印等脏后缀）
4) 前端静态断言：大窗口可调节 / 中英对照双屏 / 知识提取 / 专业引用 / 整库导出
"""
import json
import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS_DIR))                 # webui/
sys.path.insert(0, os.path.join(TESTS_DIR, "..", ".."))        # repo root
sys.path.insert(0, os.path.join(TESTS_DIR, "..", "..", "hermes-agent"))

from memomics.bio_tools import reference_library as RL  # noqa: E402
from memomics.bio_tools import literature_library as LL  # noqa: E402

HTML_PATH = os.path.join(TESTS_DIR, "..", "index.html")
HTML = open(HTML_PATH, encoding="utf-8").read()

META = {
    "title": "A conserved complex lipid signature marks human muscle aging and responds to short-term exercise",
    "authors": ["Georges E. Janssens", "Marte Molenaars", "Katharina Herzog",
                "Lotte Grevendonk"],
    "year": "2024", "journal": "Nature Aging",
    "volume": "1", "issue": "2", "pages": "145-157",
    "doi": "10.1038/s43587-024-00595-2", "entry_type": "article",
}


# ---------------------------------------------------------------- 引用格式
class TestCitationFormats:
    def test_gbt7714_numeric(self):
        s = RL.format_citation(META, "gbt7714-numeric")
        assert s.startswith("[1] JANSSENS G E, MOLENAARS M, HERZOG K, et al. ")
        assert "Nature Aging, 2024, 1(2): 145-157" in s
        assert "DOI:10.1038/s43587-024-00595-2" in s
        assert "et al.." not in s and ".. " not in s

    def test_gbt7714_author_year(self):
        s = RL.format_citation(META, "gbt7714-author-year")
        assert s.startswith("JANSSENS G E, MOLENAARS M, HERZOG K, et al. 2024. ")
        assert "[J]. Nature Aging, 1(2): 145-157." in s

    def test_apa7(self):
        s = RL.format_citation(META, "apa")
        assert s.startswith("Janssens, G. E., Molenaars, M., Herzog, K., & Grevendonk, L. (2024). ")
        assert ", 1(2), 145-157." in s
        assert "https://doi.org/10.1038/s43587-024-00595-2" in s

    def test_nlm(self):
        s = RL.format_citation(META, "nlm")
        # NLM/Vancouver ≤6 位作者全列（不加 et al.），姓名=姓+空格+首字母缩写
        assert s.startswith("Janssens GE, Molenaars M, Herzog K, Grevendonk L. ")
        assert "Nature Aging. 2024;1(2):145-157." in s
        assert "doi:10.1038/s43587-024-00595-2" in s

    def test_mla(self):
        s = RL.format_citation(META, "mla")
        # MLA 9 第一作者全名（Given Family），≥3 位作者 → et al.
        assert s.startswith('Georges E. Janssens, et al. "A conserved')
        assert "vol. 1, no. 2, 2024, pp. 145-157" in s

    def test_three_authors_no_etal(self):
        m = dict(META, authors=META["authors"][:3])
        s = RL.format_citation(m, "gbt7714-numeric")
        assert "et al." not in s
        assert s.startswith("[1] JANSSENS G E, MOLENAARS M, HERZOG K. ")

    def test_bibtex_key_and_fields(self):
        b = RL._to_bibtex(META)
        assert b.startswith("@article{janssens2024conserved,")
        assert "author = {Georges E. Janssens and Marte Molenaars" in b
        assert "volume = {1}" in b and "number = {2}" in b and "pages = {145-157}" in b

    def test_ris_family_first(self):
        r = RL._to_ris(META)
        assert "AU  - Janssens, Georges E." in r
        assert "VL  - 1" in r and "IS  - 2" in r
        assert "SP  - 145" in r and "EP  - 157" in r

    def test_graceful_degradation_without_volume(self):
        m = {k: v for k, v in META.items() if k not in ("volume", "issue", "pages")}
        s = RL.format_citation(m, "gbt7714-numeric")
        assert "Nature Aging, 2024." in s  # 无卷期页时不出现空段
        assert ", ," not in s

    def test_doi_only_fallback_url(self):
        m = {k: v for k, v in META.items() if k != "url"}
        m["url"] = ""
        s = RL.format_citation(m, "apa")
        assert "https://doi.org/10.1038/s43587-024-00595-2" in s


class TestAuthorSplit:
    def test_given_family(self):
        assert RL._split_author("Georges E. Janssens") == ("Janssens", "Georges E.")

    def test_family_comma_given(self):
        assert RL._split_author("Janssens, Georges E.") == ("Janssens", "Georges E.")

    def test_apostrophe_particle(self):
        fam, giv = RL._split_author("Stefania Dell’ Orso")
        assert fam == "Dell’ Orso" and giv == "Stefania"

    def test_van_particle(self):
        assert RL._split_author("Michel van Weeghel") == ("van Weeghel", "Michel")

    def test_prefix_family(self):
        assert RL._split_author("Raza Ur Rahman") == ("Ur Rahman", "Raza")

    def test_single_word(self):
        assert RL._split_author("Yosef") == ("Yosef", "")

    def test_upper_initials_gbt(self):
        assert RL._family_initials("Michel van Weeghel", upper=True) == "VAN WEEGHEL M"


class TestDoiClean:
    def test_strips_wiley_watermark(self):
        assert LL._clean_doi("10.1111/acel.70485WILEYlogoSocietylogo") == "10.1111/acel.70485"

    def test_strips_trailing_punct(self):
        assert LL._clean_doi("10.1038/s41586-026-10250-y.") == "10.1038/s41586-026-10250-y"

    def test_untouched_clean_doi(self):
        assert LL._clean_doi("10.1016/j.cmet.2022.05.010") == "10.1016/j.cmet.2022.05.010"


# ---------------------------------------------------------------- 段落级翻译（对照 1:1 对齐）
class TestBlockTranslation:
    def test_md_blocks_splits_headings(self):
        md = "# Title\n\npara one.\n\n## H2\n\npara two.\n\nmore two."
        blocks = LL._md_blocks(md)
        assert blocks == ["# Title", "para one.", "## H2", "para two.", "more two."]

    def test_md_blocks_paragraph_split(self):
        blocks = LL._md_blocks("a\n\nb\n\nc")
        assert blocks == ["a", "b", "c"]

    def test_batch_blocks_respects_limits(self):
        blocks = ["x" * 3000, "y" * 3000, "z" * 3000]
        batches = LL._batch_blocks(blocks, max_chars=6000, max_blocks=8)
        assert all(len("".join(b)) <= 6000 for b in batches)
        flat = [b for batch in batches for b in batch]
        assert flat == blocks

    def test_parse_numbered_output(self):
        out = "###1###\n译文一第一行\n译文一第二行\n###2### 译文二（同行标记）\n###3###\n译文三\n"
        res = LL._parse_numbered_output(out, 3)
        assert res[0] == "译文一第一行\n译文一第二行"
        assert res[1] == "译文二（同行标记）"
        assert res[2] == "译文三"

    def test_parse_numbered_missing_tolerated(self):
        out = "###2###\n只有第二段\n"
        res = LL._parse_numbered_output(out, 3)
        assert res[0] == "" and res[1] == "只有第二段" and res[2] == ""

    def test_normalize_zh_collapses_blank_lines(self):
        """块内空行折叠 + 空块回填原文 → zh 段数与原文严格一致（对照对齐关键）。"""
        blocks = ["one", "two", "three"]
        res = ["译一\n\n多行\n\n尾巴", "###2###\n译二", ""]
        zh = LL._normalize_zh(res, blocks)
        assert zh == ["译一\n多行\n尾巴", "译二", "three"]
        assert LL._md_blocks("\n\n".join(zh)) == ["译一\n多行\n尾巴", "译二", "three"]


# ---------------------------------------------------------------- 物种标准化与知识域（批O3）
class TestSpeciesCanonical:
    def test_human_variants(self):
        from memomics.bio_tools.save_knowledge import canonical_species
        assert canonical_species("human") == "Homo_sapiens"
        assert canonical_species("Homo sapiens") == "Homo_sapiens"
        assert canonical_species("人") == "Homo_sapiens"

    def test_mouse_variants(self):
        from memomics.bio_tools.save_knowledge import canonical_species
        assert canonical_species("mouse") == "Mus_musculus"
        assert canonical_species("小鼠") == "Mus_musculus"
        assert canonical_species("mice") == "Mus_musculus"

    def test_monkey_common_name(self):
        from memomics.bio_tools.save_knowledge import canonical_species
        assert canonical_species("macaque") == "monkey"
        assert canonical_species("猕猴") == "monkey"

    def test_unknown_fallback(self):
        from memomics.bio_tools.save_knowledge import canonical_species
        assert canonical_species("unknown") == "other"
        assert canonical_species("") == "other"

    def test_multivalue_first(self):
        from memomics.bio_tools.save_knowledge import canonical_species
        assert canonical_species("human;mouse") == "Homo_sapiens"


class TestKnowledgeDomains:
    def test_common_domain_path(self, tmp_path, monkeypatch):
        from memomics.bio_tools.save_knowledge import save_knowledge
        monkeypatch.setenv("MEMOMICS_KB_DIR", str(tmp_path))
        r = json.loads(save_knowledge(
            name="test_method", content="方法内容", source="literature",
            evidence="DOI x", verified="partially_verified",
            domain="common", direction="general",
            kb_category="03_测序方法", assay_type="RNA"))
        assert r["status"] == "success"
        assert os.path.normpath(r["path"]).replace("\\", "/").endswith(
            "common/general/03_测序方法/RNA/test_method.yaml")

    def test_chemistry_domain_path(self, tmp_path, monkeypatch):
        from memomics.bio_tools.save_knowledge import save_knowledge
        monkeypatch.setenv("MEMOMICS_KB_DIR", str(tmp_path))
        r = json.loads(save_knowledge(
            name="chem_resveratrol", content="- IC50: 5 uM", source="literature",
            evidence="DOI y", verified="partially_verified",
            domain="chemistry", direction="compounds"))
        assert r["status"] == "success"
        assert os.path.normpath(r["path"]).replace("\\", "/").endswith(
            "chemistry/compounds/chem_resveratrol.yaml")

    def test_chemistry_bad_category_rejected(self, tmp_path, monkeypatch):
        from memomics.bio_tools.save_knowledge import save_knowledge
        monkeypatch.setenv("MEMOMICS_KB_DIR", str(tmp_path))
        r = json.loads(save_knowledge(name="x", content="c", domain="chemistry",
                                      direction="../../evil"))
        assert r["status"] == "error"

    def test_five_level_canonicalizes_species(self, tmp_path, monkeypatch):
        from memomics.bio_tools.save_knowledge import save_knowledge
        monkeypatch.setenv("MEMOMICS_KB_DIR", str(tmp_path))
        r = json.loads(save_knowledge(
            name="test_bio", content="结论", source="literature", evidence="DOI z",
            verified="partially_verified", species="human",
            tissue="skeletal_muscle", direction="aging",
            kb_category="01_生物学知识", assay_type="RNA"))
        assert r["status"] == "success"
        assert "/Homo_sapiens/skeletal_muscle/aging/" in r["path"].replace("\\", "/")
        assert "/human/" not in r["path"]


# ---------------------------------------------------------------- 双语对照文档（批O4）
def _make_syn_pdf(path, toc=True):
    import pymupdf as fitz
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 100), f"Section {i + 1} Heading", fontsize=16)
        body = (f"Body paragraph {i + 1} with unique marker word marker{i + 1}xyz. "
                f"More text to make the block longer and searchable. ") * 3
        page.insert_text((72, 150), body, fontsize=11)
    if toc:
        doc.set_toc([[1, "Introduction", 1], [1, "Methods", 2], [1, "Results", 3]])
    doc.save(str(path))
    doc.close()


class TestBilingualBuilder:
    def test_build_with_toc(self, tmp_path, monkeypatch):
        import pymupdf as fitz
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        papers = tmp_path / "papers"
        papers.mkdir()
        pdf_path = papers / "demo.pdf"
        _make_syn_pdf(pdf_path, toc=True)
        with open(papers / ".pdf_index.json", "w", encoding="utf-8") as f:
            json.dump([{"file": "demo.pdf", "path": str(pdf_path),
                        "title": "Demo paper"}], f, ensure_ascii=False)
        r = json.loads(LL.build_bilingual("demo.pdf"))
        assert r["ok"] is True
        assert r["pages"] == 3
        assert r["toc_source"] == "toc"
        assert len(r["modules"]) == 3
        assert [m["start_page"] for m in r["modules"]] == [0, 1, 2]
        for m in r["modules"]:
            assert len(m["paras"]) >= 1
            for p in m["paras"]:
                assert m["start_page"] <= p["page"] <= m["end_page"]
                assert p["rect"] is None or len(p["rect"]) == 4

    def test_build_without_toc_falls_back(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        papers = tmp_path / "papers"
        papers.mkdir()
        pdf_path = papers / "notoc.pdf"
        _make_syn_pdf(pdf_path, toc=False)
        with open(papers / ".pdf_index.json", "w", encoding="utf-8") as f:
            json.dump([{"file": "notoc.pdf", "path": str(pdf_path),
                        "title": "NoToc paper"}], f, ensure_ascii=False)
        r = json.loads(LL.build_bilingual("notoc.pdf"))
        assert r["ok"] is True
        assert r["toc_source"] in ("headings", "none")
        assert len(r["modules"]) >= 1

    def test_map_blocks_to_pages(self):
        pages = ["page zero contains hello world marker", "page one has marker two here"]
        blocks = ["## hello world", "marker two"]
        got = LL._map_blocks_to_pages(blocks, pages)
        assert got == [0, 1]

    def test_find_rect_on_synthetic_pdf(self, tmp_path):
        pdf_path = tmp_path / "rect.pdf"
        _make_syn_pdf(pdf_path, toc=True)
        rect = LL._find_block_rect(str(pdf_path), 0, "Section 1 Heading")
        assert rect is not None and len(rect) == 4
        assert all(0 <= v <= 1 for v in rect)

    def test_missing_paper_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "papers").mkdir()
        r = json.loads(LL.build_bilingual("nope.pdf"))
        assert r["ok"] is False


# ---------------------------------------------------------------- get_summary 修复
class TestGetSummaryFix:
    def test_summary_and_authors_not_empty(self, tmp_path, monkeypatch):
        """历史 bug：get_summary 从 list_library 投影读 summary/authors → 恒为空。
        修复后必须从 .pdf_index.json 原始条目返回完整九项摘要 + 作者 + 引用。"""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        papers = tmp_path / "papers"
        papers.mkdir()
        entry = {
            "file": "demo.pdf", "path": str(papers / "demo.pdf"),
            "title": "Demo paper about muscle aging", "journal": "Nature Aging",
            "authors": ["Jane Doe", "John Smith"], "year": "2025",
            "doi": "10.1038/demo.2025.1", "volume": "3", "issue": "4", "pages": "10-20",
            "summary_done": True,
            "summary": {"idea": "切入点", "background": "背景", "species": "human",
                        "tissue": "skeletal_muscle", "problem": "问题", "solution": "方案",
                        "methods": "方法", "conclusion": "结论", "validation": "验证"},
        }
        with open(papers / ".pdf_index.json", "w", encoding="utf-8") as f:
            json.dump([entry], f, ensure_ascii=False)
        r = json.loads(LL.get_summary("demo.pdf"))
        assert r["ok"] is True
        assert r["summary"].get("background") == "背景"
        assert r["summary"].get("idea") == "切入点"
        assert r["authors"] == ["Jane Doe", "John Smith"]
        assert r["volume"] == "3" and r["pages"] == "10-20"
        c = r.get("citations") or {}
        assert c.get("gbt7714-numeric", "").startswith("[1] DOE J, SMITH J. ")
        assert "Jane Doe and John Smith" in (c.get("bibtex") or "")
        assert "AU  - Doe, Jane" in (c.get("ris") or "")

    def test_summary_md_fallback(self, tmp_path, monkeypatch):
        """index 里没有 summary 但 summaries/<stem>.md 存在时，反解析九项。"""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        papers = tmp_path / "papers"
        sdir = papers / "summaries"
        sdir.mkdir(parents=True)
        with open(papers / ".pdf_index.json", "w", encoding="utf-8") as f:
            json.dump([{"file": "x.pdf", "path": str(papers / "x.pdf"),
                        "title": "X", "summary_done": False}], f, ensure_ascii=False)
        with open(sdir / "x.md", "w", encoding="utf-8") as f:
            f.write("# X\n\n## 思路\n\n核心想法\n\n## 结论\n\n结论一\n结论二\n")
        r = json.loads(LL.get_summary("x.pdf"))
        assert r["summary"].get("idea") == "核心想法"
        assert "结论一" in r["summary"].get("conclusion", "")

    def test_list_library_includes_new_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        papers = tmp_path / "papers"
        papers.mkdir()
        with open(papers / ".pdf_index.json", "w", encoding="utf-8") as f:
            json.dump([{"file": "y.pdf", "path": str(papers / "y.pdf"),
                        "authors": ["A B"], "volume": "9", "pages": "1-5",
                        "knowledge_done": True, "imported_by": "sid-1"}], f, ensure_ascii=False)
        lib = json.loads(LL.list_library())["library"]
        assert lib[0]["authors"] == ["A B"]
        assert lib[0]["meta_complete"] is True
        assert lib[0]["knowledge_done"] is True
        assert lib[0]["imported_by"] == "sid-1"


# ---------------------------------------------------------------- 前端静态断言
class TestFrontendLitWorkbench:
    def test_new_tabs_exist(self):
        assert 'id="lit-tab-cmp"' in HTML and 'id="lit-tab-know"' in HTML
        assert 'id="lit-tab-cite"' in HTML and 'id="lit-tab-sum"' in HTML

    def test_resizable_modal(self):
        assert "function initLitResize" in HTML
        assert "function litToggleMax" in HTML
        assert "memomics_lit_box" in HTML
        assert HTML.count('class="lit-resizer') >= 8  # 八向调节

    def test_compare_view(self):
        assert "function litRenderCompare" in HTML or "function litRenderBilingual" in HTML
        assert "function litAlignBlocks" in HTML
        assert "lit-compare-cols" in HTML
        assert "lit-compare-head" in HTML
        assert "litDownloadTextRaw" in HTML

    def test_bilingual_view(self):
        assert "function litRenderBilingual" in HTML
        assert "function litBiGoModule" in HTML
        assert "function litBiGoPara" in HTML
        assert "function litBiFromPage" in HTML
        assert "/api/literature/bilingual" in HTML
        assert "/api/papers/page" in HTML
        assert "lit-pdf-pane" in HTML and "lit-mod-pane" in HTML

    def test_force_retranslate(self):
        assert "function litForceTranslate" in HTML
        assert "force" in HTML

    def test_knowledge_view(self):
        assert "function litRenderKnowledge" in HTML
        assert "gene_markers" in HTML and "organoid" in HTML and "chemicals" in HTML
        assert "sequencing" in HTML and "software" in HTML and "qc_params" in HTML

    def test_cite_view_professional(self):
        assert "function litRenderCite" in HTML
        assert "gbt7714-numeric" in HTML and "gbt7714-author-year" in HTML
        assert "APA" in HTML and "NLM" in HTML and "MLA" in HTML

    def test_export_all(self):
        assert "function litExportAll" in HTML
        assert "/api/literature/export" in HTML

    def test_enrich_flow(self):
        assert "function litEnrichPaper" in HTML and "function litEnrichAll" in HTML
        assert "/api/literature/enrich" in HTML

    def test_ask_agent(self):
        assert "function litAskAgent" in HTML

    def test_knowledge_endpoints(self):
        assert "/api/literature/knowledge" in HTML
        assert "/api/literature/knowledge-all" in HTML

    def test_force_rerun(self):
        assert "function litForceSummarize" in HTML
        assert "function litForceKnowledge" in HTML


# ---------------------------------------------------------------- 下载即正式入库（批O5f 2026-08-16）
class TestDownloadAutoImport:
    def test_finish_download_auto_imports_and_dedupes(self, tmp_path, monkeypatch):
        """download_pdf 成功后自动 import_pdfs 入正式库，并从下载索引摘除条目。"""
        from memomics.bio_tools import literature_search as LS
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        # 离线：Crossref 反查与 LLM 分类打桩
        monkeypatch.setattr(LL, "_extract_metadata", lambda dest, text, src: {
            "title": "Auto imported paper", "journal": "Test Journal",
            "authors": ["Jane Doe"], "year": "2025", "doi": "10.1000/xyz.1",
            "url": "", "volume": "1", "issue": "2", "pages": "3-4", "pmid": ""})
        monkeypatch.setattr(LL, "_classify_papers", lambda entries: {})
        out = tmp_path / "work" / "papers"
        out.mkdir(parents=True)
        pdf = out / "downloaded.pdf"
        _make_syn_pdf(pdf, toc=False)
        res = json.loads(LS._finish_download(
            {"success": True, "file_path": str(pdf), "file_size": pdf.stat().st_size},
            out, "", ""))
        ai = res["auto_import"]
        assert ai["ok"] is True and ai["imported"] == 1
        # 正式库已有 1 条（含元数据）
        lib_idx = json.loads((tmp_path / "papers" / ".pdf_index.json").read_text(encoding="utf-8"))
        assert len(lib_idx) == 1
        assert lib_idx[0]["title"] == "Auto imported paper"
        assert lib_idx[0]["imported_by"] == "download_pdf"
        # 下载索引条目已摘除
        agent_idx = json.loads((out / ".pdf_index.json").read_text(encoding="utf-8"))
        assert agent_idx == []
        # 文献库只显示 1 条，不重复
        lib = json.loads(LL.list_library())["library"]
        assert len(lib) == 1 and lib[0]["source"] == "user_import"

    def test_failed_import_keeps_agent_index(self, tmp_path, monkeypatch):
        """正式入库失败时保留下载索引兜底，文献库仍可见该文献。"""
        from memomics.bio_tools import literature_search as LS
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        out = tmp_path / "work" / "papers"
        out.mkdir(parents=True)
        pdf = out / "broken.pdf"
        _make_syn_pdf(pdf, toc=False)
        monkeypatch.setattr(LS, "_auto_import_to_library",
                            lambda fp: {"ok": False, "imported": 0, "skipped": 0,
                                        "entries": [], "library_dir": "", "error": "boom"})
        res = json.loads(LS._finish_download(
            {"success": True, "file_path": str(pdf), "file_size": pdf.stat().st_size},
            out, "", ""))
        assert res["auto_import"]["ok"] is False
        agent_idx = json.loads((out / ".pdf_index.json").read_text(encoding="utf-8"))
        assert any(e["file"] == "broken.pdf" for e in agent_idx)

    def test_list_library_cross_index_dedupe(self, tmp_path, monkeypatch):
        """历史遗留双份（同一 PDF 在正式库与下载索引各一条）只显示一次。"""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        papers = tmp_path / "papers"
        papers.mkdir()
        with open(papers / ".pdf_index.json", "w", encoding="utf-8") as f:
            json.dump([{"file": "a.pdf", "path": str(papers / "a.pdf"),
                        "title": "A", "sha256": "samehash"}], f, ensure_ascii=False)
        agent = tmp_path / "agent.json"
        with open(agent, "w", encoding="utf-8") as f:
            json.dump([{"file": "a.pdf", "path": str(tmp_path / "a.pdf"),
                        "title": "A", "sha256": "samehash"},
                       {"file": "b.pdf", "path": str(tmp_path / "b.pdf"),
                        "title": "B", "sha256": "otherhash"}], f, ensure_ascii=False)
        monkeypatch.setattr(LL, "_agent_papers_index", lambda: str(agent))
        lib = json.loads(LL.list_library())["library"]
        assert [e["file"] for e in lib] == ["a.pdf", "b.pdf"]
        assert lib[0]["source"] == "user_import"
        assert lib[1]["source"] == "agent_download"
