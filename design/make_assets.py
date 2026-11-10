"""生成 firefly/assets 下的运行时资源：标题栏字标、帮助页大图、exe 图标。

这些是**产品资源**（会打进包里），与 design/ 下的设计探索稿分开。

用法：python design/make_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from design import logo as L  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "firefly" / "assets"

# 界面配色（与 gui.py 保持一致）
UI_BG = "#F2F7F2"
UI_CORE = "#0E5F52"
BRAND_DARK = "#0E3A42"
MINT = "#35BFBF"
MINT_LIGHT = "#EAFBF0"


def cjk(size: float):
    return L.font(L.BRUSH, size)


def sans(size: float, weight: int = 620):
    return L.font(L.SANS, size, weight=weight)


def transparent_wordmark(size: float, color: str, font, tracking: float = 0.06) -> Image.Image:
    """透明底字标：只画字，不带渐变/辉光/投影（小尺寸下这些只会糊）。"""
    widths, gap, total_w, total_h = L.layout(font, "萤火虫", size, tracking)
    W = total_w + 10 * L.S
    H = total_h + 10 * L.S
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 5 * L.S
    for ch, w in zip("萤火虫", widths):
        d.text((x - font.getbbox(ch)[0], 5 * L.S), ch, font=font, fill=L.hex2rgb(color) + (255,))
        x += w + gap
    return img.crop(img.getbbox())


def make_icon_small(size: int) -> Image.Image:
    """小尺寸（<=32px）专用：萤火虫光点。汉字在此尺寸下必糊，改用简化图形。"""
    S = 8
    px = size * S
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))

    bg = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    top, bot = L.hex2rgb("#12505C"), L.hex2rgb(BRAND_DARK)
    for y in range(px):
        t = y / max(1, px - 1)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        d.line([0, y, px, y], fill=c + (255,))
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, px - 1, px - 1], radius=int(px * 0.22), fill=255)
    bg.putalpha(mask)
    img.alpha_composite(bg)

    # 光点 + 光晕（唯一主体，缩到 16px 仍是可辨的亮点）
    cx, cy = px * 0.5, px * 0.5
    halo = L.radial(int(px * 0.92), MINT, 2.0)
    img.alpha_composite(halo, (int(cx - px * 0.46), int(cy - px * 0.46)))
    r = px * 0.175
    d2 = ImageDraw.Draw(img)
    d2.ellipse([cx - r, cy - r, cx + r, cy + r], fill=L.hex2rgb(MINT_LIGHT) + (255,))
    r2 = px * 0.095
    d2.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=(255, 255, 255, 255))
    # 不加光尾：试过两道短尾，在 32px 下读作「两条腿」，像小人或气球，反而更糟
    return img


def make_icon(size: int) -> Image.Image:
    """方形图标：深青圆角底 + 薄荷辉光 + 「萤」字。"""
    if size <= 32:
        return make_icon_small(size)
    S = 4
    px = size * S
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))

    # 圆角底（深青，带轻微纵向渐变）
    bg = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    top, bot = L.hex2rgb("#12505C"), L.hex2rgb(BRAND_DARK)
    for y in range(px):
        t = y / max(1, px - 1)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        d.line([0, y, px, y], fill=c + (255,))
    # 圆角遮罩
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, px - 1, px - 1], radius=int(px * 0.22), fill=255)
    bg.putalpha(mask)
    img.alpha_composite(bg)

    # 左下角薄荷辉光
    gl = L.radial(int(px * 0.95), MINT, 2.2)
    gl.putalpha(gl.getchannel("A").point(lambda v: int(v * 0.55)))
    img.alpha_composite(gl, (-int(px * 0.30), int(px * 0.34)))

    # 「萤」字：渐变 + 上缘高光
    f = cjk(size * 0.60)
    ch = "萤"
    m = Image.new("L", (px, px), 0)
    bb = f.getbbox(ch)
    cw, chh = bb[2] - bb[0], bb[3] - bb[1]
    ImageDraw.Draw(m).text(
        ((px - cw) // 2 - bb[0], (px - chh) // 2 - bb[1]), ch, font=f, fill=255)

    top_c, mid_c, bot_c = L.hex2rgb(MINT_LIGHT), L.hex2rgb("#8FEEDC"), L.hex2rgb(MINT)
    grad = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(px):
        t = y / max(1, px - 1)
        if t <= 0.55:
            u = t / 0.55
            c = tuple(int(top_c[i] + (mid_c[i] - top_c[i]) * u) for i in range(3))
        else:
            u = (t - 0.55) / 0.45
            c = tuple(int(mid_c[i] + (bot_c[i] - mid_c[i]) * u) for i in range(3))
        gd.line([0, y, px, y], fill=c + (255,))
    grad.putalpha(m)
    img.alpha_composite(grad)
    return img


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bad = 0

    # 1) 标题栏字标：按「显示尺寸」产出 1x / 2x 两版。
    #    高倍渲染后用 LANCZOS 缩下来，比让 Tk 直接 subsample 更干净。
    #    注意 Tk 不会自动挑 @2x，加载 @2x 会显示成两倍大。
    LOGICAL = 17.0  # 逻辑字号
    ui3x = transparent_wordmark(LOGICAL, UI_CORE, sans(LOGICAL, 620), 0.05)
    w1 = max(1, round(ui3x.width / L.S))
    h1 = max(1, round(ui3x.height / L.S))
    ui1 = ui3x.resize((w1, h1), Image.LANCZOS)
    ui2 = ui3x.resize((w1 * 2, h1 * 2), Image.LANCZOS)
    ui1.save(OUT / "logo_ui.png")
    ui2.save(OUT / "logo_ui@2x.png")
    print(f"logo_ui.png      {ui1.width}x{ui1.height}  (显示尺寸)")
    print(f"logo_ui@2x.png   {ui2.width}x{ui2.height}")

    # 2) 帮助页大图（浅绿底，完整渐变+高光+投影）
    hero = L.with_dot(L.wordmark(72, bg=UI_BG, hero=True, light=True), UI_BG)
    hero.save(OUT / "logo_hero.png")
    print(f"logo_hero.png    {hero.width // L.S}x{hero.height // L.S} 逻辑像素")

    # 3) exe / 任务栏图标（多尺寸 ico）
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [make_icon(s) for s in sizes]
    ico = OUT / "icon.ico"
    imgs[-1].save(ico, format="ICO", sizes=[(s, s) for s in sizes])
    for s, im in zip(sizes, imgs):
        im.resize((s, s), Image.LANCZOS).save(OUT / f"_ico_{s}.png")
    print(f"icon.ico         {ico.stat().st_size // 1024} KB  ({len(sizes)} 个尺寸)")

    # 4) 自检：尺寸、非空、对比度
    print("\n自检:")
    for s in sizes:
        im = Image.open(OUT / f"_ico_{s}.png").convert("RGBA")
        a = np.asarray(im)
        if a[..., 3].max() == 0:
            print(f"  {s}px 全透明 FAIL")
            bad += 1
        else:
            cov = (a[..., 3] > 40).mean() * 100
            print(f"  {s:3d}px  不透明像素 {cov:4.1f}%  OK")

    cr = L.contrast(UI_CORE, UI_BG)
    print(f"  标题栏字标 {UI_CORE} on {UI_BG}: {cr:.1f}:1  "
          f"{'OK' if cr >= 4.5 else 'TOO LOW'}")
    if cr < 4.5:
        bad += 1

    print("RESULT:", "FAIL" if bad else "OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
