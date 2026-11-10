"""QA 独立验证：几何吸附（geom.snap_drawing）的合成用例断言。

与 tests/check_snap.py 无关，全部用例、期望值、断言由 QA 自行定义。
只用 Pillow 合成白底黑图（4x 超采样后缩回，模拟真实抗锯齿边缘），
再走 firefly.convert 的完整管线（potrace / vtracer -> IR -> 吸附 -> SVG/PDF），
最后用 firefly.ir.parse_svg 把 SVG 解析回 IR 做几何断言。

用法：.venv/Scripts/python.exe tests/qa_snap_verify.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from firefly import geom  # noqa: E402
from firefly.convert import Options, convert  # noqa: E402
from firefly.ir import parse_svg  # noqa: E402
from firefly.quality import rasterize_pdf  # noqa: E402

SS = 4  # 超采样倍数
WORK = ROOT / "_test" / "qa"
SRC = WORK / "src"

RESULTS: list[tuple[str, str, str, str, str]] = []  # case, assertion, expect, actual, ok


def rec(case, assertion, expect, actual, ok):
    RESULTS.append((case, assertion, expect, actual, "PASS" if ok else "FAIL"))


# ---------------------------------------------------------------- 图像合成


def _canvas(w, h):
    im = Image.new("L", (w * SS, h * SS), 255)
    return im, ImageDraw.Draw(im)


def _save(im, name, size):
    out = SRC / f"{name}.png"
    im.resize(size, Image.LANCZOS).convert("RGB").save(out)
    return out


def gen_circle(d=600, r=200):
    im, dr = _canvas(d, d)
    c = d / 2
    dr.ellipse([(c - r) * SS, (c - r) * SS, (c + r) * SS, (c + r) * SS], fill=0)
    return _save(im, "circle", (d, d))


def gen_square(side=300, d=600):
    im, dr = _canvas(d, d)
    a = (d - side) / 2
    dr.rectangle([a * SS, a * SS, (a + side) * SS, (a + side) * SS], fill=0)
    return _save(im, "square", (d, d))


def gen_roundrect(w=400, h=260, rad=40, d=600):
    im, dr = _canvas(d, d)
    x0, y0 = (d - w) / 2, (d - h) / 2
    dr.rounded_rectangle(
        [x0 * SS, y0 * SS, (x0 + w) * SS, (y0 + h) * SS], radius=rad * SS, fill=0
    )
    return _save(im, "roundrect", (d, d))


def gen_ring(outer=200, inner=100, d=600):
    im, dr = _canvas(d, d)
    c = d / 2
    dr.ellipse([(c - outer) * SS, (c - outer) * SS, (c + outer) * SS, (c + outer) * SS], fill=0)
    dr.ellipse([(c - inner) * SS, (c - inner) * SS, (c + inner) * SS, (c + inner) * SS], fill=255)
    return _save(im, "ring", (d, d))


def gen_ellipse(rx=200, ry=100, d=600):
    im, dr = _canvas(d, d)
    c = d / 2
    dr.ellipse([(c - rx) * SS, (c - ry) * SS, (c + rx) * SS, (c + ry) * SS], fill=0)
    return _save(im, "ellipse", (d, d))


def gen_octagon(r=200, d=600):
    im, dr = _canvas(d, d)
    c = d / 2
    pts = [
        ((c + r * math.cos(k * math.pi / 4)) * SS, (c + r * math.sin(k * math.pi / 4)) * SS)
        for k in range(8)
    ]
    dr.polygon(pts, fill=0)
    return _save(im, "octagon", (d, d))


def gen_slight_ellipse(rx=210, ry=200, d=600):
    im, dr = _canvas(d, d)
    c = d / 2
    dr.ellipse([(c - rx) * SS, (c - ry) * SS, (c + rx) * SS, (c + ry) * SS], fill=0)
    return _save(im, "slight_ellipse", (d, d))


def gen_color_circle(d=500, r=180):
    im = Image.new("RGB", (d * SS, d * SS), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    c = d / 2
    dr.ellipse([(c - r) * SS, (c - r) * SS, (c + r) * SS, (c + r) * SS], fill=(224, 49, 49))
    out = SRC / "color_circle.png"
    im.resize((d, d), Image.LANCZOS).save(out)
    return out


def gen_tiny(r=14, d=32):
    im, dr = _canvas(d, d)
    c = d / 2
    dr.ellipse([(c - r) * SS, (c - r) * SS, (c + r) * SS, (c + r) * SS], fill=0)
    return _save(im, "tiny", (d, d))


def gen_huge(r=1400, d=3000):
    im, dr = _canvas(d, d)
    c = d / 2
    dr.ellipse([(c - r) * SS, (c - r) * SS, (c + r) * SS, (c + r) * SS], fill=0)
    return _save(im, "huge", (d, d))


def gen_flat(v=255, d=200):
    im = Image.new("L", (d, d), v)
    name = "white" if v > 127 else "black"
    out = SRC / f"{name}.png"
    im.convert("RGB").save(out)
    return out


# ---------------------------------------------------------------- 几何测量


def anchors(sub):
    pts = [tuple(map(float, sub.start))]
    for s in sub.segs:
        if s[0] == "L":
            pts.append((float(s[1]), float(s[2])))
        elif s[0] == "C":
            pts.append((float(s[5]), float(s[6])))
    return pts


def seg_types(sub):
    nL = sum(1 for s in sub.segs if s[0] == "L")
    nC = sum(1 for s in sub.segs if s[0] == "C")
    closed = any(s[0] == "Z" for s in sub.segs)
    return nL, nC, closed


def shoelace(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a * 0.5


def sample(sub, steps=48):
    """独立采样：不调用 geom 的内部实现。起点必须算进去，否则闭合边会被漏掉。"""
    cur = tuple(map(float, sub.start))
    pts = [cur]
    for s in sub.segs:
        if s[0] == "L":
            cur = (float(s[1]), float(s[2]))
            pts.append(cur)
        elif s[0] == "C":
            p0 = cur
            p1 = (float(s[1]), float(s[2]))
            p2 = (float(s[3]), float(s[4]))
            p3 = (float(s[5]), float(s[6]))
            for i in range(1, steps + 1):
                t = i / steps
                u = 1 - t
                b0, b1, b2, b3 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
                pts.append(
                    (
                        b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
                        b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1],
                    )
                )
            cur = p3
    return pts


def bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def hausdorff(pa, pb):
    """双向最大最近距离（QA 独立实现，不复用 geom._max_dev）。"""
    def one(a, b):
        worst = 0.0
        n = len(b)
        for p in a:
            best = min(_seg_dist(p, b[i], b[(i + 1) % n]) for i in range(n))
            if best > worst:
                worst = best
        return worst

    return max(one(pa, pb), one(pb, pa))


def subpaths(svg_path):
    dr = parse_svg(Path(svg_path).read_text(encoding="utf-8"))
    return dr, [s for vp in dr.paths for s in vp.subs]


def biggest(subs):
    return max(subs, key=lambda s: abs(shoelace(anchors(s))))


def circle_stats(sub):
    """圆心取 bbox 中心：贝塞尔按 t 均匀采样时质心会有方向偏置，不能直接用均值。"""
    pts = sample(sub)
    x0, y0, x1, y1 = bbox(pts)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    rs = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    mean = sum(rs) / len(rs)
    return cx, cy, mean, max(abs(r - mean) for r in rs)


# ---------------------------------------------------------------- 转换


def run(img: Path, tag: str, snap: bool, mode="单色", preset=None):
    out = WORK / f"{tag}_{'on' if snap else 'off'}"
    opts = Options(mode=mode, snap=snap)
    if preset:
        if mode == "单色":
            opts.mono_preset = preset
        else:
            opts.color_preset = preset
    return convert(img, out, opts)


# ---------------------------------------------------------------- 用例


def case_circle(img):
    on = run(img, "circle", True)
    off = run(img, "circle", False)
    if not (on.ok and off.ok):
        rec("circle", "转换成功", "ok", f"{on.error}|{off.error}", False)
        return
    _, so = subpaths(off.svg)
    _, sn = subpaths(on.svg)
    b_off, b_on = biggest(so), biggest(sn)
    nL, nC, cl = seg_types(b_on)
    # 单色路线走 potrace，默认输出是贝塞尔（非多边形），关吸附时应为多段贝塞尔
    rec("circle", "关闭吸附时保留原始拟合（>4 段）", ">4 段",
        f"{seg_types(b_off)[0]}L/{seg_types(b_off)[1]}C",
        seg_types(b_off)[0] + seg_types(b_off)[1] > 4)
    rec("circle", "开关两次 SVG 字节不同", "不同", "不同" if on.svg_bytes != off.svg_bytes else "相同",
        on.svg_bytes != off.svg_bytes)
    rec("circle", "吸附后 4 段三次贝塞尔", "4C", f"{nC}C/{nL}L closed={cl}", nC == 4 and nL == 0 and cl)
    cx, cy, r, err = circle_stats(b_on)
    rec("circle", "采样点半径误差 < 0.5px", "<0.5", f"{err:.4f}", err < 0.5)
    rec("circle", "圆心 ≈ (300,300) ±1", "±1", f"({cx:.2f},{cy:.2f})",
        abs(cx - 300) <= 1 and abs(cy - 300) <= 1)
    rec("circle", "半径 ≈ 200 ±1", "±1", f"{r:.3f}", abs(r - 200) <= 1)
    dev = hausdorff(sample(b_off), sample(b_on))
    rec("circle", "吸附前后最大偏差 <= 1.0px", "<=1.0", f"{dev:.3f}", dev <= 1.0)


def case_square(img):
    on = run(img, "square", True)
    off = run(img, "square", False)
    _, so = subpaths(off.svg)
    _, sn = subpaths(on.svg)
    b_off, b_on = biggest(so), biggest(sn)
    nL, nC, cl = seg_types(b_on)
    # _rect_sub: start=第 1 个角点 + 3 条 L + Z => 4 个角
    rec("square", "吸附后 4 个角 / 3 段直线 + Z", "3L+Z", f"{nL}L/{nC}C closed={cl}",
        nL == 3 and nC == 0 and cl)
    pts = anchors(b_on)
    rec("square", "顶点数 = 4", "4", f"{len(pts)}", len(pts) == 4)
    ok_ortho = True
    detail = []
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
        detail.append(f"({dx:.3f},{dy:.3f})")
        if not (dx == 0.0 or dy == 0.0):
            ok_ortho = False
    rec("square", "每条边 dx 或 dy 严格为 0", "0", " ".join(detail), ok_ortho)
    x0, y0, x1, y1 = bbox(pts)
    rec("square", "bbox ≈ 300×300", "300", f"{x1 - x0:.2f}×{y1 - y0:.2f}",
        abs((x1 - x0) - 300) <= 1.5 and abs((y1 - y0) - 300) <= 1.5)
    dev = hausdorff(sample(b_off), sample(b_on))
    rec("square", "吸附前后最大偏差 <= 1.0px", "<=1.0", f"{dev:.3f}", dev <= 1.0)


def case_roundrect(img):
    on = run(img, "roundrect", True)
    off = run(img, "roundrect", False)
    _, so = subpaths(off.svg)
    _, sn = subpaths(on.svg)
    b_off, b_on = biggest(so), biggest(sn)
    nL, nC, _ = seg_types(b_on)
    rec("roundrect", "不应被吸成矩形（保留圆角）", "非 4L", f"{nL}L/{nC}C", not (nL == 4 and nC == 0))
    dev = hausdorff(sample(b_off), sample(b_on))
    rec("roundrect", "吸附前后最大偏差 <= 1.0px", "<=1.0", f"{dev:.3f}", dev <= 1.0)
    x0, y0, x1, y1 = bbox(anchors(b_on))
    rec("roundrect", "bbox ≈ 400×260", "400×260", f"{x1 - x0:.2f}×{y1 - y0:.2f}",
        abs((x1 - x0) - 400) <= 1.5 and abs((y1 - y0) - 260) <= 1.5)


def case_ring(img):
    on = run(img, "ring", True)
    off = run(img, "ring", False)
    dr_on, sn = subpaths(on.svg)
    dr_off, so = subpaths(off.svg)
    rec("ring", "子路径数保持 2（洞还在）", "2", f"{len(sn)}（关={len(so)}）", len(sn) == 2 == len(so))
    if len(sn) < 2:
        return
    subs = sorted(sn, key=lambda s: abs(shoelace(anchors(s))))
    inner, outer = subs[0], subs[-1]
    rec("ring", "内轮廓 4C / 外轮廓 4C",
        "4C/4C", f"{seg_types(inner)[1]}C/{seg_types(outer)[1]}C",
        seg_types(inner)[1] == 4 and seg_types(outer)[1] == 4)
    a_i, a_o = shoelace(anchors(inner)), shoelace(anchors(outer))
    rec("ring", "内外绕向相反（非零填充洞才有效）", "符号相反", f"{a_i:.0f} / {a_o:.0f}",
        (a_i > 0) != (a_o > 0))
    _, _, r_i, e_i = circle_stats(inner)
    _, _, r_o, e_o = circle_stats(outer)
    rec("ring", "内 r≈100 / 外 r≈200", "100/200", f"{r_i:.2f}/{r_o:.2f}",
        abs(r_i - 100) <= 1 and abs(r_o - 200) <= 1)
    rec("ring", "内外半径误差 < 0.5px", "<0.5", f"{e_i:.3f}/{e_o:.3f}", e_i < 0.5 and e_o < 0.5)
    # 栅格化验证：圆心必须白，环上必须黑
    im = rasterize_pdf(on.pdf, 600, 600).convert("L")
    px = im.load()
    c = 300
    center = px[c, c]
    ring = [px[c + 150, c], px[c, c + 150], px[c - 150, c], px[c, c - 150]]
    rec("ring", "PDF 栅格化：圆心像素为白", ">=250", f"{center}", center >= 250)
    rec("ring", "PDF 栅格化：环上像素为黑", "<=5", f"{ring}", max(ring) <= 5)


def case_ellipse(img):
    on = run(img, "ellipse", True)
    off = run(img, "ellipse", False)
    _, so = subpaths(off.svg)
    _, sn = subpaths(on.svg)
    b_off, b_on = biggest(so), biggest(sn)
    nL, nC, _ = seg_types(b_on)
    rec("ellipse", "吸附后 4 段贝塞尔", "4C", f"{nC}C/{nL}L", nC == 4)
    pts = sample(b_on)
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    rx = 200.0
    ry = 100.0
    err = max(abs(math.hypot((p[0] - cx) / rx, (p[1] - cy) / ry) - 1.0) for p in pts)
    rec("ellipse", "归一化半径误差 < 0.01（400×200）", "<0.01", f"{err:.5f}", err < 0.01)
    x0, y0, x1, y1 = bbox(pts)
    rec("ellipse", "bbox ≈ 400×200", "400×200", f"{x1 - x0:.2f}×{y1 - y0:.2f}",
        abs((x1 - x0) - 400) <= 1.5 and abs((y1 - y0) - 200) <= 1.5)
    dev = hausdorff(sample(b_off), sample(b_on))
    rec("ellipse", "吸附前后最大偏差 <= 1.0px", "<=1.0", f"{dev:.3f}", dev <= 1.0)


def case_octagon(img):
    on = run(img, "octagon", True)
    off = run(img, "octagon", False)
    _, so = subpaths(off.svg)
    _, sn = subpaths(on.svg)
    b_off, b_on = biggest(so), biggest(sn)
    nL, nC, _ = seg_types(b_on)
    is_circle = nC == 4 and nL == 0
    dev = hausdorff(sample(b_off), sample(b_on))
    rec("octagon", "不应被吸成 4 段圆（或偏差 <=1px）", "非 4C 或 dev<=1",
        f"{nL}L/{nC}C dev={dev:.3f}", (not is_circle) or dev <= 1.0)
    rec("octagon", "吸附前后最大偏差 <= 1.0px", "<=1.0", f"{dev:.3f}", dev <= 1.0)
    a_on, a_off = len(anchors(b_on)), len(anchors(b_off))
    rec("octagon", "顶点数未被改变", f"{a_off}", f"{a_on}", a_on == a_off)
    # 圆度检查：八边形圆度 4πA/P² 只有 0.948，若被吸成圆必须落在 1px 内
    pts = sample(b_on)
    area = abs(shoelace(pts))
    per = 0.0
    for i in range(len(pts)):
        per += math.hypot(pts[(i + 1) % len(pts)][0] - pts[i][0],
                          pts[(i + 1) % len(pts)][1] - pts[i][1])
    circ = 4 * math.pi * area / (per * per)
    rec("octagon", "输出圆度仍 ≈ 0.948（未被圆化）", "0.90~0.97", f"{circ:.4f}",
        0.90 <= circ <= 0.97)


def case_slight_ellipse(img):
    on = run(img, "slight", True)
    off = run(img, "slight", False)
    _, so = subpaths(off.svg)
    _, sn = subpaths(on.svg)
    b_off, b_on = biggest(so), biggest(sn)
    nL, nC, _ = seg_types(b_on)
    dev = hausdorff(sample(b_off), sample(b_on))
    pts = sample(b_on)
    x0, y0, x1, y1 = bbox(pts)
    rec("slight", "判成圆或椭圆（4C）", "4C", f"{nC}C/{nL}L", nC == 4)
    rec("slight", "bbox 保持 420×400 ±1.5", "420×400", f"{x1 - x0:.2f}×{y1 - y0:.2f}",
        abs((x1 - x0) - 420) <= 1.5 and abs((y1 - y0) - 400) <= 1.5)
    rec("slight", "吸附前后最大偏差 <= 1.0px", "<=1.0", f"{dev:.3f}", dev <= 1.0)


def case_color(img):
    on = run(img, "colorcircle", True, mode="彩色", preset="平涂图标")
    off = run(img, "colorcircle", False, mode="彩色", preset="平涂图标")
    if not (on.ok and off.ok):
        rec("color", "转换成功", "ok", f"{on.error}|{off.error}", False)
        return

    def red_sub(path):
        """彩色路线里白底矩形面积更大，必须按填充色挑出圆那一条。"""
        dr = parse_svg(Path(path).read_text(encoding="utf-8"))
        for vp in dr.paths:
            if vp.fill.upper().startswith("#E0313"):
                return vp.subs
        return []

    so, sn = red_sub(off.svg), red_sub(on.svg)
    if not sn:
        rec("color", "找到 #E03131 填充路径", "1", f"0（{on.svg}）", False)
        return
    b_on, b_off = biggest(sn), biggest(so)
    nL, nC, _ = seg_types(b_on)
    rec("color", "彩色路线：圆形 4C", "4C", f"{nC}C/{nL}L", nC == 4)
    cx, cy, r, err = circle_stats(b_on)
    rec("color", "彩色路线：半径误差 < 0.5px", "<0.5", f"{err:.4f}", err < 0.5)
    rec("color", "彩色路线：r ≈ 180 ±1", "±1", f"{r:.2f}", abs(r - 180) <= 1)
    dev = hausdorff(sample(b_off), sample(b_on))
    rec("color", "彩色路线：吸附前后偏差 <= 1.0px", "<=1.0", f"{dev:.3f}", dev <= 1.0)
    rec("color", "彩色路线：仍有颜色填充", "#E03131",
        str([vp.fill for vp in parse_svg(Path(on.svg).read_text(encoding="utf-8")).paths])[:40],
        "#E03131" in Path(on.svg).read_text(encoding="utf-8"))


def case_radius_sweep():
    """半径扫描：找出吸附在多大尺寸上开始静默失效（qa 独立发现）。"""
    sizes = [(300, 120), (400, 160), (500, 200), (700, 280), (900, 360),
             (1100, 440), (1400, 560), (1800, 720)]
    print("\n[半径扫描] r=圆半径 px / 画布 = 2.5r")
    for canvas, r in sizes:
        im, dr = _canvas(canvas, canvas)
        c = canvas / 2
        dr.ellipse([(c - r) * SS, (c - r) * SS, (c + r) * SS, (c + r) * SS], fill=0)
        img = _save(im, f"sweep_{r}", (canvas, canvas))
        res = run(img, f"sweep_{r}", True)
        if not res.ok:
            rec(f"sweep r={r}", "转换成功", "ok", res.error[:20], False)
            continue
        _, sn = subpaths(res.svg)
        b = biggest(sn)
        nL, nC, _ = seg_types(b)
        _, _, rad, err = circle_stats(b)
        rec(f"sweep r={r}", "吸成 4C 圆", "4C", f"{nC}C/{nL}L r={rad:.1f} 吸附={res.snapped}",
            nC == 4)


def case_aspect_sweep():
    """椭圆长宽比扫描：验证 CIRC_ELL_MIN=0.88 的实际可用范围。"""
    print("\n[长宽比扫描] a=200 固定，k=b/a")
    for k in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4):
        a = 200
        b = int(round(a * k))
        im, dr = _canvas(520, 520)
        c = 260
        dr.ellipse([(c - a) * SS, (c - b) * SS, (c + a) * SS, (c + b) * SS], fill=0)
        img = _save(im, f"asp_{int(k*100)}", (520, 520))
        res = run(img, f"asp_{int(k*100)}", True)
        if not res.ok:
            rec(f"aspect k={k}", "转换成功", "ok", res.error[:20], False)
            continue
        _, sn = subpaths(res.svg)
        nb = biggest(sn)
        nL, nC, _ = seg_types(nb)
        rec(f"aspect k={k}", "吸成 4 段精确椭圆", "4C", f"{nC}C/{nL}L 吸附={res.snapped}",
            nC == 4)


def case_small_big(tiny, huge):
    r = run(tiny, "tiny", True)
    rec("tiny(32px)", "转换成功不崩", "ok", r.error or "ok", r.ok)
    if r.ok:
        _, sn = subpaths(r.svg)
        b = biggest(sn)
        nL, nC, _ = seg_types(b)
        _, _, rad, err = circle_stats(b)
        rec("tiny(32px)", "圆形 r≈14 被识别", "r≈14", f"r={rad:.2f} 4C={nC == 4} err={err:.2f}",
            abs(rad - 14) <= 1.0)
        rec("tiny(32px)", "输出非空（没被吸没）", ">=1 子路径", f"{len(sn)}", len(sn) >= 1)
    import time

    t0 = time.time()
    r2 = run(huge, "huge", True)
    dt = time.time() - t0
    rec("huge(3000px)", "转换成功不崩", "ok", r2.error or "ok", r2.ok)
    rec("huge(3000px)", "耗时 < 120s", "<120", f"{dt:.1f}s", dt < 120)
    if r2.ok:
        _, sn = subpaths(r2.svg)
        b = biggest(sn)
        nL, nC, _ = seg_types(b)
        cx, cy, rad, err = circle_stats(b)
        rec("huge(3000px)", "圆形 r≈1400 被识别", "4C r≈1400", f"{nC}C r={rad:.1f}",
            nC == 4 and abs(rad - 1400) <= 3)
        rec("huge(3000px)", "图形没被吸没", "面积 > 0", f"{abs(shoelace(anchors(b))):.0f}",
            abs(shoelace(anchors(b))) > 1e5)


def case_flat(white, black):
    for name, img in (("white", white), ("black", black)):
        r = run(img, f"flat_{name}", True)
        rec(f"flat_{name}", "不抛异常（可优雅失败）", "无异常", r.error or "ok", True)
        if r.ok:
            _, sn = subpaths(r.svg)
            rec(f"flat_{name}", "输出子路径数", ">=0", f"{len(sn)}", True)


def main():
    SRC.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    imgs = {
        "circle": gen_circle(),
        "square": gen_square(),
        "roundrect": gen_roundrect(),
        "ring": gen_ring(),
        "ellipse": gen_ellipse(),
        "octagon": gen_octagon(),
        "slight": gen_slight_ellipse(),
        "color": gen_color_circle(),
        "tiny": gen_tiny(),
        "huge": gen_huge(),
        "white": gen_flat(255),
        "black": gen_flat(0),
    }

    case_circle(imgs["circle"])
    case_square(imgs["square"])
    case_roundrect(imgs["roundrect"])
    case_ring(imgs["ring"])
    case_ellipse(imgs["ellipse"])
    case_octagon(imgs["octagon"])
    case_slight_ellipse(imgs["slight"])
    case_color(imgs["color"])
    case_small_big(imgs["tiny"], imgs["huge"])
    case_flat(imgs["white"], imgs["black"])
    case_radius_sweep()
    case_aspect_sweep()

    w0 = max(len(r[0]) for r in RESULTS)
    w1 = max(len(r[1]) for r in RESULTS)
    print(f"\n{'用例':<{w0}} | {'断言':<{w1}} | {'期望':<12} | {'实际':<28} | 判定")
    print("-" * (w0 + w1 + 62))
    nfail = 0
    for c, a, e, ac, ok in RESULTS:
        if ok != "PASS":
            nfail += 1
        print(f"{c:<{w0}} | {a:<{w1}} | {str(e):<12} | {str(ac)[:28]:<28} | {ok}")
    print(f"\n合计 {len(RESULTS)} 条断言，FAIL {nfail}")
    print("RESULT:", "OK" if nfail == 0 else "FAIL")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
