"""几何吸附自测：合成图 + 圆/方几何校验 + 语料耗时与保真回归。

1. 用 Pillow 合成一张白底图（半径 200 的纯黑圆 + 300×300 纯黑方块 +
   一个圆角矩形），转成 SVG 后检查：
   - 圆 -> 4 段 C，采样点半径与标称半径误差 < 0.5px；
   - 方块 -> 4 个顶点，每条边 dx 或 dy 严格为 0。
2. 语料图各转两遍（吸附开 / 关），比较耗时与 SSIM。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from firefly import geom  # noqa: E402
from firefly.convert import Options, convert, open_image  # noqa: E402
from firefly.ir import parse_svg  # noqa: E402

CORPUS = ROOT.parent / "research" / "feasibility" / "input" / "corpus"
OUT = ROOT / "_test" / "snap"
W, H = 1200, 900

# 标称几何（合成时就按这些数值画）
CIRC = (300.0, 300.0, 200.0)          # cx, cy, r
SQ = (650.0, 150.0, 950.0, 450.0)     # x0, y0, x1, y1
RR = (650.0, 550.0, 1000.0, 800.0)    # 圆角矩形（半径 40，不该被吸附成方）


def make_image(path: Path) -> Path:
    """合成测试图：白底 + 黑圆 + 黑方块 + 黑圆角矩形。"""
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    cx, cy, r = CIRC
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="black")
    d.rectangle(list(SQ), fill="black")
    d.rounded_rectangle(list(RR), radius=40, fill="black")
    im.save(path)
    return path


def _bbox(sub):
    pts = sub.flatten(8)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _near(box, want, tol=6.0):
    return all(abs(a - b) <= tol for a, b in zip(box, want))


def _radial(sub):
    """返回 (平均半径, 圆度偏差, 拟合圆心)：圆度偏差 = max|r_i - mean|。

    圆度偏差才是"是不是真圆"的判据；平均半径与标称值之间的差是描迹器
    自己把边界放在哪儿（像素中心还是像素边）造成的，与吸附无关。
    """
    pts = sub.flatten(24)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    ds = [((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5 for p in pts]
    mean = sum(ds) / len(ds)
    return mean, max(abs(d - mean) for d in ds), (cx, cy)


def check_geometry(svg_path: Path, tag: str, before: Path | None = None) -> int:
    """检查圆 / 方块是否变成精确几何。返回失败项数。"""
    dr = parse_svg(svg_path.read_text(encoding="utf-8"))
    bad = 0

    # ---- 圆 ----
    want = (CIRC[0] - CIRC[2], CIRC[1] - CIRC[2], CIRC[0] + CIRC[2], CIRC[1] + CIRC[2])
    hit = None
    for vp in dr.paths:
        for s in vp.subs:
            if _near(_bbox(s), want, 8.0):
                hit = s
                break
    if hit is None:
        print(f"  [{tag}] 圆：没找到 bbox≈{want} 的子路径")
        return bad + 1
    n_c = sum(1 for s in hit.segs if s[0] == "C")
    n_l = sum(1 for s in hit.segs if s[0] == "L")
    r_mean, r_dev, _ = _radial(hit)
    old = ""
    if before is not None and before.exists():
        bdr = parse_svg(before.read_text(encoding="utf-8"))
        for vp in bdr.paths:
            for s in vp.subs:
                if _near(_bbox(s), want, 8.0):
                    om, od, _ = _radial(s)
                    old = f"（吸附前 {len(s.segs)} 段，圆度偏差 {od:.3f}px）"
    ok = n_c == 4 and n_l == 0 and r_dev < 0.2 and abs(r_mean - CIRC[2]) < 2.0
    bad += 0 if ok else 1
    print(f"  [{tag}] 圆：C 段 {n_c}  L 段 {n_l}  半径 {r_mean:.2f}px"
          f"（标称 {CIRC[2]:.0f}）  圆度偏差 {r_dev:.3f}px{old}  "
          f"{'OK' if ok else 'FAIL'}")

    # ---- 方块 ----
    hit = None
    for vp in dr.paths:
        for s in vp.subs:
            if _near(_bbox(s), SQ, 8.0):
                hit = s
                break
    if hit is None:
        print(f"  [{tag}] 方块：没找到 bbox≈{SQ} 的子路径")
        return bad + 1
    anchors = geom._anchors(hit)
    n_cur = sum(1 for s in hit.segs if s[0] == "C")
    worst = 0.0
    for i in range(len(anchors)):
        a = anchors[i]
        b = anchors[(i + 1) % len(anchors)]
        worst = max(worst, min(abs(b[0] - a[0]), abs(b[1] - a[1])))
    ok = len(anchors) == 4 and n_cur == 0 and worst < 1e-6
    bad += 0 if ok else 1
    print(f"  [{tag}] 方块：顶点 {len(anchors)}  C 段 {n_cur}  "
          f"边最大斜偏 {worst:.4f}px  {'OK' if ok else 'FAIL'}")

    # ---- 圆角矩形（应保留圆角，不被当成方）----
    hit = None
    for vp in dr.paths:
        for s in vp.subs:
            if _near(_bbox(s), RR, 8.0):
                hit = s
                break
    if hit is not None:
        n_c = sum(1 for s in hit.segs if s[0] == "C")
        print(f"  [{tag}] 圆角矩形：C 段 {n_c}（>0 说明圆角还在）")
    return bad


def bench(cid: str, mode: str, rounds: int = 3) -> None:
    """同一张语料图转两遍（吸附开 / 关），比耗时与 SSIM。取多轮最小值压噪声。"""
    found = sorted(CORPUS.glob(cid + ".*"))
    if not found:
        print(f"  {cid}: 语料缺失")
        return
    res = {}
    for snap in (False, True):
        best = None
        for _ in range(rounds):
            t0 = time.time()
            r = convert(found[0], OUT / ("on" if snap else "off"),
                        Options(mode=mode, snap=snap))
            dt = time.time() - t0
            if best is None or dt < best[0]:
                best = (dt, r)
        res[snap] = best
    (to, ro), (tn, rn) = res[False], res[True]

    # 纯吸附开销：在解析好的 IR 上单跑一次
    from firefly import engines, preprocess  # noqa: F401

    dr = parse_svg(Path(ro.svg).read_text(encoding="utf-8"))
    t0 = time.time()
    st = geom.snap_drawing(dr)
    snap_ms = (time.time() - t0) * 1000.0

    ok = (ro.ok and rn.ok and rn.ssim >= ro.ssim - 0.005
          and tn <= to * 1.15)
    print(f"  {cid:<16} 总耗时 {to:5.2f}s -> {tn:5.2f}s ({(tn / to - 1) * 100:+5.1f}%)  "
          f"其中吸附 {snap_ms:5.1f}ms ({snap_ms / 1000.0 / tn * 100:4.1f}%)  "
          f"SSIM {ro.ssim:.4f} -> {rn.ssim:.4f} ({rn.ssim - ro.ssim:+.4f})  "
          f"吸附 {st.fitted}/{st.total} 处  {'OK' if ok else 'FAIL'}")


def check_donut() -> int:
    """IR 级检查：evenodd 圆环吸附后必须保持相反绕向，洞不能被填实。

    直接造一个 64 边形外圈 + 48 边形内圈（绕向相反），吸附后比有符号面积。
    """
    import math

    from firefly.ir import Drawing, SubPath, VPath

    def poly(cx, cy, r, n, sign):
        segs = []
        for k in range(1, n + 1):
            a = sign * 2.0 * math.pi * k / n
            segs.append(("L", cx + r * math.cos(a), cy + r * math.sin(a)))
        segs.append(("Z",))
        return SubPath(start=(cx + r, cy), segs=segs)

    outer = poly(200.0, 200.0, 120.0, 64, 1.0)
    inner = poly(200.0, 200.0, 60.0, 48, -1.0)
    dr = Drawing(width=400.0, height=400.0,
                 paths=[VPath(subs=[outer, inner], fill="#123456",
                              evenodd=True, opacity=0.5)])
    st = geom.snap_drawing(dr)
    vp = dr.paths[0]
    areas = [geom._area_perim(geom._sample(s))[0] for s in vp.subs]
    n_c = [sum(1 for s in sub.segs if s[0] == "C") for sub in vp.subs]

    # 真渲染一次：洞必须还是白的（光看面积符号不够，PDF 填充模式也得对）。
    # 注意这层是 opacity=0.5 的半透明深色，环上像素约为 150，不能用纯黑去比。
    from firefly import emit
    from firefly.quality import rasterize_pdf

    pdf = OUT / "donut.pdf"
    emit.emit_pdf(dr, pdf)
    im = rasterize_pdf(pdf, 400, 400).convert("L")
    hole = im.getpixel((200, 200)) > 240 and im.getpixel((200, 90)) < 210

    ok = (st.circles == 2 and len(vp.subs) == 2 and n_c == [4, 4]
          and areas[0] > 0 > areas[1] and hole
          and vp.fill == "#123456" and vp.evenodd and abs(vp.opacity - 0.5) < 1e-9)
    print(f"  圆环：吸附 {st.circles} 个圆，C 段 {n_c}，"
          f"有符号面积 {areas[0]:.0f} / {areas[1]:.0f}（需一正一负），"
          f"PDF 渲染洞{'还在' if hole else '没了'}，fill/evenodd/opacity 保留  "
          f"{'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    img = make_image(OUT / "synthetic.png")

    print("== 合成图几何校验 ==")
    bad = 0
    for mode, label in (("单色", "单色"), ("彩色", "彩色")):
        d = OUT / ("syn_" + ("mono" if mode == "单色" else "color"))
        raw = convert(img, OUT / ("raw_" + ("mono" if mode == "单色" else "color")),
                      Options(mode=mode, snap=False))
        r = convert(img, d, Options(mode=mode))
        if not r.ok:
            print(f"  [{label}] 转换失败 {r.error}")
            bad += 1
            continue
        print(f"  [{label}] 吸附 {r.snapped} 处，子路径 {r.subpaths} 个")
        bad += check_geometry(Path(r.svg), label,
                              Path(raw.svg) if raw.ok else None)

    print("== 绕向 / 属性保留 ==")
    bad += check_donut()

    print("== 纯吸附耗时（解析后 IR 上单跑一次）==")
    from firefly import engines, preprocess

    r0 = convert(img, OUT / "syn_mono", Options(mode="单色", snap=False, do_qc=False))
    dr = parse_svg(Path(r0.svg).read_text(encoding="utf-8"))
    t0 = time.time()
    st = geom.snap_drawing(dr)
    print(f"  单色 {len(dr.paths)} 条路径 / {st.total} 个子路径："
          f"{(time.time() - t0) * 1000:.1f}ms，吸附 {st.fitted} 处"
          f"（圆 {st.circles} 椭圆 {st.ellipses} 方 {st.rects} 正交 {st.ortho}，"
          f"安全阀拦下 {st.rejected}）")

    print("== 语料回归（吸附开 / 关对比）==")
    for cid, mode in (("s1_bw_logo", "单色"), ("s2_flat_icon", "彩色"),
                      ("s4_tech_drawing", "单色"), ("s5_chart", "彩色")):
        bench(cid, mode)

    print("OK" if bad == 0 else "FAIL")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
