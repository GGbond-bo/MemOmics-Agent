"""cli-anything-illustrator — agent-native CLI for Adobe Illustrator (Windows COM/ExtendScript).

Iron rules (CLI-Anything Hermes skill):
  * one-shot subcommands + REPL default
  * --json machine-readable output
  * real backend (Illustrator COM) preferred over reimplementation
  * NEVER save the user's document unless explicitly asked
"""

from __future__ import annotations

import json
import sys

import click

from .utils import illustrator_backend as be


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for k, v in payload.items():
            click.echo(f"{k}: {v}")


def _guard(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        click.echo(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
@click.option("--timeout", default=180, show_default=True, help="Bridge timeout (seconds)")
@click.pass_context
def cli(ctx: click.Context, as_json: bool, timeout: int) -> None:
    """CLI harness for Adobe Illustrator (documents, artboards, text, export)."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json
    ctx.obj["timeout"] = timeout
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@cli.command()
@click.pass_context
def info(ctx: click.Context) -> None:
    """Active document / artboard / object counts (read-only)."""
    res = _guard(be.run_jsx, be.JSX_INFO, timeout=ctx.obj["timeout"])
    _emit(res, ctx.obj["json"])


@cli.command()
@click.pass_context
def artboards(ctx: click.Context) -> None:
    """List artboards of the active document."""
    res = _guard(be.run_jsx, be.JSX_ARTBOARDS, timeout=ctx.obj["timeout"])
    if ctx.obj["json"]:
        _emit(res, True)
    else:
        click.echo(f"active_doc: {res.get('active_doc')}  artboards: {len(res.get('artboards', []))}")
        for ab in res.get("artboards", []):
            star = "*" if ab.get("active") else " "
            click.echo(f" {star} [{ab['index']}] {ab['name']}  rect={ab['rect']}")


@cli.command("text-list")
@click.pass_context
def text_list(ctx: click.Context) -> None:
    """List text frames (contents / font / size / bounds)."""
    res = _guard(be.run_jsx, be.JSX_TEXT_LIST, timeout=ctx.obj["timeout"])
    if ctx.obj["json"]:
        _emit(res, True)
    else:
        click.echo(f"active_doc: {res.get('active_doc')}  text_frames: {res.get('count')}")
        for it in res.get("items", []):
            click.echo(f" [{it['index']}] {it['size']}pt {it['font']} :: {it['contents'][:60]}")


@cli.command("text-set")
@click.option("--size", type=float, default=None, help="Set font size (pt) on all text frames")
@click.option("--font", default=None, help="Set font PostScript name, e.g. ArialMT")
@click.pass_context
def text_set(ctx: click.Context, size: float | None, font: str | None) -> None:
    """Batch-set font size / font on every text frame of the ACTIVE document (no save)."""
    if size is None and font is None:
        click.echo("error: pass --size and/or --font")
        sys.exit(2)
    res = _guard(be.run_jsx, be.jsx_text_set(size, font), timeout=ctx.obj["timeout"])
    _emit(res, ctx.obj["json"])


@cli.command()
@click.argument("output_path", type=click.Path())
@click.option("-f", "--format", "fmt", type=click.Choice(["pdf", "svg", "png"]), default="pdf")
@click.option("--bg", type=click.Choice(["transparent", "white"]), default="transparent",
              show_default=True, help="PNG background (white = flatten onto white)")
@click.pass_context
def export(ctx: click.Context, output_path: str, fmt: str, bg: str) -> None:
    """Export the active document to PDF / SVG / PNG."""
    res = _guard(be.run_jsx, be.jsx_export(output_path, fmt, bg), timeout=ctx.obj["timeout"])
    _emit(res, ctx.obj["json"])


@cli.command()
@click.option("--text", default="MemOmics CLI probe", show_default=True)
@click.option("--size", type=float, default=12.0, show_default=True)
@click.pass_context
def probe(ctx: click.Context, text: str, size: float) -> None:
    """Sanity check: isolated new doc -> rect+text -> PNG export -> close unsaved."""
    res = _guard(be.run_jsx, be.jsx_probe_text(text, size), timeout=ctx.obj["timeout"])
    _emit(res, ctx.obj["json"])


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check whether the Illustrator COM bridge is reachable."""
    try:
        cs = be.find_cscript()
    except Exception as exc:  # noqa: BLE001
        _emit({"bridge": False, "reason": str(exc)}, ctx.obj["json"])
        sys.exit(2)
    ok = _guard(be.run_jsx, be.JSX_INFO, timeout=ctx.obj["timeout"])
    _emit({"bridge": True, "cscript": cs, "illustrator": ok}, ctx.obj["json"])


@cli.command("gradient-probe")
@click.pass_context
def gradient_probe(ctx: click.Context) -> None:
    """Test the gradient workaround: reuse an existing gradient swatch (isolated doc)."""
    res = _guard(be.run_jsx, be.jsx_gradient_probe(), timeout=ctx.obj["timeout"])
    _emit(res, ctx.obj["json"])


@cli.command("new-doc")
@click.option("--width", type=float, default=800, show_default=True)
@click.option("--height", type=float, default=600, show_default=True)
@click.pass_context
def new_doc(ctx: click.Context, width: float, height: float) -> None:
    """Create a NEW untitled document (left open for iterate/export; never saved)."""
    res = _guard(be.run_jsx, be.jsx_new_doc(width, height), timeout=ctx.obj["timeout"])
    _emit(res, ctx.obj["json"])


@cli.command("rect")
@click.option("--x", type=float, default=60, show_default=True, help="px from artboard LEFT")
@click.option("--y", type=float, default=60, show_default=True, help="px from artboard TOP")
@click.option("--w", type=float, default=280, show_default=True)
@click.option("--h", type=float, default=160, show_default=True)
@click.option("--color", default="#e04040", show_default=True, help="#RRGGBB fill")
@click.pass_context
def rect(ctx: click.Context, x: float, y: float, w: float, h: float, color: str) -> None:
    """Draw a rectangle on the ACTIVE document (x/y = left/top; no save)."""
    res = _guard(lambda: be.run_jsx(be.jsx_rect(x, y, w, h, color), timeout=ctx.obj["timeout"]))
    _emit(res, ctx.obj["json"])


@cli.command("text-add")
@click.option("--content", required=True, help="Text contents")
@click.option("--x", type=float, default=60, show_default=True, help="px from artboard LEFT")
@click.option("--y", type=float, default=60, show_default=True, help="px from artboard TOP")
@click.option("--size", type=float, default=24.0, show_default=True)
@click.option("--color", default="#111111", show_default=True, help="#RRGGBB")
@click.option("--font", default=None, help="PostScript name, e.g. ArialMT")
@click.pass_context
def text_add(ctx: click.Context, content: str, x: float, y: float, size: float,
             color: str, font: str) -> None:
    """Add a text frame to the ACTIVE document (nowhere saved)."""
    res = _guard(lambda: be.run_jsx(be.jsx_text_add(content, x, y, size, color, font),
                                    timeout=ctx.obj["timeout"]))
    _emit(res, ctx.obj["json"])


@cli.command("recolor")
@click.option("--color", required=True, help="#RRGGBB")
@click.option("--index", type=int, default=-1, show_default=True, help="-1 = all items")
@click.option("--target", type=click.Choice(["path", "text"]), default="path", show_default=True)
@click.pass_context
def recolor(ctx: click.Context, color: str, index: int, target: str) -> None:
    """Recolor rectangles (path) or text frames of the ACTIVE document (no save)."""
    res = _guard(lambda: be.run_jsx(be.jsx_recolor(color, index, target), timeout=ctx.obj["timeout"]))
    _emit(res, ctx.obj["json"])


@cli.command("move")
@click.option("--index", type=int, required=True)
@click.option("--dx", type=float, default=0.0, show_default=True, help="positive = right")
@click.option("--dy", type=float, default=0.0, show_default=True, help="positive = DOWN")
@click.option("--target", type=click.Choice(["path", "text"]), default="path", show_default=True)
@click.pass_context
def move(ctx: click.Context, index: int, dx: float, dy: float, target: str) -> None:
    """Move one rectangle / text frame of the ACTIVE document (no save)."""
    res = _guard(be.run_jsx, be.jsx_move(index, dx, dy, target), timeout=ctx.obj["timeout"])
    _emit(res, ctx.obj["json"])


@cli.command("items")
@click.pass_context
def items(ctx: click.Context) -> None:
    """List rectangles + text frames of the ACTIVE document (bounds/fill/size)."""
    res = _guard(be.run_jsx, be.JSX_ITEMS, timeout=ctx.obj["timeout"])
    if ctx.obj["json"]:
        _emit(res, True)
    else:
        click.echo(f"active_doc: {res.get('doc')}  pathitems: {res.get('pathitems_count')}  textframes: {res.get('textframes_count')}")
        for it in res.get("pathitems", []):
            click.echo(f" [rect {it['index']}] fill={it['fill']} bounds={it['bounds']}")
        for it in res.get("textframes", []):
            click.echo(f" [text {it['index']}] {it['size']}pt fill={it['fill']} :: {str(it.get('contents',''))[:50]}")


@cli.command("close-untitled")
@click.option("--dry-run", is_flag=True, help="Report only, close nothing")
@click.pass_context
def close_untitled(ctx: click.Context, dry_run: bool) -> None:
    """Close UNSAVED 未标题-* documents the harness created (always without saving)."""
    res = _guard(be.run_jsx, be.jsx_close_untitled(dry_run), timeout=ctx.obj["timeout"])
    _emit(res, ctx.obj["json"])


@cli.command()
@click.pass_context
def repl(ctx: click.Context) -> None:
    """Interactive REPL (default when no subcommand given)."""
    click.echo("cli-anything-illustrator REPL — ':q' to quit, ':h' for this list")
    while True:
        try:
            raw = click.prompt("ai", prompt_suffix="> ", default="", show_default=False)
        except (EOFError, click.Abort):
            click.echo()
            return
        raw = (raw or "").strip()
        if not raw:
            continue
        if raw in (":q", "quit", "exit"):
            return
        if raw in (":h", "help"):
            click.echo(" :q | :h | :info | :artboards | :textlist | :set <pt> | :probe")
            continue
        try:
            if raw == ":info":
                _emit(be.run_jsx(be.JSX_INFO, timeout=ctx.obj["timeout"]), ctx.obj["json"])
            elif raw == ":artboards":
                _emit(be.run_jsx(be.JSX_ARTBOARDS, timeout=ctx.obj["timeout"]), ctx.obj["json"])
            elif raw == ":textlist":
                _emit(be.run_jsx(be.JSX_TEXT_LIST, timeout=ctx.obj["timeout"]), ctx.obj["json"])
            elif raw.startswith(":set "):
                size = float(raw.split()[1])
                _emit(be.run_jsx(be.jsx_text_set(size=size), timeout=ctx.obj["timeout"]), ctx.obj["json"])
            elif raw == ":probe":
                _emit(be.run_jsx(be.jsx_probe_text(), timeout=ctx.obj["timeout"]), ctx.obj["json"])
            else:
                click.echo("? unknown command, ':h' for help")
        except Exception as exc:  # noqa: BLE001
            click.echo(f"! {exc}")