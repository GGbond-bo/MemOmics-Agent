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


# ------------------------------------------------- 翻译提速：超大段拆单元 + 并发（2026-09-17）
class TestTranslationUnits:
    """用户反馈"翻译太慢"的回归护栏。

    实测：单段 3630 字符整段直译要 32.4s；某篇 31 段里 18 段 >6000 字符（最大 8995）
    → 旧代码 25 批、每批一次超大调用、2 并发，整篇 5–6 分钟，还常顶到 120s 超时截断。
    改造：超大段按句子边界拆成 ≤1800 字符的小单元并发翻译，译完拼回原段
    （中英对照仍严格 1:1）。
    """

    def test_oversized_block_split_into_units(self):
        block = ("Sentence number one is here. " * 300).strip()
        units = LL._split_units([block])
        assert len(units) > 1, "超大段必须被拆"
        assert all(len(t) <= 1800 for _bi, t in units)
        assert {bi for bi, _t in units} == {0}, "拆出的单元仍属于原段"
        assert "".join(t for _bi, t in units).replace(" ", "") == block.replace(" ", "")

    def test_small_blocks_stay_whole(self):
        units = LL._split_units(["short paragraph.", "y" * 2000])
        assert units[0] == (0, "short paragraph.")
        assert len([u for u in units if u[0] == 1]) >= 2

    def test_join_unit_texts(self):
        assert LL._join_unit_texts(["第一句。", "第二句。"]) == "第一句。第二句。"
        assert LL._join_unit_texts(["end.", "Next"]) == "end. Next"
        assert LL._join_unit_texts(["", "只有这段", ""]) == "只有这段"

    def test_translate_reassembles_units_into_same_block_count(self, tmp_path, monkeypatch):
        """整篇翻译完成后：译文段数 == 原文段数，且每段都含其全部单元译文。"""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "papers").mkdir()
        md = ("# Title\n\n" + ("This is a very long paragraph sentence. " * 240)
              + "\n\nshort tail paragraph.")
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 20)
        monkeypatch.setattr(LL, "list_library",
                            lambda *a, **k: json.dumps({"library": [{"file": "p.pdf", "title": "P"}]}))
        monkeypatch.setattr(LL, "_resolve_paper_path", lambda hit: str(pdf))
        monkeypatch.setattr(LL, "pdf_to_markdown", lambda *a, **k: md)
        batches = {"n": 0, "sizes": []}

        def fake_batch(batch):
            batches["n"] += 1
            batches["sizes"].append(len(batch))
            return [f"<译{b[:8]}…>" for b in batch]

        monkeypatch.setattr(LL, "_translate_block_batch", fake_batch)
        r = json.loads(LL.translate_paper("p.pdf"))
        assert r.get("ok") is True, r
        zh_path = tmp_path / "papers" / "translations" / "p.zh.md"
        zh_blocks = LL._md_blocks(zh_path.read_text(encoding="utf-8"))
        assert len(zh_blocks) == len(LL._md_blocks(md)), "译文段数必须与原文严格一致"
        assert all("<译" in b for b in zh_blocks), "每段都要拼回单元译文"
        assert batches["n"] > 1, "超大段应拆成多批"
        assert max(batches["sizes"]) <= 4


# ------------------------------------------------- 知识/摘要提速：分块并发（2026-09-17）
class TestParallelChunkExtraction:
    """分块 LLM 提炼并发化（知识提取 19 块串行 → 并发 5 路）+ 碎片去重压缩。"""

    def test_chunks_run_concurrently_and_keep_order(self, monkeypatch):
        import threading as _th
        import time as _time
        live = {"cur": 0, "max": 0}
        lock = _th.Lock()

        def fake_llm(prompt, label, **kw):
            with lock:
                live["cur"] += 1
                live["max"] = max(live["max"], live["cur"])
            _time.sleep(0.15)
            with lock:
                live["cur"] -= 1
            return json.dumps({"idx": int(label.rsplit("_", 1)[1])})

        monkeypatch.setattr(LL, "_llm_content", fake_llm)
        out = LL._llm_chunks_parallel(["a", "b", "c", "d"], lambda i, c: c, "chunk", workers=4)
        assert [p.get("idx") for p in out] == [0, 1, 2, 3], "结果必须按输入顺序返回"
        assert live["max"] >= 2, "必须真的并发"
        assert live["max"] <= 4

    def test_empty_chunk_retried_once(self, monkeypatch):
        """某块没产出合法 JSON 时必须严格模式重试一次——否则那块知识直接蒸发
        （实测 lung_no-smoking 缺了 Methods 的 FACETS/GISTIC 就是这类丢块）。"""
        seen = []

        def fake_llm(prompt, label, **kw):
            seen.append(label)
            if label.endswith("_fix_1"):
                return json.dumps({"ok": "fixed"})
            if label.endswith("_1"):
                return "抱歉，我无法按要求输出 JSON"
            return json.dumps({"ok": "first"})

        monkeypatch.setattr(LL, "_llm_content", fake_llm)
        out = LL._llm_chunks_parallel(["a", "b", "c"], lambda i, c: c, "chunk", workers=3)
        assert out[0] == {"ok": "first"} and out[2] == {"ok": "first"}
        assert out[1] == {"ok": "fixed"}, f"空块必须补齐，实际 {out[1]}；调用={seen}"
        assert sum(1 for s in seen if s.endswith("_fix_1")) == 1

    def test_chunk_failure_isolated(self, monkeypatch):
        def fake_llm(prompt, label, **kw):
            if label.endswith("_1"):
                raise RuntimeError("boom")
            return json.dumps({"ok": 1})

        monkeypatch.setattr(LL, "_llm_content", fake_llm)
        out = LL._llm_chunks_parallel(["a", "b"], lambda i, c: c, "chunk", workers=2)
        assert out[0] == {"ok": 1} and out[1] == {}, "单块失败不能拖垮整篇"

    def test_oversized_section_is_split(self):
        """没有标题行的 PDF（整篇=1 节）必须被拆成多块——否则一次巨型调用必然失败。"""
        big = ("This is a body paragraph sentence. " * 2000).strip()   # ~66k 字符
        chunks = LL._chunk_sections([("", big)], max_chars=9000)
        assert len(chunks) > 5, f"必须拆成多块，实际 {len(chunks)}"
        assert all(len(c) <= 9000 for c in chunks)
        # 段落间用 \n\n 拼接，去空白后内容不丢
        assert "".join("".join(c.split()) for c in chunks) == big.replace(" ", "")

    def test_chunk_sections_merges_small_sections_and_keeps_heading(self):
        secs = [("Intro", "p1"), ("Methods", "p2"), ("Long", "x" * 12000)]
        chunks = LL._chunk_sections(secs, max_chars=9000)
        assert all(len(c) <= 9000 for c in chunks)
        assert "## Intro" in chunks[0] and "## Methods" in chunks[0], "小节能合并"
        assert any("## Long" in c for c in chunks)
        assert sum(c.count("x") for c in chunks) == 12000, "长节内容不丢"

    def test_cap_json_size_keeps_json_valid(self):
        """截图式截断会切出非法 JSON → 合并调用拿到垃圾；这里必须按完整条目丢弃。"""
        big = {"biology": {"conclusions": [f"结论{i}·" + "x" * 200 for i in range(60)]},
               "bioinfo": {"software": [{"name": f"S{i}"} for i in range(30)]}}
        s = LL._cap_json_size(big, 3000)
        assert len(s) <= 3000
        parsed = json.loads(s)          # 关键：仍是合法 JSON
        assert parsed["biology"]["conclusions"], "不能把内容全丢光"
        assert len(parsed["biology"]["conclusions"]) < 60

    def test_cap_json_size_passthrough(self):
        small = {"biology": {"conclusions": ["A"]}}
        assert json.loads(LL._cap_json_size(small, 3000)) == small

    def test_long_paper_skips_llm_merge_and_keeps_all_fragments(self, tmp_path, monkeypatch):
        """碎片过大时必须跳过 LLM 合并（会失败）并保留全部碎片内容。"""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "papers").mkdir()
        big_md = ("\n\n".join("Body paragraph %d about single cell RNA sequencing. " % i
                              for i in range(3000)))     # >18000 字符 → 走分块
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 10)
        monkeypatch.setattr(LL, "_find_raw_entry", lambda q: {"file": "p.pdf", "title": "P",
                                                              "journal": "J", "doi": "10.1/x",
                                                              "tags": {"species": ["human"], "tissue": ["lung"], "direction": ["cancer"], "assay": "RNA"}})
        monkeypatch.setattr(LL, "_resolve_paper_path", lambda hit: str(pdf))
        monkeypatch.setattr(LL, "pdf_to_markdown", lambda *a, **k: big_md)
        monkeypatch.setattr(LL, "_write_knowledge_entries", lambda *a, **k: ([], []))
        monkeypatch.setattr(LL, "_save_index_entry", lambda *a, **k: None, raising=False)
        calls = []

        def fake_llm(prompt, label, **kw):
            calls.append(label)
            if label.startswith("lit_know_chunk"):
                # 每块给一大段结论 → 24 块碎片总长 >14000 字符，命中"跳过合并"分支
                return json.dumps({"biology": {"conclusions": ["结论-" + label + "·" + "细" * 1200]},
                                   "bioinfo": {"software": [{"name": "S-" + label}]}})
            raise AssertionError("碎片过长时不应再发 LLM 合并调用")

        monkeypatch.setattr(LL, "_llm_content", fake_llm)
        r = json.loads(LL.extract_paper_knowledge("p.pdf", force=True))
        assert r.get("ok") is True, r
        assert not any(lbl.startswith("lit_knowledge_merge") for lbl in calls)
        md_file = tmp_path / "papers" / "knowledge" / "p.md"
        body = md_file.read_text(encoding="utf-8")
        assert body.count("结论-lit_know_chunk_") >= 3, "每个分块的结论都要保留"
        assert "S-lit_know_chunk_" in body

    def test_compact_fragments_dedupes_and_shrinks(self):
        parts = [{"conclusions": ["A", "B"], "pathways": ["P"], "reference_genome": "GRCh38"},
                 {"conclusions": ["B", "C"], "pathways": ["P", "Q"], "reference_genome": "mm10"}]
        out = LL._compact_fragments(parts)
        assert out["conclusions"] == ["A", "B", "C"], "重复结论要去掉"
        assert out["pathways"] == ["P", "Q"]
        assert out["reference_genome"] == "GRCh38", "标量取首个非空"
        assert len(json.dumps(out, ensure_ascii=False)) <= len(json.dumps(parts, ensure_ascii=False))


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


# ---------------------------------------------------------------- 导入提速（2026-09-17）
class TestImportSpeedup:
    """导入提速的回归护栏（用户反馈"导入太慢"）：

    实测基线：18 篇 210MB → 43.25s（2.40s/篇）；其中串行 Crossref 反查占大头、
    LLM 分类固定 15–20s 全程阻塞。改造后同批 6.05s（0.34s/篇）。
    - 便宜去重在前：同名同大小不再读全文算 sha256
    - Crossref 结果落盘缓存 + 并发预取：每篇只查一次网络
    - LLM 分类与复制入库并行，标签先按规则落库、精细标签后台改写
    """

    def _fake_pdf(self, path, pad=30):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4\n" + b"x" * pad)
        return path

    def _fresh_cr_cache(self, monkeypatch):
        monkeypatch.setattr(LL, "_cr_cache_mem", None)
        monkeypatch.setattr(LL, "_cr_cache_dirty", False)

    def test_dup_name_size_skips_before_hashing(self, tmp_path, monkeypatch):
        """已导入过的文件（同名同大小）应在算 sha256 之前就跳过 —— 否则重复导入白读全文。"""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        papers = tmp_path / "papers";
        papers.mkdir()
        src = self._fake_pdf(tmp_path / "a.pdf")
        with open(papers / ".pdf_index.json", "w", encoding="utf-8") as f:
            json.dump([{"file": "a.pdf", "size": src.stat().st_size, "sha256": "known"}],
                      f, ensure_ascii=False)
        calls = {"n": 0}

        def _sha(p):
            calls["n"] += 1
            return "hash"

        monkeypatch.setattr(LL, "_sha256_of", _sha)
        res = json.loads(LL.import_pdfs([str(src)]))
        assert res["imported"] == 0 and res["skipped"] == 1   # 结果里 skipped 是条数
        assert calls["n"] == 0, "同名同大小必须在 sha256 之前短路"

    def test_crossref_cache_hit_avoids_second_lookup(self, tmp_path, monkeypatch):
        """同一篇文献（同 DOI）第二次导入不再打 Crossref；缓存落盘后新进程也命中。"""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "papers").mkdir()
        self._fresh_cr_cache(monkeypatch)
        calls = {"n": 0}

        def _fake_extract(pdf_path, text, original_path):
            calls["n"] += 1
            return {"title": "T", "journal": "J", "authors": ["A"], "year": "2026",
                    "doi": "10.1234/abc.def", "url": "", "volume": "", "issue": "",
                    "pages": "", "pmid": ""}

        monkeypatch.setattr(LL, "_extract_metadata", _fake_extract)
        text = "see doi 10.1234/abc.def for details"
        m1 = LL._crossref_meta_cached("p.pdf", text, "p.pdf")
        m2 = LL._crossref_meta_cached("p.pdf", text, "p.pdf")
        assert calls["n"] == 1 and m1["journal"] == "J" and m2["title"] == "T"
        LL._cr_cache_flush()
        cache_file = tmp_path / "papers" / ".crossref_cache.json"
        assert cache_file.exists()
        monkeypatch.setattr(LL, "_cr_cache_mem", None)          # 模拟进程重启：从磁盘读回
        m3 = LL._crossref_meta_cached("p.pdf", text, "p.pdf")
        assert calls["n"] == 1 and m3["journal"] == "J"

    def test_import_prefetches_metadata_once_per_file(self, tmp_path, monkeypatch):
        """并发预取的元数据必须被复制入库阶段复用：每篇只解析一次，且返回耗时。"""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "papers").mkdir()
        self._fresh_cr_cache(monkeypatch)
        monkeypatch.setattr(LL, "_pdf_text", lambda p, pages=2: "text")
        monkeypatch.setattr(LL, "_classify_papers", lambda entries: {})
        calls = {"n": 0}

        def _fake_extract(pdf_path, text, original_path):
            calls["n"] += 1
            return {"title": "T%d" % calls["n"], "journal": "J", "authors": [], "year": "2026",
                    "doi": "10.1000/x%d" % calls["n"], "url": "", "volume": "", "issue": "",
                    "pages": "", "pmid": ""}

        monkeypatch.setattr(LL, "_extract_metadata", _fake_extract)
        srcs = [str(self._fake_pdf(tmp_path / ("s%d.pdf" % i), 20 + i)) for i in range(3)]
        res = json.loads(LL.import_pdfs(srcs))
        assert res["imported"] == 3
        assert calls["n"] == 3, "每篇只应解析一次元数据（预取结果复用）"
        assert isinstance(res.get("elapsed_s"), (int, float))
        assert "crossref_cache" in res
        idx = json.loads((tmp_path / "papers" / ".pdf_index.json").read_text(encoding="utf-8"))
        assert len(idx) == 3
        assert all(e.get("tags") for e in idx), "导入返回时标签（规则）必须已可用"

    def test_bg_classification_overwrites_rule_tags(self, tmp_path, monkeypatch):
        """后台精细分类只改 tags、按文件名对号入座，不阻塞也不需要用户等待。"""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        papers = tmp_path / "papers";
        papers.mkdir()
        idx = papers / ".pdf_index.json"
        with open(idx, "w", encoding="utf-8") as f:
            json.dump([{"file": "a.pdf", "title": "T", "tags": LL._rule_classify("T")}],
                      f, ensure_ascii=False)

        class _F:
            def result(self):
                return {"__0": {"species": ["mouse"], "tissue": ["skeletal_muscle"],
                                "direction": ["aging"], "assay": "RNA",
                                "kb_category": "01_生物学知识"}}

        LL._apply_classification_bg(str(idx), {"a.pdf": "__0"}, _F())
        after = json.loads(idx.read_text(encoding="utf-8"))
        assert after[0]["tags"]["species"] == ["mouse"]
        assert after[0]["tags"]["tissue"] == ["skeletal_muscle"]
