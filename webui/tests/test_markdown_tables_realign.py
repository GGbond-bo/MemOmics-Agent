"""hermes 表格重排器（hermes-agent/agent/markdown_tables.py）的转义竖线回归测试。

为什么放这儿而不是 hermes-agent/tests/：仓库 .gitignore 第 54 行的 test_*.py 只放行
webui/tests/，hermes-agent/tests 整个目录是不跟踪的（2135 个文件被忽略）。放那儿的
测试等于没进版本库，所以挪到这个真正被跟踪的套件里。

同时也解释了这里的加载方式：用 importlib 按文件路径加载，不往 sys.path 里塞
hermes-agent —— 那会引入一个名为 agent 的顶层包，可能和其他 webui 测试撞名。

用户 2026-09 报的 bug：表里表示「绝对值」的竖线必须写成 |coef| 的转义形式，
而切分是裸 split('|')，把一格切成三格；又因为列数取的是 max(len(row))，
整张表被重排成 9 列、数据行补 4 个空格子 —— 表就「散」了。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_MT_PATH = ROOT / "hermes-agent" / "agent" / "markdown_tables.py"

_spec = importlib.util.spec_from_file_location("_memomics_markdown_tables", _MT_PATH)
assert _spec and _spec.loader, "没找到 %s" % _MT_PATH
_mt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mt)

split_table_row = _mt.split_table_row
realign_markdown_tables = _mt.realign_markdown_tables

# 用户原表（|coef| 已按 markdown 正确转义）
_ABS_TABLE = "\n".join([
    "| 对比 | FDR<0.05 | + \\|coef\\| >0.20 | + \\|coef\\| >0.25 | 0.20→0.25 再砍 |",
    "|---|---|---|---|---|",
    "| Aging (Y_Pre vs O_Pre) | 59,681 行 / 8,491 基因 | 34,289 / 7,591 | 23,178 / 6,679 | −11,111 行（−32.4%） |",
    "| Ex_Old (O_Pre vs O_Post) | 51,241 / 7,941 | 6,056 / 3,382 | 1,846 / 985 | −4,210（−69.5%） |",
])


def test_split_honours_escaped_pipe():
    assert split_table_row("| a | + \\|coef\\| >0.20 | b |") == ["a", "+ |coef| >0.20", "b"]


def test_split_keeps_escaped_trailing_pipe():
    """收尾的竖线被转义了就不是边框，不能当边框剥掉。"""
    assert split_table_row("| a | b \\|") == ["a", "b |"]


def test_split_double_backslash_is_a_real_backslash():
    """双反斜杠是真反斜杠，它后面的竖线仍然分隔单元格。"""
    assert split_table_row("| a \\\\ | b |") == ["a \\", "b"]


def test_realign_keeps_absolute_value_header_in_one_column():
    """核心回归：表头列数必须与数据行一致，且转义要原样保留给下游渲染器。"""
    out = realign_markdown_tables(_ABS_TABLE)
    rows = [ln for ln in out.split("\n") if ln.strip().startswith("|")]
    assert rows, "重排后没有表格行"
    counts = [len(split_table_row(r)) for r in rows]
    assert counts == [5] * len(rows), "列数被撑开了：%s" % counts
    assert split_table_row(rows[0])[2] == "+ |coef| >0.20"
    assert "\\|coef\\|" in out, "输出没重新转义，下游渲染器会再把它切开"


def test_realign_truncates_extra_body_cells():
    """边界：某行多写一个竖线只截断，绝不能反过来把整张表撑宽。"""
    src = "| a | b |\n|---|---|\n| 1 | 2 | 3 |\n"
    rows = [ln for ln in realign_markdown_tables(src).split("\n")
            if ln.strip().startswith("|")]
    assert [len(split_table_row(r)) for r in rows] == [2, 2, 2]


def test_realign_leaves_lone_backslash_alone():
    """不变量：不含竖线的单元格重排后逐字节不变（Windows 路径、正则等）。"""
    src = "| path | n |\n|------|---|\n| C:\\data | 1 |\n"
    out = realign_markdown_tables(src)
    assert "C:\\data" in out, "单独的反斜杠被转义了"


def test_realign_passthrough_when_no_pipe():
    """边界：没有竖线的文本必须原样返回。"""
    assert realign_markdown_tables("普通说明文字\n第二行") == "普通说明文字\n第二行"
