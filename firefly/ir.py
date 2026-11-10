"""几何 IR：与后端无关的路径集合。SVG 与 PDF 都从这里发射。

单位统一为 px（96 dpi），y 轴向下。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


@dataclass
class SubPath:
    start: tuple[float, float]
    segs: list[tuple] = field(default_factory=list)

    def flatten(self, steps: int = 10) -> list[tuple[float, float]]:
        pts = [self.start]
        cur = self.start
        for s in self.segs:
            if s[0] == "L":
                cur = (s[1], s[2])
                pts.append(cur)
            elif s[0] == "C":
                p0, p1, p2, p3 = cur, (s[1], s[2]), (s[3], s[4]), (s[5], s[6])
                for i in range(1, steps + 1):
                    t = i / steps
                    u = 1.0 - t
                    b0, b1, b2, b3 = u**3, 3 * u * u * t, 3 * u * t * t, t**3
                    pts.append(
                        (
                            b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
                            b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1],
                        )
                    )
                cur = p3
        return pts


@dataclass
class VPath:
    subs: list[SubPath]
    fill: str = "#000000"
    evenodd: bool = False
    opacity: float = 1.0


@dataclass
class Drawing:
    width: float
    height: float
    paths: list[VPath] = field(default_factory=list)
    route: str = ""

    @property
    def n_subpaths(self) -> int:
        return sum(len(p.subs) for p in self.paths)


IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def scale_drawing(drawing: Drawing, k: float) -> None:
    """整体等比缩放（就地修改）。

    超采样描迹后用它把坐标还原到原图尺度：先在 k 倍图上描，再把所有坐标
    乘 1/k，得到的是"同样尺寸、但边缘描述更细"的矢量。
    """
    for vp in drawing.paths:
        for s in vp.subs:
            s.start = (s.start[0] * k, s.start[1] * k)
            s.segs = [
                seg if seg[0] == "Z" else (seg[0],) + tuple(v * k for v in seg[1:])
                for seg in s.segs
            ]
    drawing.width *= k
    drawing.height *= k


def _poly_points(s: SubPath) -> list[tuple[float, float]]:
    """子路径的端点序列（三次贝塞尔只取终点），够算包围盒和近似面积。"""
    pts = [s.start]
    cur = s.start
    for seg in s.segs:
        if seg[0] == "Z":
            continue
        cur = (seg[1], seg[2]) if seg[0] == "L" else (seg[5], seg[6])
        pts.append(cur)
    return pts


def prune_specks(drawing: Drawing, ref: float = 1600.0,
                 min_dim: float = 3.5, min_area: float = 40.0) -> int:
    """剪掉亚像素级碎块，返回删掉的子路径数。

    vtracer 关掉碎块过滤（filter_speckle=0）时会把抗锯齿边缘拆成成千上万个
    1–2px 的小岛，肉眼看不见却占掉大半体积。这里在几何 IR 上按包围盒 + 面积
    剪掉它们，文字笔画（3px 以上）不受影响。

    阈值按长边缩放：ref 是标定基准（1600px）。小图收紧、大图放宽，
    但限制在 0.35–2.5 倍之间，避免极端尺寸误伤正常细节。
    """
    k = ref / 1600.0
    k = 0.35 if k < 0.35 else (2.5 if k > 2.5 else k)
    dmin = min_dim * k
    amin = min_area * k * k

    dropped = 0
    kept = []
    for vp in drawing.paths:
        subs = []
        for s in vp.subs:
            pts = _poly_points(s)
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if max(xs) - min(xs) < dmin and max(ys) - min(ys) < dmin:
                a = 0.0
                for i in range(len(pts) - 1):
                    a += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
                if abs(a) * 0.5 < amin:
                    dropped += 1
                    continue
            subs.append(s)
        if subs:
            vp.subs = subs
            kept.append(vp)
    drawing.paths = kept
    return dropped


def mat_mul(m, n):
    """返回 m∘n：先应用 n 再应用 m。"""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def mat_apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


_XF = re.compile(r"(matrix|translate|scale|rotate)\s*\(([^)]*)\)")


def parse_transform(text):
    m = IDENT
    if not text:
        return m
    for name, args in _XF.findall(text):
        v = [float(x) for x in re.split(r"[,\s]+", args.strip()) if x]
        if not v:
            continue
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate":
            t = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            sy = v[1] if len(v) > 1 else v[0]
            t = (v[0], 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "rotate":
            a = math.radians(v[0])
            ca, sa = math.cos(a), math.sin(a)
            rot = (ca, sa, -sa, ca, 0.0, 0.0)
            if len(v) >= 3:
                cx, cy = v[1], v[2]
                t = mat_mul(
                    (1.0, 0.0, 0.0, 1.0, cx, cy),
                    mat_mul(rot, (1.0, 0.0, 0.0, 1.0, -cx, -cy)),
                )
            else:
                t = rot
        else:
            continue
        m = mat_mul(m, t)
    return m


_TOK = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def _arc_pts(x1, y1, rx, ry, phi, large, sweep, x2, y2):
    """SVG 椭圆弧 -> 折线（端点参数化，按标准算法转中心参数化）。"""
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x2, y2)]
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cp * dx + sp * dy
    y1p = -sp * dx + cp * dy
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2.0
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2.0

    def ang(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        n = math.hypot(ux, uy) * math.hypot(vx, vy)
        a = math.acos(max(-1.0, min(1.0, dot / n))) if n else 0.0
        return -a if ux * vy - uy * vx < 0 else a

    th1 = ang(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = ang(
        (x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry
    )
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi
    n = max(2, int(abs(dth) / (math.pi / 16)) + 1)
    out = []
    for k in range(1, n + 1):
        th = th1 + dth * k / n
        ex, ey = rx * math.cos(th), ry * math.sin(th)
        out.append((cp * ex - sp * ey + cx, sp * ex + cp * ey + cy))
    return out


def parse_path_d(d, m=IDENT):
    """解析 SVG path 的 d 属性，返回已应用变换 m 的 SubPath 列表。"""
    toks = _TOK.findall(d or "")
    i, n = 0, len(toks)
    subs = []
    cur = start = (0.0, 0.0)
    sp = None
    cmd = None
    last_c2 = last_q = None

    def f():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    def pt(rel, px, py):
        return (cur[0] + px, cur[1] + py) if rel else (px, py)

    while i < n:
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
        elif cmd is None:
            break
        if cmd is None:
            break
        C = cmd.upper()
        rel = cmd.islower()
        if C == "Z":
            if sp is not None:
                sp.segs.append(("Z",))
            cur = start
            last_c2 = last_q = None
            cmd = None
            continue
        if C == "M":
            x, y = f(), f()
            cur = pt(rel, x, y)
            start = cur
            sp = SubPath(mat_apply(m, *cur))
            subs.append(sp)
            last_c2 = last_q = None
            cmd = "l" if rel else "L"
            continue
        if sp is None:
            sp = SubPath(mat_apply(m, *cur))
            subs.append(sp)
        if C == "L":
            x, y = f(), f()
            cur = pt(rel, x, y)
            sp.segs.append(("L", *mat_apply(m, *cur)))
            last_c2 = last_q = None
        elif C == "H":
            x = f()
            cur = (cur[0] + x, cur[1]) if rel else (x, cur[1])
            sp.segs.append(("L", *mat_apply(m, *cur)))
            last_c2 = last_q = None
        elif C == "V":
            y = f()
            cur = (cur[0], cur[1] + y) if rel else (cur[0], y)
            sp.segs.append(("L", *mat_apply(m, *cur)))
            last_c2 = last_q = None
        elif C in ("C", "S"):
            if C == "C":
                c1 = pt(rel, f(), f())
            else:
                c1 = (
                    (2 * cur[0] - last_c2[0], 2 * cur[1] - last_c2[1])
                    if last_c2
                    else cur
                )
            c2 = pt(rel, f(), f())
            end = pt(rel, f(), f())
            sp.segs.append(
                ("C", *mat_apply(m, *c1), *mat_apply(m, *c2), *mat_apply(m, *end))
            )
            last_c2, cur, last_q = c2, end, None
        elif C in ("Q", "T"):
            q = pt(rel, f(), f()) if C == "Q" else (
                (2 * cur[0] - last_q[0], 2 * cur[1] - last_q[1]) if last_q else cur
            )
            end = pt(rel, f(), f())
            c1 = (cur[0] + 2 / 3 * (q[0] - cur[0]), cur[1] + 2 / 3 * (q[1] - cur[1]))
            c2 = (end[0] + 2 / 3 * (q[0] - end[0]), end[1] + 2 / 3 * (q[1] - end[1]))
            sp.segs.append(
                ("C", *mat_apply(m, *c1), *mat_apply(m, *c2), *mat_apply(m, *end))
            )
            last_q, cur, last_c2 = q, end, None
        elif C == "A":
            rx, ry, phi, la, sw = f(), f(), f(), f(), f()
            end = pt(rel, f(), f())
            for px, py in _arc_pts(cur[0], cur[1], rx, ry, phi, bool(la), bool(sw), *end):
                sp.segs.append(("L", *mat_apply(m, px, py)))
            cur = end
            last_c2 = last_q = None
        else:
            i += 1
    return subs


_UNIT = {"": 1.0, "px": 1.0, "pt": 4.0 / 3.0, "pc": 16.0, "in": 96.0, "mm": 96.0 / 25.4, "cm": 96.0 / 2.54}


def _len(v, default=0.0):
    """把 SVG 长度字符串换成 px（关键：potrace 写 pt，必须 ×4/3）。"""
    if not v:
        return default
    m = re.match(r"\s*(-?[\d.]+)\s*([a-z]*)\s*$", v)
    if not m:
        return default
    return float(m.group(1)) * _UNIT.get(m.group(2).lower(), 1.0)


def norm_color(c):
    if not c or c == "none":
        return None
    c = c.strip()
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) >= 6:
            return "#" + h[:6].upper()
        return "#000000"
    m = re.match(r"rgba?\(([^)]*)\)", c)
    if m:
        v = [x.strip() for x in m.group(1).split(",")]
        try:
            r, g, b = (int(round(float(x))) for x in v[:3])
            return "#%02X%02X%02X" % (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
        except (ValueError, IndexError):
            return "#000000"
    named = {"black": "#000000", "white": "#FFFFFF", "red": "#FF0000", "green": "#008000", "blue": "#0000FF"}
    return named.get(c.lower())


def parse_svg(text):
    """把 potrace / vtracer 输出的 SVG 转成 Drawing。"""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(text)
    vb = root.get("viewBox")
    if vb:
        p = [float(x) for x in re.split(r"[,\s]+", vb.strip()) if x]
        w, h = (p[2], p[3]) if len(p) == 4 else (p[-2], p[-1])
    else:
        w = _len(root.get("width"), 0.0)
        h = _len(root.get("height"), 0.0)
    dr = Drawing(width=w or 1.0, height=h or 1.0)
    stack = [(root, IDENT, "#000000", False, 1.0)]
    while stack:
        el, pm, pfill, peven, pop = stack.pop()
        tag = el.tag.split("}")[-1]
        if tag in ("defs", "metadata", "title", "desc", "style"):
            continue
        m = mat_mul(pm, parse_transform(el.get("transform")))
        fill = el.get("fill") or pfill
        fr = el.get("fill-rule")
        even = (fr == "evenodd") if fr else peven
        op = el.get("opacity") or el.get("fill-opacity")
        try:
            opacity = float(op) if op else pop
        except ValueError:
            opacity = pop
        if tag == "path":
            col = norm_color(fill)
            subs = [s for s in parse_path_d(el.get("d"), m) if s.segs]
            if col and subs and opacity > 0.003:
                dr.paths.append(VPath(subs=subs, fill=col, evenodd=even, opacity=opacity))
        for ch in reversed(el):
            stack.append((ch, m, fill, even, opacity))
    return dr

