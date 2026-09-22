"""分析结果「文件直读」转换层（P5，2026-09-22）。

设计原则
--------
1. 全部在服务端转换：不引 CDN、不往 webui/assets 塞解析库；离线/打包后行为一致。
2. 依赖只做增强，不做前提：openpyxl / pypdf 有则用；没有就走标准库兜底
   （.xlsx 用 zipfile+XML，.docx 用 zipfile+XML），保证随包 python 少装东西也能看。
3. 任何转换失败都不许 500：退回 kind=binary + 元信息 + 下载按钮。
4. 只读：本模块不写任何文件，也不执行被预览文件的任何内容。

对外主入口：preview(path, sheet=None) -> dict
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import zipfile
from datetime import datetime
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------- 多语言
# P5.1（2026-09-22）：后端只按 lang 输出「固定文案」，前端不做中文解析 —— UI 切英文时
# 整条链路（含 note / error / hint）都是英文。默认 zh，既有行为与既有测试不受影响。
# 说明：server.py 用 run_in_executor 调 preview()，请求可能落在不同工作线程上；
# 所以语言状态放 threading.local（每线程一份），而不是模块级全局，避免并发请求串语言。
_LANG_LOCAL = threading.local()


def _get_lang() -> str:
    return getattr(_LANG_LOCAL, "lang", "zh")


def set_lang(lang) -> str:
    """设置本次预览的文案语言（zh / en），返回生效值。"""
    _LANG_LOCAL.lang = "en" if str(lang or "").strip().lower().startswith("en") else "zh"
    return _LANG_LOCAL.lang


def lang_now() -> str:
    return _get_lang()


def T(zh: str, en: str, *args) -> str:
    """按当前语言取文案；给了 args 就走 %-格式化（格式化失败时原样返回，绝不抛）。"""
    s = en if _get_lang() == "en" else zh
    if args:
        try:
            return s % args
        except Exception:
            return s
    return s


def hint_for(ext: str) -> str:
    """二进制/专用格式的「这是什么文件」说明，按语言取。"""
    pair = BINARY_HINTS.get(ext or "")
    if pair:
        return pair[1] if _get_lang() == "en" else pair[0]
    return "Binary / proprietary format" if _get_lang() == "en" else "二进制/专用格式"


# ---------------------------------------------------------------- 分类

TEXT_EXTS = {".txt", ".log", ".out", ".err", ".text", ".nfo",
             ".ini", ".cfg", ".conf", ".env", ".properties"}
CODE_EXTS = {".py", ".r", ".rmd", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".js",
             ".ts", ".jsx", ".tsx", ".java", ".c", ".h", ".cpp", ".hpp", ".go",
             ".rs", ".pl", ".jl", ".sql", ".yaml", ".yml", ".toml", ".json",
             ".xml", ".css", ".smk", ".mk", ".qmd", ".nf", ".obo"}
MARKDOWN_EXTS = {".md", ".markdown", ".mdown", ".rst"}
TABLE_EXTS = {".csv", ".tsv"}
EXCEL_EXTS = {".xlsx", ".xlsm", ".xltx", ".xltm"}
WORD_EXTS = {".docx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg"}
PDF_EXTS = {".pdf"}
HTML_EXTS = {".html", ".htm"}
NOTEBOOK_EXTS = {".ipynb"}
# 明确知道的二进制（给出「为什么看不了」的解释，而不是笼统的未知类型）
# 值统一是 (中文, English) 二元组：按 lang 取，见 hint_for()
BINARY_HINTS = {
    ".rds": ("R 序列化对象（RDS）", "R serialized object (RDS)"),
    ".rdata": ("R 工作空间（RData）", "R workspace image (RData)"),
    ".rda": ("R 数据（RDA）", "R data file (RDA)"),
    ".h5ad": ("AnnData/HDF5 单细胞对象", "AnnData/HDF5 single-cell object"),
    ".h5": ("HDF5 数据", "HDF5 data"), ".hdf5": ("HDF5 数据", "HDF5 data"),
    ".loom": ("Loom 单细胞对象", "Loom single-cell object"),
    ".mtx": ("稀疏矩阵（MatrixMarket）", "Sparse matrix (MatrixMarket)"),
    ".bam": ("BAM 比对文件", "BAM alignment"), ".bai": ("BAM 索引", "BAM index"),
    ".sam": ("SAM 比对文件", "SAM alignment"),
    ".cram": ("CRAM 比对文件", "CRAM alignment"),
    ".bed": ("BED 区间文件", "BED intervals"),
    ".bigwig": ("BigWig 覆盖度", "BigWig coverage"), ".bw": ("BigWig 覆盖度", "BigWig coverage"),
    ".wig": ("Wiggle 覆盖度", "Wiggle coverage"),
    ".parquet": ("Parquet 列式数据", "Parquet columnar data"),
    ".feather": ("Feather 列式数据", "Feather columnar data"),
    ".arrow": ("Arrow 数据", "Arrow data"),
    ".npy": ("NumPy 数组", "NumPy array"), ".npz": ("NumPy 压缩数组", "NumPy compressed array"),
    ".pkl": ("Python pickle", "Python pickle"), ".pickle": ("Python pickle", "Python pickle"),
    ".joblib": ("joblib 序列化对象", "joblib serialized object"),
    ".zip": ("压缩包", "ZIP archive"), ".gz": ("gzip 压缩文件", "gzip file"),
    ".bz2": ("bzip2 压缩文件", "bzip2 file"),
    ".tar": ("tar 归档", "tar archive"), ".7z": ("7z 压缩包", "7z archive"),
    ".rar": ("rar 压缩包", "rar archive"),
    ".xls": ("旧版 Excel（.xls，二进制格式）", "Legacy Excel (.xls, binary)"),
    ".doc": ("旧版 Word（.doc，二进制格式）", "Legacy Word (.doc, binary)"),
    ".ppt": ("旧版 PowerPoint", "Legacy PowerPoint"),
    ".pptx": ("PowerPoint 演示文稿", "PowerPoint presentation"),
    ".hic": ("Hi-C 接触矩阵", "Hi-C contact matrix"),
    ".cool": ("cool 矩阵", "cool matrix"), ".mcool": ("multi-cool 矩阵", "multi-cool matrix"),
    ".fastq": ("FASTQ 测序数据", "FASTQ reads"), ".fq": ("FASTQ 测序数据", "FASTQ reads"),
    ".fasta": ("FASTA 序列", "FASTA sequence"), ".fa": ("FASTA 序列", "FASTA sequence"),
    ".gtf": ("GTF 注释", "GTF annotation"), ".gff": ("GFF 注释", "GFF annotation"),
    ".gff3": ("GFF3 注释", "GFF3 annotation"),
    ".vcf": ("VCF 变异文件", "VCF variants"), ".bcf": ("BCF 变异文件", "BCF variants"),
    ".tif": ("TIFF 图像", "TIFF image"), ".tiff": ("TIFF 图像", "TIFF image"),
    ".eps": ("EPS 矢量图", "EPS vector graphic"), ".ps": ("PostScript", "PostScript"),
    ".psd": ("Photoshop 文件", "Photoshop document"),
    ".ai": ("Illustrator 文件", "Illustrator document"),
    ".sbml": ("SBML 模型", "SBML model"), ".cel": ("Affymetrix CEL", "Affymetrix CEL"),
}

# 文本读入上限（超过只给头部，前端提示下载完整文件）
MAX_TEXT_BYTES = 400_000
MAX_TEXT_LINES = 6000
MAX_TABLE_ROWS = 500
MAX_TABLE_COLS = 60
MAX_TABLE_SHEETS = 12
MAX_HTML_CHARS = 400_000
MAX_NOTEBOOK_CELLS = 300
MAX_NOTEBOOK_IMAGE_BYTES = 1_500_000
MAX_NOTEBOOK_IMAGE_TOTAL = 4_000_000


def ext_of(path: str) -> str:
    return os.path.splitext(str(path or ""))[1].lower()


def human_size(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return ""


def file_meta(path: str) -> dict:
    """文件元信息（永远可用，即使预览失败）"""
    try:
        st = os.stat(path)
        size = int(st.st_size)
        mtime = float(st.st_mtime)
    except OSError:
        return {"name": os.path.basename(str(path or "")), "size": 0, "mtime": 0,
                "mtime_str": "", "ext": ext_of(path), "exists": False, "size_str": ""}
    return {
        "name": os.path.basename(path),
        "size": size,
        "size_str": human_size(size),
        "mtime": mtime,
        "mtime_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "ext": ext_of(path),
        "exists": True,
    }


def kind_of(path: str) -> str:
    e = ext_of(path)
    if e in IMAGE_EXTS:
        return "image"
    if e in PDF_EXTS:
        return "pdf"
    if e in HTML_EXTS:
        return "html"
    if e in MARKDOWN_EXTS:
        return "markdown"
    if e in TABLE_EXTS:
        return "table"
    if e in EXCEL_EXTS:
        return "excel"
    if e in WORD_EXTS:
        return "word"
    if e in NOTEBOOK_EXTS:
        return "notebook"
    if e in CODE_EXTS:
        return "code"
    if e in TEXT_EXTS:
        return "text"
    return "binary"


# ---------------------------------------------------------------- 文本

_ENCODINGS = ("utf-8", "gb18030", "big5", "latin-1")


def _decode_utf8(raw: bytes, allow_partial_tail: bool = True) -> str:
    """严格 utf-8 解码；截断导致的尾部残缺序列不报错（增量解码 final=False）。"""
    import codecs
    dec = codecs.getincrementaldecoder("utf-8")()
    text = dec.decode(raw, final=not allow_partial_tail)
    if not allow_partial_tail:
        return text
    return text


def read_text_file(path: str, max_bytes: int = MAX_TEXT_BYTES):
    """读文本，返回 (text, truncated, encoding)。多编码兜底，绝不抛异常。"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return "", False, ""
    try:
        with open(path, "rb") as f:
            raw = f.read(max_bytes + 1)
    except OSError:
        return "", False, ""
    truncated = len(raw) > max_bytes or size > max_bytes
    raw = raw[:max_bytes]
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
        try:
            return _decode_utf8(raw), truncated, "utf-8-sig"
        except UnicodeDecodeError:
            pass
    for enc in _ENCODINGS:
        try:
            if enc.startswith("utf-8"):
                # 2026-09-22：截断处可能把一个多字节字符切成两半，用增量解码器
                # （final=False）丢弃尾部残缺序列，别让 utf-8 误退回 latin-1 乱码
                return _decode_utf8(raw), truncated, enc
            return raw.decode(enc), truncated, enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace"), truncated, "utf-8(replace)"


def _cap_lines(text: str, max_lines: int = MAX_TEXT_LINES):
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text, False, len(lines)
    return "\n".join(lines[:max_lines]), True, len(lines)


def preview_text(path: str, kind: str = "text") -> dict:
    text, truncated, enc = read_text_file(path)
    text, line_cut, total_lines = _cap_lines(text)
    cut = bool(truncated or line_cut)
    return {"kind": kind, "text": text, "encoding": enc,
            "truncated": cut,
            "truncated_reason": T("文件较大，仅显示前 %d 行 / %s",
                                  "Large file — showing the first %d lines / %s",
                                  MAX_TEXT_LINES, human_size(MAX_TEXT_BYTES)) if cut else "",
            "total_lines": total_lines}


def preview_markdown(path: str) -> dict:
    return preview_text(path, kind="markdown")


# ---------------------------------------------------------------- 表格（csv/tsv）

def _sniff_delim(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except Exception:
        return "\t" if sample.count("\t") > sample.count(",") else ","


def _cell_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:
            return ""
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        return repr(round(v, 6))
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _grid_to_sheet(name: str, rows, total_rows=None, total_cols=None) -> dict:
    """把二维表整理成 表头 + 数据行（首行当表头，空表头自动补 列N）。"""
    while rows and all((c or "") == "" for c in rows[-1]):
        rows.pop()
    header = list(rows[0]) if rows else []
    body = [list(r) for r in rows[1:]] if rows else []
    if not header or all((h or "") == "" for h in header):
        width0 = len(body[0]) if body else len(header)
        header = [T("列%d", "Col %d", i + 1) for i in range(width0)]
        body = [list(r) for r in rows]
    width = max([len(header)] + [len(r) for r in body]) if body else len(header)
    header = (header + [""] * width)[:width]
    body = [(r + [""] * width)[:width] for r in body]
    out = {"name": name, "columns": header, "rows": body}
    if total_rows is not None:
        out["total_rows"] = int(total_rows)
    if total_cols is not None:
        out["total_cols"] = int(total_cols)
    return out


def preview_table(path: str, max_rows: int = MAX_TABLE_ROWS, max_cols: int = MAX_TABLE_COLS) -> dict:
    text, truncated, enc = read_text_file(path, max_bytes=2_000_000)
    if not text:
        return {"kind": "table", "sheets": [{"name": os.path.basename(path), "columns": [], "rows": []}],
                "truncated": truncated, "note": T("文件为空或无法解码", "File is empty or cannot be decoded")}
    delim = _sniff_delim(text[:8192])
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows, total, wide = [], 0, False
    for row in reader:
        total += 1
        if len(row) > max_cols:
            wide = True
        if len(rows) < max_rows + 1:
            rows.append([_cell_str(c) for c in row[:max_cols]])
    sheet = _grid_to_sheet(os.path.basename(path), rows, total_rows=max(total - 1, 0))
    return {"kind": "table", "delimiter": "\t" if delim == "\t" else delim, "sheets": [sheet],
            "truncated": bool(truncated or total - 1 > max_rows or wide), "encoding": enc,
            "engine": "csv"}


# ---------------------------------------------------------------- Excel

def _excel_openpyxl(path: str, max_rows: int, max_cols: int, only_sheet=None):
    import openpyxl  # type: ignore
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets, truncated = [], False
    try:
        for ws in wb.worksheets:
            if only_sheet and ws.title != only_sheet:
                continue
            raw = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i > max_rows:
                    truncated = True
                    break
                raw.append([_cell_str(c) for c in list(row)[:max_cols]])
            sheets.append(_grid_to_sheet(ws.title, raw, total_rows=ws.max_row, total_cols=ws.max_column))
            if len(sheets) >= MAX_TABLE_SHEETS:
                truncated = True
                break
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return sheets, truncated


# --- 标准库兜底：.xlsx 就是 zip + XML ---

_M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_index(ref: str) -> int:
    m = re.match(r"([A-Z]+)", (ref or "").upper())
    if not m:
        return 0
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _xlsx_date_styles(zf: zipfile.ZipFile) -> set:
    """哪些 cellXfs 下标是日期格式（标准库兜底里用来把 46083 还原成 2026-03-01）。"""
    try:
        root = ET.fromstring(zf.read("xl/styles.xml"))
    except Exception:
        return set()
    custom = {}
    for nf in root.iter(_M + "numFmt"):
        try:
            custom[int(nf.get("numFmtId") or -1)] = nf.get("formatCode") or ""
        except (TypeError, ValueError):
            continue
    builtin_date = set(range(14, 23)) | {27, 30, 36, 45, 46, 47, 50, 57}
    out = set()
    cellxfs = root.find(_M + "cellXfs")
    if cellxfs is None:
        return out
    for i, xf in enumerate(cellxfs.findall(_M + "xf")):
        try:
            fid = int(xf.get("numFmtId") or 0)
        except (TypeError, ValueError):
            fid = 0
        if fid in builtin_date:
            out.add(i)
            continue
        code = custom.get(fid, "")
        if code and "[" not in code and re.search(r"[yY]", code) and re.search(r"[mM]", code):
            out.add(i)
    return out


def _excel_serial_to_str(v: str) -> str:
    """Excel 日期序列号 -> 可读时间（1900 日期系统，含 Excel 的闰年 bug 偏移）。"""
    try:
        serial = float(v)
    except (TypeError, ValueError):
        return v
    if serial <= 0 or serial > 200000:
        return v
    try:
        from datetime import timedelta
        dt = datetime(1899, 12, 30) + timedelta(days=serial)
    except Exception:
        return v
    return dt.strftime("%Y-%m-%d %H:%M:%S") if (serial % 1) else dt.strftime("%Y-%m-%d")


def _xlsx_shared_strings(zf: zipfile.ZipFile):
    out = []
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except Exception:
        return out
    for si in root.findall(_M + "si"):
        out.append("".join(t.text or "" for t in si.iter(_M + "t")))
    return out


def _xlsx_sheets_via_zip(path: str, max_rows: int, max_cols: int, only_sheet=None):
    """不依赖 openpyxl 的 .xlsx 读取（sharedStrings + 单元格值）。"""
    zf = zipfile.ZipFile(path)
    try:
        shared = _xlsx_shared_strings(zf)
        date_styles = _xlsx_date_styles(zf)
        names, rels, targets = [], {}, []
        try:
            wbroot = ET.fromstring(zf.read("xl/workbook.xml"))
            for sh in wbroot.iter(_M + "sheet"):
                names.append((sh.get("name") or "Sheet", sh.get(_R + "id") or ""))
        except Exception:
            names = []
        try:
            for rel in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")):
                rels[rel.get("Id")] = rel.get("Target") or ""
        except Exception:
            rels = {}
        for nm, rid in names:
            tgt = rels.get(rid, "")
            if not tgt:
                continue
            tgt = tgt.lstrip("/")
            targets.append((nm, tgt if tgt.startswith("xl/") else "xl/" + tgt))
        if not targets:
            targets = [(os.path.basename(n)[:-5], n) for n in zf.namelist()
                       if n.startswith("xl/worksheets/") and n.endswith(".xml")][:MAX_TABLE_SHEETS]
        sheets, truncated = [], False
        for nm, tgt in targets:
            if only_sheet and nm != only_sheet:
                continue
            try:
                sroot = ET.fromstring(zf.read(tgt))
            except Exception:
                continue
            raw = []
            for r_i, row in enumerate(sroot.iter(_M + "row")):
                if r_i > max_rows:
                    truncated = True
                    break
                cells = []
                for c in row.findall(_M + "c"):
                    idx = _col_index(c.get("r") or "")
                    if idx >= max_cols:
                        continue
                    t = c.get("t")
                    v = c.find(_M + "v")
                    isn = c.find(_M + "is")
                    if t == "s" and v is not None and v.text is not None:
                        try:
                            val = shared[int(v.text)]
                        except (ValueError, IndexError):
                            val = v.text or ""
                    elif t == "inlineStr" and isn is not None:
                        val = "".join(x.text or "" for x in isn.iter(_M + "t"))
                    else:
                        val = (v.text if v is not None and v.text is not None else "")
                        try:
                            if int(c.get("s") or -1) in date_styles:
                                val = _excel_serial_to_str(val)
                        except (TypeError, ValueError):
                            pass
                    while len(cells) < idx:
                        cells.append("")
                    cells.append(val)
                raw.append(cells[:max_cols])
            sheets.append(_grid_to_sheet(nm, raw, total_rows=len(raw)))
            if len(sheets) >= MAX_TABLE_SHEETS:
                truncated = True
                break
        return sheets, truncated
    finally:
        zf.close()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _spreadsheetml_2003(path: str, max_rows: int, max_cols: int, only_sheet=None):
    """Excel 2003 XML（SpreadsheetML）：有些工具会把这种 XML 直接存成 .xlsx。

    2026-09-22：本机 results/memomics-d9023985/data/senmayo_supp.xlsx 就是这种文件
    （openpyxl 报 File is not a zip file），所以单独兜一层。
    """
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        raise ValueError(T("不是 XML 表格：%s", "Not an XML spreadsheet: %s", e))
    if _local(root.tag) != "Workbook":
        raise ValueError(T("不是 SpreadsheetML 工作簿（根节点 %s）",
                           "Not a SpreadsheetML workbook (root node %s)", _local(root.tag)))
    sheets, truncated = [], False
    for ws in root:
        if _local(ws.tag) != "Worksheet":
            continue
        name = ""
        for k, v in (ws.attrib or {}).items():
            if _local(k) == "Name":
                name = v
        if only_sheet and name != only_sheet:
            continue
        table = None
        for ch in ws:
            if _local(ch.tag) == "Table":
                table = ch
                break
        raw = []
        if table is not None:
            for row in table:
                if _local(row.tag) != "Row":
                    continue
                if len(raw) > max_rows:
                    truncated = True
                    break
                cells = []
                try:
                    skip = int([v for k, v in (row.attrib or {}).items() if _local(k) == "Index"][0]) - 1
                except Exception:
                    skip = 0
                cells.extend([""] * max(0, skip))
                for cell in row:
                    if _local(cell.tag) != "Cell":
                        continue
                    data, dtype = "", ""
                    for ch in cell:
                        if _local(ch.tag) == "Data":
                            data = ch.text or ""
                            for k, v in (ch.attrib or {}).items():
                                if _local(k) == "Type":
                                    dtype = v
                    if dtype in ("Number", "DateTime") and data.strip():
                        try:
                            if dtype == "DateTime":
                                data = data.replace("T", " ")[:19]
                            else:
                                fv = float(data)
                                data = str(int(fv)) if fv.is_integer() else str(fv)
                        except ValueError:
                            pass
                    cells.append(data)
                raw.append(cells[:max_cols])
        sheets.append(_grid_to_sheet(name or "Sheet%d" % (len(sheets) + 1), raw, total_rows=len(raw)))
        if len(sheets) >= MAX_TABLE_SHEETS:
            truncated = True
            break
    if not sheets:
        raise ValueError(T("SpreadsheetML 里没有工作表", "No worksheet inside the SpreadsheetML"))
    return sheets, truncated


def preview_excel(path: str, sheet=None, max_rows: int = MAX_TABLE_ROWS, max_cols: int = MAX_TABLE_COLS) -> dict:
    sheets, truncated, engine, err = [], False, "", ""
    try:
        sheets, truncated = _excel_openpyxl(path, max_rows, max_cols, sheet)
        engine = "openpyxl"
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
        for fn, label in ((_xlsx_sheets_via_zip, "stdlib-zip"), (_spreadsheetml_2003, "excel-2003-xml")):
            try:
                sheets, truncated = fn(path, max_rows, max_cols, sheet)
                engine, err = label, ""
                break
            except Exception as e2:
                err = (err + " / " if err else "") + "%s" % e2
        if not sheets:
            return {"kind": "excel", "sheets": [], "truncated": False, "engine": "",
                    "error": T("无法解析该表格：%s", "Cannot parse this spreadsheet: %s", err)}
    if not sheets:
        return {"kind": "excel", "sheets": [], "truncated": truncated, "engine": engine,
                "error": err or T("没有可显示的工作表", "No worksheet to display")}
    return {"kind": "excel", "sheets": sheets, "truncated": bool(truncated), "engine": engine, "error": err}


# ---------------------------------------------------------------- Word (.docx)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _run_html(r) -> str:
    txt = ""
    for node in r.iter():
        tag = node.tag
        if tag == _W + "t":
            txt += node.text or ""
        elif tag == _W + "tab":
            txt += "    "
        elif tag in (_W + "br", _W + "cr"):
            txt += "\n"
    if not txt:
        return ""
    html = _escape(txt).replace("\n", "<br>")
    rpr = r.find(_W + "rPr")
    if rpr is not None:
        if rpr.find(_W + "b") is not None:
            html = "<strong>" + html + "</strong>"
        if rpr.find(_W + "i") is not None:
            html = "<em>" + html + "</em>"
        if rpr.find(_W + "u") is not None:
            html = "<u>" + html + "</u>"
        va = rpr.find(_W + "vertAlign")
        if va is not None and va.get(_W + "val") == "superscript":
            html = "<sup>" + html + "</sup>"
    return html


def _para_html(p) -> str:
    inner = "".join(_run_html(r) for r in p.findall(_W + "r"))
    for hl in p.findall(_W + "hyperlink"):
        inner += "".join(_run_html(r) for r in hl.findall(_W + "r"))
    style = ""
    ppr = p.find(_W + "pPr")
    if ppr is not None:
        st = ppr.find(_W + "pStyle")
        if st is not None:
            style = (st.get(_W + "val") or "").lower()
        if ppr.find(_W + "numPr") is not None and inner.strip():
            inner = "• " + inner
    if not inner.strip():
        return ""
    if style.startswith("heading") or style in ("title", "subtitle"):
        m = re.search(r"(\d+)", style)
        lvl = min(max(int(m.group(1)) if m else 1, 1), 6)
        return "<h%d>%s</h%d>" % (lvl, inner, lvl)
    if style.startswith("quote") or style == "intensequote":
        return "<blockquote>" + inner + "</blockquote>"
    if style.startswith("listparagraph"):
        return "<div class='dx-li'>" + inner + "</div>"
    return "<p>" + inner + "</p>"


def _tbl_html(tbl) -> str:
    out = ["<table class=\"dx-table\">"]
    for tr in tbl.findall(_W + "tr"):
        out.append("<tr>")
        for tc in tr.findall(_W + "tc"):
            cell = "".join(_para_html(p) for p in tc.findall(_W + "p"))
            out.append("<td>" + (cell or "") + "</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def preview_docx(path: str) -> dict:
    """标准库解析 .docx：段落（标题/加粗/列表）+ 表格 -> HTML。"""
    try:
        zf = zipfile.ZipFile(path)
        try:
            with zf.open("word/document.xml") as f:
                root = ET.fromstring(f.read())
        finally:
            zf.close()
    except Exception as e:
        return {"kind": "word", "html": "",
                "error": T("无法解析该 Word 文件：%s", "Cannot parse this Word file: %s", e)}
    body = root.find(_W + "body")
    if body is None:
        return {"kind": "word", "html": "",
                "error": T("文档结构异常（没有 body）", "Malformed document (no body element)")}
    html, n_par, n_tbl, chars, truncated = [], 0, 0, 0, False
    for child in body:
        if child.tag == _W + "p":
            frag, n_par = _para_html(child), n_par + 1
        elif child.tag == _W + "tbl":
            frag, n_tbl = _tbl_html(child), n_tbl + 1
        else:
            continue
        if frag:
            html.append(frag)
            chars += len(frag)
        if len(html) > 4000 or chars > MAX_HTML_CHARS:
            truncated = True
            break
    return {"kind": "word", "html": "".join(html), "paragraphs": n_par, "tables": n_tbl,
            "truncated": truncated, "error": ""}


# ---------------------------------------------------------------- Jupyter

def preview_notebook(path: str) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            nb = json.load(f)
    except Exception as e:
        return {"kind": "notebook", "cells": [],
                "error": T("无法解析 .ipynb：%s", "Cannot parse this .ipynb: %s", e)}
    cells, truncated, img_total = [], False, 0
    all_cells = nb.get("cells") or []
    for c in all_cells[:MAX_NOTEBOOK_CELLS]:
        src = c.get("source") or ""
        if isinstance(src, list):
            src = "".join(src)
        item = {"type": c.get("cell_type") or "code", "source": src, "outputs": []}
        for o in (c.get("outputs") or [])[:20]:
            otype = o.get("output_type") or ""
            if otype == "stream":
                txt = o.get("text") or ""
                item["outputs"].append({"type": "text", "text": "".join(txt) if isinstance(txt, list) else txt})
            elif otype in ("execute_result", "display_data"):
                data = o.get("data") or {}
                if "image/png" in data and img_total < MAX_NOTEBOOK_IMAGE_TOTAL:
                    b64 = data["image/png"]
                    b64 = "".join(b64) if isinstance(b64, list) else b64
                    if len(b64) <= MAX_NOTEBOOK_IMAGE_BYTES:
                        img_total += len(b64)
                        item["outputs"].append({"type": "image", "mime": "image/png", "data": b64})
                        continue
                tp = data.get("text/plain")
                if tp:
                    item["outputs"].append({"type": "text", "text": "".join(tp) if isinstance(tp, list) else tp})
            elif otype == "error":
                tb = o.get("traceback") or []
                item["outputs"].append({"type": "error", "text": "\n".join(tb) if isinstance(tb, list) else str(tb)})
        cells.append(item)
    if len(all_cells) > MAX_NOTEBOOK_CELLS:
        truncated = True
    return {"kind": "notebook", "cells": cells, "truncated": truncated, "error": ""}


# ---------------------------------------------------------------- PDF

def preview_pdf(path: str) -> dict:
    info = {"kind": "pdf", "pages": 0, "text_excerpt": "", "error": ""}
    try:
        from pypdf import PdfReader  # type: ignore
        rd = PdfReader(path)
        info["pages"] = len(rd.pages)
        try:
            info["encrypted"] = bool(rd.is_encrypted)
        except Exception:
            info["encrypted"] = False
        if info["pages"]:
            try:
                info["text_excerpt"] = (rd.pages[0].extract_text() or "")[:2000]
            except Exception:
                pass
    except Exception as e:
        info["error"] = T("无法读取 PDF 信息（浏览器内嵌阅读不受影响）：%s",
                          "Cannot read PDF metadata (inline viewing is unaffected): %s", e)
    return info


# ---------------------------------------------------------------- 内容嗅探兜底

def _looks_like_text(path: str, probe: int = 4096) -> bool:
    """文件到底是不是文本？（用于「扩展名骗人」的兜底判断）

    2026-09-22：本机真实案例 results/memomics-d9023985/data/senmayo_supp.xlsx 是
    下载失败留下的 GCS AccessDenied XML（466 字节）——扩展名 .xlsx，内容却是 XML。
    这种文件不该报「无法解析」，而该直接把原文摊给用户看。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read(probe)
    except OSError:
        return False
    if not raw or b"\x00" in raw:
        return False
    head = raw[:8].lstrip().lower()
    if head.startswith(b"%pdf") or head.startswith(b"\x89png") or head.startswith(b"\xff\xd8") or head.startswith(b"gif8"):
        return False
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("gb18030")
    except UnicodeDecodeError:
        return False
    printable = sum(1 for b in raw if b >= 0x20 or b in (9, 10, 13))
    return printable >= len(raw) * 0.9


def _text_fallback(path: str, meta: dict, original_kind: str, reason: str) -> dict:
    text, truncated, enc = read_text_file(path, max_bytes=200_000)
    text, line_cut, total = _cap_lines(text, 2000)
    return {"kind": "text", "text": text, "encoding": enc, "meta": meta,
            "name": meta.get("name", ""), "ext": meta.get("ext", ""),
            "truncated": bool(truncated or line_cut), "total_lines": total,
            "original_kind": original_kind, "note": reason, "error": ""}


# ---------------------------------------------------------------- 分发

def preview(path: str, sheet=None, max_rows: int = MAX_TABLE_ROWS, max_cols: int = MAX_TABLE_COLS,
            lang: str = "zh"):
    """把任意文件转成前端能直接显示的结构。永远返回 dict，带 kind。

    lang: "zh"（默认）| "en" —— 只影响 note / error / hint 这些固定文案。
    """
    set_lang(lang)
    meta = file_meta(path)
    kind = kind_of(path)
    if not meta.get("exists"):
        return {"kind": "missing", "meta": meta,
                "error": T("文件不存在或已被删除", "File does not exist or was deleted")}
    if not os.path.isfile(path):
        return {"kind": "missing", "meta": meta,
                "error": T("这是一个目录，不能预览", "This is a directory and cannot be previewed")}
    out = {"kind": kind, "meta": meta, "name": meta["name"], "ext": meta["ext"], "error": ""}
    try:
        if kind == "markdown":
            out.update(preview_markdown(path))
        elif kind in ("text", "code"):
            out.update(preview_text(path, kind))
        elif kind == "table":
            out.update(preview_table(path, max_rows, max_cols))
        elif kind == "excel":
            out.update(preview_excel(path, sheet, max_rows, max_cols))
        elif kind == "word":
            out.update(preview_docx(path))
        elif kind == "notebook":
            out.update(preview_notebook(path))
        elif kind == "pdf":
            out.update(preview_pdf(path))
        elif kind in ("image", "html"):
            out["inline"] = True   # 交给浏览器直接用原始字节渲染
        else:
            out["hint"] = hint_for(meta["ext"])

        # 内容嗅探兜底：扩展名与内容不符时（下载失败的错误页、纯文本占位文件），
        # 直接当文本显示，别让用户只看到一句「无法解析」。
        if kind in ("excel", "word", "notebook"):
            empty = not (out.get("sheets") or out.get("html") or out.get("cells"))
            if (out.get("error") or empty) and _looks_like_text(path):
                return _text_fallback(path, meta, kind,
                                      T("这个 .%s 文件的内容其实不是可解析的表格/文档（可能是下载失败或占位文件），以下是原文",
                                        "The content of this .%s file is not a parsable spreadsheet/document "
                                        "(probably a failed download or a placeholder). Raw content below.",
                                        (meta.get("ext") or "").lstrip(".")))
        elif kind in ("pdf", "binary") and meta.get("ext") != ".svg" and meta.get("size", 0) < 65536:
            if _looks_like_text(path):
                return _text_fallback(path, meta, kind,
                                      T("这个 .%s 文件的内容不是二进制数据（可能是下载失败或占位文本），以下是原文",
                                        "The content of this .%s file is not binary data "
                                        "(probably a failed download or placeholder text). Raw content below.",
                                        (meta.get("ext") or "").lstrip(".")))
        return out
    except Exception as e:  # 兜底：任何异常都不许冒泡成 500
        return {"kind": "binary", "meta": meta, "name": meta["name"], "ext": meta["ext"],
                "hint": hint_for(meta["ext"]) if meta["ext"] in BINARY_HINTS else "",
                "error": T("预览失败，可下载后用本地软件打开：%s: %s",
                           "Preview failed — download the file and open it locally: %s: %s",
                           type(e).__name__, e)}
