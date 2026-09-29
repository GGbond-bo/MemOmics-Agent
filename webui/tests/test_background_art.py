"""背景图（皮肤插画）回归：素材、接线、白名单、许可署名。

只做 HTML/CSS/JS 文本断言（前端测试一贯风格），不执行浏览器。
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(ROOT, "index.html")
BG_DIR = os.path.join(ROOT, "assets", "backgrounds")
NOTICE_PATH = os.path.join(BG_DIR, "NOTICE.txt")

ASSETS = ["palace-day.webp", "palace-night.webp", "maid-left.webp",
          "maid-right.webp", "chibi.webp"]
# BACKGROUNDS 里除 none 之外的全部 id
BG_IDS = ["palace", "maid", "chibi"]


@pytest.fixture(scope="module")
def html():
    with open(HTML_PATH, encoding="utf-8") as f:
        return f.read()


# --- 素材本身 ---

@pytest.mark.parametrize("name", ASSETS)
def test_background_asset_is_local_real_webp(name):
    """每个素材必须真实存在、是 WebP 魔数、且有实际体积（不是占位空文件）。"""
    p = os.path.join(BG_DIR, name)
    assert os.path.isfile(p), f"素材缺失: {name}"
    raw = open(p, "rb").read()
    assert raw[:4] == b"RIFF" and raw[8:12] == b"WEBP", f"{name} 不是 WebP"
    assert len(raw) > 20 * 1024, f"{name} 体积异常（{len(raw)} B），疑似占位文件"


def test_background_assets_total_size_bounded():
    """背景目录总积压不能失控（打包体积敏感）。"""
    total = sum(os.path.getsize(os.path.join(BG_DIR, n)) for n in ASSETS)
    assert total < 1500 * 1024, f"背景素材合计 {total/1024/1024:.2f} MB，超出预期"


# --- 接线 ---

def test_background_options_wired_in_settings(html):
    """设置页要有「背景图」分组，容器 id 与 JS 里找的 id 必须一致。"""
    assert 'id="bg-options"' in html
    assert "<label>背景图</label>" in html
    assert "document.getElementById('bg-options')" in html
    assert "renderBackgroundOptions();" in html, "开机没渲染背景按钮"


def test_background_list_ids_have_css_rules(html):
    """BACKGROUNDS 里每个 id 都要有对应的 CSS 规则（防 JS 加项、CSS 漏写）。"""
    for bid in BG_IDS:
        assert f'html[data-bg="{bid}"]' in html, f"{bid} 没有 CSS 规则"


def test_background_layer_is_behind_content(html):
    """背景层必须放在内容之下且不挡鼠标。"""
    m = re.search(r"#bg-art \{[^}]*\}", html)
    assert m, "找不到 #bg-art 样式"
    rule = m.group(0)
    assert "z-index:-1" in rule.replace(" ", "")
    assert "pointer-events:none" in rule.replace(" ", "")
    assert "position:fixed" in rule.replace(" ", "")


def test_background_none_is_default_and_has_no_image(html):
    """边界：默认必须是 none，且 none 不得挂任何图片层。"""
    assert "{id:'none'" in html, "BACKGROUNDS 缺少 none 项"
    assert "localStorage.getItem('memomics-bg')" in html, "没有持久化恢复"
    # none 的 CSS 里不能出现 data-bg="none" 的图片规则
    assert 'html[data-bg="none"] #bg-art' not in html


def test_background_unknown_id_falls_back(html):
    """边界：未知 id 必须回退 none（白名单校验），不能把属性写成任意值。"""
    body = html.split("function setBackground(id)")[1].split("\n}")[0]
    assert "BACKGROUNDS.some" in body, "setBackground 没有白名单校验"
    assert "id = 'none'" in body, "setBackground 未回退到 none"


def test_background_layer_tracks_chat_area(html):
    """背景层要跟着「中间交互区」走：实测矩形 + ResizeObserver + 开机初始化。"""
    assert "function syncBgArtBox()" in html
    assert "function initBgArtBox()" in html
    assert "initBgArtBox();" in html, "开机没初始化背景层几何"
    body = html.split("function initBgArtBox()")[1].split("\n}")[0]
    assert ".chat-area" in body, "没有观测中间交互区"
    assert "ResizeObserver" in body, "没有用 ResizeObserver，拖右栏不会跟随"
    assert "window.addEventListener('resize'" in body
    sb = html.split("function setBackground(id)")[1].split("\n}")[0]
    assert "syncBgArtBox()" in sb, "切换背景后没立刻贴合"


def test_background_box_falls_back_when_area_unmeasurable(html):
    """边界：交互区量不到尺寸时必须退回整屏，不能留 0 尺寸空窗。"""
    body = html.split("function syncBgArtBox()")[1].split("\n}")[0]
    assert "r.width < 1 || r.height < 1" in body, "缺少 0 尺寸兜底"
    assert "100vw" in body and "100vh" in body, "兜底没有退回整屏"


def test_background_character_size_is_not_viewport_relative(html):
    """人物尺寸不能绑视口单位 —— 用 vh 就等于又绑回视口，等于没适配。"""
    seg = html.split("=== 背景图（皮肤插画")[1].split("</style>")[0]
    # 只盯 background-size：整屏兜底用 100vh 是合理的，不该一起禁掉
    assert not re.search(r"background-size:[^;}]*vh", seg), \
        "background-size 还在用视口单位，人物不随交互区缩放"
    # 尺寸由 JS 按交互区算好写进 CSS 变量，兜底值也是区域内百分比
    assert "var(--bg-char-size-l," in seg and "var(--bg-char-size-r," in seg
    assert "auto 78%" in seg and "auto 62%" in seg


def test_background_palace_follows_theme_darkness(html):
    """宫殿不再拆成晨/夜两个选项：亮主题用晨景，深色主题自动换夜景。"""
    assert 'html[data-bg="palace"] #bg-art' in html
    assert 'html[data-bg="palace-day"]' not in html, "旧的「宫殿·晨」选项残留"
    assert 'html[data-bg="palace-night"]' not in html, "旧的「宫殿·夜」选项残留"
    for bg in ("palace", "maid", "chibi"):
        assert f'html[data-theme="dark"][data-bg="{bg}"] #bg-art' in html, \
            f"{bg} 在深色主题下没有切到夜景"
    assert "palace-night.webp" in html


def test_background_left_right_merged_into_one(html):
    """左右两个角色要合成一个选项，不能再有单独的「左」「右」。"""
    assert 'html[data-bg="maid-left"]' not in html
    assert 'html[data-bg="maid-right"]' not in html
    seg = html.split('html[data-bg="maid"] #bg-art::before {')[1].split("}")[0]
    assert "maid-left.webp" in seg and "maid-right.webp" in seg, \
        "合成选项里没同时带上左右两位角色"


def test_background_content_column_narrows_for_characters(html):
    """带角色的背景要把中间内容列收窄 —— 消息列和输入框那三行都要收，否则底部输入框仍压住角色。"""
    for bg in ("maid", "chibi"):
        for sel in (".chat-messages", ".chat-input .input-row",
                    ".chat-input .input-info", ".chat-input .input-grip",
                    ".chat-skill-bar", ".sk3-slash"):
            assert f'html[data-bg="{bg}"] {sel}' in html, f"{bg} 没给 {sel} 收窄"
    assert "max-width:var(--bg-content-w, 90%)" in html
    # 纯宫殿背景不该收窄内容
    assert 'html[data-bg="palace"] .chat-messages' not in html


def test_background_input_box_is_balanced(html):
    """输入框本身要居中：行内右侧按钮组比左侧上传按钮宽，必须补左外边距才不偏左。"""
    for bg in ("maid", "chibi"):
        assert f'html[data-bg="{bg}"] .img-upload-btn' in html, f"{bg} 没给上传按钮补平衡边距"
        assert f'html[data-bg="{bg}"] .chat-input button' in html, f"{bg} 没收紧按钮"
    assert "margin-left:var(--bg-input-balance, 0px)" in html
    body = html.split("function syncBgArtBox()")[1].split("\n}")[0]
    assert "--bg-input-balance" in body, "没有人算平衡量"
    assert "- 200" in body, "平衡时没有保住输入框最小宽度（会把它压瘪）"
    assert "Math.min(need, room)" in body, "没有取「需要的量」和「放得下的量」的较小值"


def test_background_input_balance_untouched_without_characters(html):
    """边界：纯宫殿 / 无背景时绝不能动输入框布局 —— 默认 UI 必须原样。"""
    for bg in ("palace", "none"):
        assert f'html[data-bg="{bg}"] .img-upload-btn' not in html, f"{bg} 不该补平衡边距"
        assert f'html[data-bg="{bg}"] .chat-input button' not in html, f"{bg} 不该收紧按钮"
    body = html.split("function syncBgArtBox()")[1].split("\n}")[0]
    assert "root.style.removeProperty('--bg-input-balance')" in body, \
        "退出角色背景时没把平衡边距清掉"


def test_background_char_fit_guards_narrow_area(html):
    """边界：交互区太窄时必须反过来压人物，不能把内容列压成负数或窄到不可用。"""
    assert "_BG_ART_CHARS" in html, "缺少角色宽高比配置"
    body = html.split("function _bgArtFitChars(W, H, bg)")[1].split("\n}")[0]
    assert "content < 380" in body, "缺少内容列最小宽度兜底"
    assert "Math.max(0.2" in body, "人物压缩没有下限"
    assert "H * 0.86" in body, "人物高度没有封顶"


def test_background_assets_all_local(html):
    """URL 必须是站内相对路径 —— 不能引入外部图床（离线可用 + 无外链风险）。"""
    section = html.split("=== 背景图（皮肤插画")[1].split("// === 文件浏览")[0]
    urls = set(re.findall(r'url\("([^"]+)"\)', section))
    assert urls, "背景段里没找到任何 url()"
    for u in urls:
        assert u.startswith("/assets/backgrounds/"), f"非站内路径: {u}"


# --- 许可（CC BY-NC-SA 4.0 的署名是硬要求，测试兜住） ---

def test_background_license_notice_keeps_full_attribution_chain():
    """NOTICE 必须保住完整创作链署名与三个上游链接，少一个都算违反 BY 条款。"""
    txt = open(NOTICE_PATH, encoding="utf-8").read()
    for who in ("上善", "zipzip", "Small-tailqwq"):
        assert who in txt, f"署名链缺 {who}"
    for url in ("pixiv.net/users/62155430", "pixiv.net/users/18604994",
                "github.com/dsh-external/dsh-deep-whale"):
        assert url in txt, f"署名链缺链接 {url}"


def test_background_license_notice_states_noncommercial():
    """NC 条款必须写在 NOTICE 里 —— 这是「不能商业使用」的唯一提示点。"""
    txt = open(NOTICE_PATH, encoding="utf-8").read()
    assert "CC BY-NC-SA 4.0" in txt
    assert "禁止任何商业性使用" in txt


def test_background_settings_shows_license_hint(html):
    """设置页也要有一句许可提示，用户选背景时看得见。"""
    seg = html.split("<label>背景图</label>")[1].split("<label>")[0]
    assert "CC BY-NC-SA 4.0" in seg
    assert "NOTICE.txt" in seg
