"""渲染 img2vec 界面设计稿（静态 PNG，只用来定风格，不参与打包）。

用法：python design/mockup.py
输出：design/style-a-light.png、design/style-b-dark.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import numpy as np

S = 2  # 渲染倍数
UI_SCALE = 1.08  # 全局字号放大系数（一眼看去偏小，统一放 8%）
W, H = 1120, 800  # 逻辑尺寸

FONT_DIR = Path(r"C:\Windows\Fonts")
REG = FONT_DIR / "msyh.ttc"
BOLD = FONT_DIR / "msyhbd.ttc"

_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(kind: str, size: float) -> ImageFont.FreeTypeFont:
    key = (kind, int(size * S * UI_SCALE))
    if key not in _cache:
        path = BOLD if kind == "bold" else REG
        _cache[key] = ImageFont.truetype(str(path), int(size * S * UI_SCALE), index=0)
    return _cache[key]


def hex2rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def rgb2hex(r) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v))) for v in r)


def blend(c1: str, c2: str, t: float) -> str:
    a, b = hex2rgb(c1), hex2rgb(c2)
    return rgb2hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


class Sheet:
    def __init__(self, theme: dict):
        self.t = theme
        self.viol: list[str] = []
        self.img = Image.new("RGB", (W * S, H * S), hex2rgb(theme["bg"]))
        self.d = ImageDraw.Draw(self.img)

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, w=1, r=0):
        box = [x0 * S, y0 * S, x1 * S, y1 * S]
        if r:
            self.d.rounded_rectangle(
                box, radius=r * S, fill=hex2rgb(fill) if fill else None,
                outline=hex2rgb(outline) if outline else None, width=max(1, int(w * S)),
            )
        else:
            self.d.rectangle(
                box, fill=hex2rgb(fill) if fill else None,
                outline=hex2rgb(outline) if outline else None, width=max(1, int(w * S)),
            )

    def text(self, x, y, s, kind="regular", size=12, color="#000", anchor="lm",
             max_x: float | None = None):
        f = font(kind, size)
        if max_x is not None and anchor == "lm":
            right = x + self.d.textlength(s, font=f) / S
            if right > max_x:
                self.viol.append(f"文字溢出 [{s[:16]}…] 右边 {right:.0f} > 限 {max_x:.0f}")
        self.d.text((x * S, y * S), s, font=f, fill=hex2rgb(color), anchor=anchor)

    def hline(self, x0, x1, y, color):
        self.d.line([x0 * S, y * S, x1 * S, y * S], fill=hex2rgb(color), width=S)

    def button(self, x0, y0, x1, y1, label, kind="secondary", size=12):
        t = self.t
        if kind == "primary":
            self.rect(x0, y0, x1, y1, fill=t["accent"], r=7)
            self.text((x0 + x1) / 2, (y0 + y1) / 2, label, "bold", size, t["on_accent"], "mm")
        elif kind == "ghost":
            self.text((x0 + x1) / 2, (y0 + y1) / 2, label, "regular", size, t["sub"], "mm")
        else:
            self.rect(x0, y0, x1, y1, fill=t["btn"], outline=t["border"], r=7)
            self.text((x0 + x1) / 2, (y0 + y1) / 2, label, "regular", size, t["text"], "mm")

    def combo(self, x0, y0, x1, y1, label, dim=False):
        t = self.t
        fill = t["field"] if not dim else blend(t["field"], t["card"], 0.55)
        fg = t["text"] if not dim else blend(t["text"], t["card"], 0.6)
        self.rect(x0, y0, x1, y1, fill=fill, outline=t["border"], r=6)
        self.text(x0 + 10, (y0 + y1) / 2, label, "regular", 11.5, fg)
        cx, cy = x1 - 14, (y0 + y1) / 2 - 1.5
        chev = blend(t["sub"], t["card"], 0.3)
        self.d.line([(cx - 4) * S, cy * S, cx * S, (cy + 4) * S], fill=hex2rgb(chev), width=S)
        self.d.line([cx * S, (cy + 4) * S, (cx + 4) * S, cy * S], fill=hex2rgb(chev), width=S)

    def check(self, x, y, label, on=True):
        t = self.t
        self.rect(x, y - 8, x + 15, y + 7, fill=t["field"], outline=t["border"], r=4)
        if on:
            self.d.line([(x + 3.5) * S, y * S, (x + 6.5) * S, (y + 3.5) * S],
                        fill=hex2rgb(t["accent"]), width=int(1.8 * S))
            self.d.line([(x + 6.5) * S, (y + 3.5) * S, (x + 11.5) * S, (y - 3.5) * S],
                        fill=hex2rgb(t["accent"]), width=int(1.8 * S))
        self.text(x + 23, y, label, "regular", 12, t["text"])

    def card(self, x0, y0, x1, y1, title=None):
        t = self.t
        self.rect(x0, y0, x1, y1, fill=t["card"], outline=t["border"], r=10)
        if title:
            self.text(x0 + 18, y0 + 20, title, "bold", 13, t["text"])

    def vscroll(self, x, y0, y1, frac=0.9):
        """竖向滚动条（贴右内壁）。rows 画到卡片边缘会盖掉边框，这里叠在上面。"""
        t = self.t
        self.rect(x, y0, x + 7, y1, fill=t["head"], r=3)
        self.rect(x, y0 + 2, x + 7, y0 + 2 + (y1 - y0 - 4) * frac, fill=t["thumb"], r=3)

    def sep(self, x0, x1, y):
        """行分隔细线（比卡片边框浅一档）。"""
        self.d.line([x0 * S, y * S, x1 * S, y * S],
                    fill=hex2rgb(blend(self.t["border"], self.t["card"], 0.45)), width=S)


THEMES = {
    "light": {
        "bg": "#F4F6F9", "card": "#FFFFFF", "border": "#DDE3EC", "field": "#FFFFFF",
        "btn": "#F7F9FC", "text": "#1E2329", "sub": "#66707F",
        "accent": "#2F6FEB", "on_accent": "#FFFFFF", "track": "#E9EDF3",
        "head": "#EDF1F7", "rowalt": "#F4F7FB", "thumb": "#C3CBD8",
        "A_fg": "#E9F6EE", "B_fg": "#FFF6E7", "C_fg": "#FDEDEF",
        "A_tx": "#177245", "B_tx": "#8F5400", "C_tx": "#B3122B",
    },
    "dark": {
        "bg": "#15171C", "card": "#1E2128", "border": "#333A45", "field": "#232730",
        "btn": "#262B34", "text": "#E7EAF0", "sub": "#9AA5B6",
        "accent": "#4F8DF7", "on_accent": "#FFFFFF", "track": "#2A2F39",
        "head": "#262B34", "rowalt": "#20242B", "thumb": "#3D4552",
        "A_fg": "#1C2E24", "B_fg": "#2A2317", "C_fg": "#2C1A1F",
        "A_tx": "#5AD68C", "B_tx": "#F0B45A", "C_tx": "#FF8095",
    },
}


def draw(theme_key: str, out: Path) -> list[str]:
    t = THEMES[theme_key]
    s = Sheet(t)
    log: list[str] = []

    # 顶部标题栏
    s.text(26, 30, "img2vec", "bold", 21, t["text"])
    wid = s.d.textlength("img2vec", font=font("bold", 21)) / S
    s.rect(26 + wid + 10, 20, 26 + wid + 62, 40,
           fill=blend(t["accent"], t["card"], 0.88), r=10)
    s.text(26 + wid + 36, 30, "v1.0", "regular", 10.5, t["accent"], "mm")
    s.text(26 + wid + 74, 31, "位图转矢量 · SVG / PDF", "regular", 12, t["sub"], max_x=950)
    s.button(974, 17, 1088, 45, "使用说明", "secondary", 11.5)
    log.append(f"header ok, title {wid:.0f}px")

    # 输出目录卡
    s.card(16, 62, 1104, 128)
    s.text(34, 95, "输出目录", "regular", 12, t["sub"])
    s.rect(104, 81, 908, 109, fill=t["field"], outline=t["border"], r=6)
    s.text(114, 95, r"C:\Users\你\Pictures\img2vec", "regular", 11.5, t["text"], max_x=898)
    s.button(918, 81, 1000, 109, "浏览…", "secondary", 11.5)
    s.button(1010, 81, 1086, 109, "打开目录", "secondary", 11)
    log.append("output card ok (62..128)")

    # 左卡：文件列表
    s.card(16, 140, 736, 500)
    s.button(34, 152, 130, 182, "添加图片…", "secondary", 11.5)
    s.button(136, 152, 224, 182, "移除所选", "secondary", 11.5)
    s.button(230, 152, 292, 182, "清空", "secondary", 11.5)
    s.text(718, 167, "8 个文件", "regular", 11, t["sub"], "rm")

    s.rect(17, 190, 735, 218, fill=t["head"])
    s.hline(17, 735, 218, t["border"])
    s.text(34, 204, "文件名", "regular", 11, t["sub"])
    s.text(380, 204, "所在目录", "regular", 11, t["sub"])

    files = [
        ("s4_tech_drawing.png", r"D:\research\input\corpus"),
        ("s1_bw_logo.png", r"D:\research\input\corpus"),
        ("s2_flat_icon.png", r"D:\research\input\corpus"),
        ("s6_text.png", r"D:\research\input\corpus"),
        ("s10_gradient.png", r"D:\research\input\corpus"),
        ("s5_chart.png", r"D:\research\input\corpus"),
        ("r4_pasted_png.png", r"D:\Users\你\Pictures\screenshots"),
        ("s9_alpha_png.png", r"D:\Users\你\Pictures\screenshots"),
    ]
    y = 218
    for i, (name, d) in enumerate(files):
        if i % 2 == 1:
            s.rect(17, y, 735, y + 33, fill=t["rowalt"])
        s.text(34, y + 17, name, "regular", 12, t["text"], max_x=370)
        s.text(380, y + 17, d, "regular", 11, t["sub"], max_x=716)
        y += 33
    s.hline(17, 735, y, t["border"])
    s.vscroll(725, 220, 481, frac=0.92)
    log.append(f"file list ok, bottom {y} < 500（{len(files)} 行）")

    # 右卡：设置
    s.card(752, 140, 1104, 500, "转换设置")
    s.hline(770, 1086, 172, t["border"])
    rows = [
        ("路线", "自动", False),
        ("二值化", "自动阈值 (Otsu)", False),
        ("Sauvola 窗口", "51", True),
        ("线条类细节", "标准", False),
        ("彩色类风格", "标准", False),
    ]
    ry = 184
    for label, val, dim in rows:
        s.text(770, ry + 14, label, "regular", 11.5,
               t["sub"] if not dim else blend(t["sub"], t["card"], 0.55), max_x=876)
        s.combo(880, ry, 1086, ry + 28, val, dim)
        ry += 36
    s.check(770, 384, "反色（白画黑底）", on=False)
    s.check(770, 410, "转换后做质量检查", on=True)
    s.text(770, 438, "文字类截图只能得到轮廓，", "regular", 11, t["sub"], max_x=1086)
    s.text(770, 458, "不能选中 / 搜索文字。", "regular", 11, t["sub"], max_x=1086)
    s.text(770, 482, "恢复默认设置", "regular", 11, t["accent"], max_x=1086)
    log.append(f"settings ok, rows end {ry - 36 + 28}, link 482, bottom margin 18")
    log.append(f"文字溢出检查: {len(s.viol)} 处")
    log.extend("  ! " + v for v in s.viol)

    # 动作行
    s.button(16, 512, 132, 548, "开始转换", "primary", 13)
    s.button(142, 512, 214, 548, "取消", "secondary", 11.5)
    s.rect(228, 525, 886, 535, fill=t["track"], r=5)
    s.rect(228, 525, 228 + 658 * 0.25, 535, fill=t["accent"], r=5)
    s.text(1104, 530, "3 / 12   s4_tech_drawing.png", "regular", 11.5, t["sub"], "rm")
    log.append("action row ok (512..548)")

    # 结果表
    s.card(16, 560, 1104, 784)
    cols = [("文件", 34), ("路线", 330), ("等级", 412), ("SSIM", 470),
            ("体积比", 552), ("说明", 630)]
    s.rect(17, 572, 1103, 600, fill=t["head"])
    s.hline(17, 1103, 600, t["border"])
    for name, x in cols:
        s.text(x, 586, name, "regular", 11, t["sub"])

    res = [
        ("s4_tech_drawing.png", "单色", "A", "0.9935", "0.78×", "接近原图", "A"),
        ("s1_bw_logo.png", "单色", "A", "0.9958", "0.19×", "接近原图", "A"),
        ("s2_flat_icon.png", "彩色", "A", "0.9965", "0.05×", "接近原图", "A"),
        ("s6_text.png", "彩色", "B", "0.9699", "4.75×", "文字已成轮廓，不能选中/搜索", "B"),
        ("s10_gradient.png", "彩色", "C", "0.9467", "—", "渐变出色带，不适合矢量化", "C"),
    ]
    y = 600
    for name, mode, g, ssim, ratio, note, tag in res:
        s.rect(17, y, 1103, y + 34, fill=t[f"{tag}_fg"])
        s.text(34, y + 17, name, "regular", 12, t["text"], max_x=322)
        s.text(330, y + 17, mode, "regular", 11.5, t["sub"])
        s.text(412, y + 17, g, "bold", 12.5, t[f"{tag}_tx"])
        s.text(470, y + 17, ssim, "regular", 11.5, t["text"])
        s.text(552, y + 17, ratio, "regular", 11.5, t["text"])
        s.text(630, y + 17, note, "regular", 11.5, t["sub"], max_x=1086)
        s.sep(17, 1103, y + 34)
        y += 34
    s.hline(17, 1103, y, t["border"])
    s.vscroll(1093, 602, 770, frac=0.95)
    log.append(f"results ok, bottom {y} < 784")

    out.parent.mkdir(parents=True, exist_ok=True)
    s.img.save(out)
    return log


def _glyph(ch: str) -> "np.ndarray":
    im = Image.new("L", (64, 64), 0)
    ImageDraw.Draw(im).text((4, 4), ch, font=font("regular", 24), fill=255)
    return np.asarray(im)


def probe(theme_key: str, path: Path) -> int:
    """在已知坐标取样，确认色块画在正确位置（我无法用眼睛验证时的替代手段）。"""
    t = THEMES[theme_key]
    img = Image.open(path).convert("RGB")
    bad = 0
    checks = [
        (600, 160, "left card bg", t["card"]),
        (300, 234, "list row even", t["card"]),
        (300, 267, "list row odd", t["rowalt"]),
        (22, 530, "primary btn", t["accent"]),
        (300, 530, "progress filled", t["accent"]),
        (500, 530, "progress track", t["track"]),
        (600, 617, "row grade A", t["A_fg"]),
        (600, 720, "row grade B", t["B_fg"]),
        (600, 750, "row grade C", t["C_fg"]),
        (924, 88, "browse btn", t["btn"]),
    ]
    for x, y, name, expect in checks:
        got = rgb2hex(img.getpixel((x * S, y * S)))
        ok = got.upper() == expect.upper()
        bad += 0 if ok else 1
        print(f"    {name:14s} ({x:4d},{y:3d}) expect {expect} got {got}  "
              f"{'OK' if ok else 'MISMATCH'}")
    return bad


def main() -> int:
    # 中文字形自检：必须有墨迹，且不同字必须画出不同位图（否则是字体回退成方块）
    a, b = _glyph("路"), _glyph("线")
    if a.sum() == 0 or np.array_equal(a, b):
        print("FAIL: 中文字形异常（字体回退），设计稿不可信")
        return 1
    print(f"font OK: {font('regular', 12).getname()[0]}，路/线 位图不同且在墨")

    base = Path(__file__).resolve().parent
    bad = 0
    for key, fname in (("light", "style-a-light.png"), ("dark", "style-b-dark.png")):
        out = base / fname
        for line in draw(key, out):
            print(f"  [{key}] {line}")
            if line.strip().startswith("!"):
                bad += 1
        img = Image.open(out)
        print(f"  [{key}] {fname}  {img.size[0]}x{img.size[1]}  "
              f"{out.stat().st_size // 1024} KB")
        bad += probe(key, out)
    print("RESULT:", "FAIL（见上方 ✗）" if bad else "OK 无溢出、色块位置正确")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
