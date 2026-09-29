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
BG_IDS = ["palace-day", "palace-night", "maid-duo", "maid-left", "maid-right", "chibi"]


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
