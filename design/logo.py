"""萤火虫 logo：书法字形 + 薄荷→青绿渐变 + 高光边 + 深色投影 + 柔光。

参考图的四点特征：
  1. 书法笔触（用楷体 KaiTi，起收笔有锋）
  2. 上浅下深的薄荷绿→青绿渐变
  3. 笔画上缘的浅色高光
  4. 深色偏移投影（原图是深蓝，这里改深青以配浅绿界面）

用法：python design/logo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 3  # 超采样倍数
TEXT = "萤火虫"
BRUSH = Path(r"C:\Windows\Fonts\simkai.ttf")        # 楷体，书法感
SANS = Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf")  # 小尺寸用无衬线
PAD = 110

G = {
    # 深底渐变：上→下
    "top": "#EAFBF0", "mid": "#8FEEDC", "bot": "#35BFBF",
    # 浅底渐变：整体压深，否则上半段与浅绿背景融为一体（实测仅 1.01:1）
    "top_l": "#26806C", "mid_l": "#1A7362", "bot_l": "#0E5F52",
    # 高光边
    "rim": "#FFFFFF",
    # 投影
    "shadow": "#134F5C",
    # 外发光
    "glow": "#7FE3C8",
    # 金色点缀
    "gold": "#FFC96B", "gold_deep": "#D99A2B",
    # 界面用深绿（浅绿底上要够深）
    "ui_core": "#0E5F52",
}


def hex2rgb(c: str):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def font(path: Path, size: float, weight: int | None = None):
    f = ImageFont.truetype(str(path), int(size * S))
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except OSError:
            pass
    return f


def layout(f, text: str, size: float, tracking: float):
    """返回 (每个字的 (x偏移, 宽), 总宽, 总高)。"""
    widths = [f.getbbox(ch)[2] - f.getbbox(ch)[0] for ch in text]
    gap = int(size * tracking * S)
    total_w = sum(widths) + gap * (len(text) - 1)
    asc, desc = f.getmetrics()
    return widths, gap, total_w, asc + desc


def text_mask(text, size, tracking, f, W, H):
    widths, gap, total_w, _ = layout(f, text, size, tracking)
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    x = PAD * S
    for ch, w in zip(text, widths):
        d.text((x - f.getbbox(ch)[0], PAD * S), ch, font=f, fill=255)
        x += w + gap
    return m, widths, gap


def vgrad(w: int, h: int, y0: int, y1: int, keys=("top", "mid", "bot")) -> Image.Image:
    """竖向三段渐变（上→中→下），只覆盖 y0..y1 区间。"""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    c_top, c_mid, c_bot = (hex2rgb(G[keys[0]]), hex2rgb(G[keys[1]]),
                           hex2rgb(G[keys[2]]))
    span = max(1, y1 - y0)
    for y in range(h):
        t = (y - y0) / span
        if t <= 0.5:
            u = max(0.0, t) * 2
            c = tuple(c_top[i] + (c_mid[i] - c_top[i]) * u for i in range(3))
        else:
            u = min(1.0, (t - 0.5) * 2)
            c = tuple(c_mid[i] + (c_bot[i] - c_mid[i]) * u for i in range(3))
        d.line([0, y, w, y], fill=tuple(int(v) for v in c))
    return img


def radial(size: int, color: str, power: float = 2.0) -> Image.Image:
    yy, xx = np.mgrid[0:size, 0:size]
    c = (size - 1) / 2
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    a = np.clip(1.0 - d, 0, 1) ** power
    rgb = hex2rgb(color)
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = rgb
    arr[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def wordmark(size: float = 150.0, tracking: float = 0.10,
             bg: str = "#0E3A42", hero: bool = True, light: bool = False) -> Image.Image:
    """萤火虫 字标。bg 必须给具体底色（辉光和投影都要靠它成立）。

    light=True 用浅底专用深色渐变，否则上半段会和浅色背景融为一体。
    """
    f = font(BRUSH, size)
    widths, gap, total_w, total_h = layout(f, TEXT, size, tracking)
    W = total_w + PAD * 2 * S
    H = total_h + PAD * 2 * S

    mask, _, _ = text_mask(TEXT, size, tracking, f, W, H)
    bbox = mask.getbbox()
    if bbox is None:
        raise RuntimeError("空字形")

    img = Image.new("RGBA", (W, H), hex2rgb(bg) + (255,))

    if hero:
        # 1) 外发光（很淡，只做气氛）；浅底上不加，否则会脏
        if not light:
            b = mask.filter(ImageFilter.GaussianBlur(9 * S))
            g = Image.new("RGBA", (W, H), hex2rgb(G["glow"]) + (0,))
            g.putalpha(b.point(lambda v: int(v * 0.28)))
            img = Image.alpha_composite(img, g)

        # 2) 深色偏移投影（原图的深蓝块 → 这里深青）
        off = int(size * 0.035 * S)
        sh = Image.new("L", (W, H), 0)
        sh.paste(mask, (off, off))
        sh = sh.filter(ImageFilter.GaussianBlur(1.4 * S))
        sc = Image.new("RGBA", (W, H), hex2rgb(G["shadow"]) + (0,))
        sc.putalpha(sh.point(lambda v: int(v * (0.45 if light else 0.88))))
        img = Image.alpha_composite(img, sc)

    # 3) 渐变字身
    keys = ("top_l", "mid_l", "bot_l") if light else ("top", "mid", "bot")
    grad = vgrad(W, H, bbox[1], bbox[3], keys).convert("RGBA")
    grad.putalpha(mask)
    img = Image.alpha_composite(img, grad)

    if hero and not light:
        # 4) 上缘高光：mask 减去向下偏移的 mask，只留顶部那一条
        sh2 = Image.new("L", (W, H), 0)
        sh2.paste(mask, (0, int(size * 0.055 * S)))
        inn = np.asarray(mask, dtype=np.int16) - np.asarray(sh2, dtype=np.int16)
        rim = Image.fromarray(np.clip(inn, 0, 255).astype(np.uint8))
        # 只在字身上半部亮，下半部淡出
        fade = np.zeros((H, W), dtype=np.float32)
        top, bot = bbox[1], bbox[3]
        for y in range(top, min(bot, H)):
            fade[y, :] = max(0.0, 1.0 - (y - top) / max(1, (bot - top)) * 1.5)
        ra = (np.asarray(rim, dtype=np.float32) * fade / 255.0 * 235).astype(np.uint8)
        rc = Image.new("RGBA", (W, H), hex2rgb(G["rim"]) + (0,))
        rc.putalpha(Image.fromarray(ra))
        img = Image.alpha_composite(img, rc)

    out = img.crop(img.getbbox())
    return out.convert("RGB")


def with_dot(mark: Image.Image, bg: str, dot_frac: float = 0.055) -> Image.Image:
    """在字标右上方加一颗发光的萤火虫光点（金色）。"""
    pad = int(mark.height * 0.22)
    W = mark.width + pad * 2
    H = mark.height + pad * 2
    canvas = Image.new("RGBA", (W, H), hex2rgb(bg) + (255,))
    canvas.alpha_composite(mark.convert("RGBA"), (pad, pad))

    r = max(3, int(mark.height * dot_frac))
    cx = int(pad + mark.width * 0.90)
    cy = int(pad + mark.height * 0.12)
    big = r * 8
    canvas.alpha_composite(radial(big, G["gold"], 2.4), (cx - big // 2, cy - big // 2))
    d = ImageDraw.Draw(canvas)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=hex2rgb(G["gold"]))
    d.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2],
              fill=hex2rgb("#FFF6DF"))
    return canvas.convert("RGB")


def ui_small(size: float = 26.0, bg: str = "#F2F7F2") -> Image.Image:
    """标题栏用的小字标：楷体太细会糊，改用无衬线中粗 + 深绿实色。"""
    f = font(SANS, size, weight=620)
    widths, gap, total_w, total_h = layout(f, TEXT, size, 0.04)
    W = total_w + 8 * S
    H = total_h + 8 * S
    img = Image.new("RGB", (W, H), hex2rgb(bg))
    d = ImageDraw.Draw(img)
    x = 4 * S
    for ch, w in zip(TEXT, widths):
        d.text((x - f.getbbox(ch)[0], 4 * S), ch, font=f, fill=hex2rgb(G["ui_core"]))
        x += w + gap
    return img


def lum(c: str) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = hex2rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def main() -> int:
    if not BRUSH.exists():
        print("FAIL: 缺 simkai.ttf")
        return 1
    base = Path(__file__).resolve().parent
    bad = 0

    # hero（深青底，完整效果）与 浅绿底版本
    hero_bg = "#0E3A42"
    light_bg = "#F2F7F2"

    h = with_dot(wordmark(150, bg=hero_bg, hero=True), hero_bg)
    h.save(base / "logo-hero.png")
    print(f"hero   {h.width // S}x{h.height // S}")

    # 浅绿底：换深色渐变（否则上半段与背景几乎同色）
    li = with_dot(wordmark(150, bg=light_bg, hero=True, light=True), light_bg)
    li.save(base / "logo-on-light.png")
    print(f"light  {li.width // S}x{li.height // S}")

    sm = ui_small(26, light_bg)
    sm.save(base / "logo-ui-26px.png")
    print(f"ui26   {sm.width // S}x{sm.height // S}")

    # 小尺寸放大预览（看清有没有糊）
    sm.resize((sm.width * 6, sm.height * 6), Image.NEAREST).save(base / "logo-ui-26px-zoom.png")

    print("\n对比度（大字 150px 门槛 3.0；26px 界面字门槛 4.5）:")
    for name, fg, bgx, need in (
        ("hero top  vs 深青底", G["top"], hero_bg, 3.0),
        ("hero bot  vs 深青底", G["bot"], hero_bg, 3.0),
        ("light top vs 浅绿底", G["top_l"], light_bg, 3.0),
        ("light bot vs 浅绿底", G["bot_l"], light_bg, 3.0),
        ("ui 深绿   vs 浅绿底", G["ui_core"], light_bg, 4.5),
        ("ui 深绿   vs 白卡", G["ui_core"], "#FFFFFF", 4.5),
    ):
        cr = contrast(fg, bgx)
        ok = cr >= need
        bad += 0 if ok else 1
        print(f"  {name}: {cr:.1f}:1  {'OK' if ok else 'TOO LOW'}")

    print("RESULT:", "FAIL" if bad else "OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
