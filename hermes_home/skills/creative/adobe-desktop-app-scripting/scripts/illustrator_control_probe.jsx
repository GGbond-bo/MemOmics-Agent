// Illustrator 全操控探针（30 秒体检 + 能力自证）
// 用法：改 OUTDIR → cscript //nologo run_jsx.vbs <本文件绝对路径>
// 安全：只读用户已打开的文档，绝不修改/关闭它们；开头清理上次残留的探测文档
#target illustrator

// ==== 只改这里 ====
var OUTDIR = "E:/MemOmics-Agent/results/<session>/figures/";
var PROBE_NAME = "memomics_full_probe";
// ==================

function main() {
    app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
    var out = [];

    // 0. 清理上轮残留（脚本中途抛错会把探测文档留在界面上）
    for (var q = app.documents.length - 1; q >= 0; q--) {
        if (app.documents[q].name.indexOf(PROBE_NAME) === 0) {
            app.documents[q].close(SaveOptions.DONOTSAVECHANGES);
            out.push("cleaned_leftover=1");
        }
    }

    // 1. 读控制：用户手上有什么（只读，不动）
    out.push("open_docs=" + app.documents.length);
    for (var i = 0; i < app.documents.length; i++) {
        var d = app.documents[i];
        out.push("  doc[" + i + "]=" + d.name + "|saved=" + d.saved
                 + "|artboards=" + d.artboards.length
                 + "|layers=" + d.layers.length
                 + "|pathItems=" + d.pathItems.length
                 + "|textFrames=" + d.textFrames.length
                 + "|groups=" + d.groupItems.length);
        for (var a = 0; a < d.artboards.length; a++) {
            out.push("    artboard[" + a + "] rect=" + d.artboards[a].artboardRect.join(","));
        }
    }

    // 2. 新建探测文档 + 3 画板
    var doc = app.documents.add(DocumentColorSpace.RGB, 200, 150);
    doc.name = PROBE_NAME;
    doc.artboards[0].name = "AB_1_keep";
    doc.artboards.add([210, 150, 410, 0]);
    doc.artboards[1].name = "AB_2_delete_me";
    doc.artboards.add([420, 150, 620, 0]);
    doc.artboards[2].name = "AB_3_keep";
    out.push("new_doc_artboards=" + doc.artboards.length);

    // 3. 图层
    var ly = doc.layers.add();
    ly.name = "MemOmics_DemoLayer";

    // 4. 图形（矩形/椭圆/多边形/贝塞尔）
    var c = new RGBColor(); c.red = 224; c.green = 122; c.blue = 95;
    var c2 = new RGBColor(); c2.red = 46; c2.green = 134; c2.blue = 171;
    var c3 = new RGBColor(); c3.red = 241; c3.green = 196; c3.blue = 15;
    var c4 = new RGBColor(); c4.red = 26; c4.green = 26; c4.blue = 26;

    var rect = ly.pathItems.rectangle(120, 30, 140, 60);
    rect.filled = true; rect.fillColor = c; rect.stroked = false;

    var ell = ly.pathItems.ellipse(120, 30, 90, 90);
    ell.filled = true; ell.fillColor = c2; ell.stroked = false;

    var star = ly.pathItems.polygon(120, 40, 40, 6);
    star.filled = true; star.fillColor = c3; star.stroked = false;

    var bez = ly.pathItems.add();
    bez.setEntirePath([[30, 300], [90, 340], [150, 300]]);
    bez.closed = false; bez.filled = false; bez.stroked = true;
    bez.strokeColor = c4; bez.strokeWidth = 2;

    // 5. 渐变：已知在部分版本上会报 Error 1200 → 包 try/catch，失败不影响其余动作
    var gradOk = false, gradMsg = "";
    var grect = ly.pathItems.rectangle(150, 420, 150, 70);
    grect.filled = true; grect.stroked = false;
    try {
        var g = doc.gradients.add();
        g.type = GradientType.LINEAR;
        g.gradientStops[0].color = c;
        g.gradientStops[1].color = c2;
        try { grect.fillColor = g; gradOk = true; gradMsg = "new_gradient"; }
        catch (e1) {
            try { grect.fillColor = doc.gradients[0]; gradOk = true; gradMsg = "default_gradient"; }
            catch (e2) { gradMsg = "assign_fail:" + e1.message; }
        }
    } catch (e0) { gradMsg = "create_fail:" + e0.message; }
    out.push("gradient_ok=" + gradOk + " (" + gradMsg + ")");

    // 6. 文字
    var tf = ly.textFrames.add();
    tf.contents = "MemOmics to Illustrator full control\nread / write / artboard / export / save";
    tf.position = [30, 150];
    tf.textRange.characterAttributes.size = 12;

    // 7. 分组
    var grp = ly.groupItems.add();
    grp.name = "DemoGroup";
    ell.move(grp, ElementPlacement.INSIDE);
    star.move(grp, ElementPlacement.INSIDE);
    out.push("group_children=" + grp.pageItems.length);

    out.push("new_doc_layers=" + doc.layers.length
             + " pathItems=" + doc.pathItems.length
             + " textFrames=" + doc.textFrames.length
             + " groups=" + doc.groupItems.length);

    // 8. 删画板（用户最常要的那一击）
    doc.artboards[1].remove();
    out.push("after_remove_artboards=" + doc.artboards.length);

    // 9. 导出 PNG / SVG
    var fpng = new File(OUTDIR + "ai_control_full.png");
    var opts = new ExportOptionsPNG24();
    opts.antiAliasing = true; opts.transparency = false; opts.artBoardClipping = false;
    doc.exportFile(fpng, ExportType.PNG24, opts);
    out.push("png_bytes=" + (fpng.exists ? fpng.length : 0));

    var fsvg = new File(OUTDIR + "ai_control_full.svg");
    doc.exportFile(fsvg, ExportType.SVG, new ExportOptionsSVG());
    out.push("svg_bytes=" + (fsvg.exists ? fsvg.length : 0));

    // 10. 存盘 .ai
    var fai = new File(OUTDIR + "ai_control_full.ai");
    var sao = new IllustratorSaveOptions();
    sao.pdfCompatible = true;
    doc.saveAs(fai, sao);
    out.push("ai_bytes=" + (fai.exists ? fai.length : 0));

    // 11. 收尾：关掉探测文档 + 证明用户文档安然无恙
    doc.close(SaveOptions.DONOTSAVECHANGES);
    out.push("docs_after_close=" + app.documents.length);
    var names = [];
    for (var k = 0; k < app.documents.length; k++) {
        names.push(app.documents[k].name + "(saved=" + app.documents[k].saved + ")");
    }
    out.push("remaining_open=" + names.join(" | "));

    return "OK|" + out.join("; ");
}

main();