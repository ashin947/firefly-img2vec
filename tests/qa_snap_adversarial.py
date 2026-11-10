"""QA 对抗用例（第 2 轮）：针对「放宽椭圆判据 + tol 上限 2.5px + 面积守恒闸」
这三处放松/收紧改动，专门构造**过吸**风险用例。

分组对应 team-lead 的要求：
  A. 新椭圆判据会不会过度吸附（面积比是唯一粗筛）
  B. 大画布下 tol 放宽到 2.5px 会不会误伤（大尺寸多边形）
  C. 面积守恒闸（3%）会不会把该吸的直边也挡掉

判定口径：只要「被吸成 4C/3L 且实测偏差 > tol」就是 FAIL。
用法：.venv/Scripts/python.exe tests/qa_snap_adversarial.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image, ImageDraw  # noqa: E402

from qa_snap_verify import (  # noqa: E402  复用 QA 自己的测量实现
    anchors,
    biggest,
    gen_flat,
    hausdorff,
    sample,
    seg_types,
    subpaths,
)

from firefly import geom  # noqa: E402
from firefly.convert import Options, convert  # noqa: E402

WORK = ROOT / "_test" / "qa_adv"
SRC = WORK / "src"
RESULTS = []


def rec(case, assertion, expect, actual, ok):
    RESULTS.append((case, assertion, expect, str(actual), "PASS" if ok else "FAIL"))


def canvas(w, h, ss=4):
    im = Image.new("L", (w * ss, h * ss), 255)
    return im, ImageDraw.Draw(im), ss


def save(im, name, size):
    p = SRC / f"{name}.png"
    im.resize(size, Image.LANCZOS).convert("RGB").save(p)
    return p


def ngon(d, cx, cy, r, n, rot, ss):
    d.polygon(
        [((cx + r * math.cos(rot + 2 * math.pi * k / n)) * ss,
          (cy + r * math.sin(rot + 2 * math.pi * k / n)) * ss) for k in range(n)],
        fill=0,
    )


def squircle(d, cx, cy, a, b, ss, n=4.0, steps=360):
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        ct, st = math.cos(t), math.sin(t)
        x = math.copysign(abs(ct) ** (2.0 / n), ct)
        y = math.copysign(abs(st) ** (2.0 / n), st)
        pts.append(((cx + a * x) * ss, (cy + b * y) * ss))
    d.polygon(pts, fill=0)


def run(img, tag, snap=True):
    return convert(img, WORK / f"{tag}_{'on' if snap else 'off'}", Options(mode="单色", snap=snap))


def probe(case, img, tag):
    """返回 (是否被吸成 4C, 是否被吸成 3L 矩形, 实测偏差, 段型)。"""
    on = run(img, tag, True)
    off = run(img, tag, False)
    if not on.ok or not off.ok:
        rec(case, "转换成功", "ok", f"{on.error}|{off.error}", False)
        return None
    _, sn = subpaths(on.svg)
    _, so = subpaths(off.svg)
    b_on, b_off = biggest(sn), biggest(so)
    nL, nC, _ = seg_types(b_on)
    dev = hausdorff(sample(b_off), sample(b_on))
    pts = sample(b_on)
    span = max(max(p[0] for p in pts) - min(p[0] for p in pts),
               max(p[1] for p in pts) - min(p[1] for p in pts))
    tol = geom._tol_for(span)
    is_round = nC == 4 and nL == 0
    is_rect = nL == 3 and nC == 0
    # 核心断言：被吸了就必须在 tol 内（过吸 = 偏差超 tol）
    ok = (not (is_round or is_rect)) or dev <= tol
    rec(case, "未过吸（被吸则偏差<=tol）", f"dev<={tol:.2f}",
        f"{'4C' if is_round else '3L' if is_rect else f'{nL}L/{nC}C'} dev={dev:.3f} tol={tol:.2f}",
        ok)
    return is_round, is_rect, dev, (nC, nL)


def must_not(case, img, tag, kind="round"):
    """明确断言：不得被吸成圆/椭圆（kind=round）或矩形（kind=rect）。"""
    r = probe(case, img, tag)
    if r is None:
        return
    is_round, is_rect, dev, seg = r
    if kind == "round":
        rec(case, "不得被吸成圆/椭圆", "非 4C", f"{'4C 被吸!' if is_round else f'{seg[1]}L/{seg[0]}C'} dev={dev:.3f}",
            not is_round)
    else:
        rec(case, "不得被吸成精确矩形", "非 3L", f"{'3L 被吸!' if is_rect else f'{seg[1]}L/{seg[0]}C'} dev={dev:.3f}",
            not is_rect)


def main():
    SRC.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    # ---------------- A. 新椭圆判据的过吸风险 ----------------
    print("[A] 椭圆判据过吸")
    # 正六边形 R=200：面积比 0.955 落在 [0.92,1.08] 内，只能靠残差挡
    im, d, ss = canvas(600, 600)
    ngon(d, 300, 300, 200, 6, math.pi / 6, ss)
    must_not("A1 正六边形 R200(30°)", save(im, "a_hex30", (600, 600)), "a_hex30")
    im, d, ss = canvas(600, 600)
    ngon(d, 300, 300, 200, 6, math.pi / 12, ss)
    must_not("A1b 正六边形 R200(15°)", save(im, "a_hex15", (600, 600)), "a_hex15")
    # 胶囊 400×160：面积比 1.205
    im, d, ss = canvas(600, 400)
    d.rounded_rectangle([100 * ss, 120 * ss, 500 * ss, 280 * ss], radius=80 * ss, fill=0)
    must_not("A2 胶囊 400×160", save(im, "a_capsule", (600, 400)), "a_capsule")
    # 菱形（正方形旋转 45°）：面积比 0.637
    im, d, ss = canvas(600, 600)
    ngon(d, 300, 300, 250, 4, math.pi / 2, ss)
    must_not("A3 菱形 R250", save(im, "a_rhombus", (600, 600)), "a_rhombus")
    # 圆角矩形 r=40 / r=100
    for rad in (40, 100):
        im, d, ss = canvas(600, 600)
        d.rounded_rectangle([100 * ss, 170 * ss, 500 * ss, 430 * ss], radius=rad * ss, fill=0)
        must_not(f"A4 圆角矩形 400×260 r{rad}", save(im, f"a_rr{rad}", (600, 600)), f"a_rr{rad}")
    # 超椭圆 n=4：面积比 1.181
    im, d, ss = canvas(600, 600)
    squircle(d, 300, 300, 200, 200, ss, n=4.0)
    must_not("A5 超椭圆 n=4 (squircle)", save(im, "a_squircle", (600, 600)), "a_squircle")
    # 对照：真正的椭圆必须被吸
    im, d, ss = canvas(600, 600)
    d.ellipse([100 * ss, 170 * ss, 500 * ss, 430 * ss], fill=0)
    r = probe("A6 对照 真椭圆 400×260", save(im, "a_ellipse", (600, 600)), "a_ellipse")
    rec("A6 对照 真椭圆 400×260", "必须吸成 4C", "4C",
        f"{'4C' if r and r[0] else ('%dL/%dC'%(r[3][1],r[3][0])) if r else '-'}", bool(r and r[0]))

    # ---------------- B. 大画布 tol 放宽 ----------------
    print("[B] 大画布 tol=2.5px 误伤")
    # 六边形 R=1500：理论偏差 200px 级
    im, d, ss = canvas(3000, 3000)
    ngon(d, 1500, 1500, 1500, 6, math.pi / 6, ss)
    must_not("B1 六边形 R1500", save(im, "b_hex1500", (3000, 3000)), "b_hex1500")
    # 十二边形 R=1500：理论偏差 1500*(1-cos15°)=51px，最危险
    im, d, ss = canvas(3000, 3000)
    ngon(d, 1500, 1500, 1500, 12, 0.0, ss)
    must_not("B2 十二边形 R1500 (偏差理论51px)", save(im, "b_dodec1500", (3000, 3000)), "b_dodec1500")
    # 大圆角矩形
    im, d, ss = canvas(3000, 2000)
    d.rounded_rectangle([200 * ss, 200 * ss, 2800 * ss, 1800 * ss], radius=400 * ss, fill=0)
    must_not("B3 大圆角矩形 2600×1600 r400", save(im, "b_rr", (3000, 2000)), "b_rr")
    # 对照：真圆 r=1400 必须被吸
    im, d, ss = canvas(3000, 3000)
    d.ellipse([100 * ss, 100 * ss, 2900 * ss, 2900 * ss], fill=0)
    r = probe("B4 对照 真圆 r1400", save(im, "b_circle", (3000, 3000)), "b_circle")
    rec("B4 对照 真圆 r1400", "必须吸成 4C", "4C",
        f"{'4C' if r and r[0] else ('%dL/%dC'%(r[3][1],r[3][0])) if r else '-'}", bool(r and r[0]))

    # ---------------- C. 面积守恒闸是否误伤直边 ----------------
    print("[C] 面积守恒闸误伤直边")
    im, d, ss = canvas(600, 600)
    d.rectangle([150 * ss, 150 * ss, 450 * ss, 450 * ss], fill=0)
    p = save(im, "c_square", (600, 600))
    r = probe("C1 正方形 300×300", p, "c_square")
    if r:
        is_round, is_rect, dev, seg = r
        rec("C1 正方形 300×300", "吸成 3L 精确矩形", "3L", f"{seg[1]}L/{seg[0]}C", is_rect)
        _, sn = subpaths(WORK / "c_square_on" / "c_square.svg")
        pts = anchors(biggest(sn))
        ortho = all(
            abs(pts[(i + 1) % 4][0] - pts[i][0]) == 0.0
            or abs(pts[(i + 1) % 4][1] - pts[i][1]) == 0.0
            for i in range(4)
        )
        rec("C1 正方形 300×300", "每条边 dx 或 dy 严格为 0", "0", f"{ortho}", ortho)
    # 长条 800×100
    im, d, ss = canvas(900, 200)
    d.rectangle([50 * ss, 50 * ss, 850 * ss, 150 * ss], fill=0)
    r = probe("C2 长条 800×100", save(im, "c_bar800", (900, 200)), "c_bar800")
    rec("C2 长条 800×100", "吸成 3L 矩形", "3L",
        f"{r[3][1]}L/{r[3][0]}C" if r else "-", bool(r and r[1]))
    # 细长条 1200×40（边界）
    im, d, ss = canvas(1300, 200)
    d.rectangle([50 * ss, 80 * ss, 1250 * ss, 120 * ss], fill=0)
    r = probe("C3 细长条 1200×40", save(im, "c_bar1200", (1300, 200)), "c_bar1200")
    rec("C3 细长条 1200×40", "吸成 3L 矩形", "3L",
        f"{r[3][1]}L/{r[3][0]}C dev={r[2]:.3f}" if r else "-", bool(r and r[1]))

    # 纯黑整页（本来就该是矩形）
    r = probe("C4 纯黑 200px", gen_flat(0), "c_black")
    rec("C4 纯黑 200px", "整页黑块吸成 3L（正确）", "3L",
        f"{r[3][1]}L/{r[3][0]}C" if r else "-", bool(r and r[1]))

    w0 = max(len(r[0]) for r in RESULTS)
    w1 = max(len(r[1]) for r in RESULTS)
    print(f"\n{'用例':<{w0}} | {'断言':<{w1}} | {'期望':<12} | {'实际':<34} | 判定")
    print("-" * (w0 + w1 + 66))
    nfail = 0
    for c, a, e, ac, ok in RESULTS:
        nfail += ok != "PASS"
        print(f"{c:<{w0}} | {a:<{w1}} | {e:<12} | {ac[:34]:<34} | {ok}")
    print(f"\n合计 {len(RESULTS)} 条断言，FAIL {nfail}")
    print("RESULT:", "OK" if nfail == 0 else "FAIL")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
