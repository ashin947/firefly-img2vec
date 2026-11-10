"""几何吸附：把近似圆 / 椭圆 / 矩形 / 正交边的轮廓替换成精确几何。

描迹引擎把每个色块拟合成折线多边形（vtracer 的 polygon 模式）或带抖动的
贝塞尔（potrace），于是圆变成 40–80 段的 N 边形、直边变成轻微起伏的波浪，
放大看就是"歪的"。这里在几何 IR 上做一次"拟合—校验—替换"：

1. 圆：圆度、半径残差、包围盒长宽比都达标 -> 4 段精确三次贝塞尔圆；
2. 椭圆：圆度略低但仍是轴对齐椭圆 -> 4 段贝塞尔椭圆；
3. 矩形：轮廓几乎填满包围盒且四边贴合 -> 精确 4 点矩形；
4. 正交吸附：剩下的路径把近似水平 / 垂直的边掰成严格水平 / 垂直。

两条铁律：

* 保持原绕向。evenodd 的洞是靠绕向区分内外的，翻转会让洞变实心。
* 安全阀。替换前后各算一次"拟合轮廓 vs 原轮廓"的双向最大偏差，
  超过 TOL_DEV 就放弃替换、保留原路径 —— 宁可歪一点，不能改坏形状。

只改 Drawing 里的 SubPath，不动 fill / evenodd / opacity，也不合并子路径，
所以 emit 的双发射器结构完全不受影响。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .ir import Drawing, SubPath

# 四段三次贝塞尔拟合圆 / 椭圆时的控制点系数（标准值）
KAPPA = 0.5522847498

# ---- 判定阈值 ----
TOL_EDGE = 0.75         # 正交吸附：小于这个距离的两条边 / 两个顶点视为同一位置（px）
TOL_DEV = 1.0           # 安全阀基准：允许的最大轮廓偏差（px）
TOL_DEV_SLOPE = 0.0005  # 安全阀随尺寸放宽的斜率（见 _tol_for）
TOL_DEV_MAX = 2.5       # 安全阀上限（px）
CIRC_MIN = 0.90         # 圆的最小圆度 4πA/P²
ELL_FILL_LO = 0.92      # 椭圆：轮廓面积 / πab 的下限
ELL_FILL_HI = 1.08      # 椭圆：轮廓面积 / πab 的上限
RESID_MAX = 0.06        # 半径相对残差上限 std(|p-c|)/r
ASPECT_LO = 0.88        # 圆：包围盒宽高比下限
ASPECT_HI = 1.14        # 圆：包围盒宽高比上限
RECT_FILL = 0.97        # 矩形：轮廓面积 / 包围盒面积 下限
RECT_EDGE = 0.6         # 矩形：轮廓点到包围盒四边的最大距离（px）
MIN_SIDE = 4.0          # 短边小于这个值的轮廓不值得拟合（px）
MAX_ANCHORS = 2000      # 顶点太多的路径（照片类）跳过正交吸附
ORTHO_AREA_TOL = 0.03   # 正交吸附允许的最大面积变化比例（防止把描边两侧各推一半）
STRAIGHT_SHARE = 0.35   # 直线段占周长比例低于此值不做正交吸附（纯曲线没有"直角"可修）
STRAIGHT_TOL = 2.5      # 曲线段控制点离弦不超过这个距离就算"直"（px）
# 2.5 是实测标定值：potrace 给直边拟合的贝塞尔控制点会离开弦 1.7–1.9px
# （源图边界量化到像素格），圆角弧则是 6px 以上，两者分得很开。

# 扁平化弦高：粗采样用于常规判定，细采样只在粗判失败后复核，避免误杀
CHORD_COARSE = 0.35
CHORD_CAND = 0.10
CHORD_FINE = 0.08


@dataclass
class SnapStats:
    """吸附统计：各类命中数与安全阀拦下的次数。"""

    circles: int = 0
    ellipses: int = 0
    rects: int = 0
    ortho: int = 0
    rejected: int = 0
    total: int = 0

    @property
    def fitted(self) -> int:
        """被替换掉的子路径总数。"""
        return self.circles + self.ellipses + self.rects + self.ortho

    def note(self) -> str:
        """给界面用的一句话摘要，没有命中就返回空串。"""
        bits = []
        if self.circles:
            bits.append(f"圆 {self.circles}")
        if self.ellipses:
            bits.append(f"椭圆 {self.ellipses}")
        if self.rects:
            bits.append(f"矩形 {self.rects}")
        if self.ortho:
            bits.append(f"正交边 {self.ortho}")
        if not bits:
            return ""
        return "吸附 " + " / ".join(bits)


# ---------------------------------------------------------------- 采样与测量


def _anchors(sub: SubPath) -> list[tuple[float, float]]:
    """子路径的锚点序列（贝塞尔只取终点），不闭合。"""
    pts = [(float(sub.start[0]), float(sub.start[1]))]
    for s in sub.segs:
        if s[0] == "L":
            pts.append((float(s[1]), float(s[2])))
        elif s[0] == "C":
            pts.append((float(s[5]), float(s[6])))
    return pts


def _poly_only(sub: SubPath) -> bool:
    """整条子路径只有直线段（vtracer polygon 模式的输出）。"""
    return all(s[0] in ("L", "Z") for s in sub.segs)


def _bez_steps(p0, p1, p2, p3, chord, lo=2, hi=64) -> int:
    """按三次贝塞尔的平坦度反推步数：n 等分后弦高约 0.75·d/n²。

    d 是控制点到首尾弦的最大距离。必须按"段长/弯曲度"而不是按"段数"分配
    步数 —— potrace 会把近乎平直的弧合并成长段（单段可达 600px），按段数
    平均分会让长段严重欠采样，弦高被算成偏差，把好拟合误判成坏拟合。
    """
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        d = max(
            math.hypot(p1[0] - p0[0], p1[1] - p0[1]),
            math.hypot(p2[0] - p0[0], p2[1] - p0[1]),
        )
    else:
        ux, uy = dx / length, dy / length
        d = max(
            abs((p1[0] - p0[0]) * uy - (p1[1] - p0[1]) * ux),
            abs((p2[0] - p0[0]) * uy - (p2[1] - p0[1]) * ux),
        )
    if d <= chord:
        return lo
    n = int(math.ceil(math.sqrt(0.75 * d / chord)))
    return max(lo, min(hi, n))


def _flatten(sub: SubPath, counts: list[int]) -> list[tuple[float, float]]:
    """按逐段步数扁平化（counts 与「非 Z 段」一一对应，直线段步数忽略）。"""
    pts = [(float(sub.start[0]), float(sub.start[1]))]
    cur = pts[0]
    k = 0
    for s in sub.segs:
        if s[0] == "Z":
            continue
        n = counts[k] if k < len(counts) else 1
        k += 1
        if s[0] == "L":
            cur = (float(s[1]), float(s[2]))
            pts.append(cur)
            continue
        p0 = cur
        p1, p2, p3 = (s[1], s[2]), (s[3], s[4]), (s[5], s[6])
        for i in range(1, n + 1):
            t = i / n
            u = 1.0 - t
            b0, b1, b2, b3 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
            pts.append(
                (
                    b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
                    b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1],
                )
            )
        cur = p3
    return pts


def _sample(
    sub: SubPath, chord: float = 0.35, max_pts: int = 240
) -> list[tuple[float, float]]:
    """扁平化采样，弦高目标为 chord 像素，总点数不超过 max_pts。

    纯折线不需要扁平化（锚点就是精确轮廓），直接返回锚点；顶点极多的路径
    仍要抽稀，否则最近点扫描的数组会吃内存。
    """
    if _poly_only(sub):
        pts = _anchors(sub)
        if len(pts) > 2000:
            k = int(math.ceil(len(pts) / 2000.0))
            pts = pts[::k]
        return pts

    counts: list[int] = []
    cur = (float(sub.start[0]), float(sub.start[1]))
    for s in sub.segs:
        if s[0] == "Z":
            continue
        if s[0] == "L":
            counts.append(0)
            cur = (float(s[1]), float(s[2]))
            continue
        counts.append(
            _bez_steps(cur, (s[1], s[2]), (s[3], s[4]), (s[5], s[6]), chord)
        )
        cur = (s[5], s[6])

    total = sum(counts)
    if total > max_pts and total > 0:
        # 超预算就整体等比降步数（长段本来就分得多，按比例缩仍然优先保住长段）
        f = max_pts / float(total)
        counts = [max(2, int(round(c * f))) for c in counts]

    pts = _flatten(sub, counts)
    if len(pts) > 2:
        if math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 1e-6:
            pts.pop()
    return pts


def _area_perim(pts: list[tuple[float, float]]) -> tuple[float, float]:
    """鞋带公式算有符号面积，同时算闭合周长。"""
    n = len(pts)
    a = 0.0
    p = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
        p += math.hypot(x2 - x1, y2 - y1)
    return a * 0.5, p


def _solve3(m, v):
    """3×3 线性方程组（克莱姆法则），奇异时返回 None。"""
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        return None
    p, q, r = v
    dx = p * (e * i - f * h) - b * (q * i - f * r) + c * (q * h - e * r)
    dy = a * (q * i - f * r) - p * (d * i - f * g) + c * (d * r - q * g)
    dz = a * (e * r - q * h) - b * (d * r - q * g) + p * (d * h - e * g)
    return dx / det, dy / det, dz / det


def _fit_circle(
    pts: list[tuple[float, float]]
) -> tuple[float, float, float, float] | None:
    """最小二乘（Kasa）拟合圆，返回 (cx, cy, r, 相对残差)。"""
    n = len(pts)
    if n < 3:
        return None
    sx = sy = sxx = syy = sxy = sxz = syz = sz = 0.0
    for x, y in pts:
        z = x * x + y * y
        sx += x
        sy += y
        sxx += x * x
        syy += y * y
        sxy += x * y
        sxz += x * z
        syz += y * z
        sz += z
    # x²+y² = D·x + E·y + F 的最小二乘正规方程
    sol = _solve3(
        ((sxx, sxy, sx), (sxy, syy, sy), (sx, sy, float(n))),
        (sxz, syz, sz),
    )
    if sol is None:
        return None
    d, e, f = sol
    cx, cy = d / 2.0, e / 2.0
    r2 = f + cx * cx + cy * cy
    if r2 <= 1e-9:
        return None
    r = math.sqrt(r2)
    ds = [math.hypot(x - cx, y - cy) for x, y in pts]
    mean = sum(ds) / n
    var = sum((v - mean) ** 2 for v in ds) / n
    # 残差取两项：半径离散度 + 平均半径与拟合半径的偏离
    resid = max(math.sqrt(var) / r, abs(mean - r) / r)
    return cx, cy, r, resid


def _ellipse_resid(
    pts: list[tuple[float, float]], cx: float, cy: float, rx: float, ry: float
) -> tuple[float, float]:
    """轴对齐椭圆的归一化半径残差，返回 (相对标准差, 平均归一化半径)。"""
    vals = [math.hypot((x - cx) / rx, (y - cy) / ry) for x, y in pts]
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    return math.sqrt(var) / (mean if mean > 1e-9 else 1.0), mean


def _edge_dev(
    pts: list[tuple[float, float]], x0: float, y0: float, x1: float, y1: float
) -> float:
    """轮廓点到包围盒四条边的最大距离（越小越像矩形）。"""
    worst = 0.0
    for x, y in pts:
        d = min(x - x0, x1 - x, y - y0, y1 - y)
        if d > worst:
            worst = d
    return worst


# ---------------------------------------------------------------- 偏差校验


def _one_way(a, b) -> float:
    """a 上每个点到折线 b（闭合）的最短距离，返回最大值。"""
    na, nb = len(a), len(b)
    # 小规模直接上纯 Python：numpy 的调用开销比算这几十个点还贵
    if na * nb <= 1024:
        worst = 0.0
        for px, py in a:
            best = float("inf")
            for k in range(nb):
                ax, ay = b[k]
                bx, by = b[(k + 1) % nb]
                dx, dy = bx - ax, by - ay
                l2 = dx * dx + dy * dy
                if l2 < 1e-12:
                    d = math.hypot(px - ax, py - ay)
                else:
                    t = ((px - ax) * dx + (py - ay) * dy) / l2
                    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                    d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
                if d < best:
                    best = d
            if best > worst:
                worst = best
        return worst

    pa = np.asarray(a, dtype=np.float64)
    pb = np.asarray(b, dtype=np.float64)
    p0 = pb
    p1 = np.roll(pb, -1, axis=0)
    d = p1 - p0
    l2 = (d * d).sum(axis=1)
    l2[l2 < 1e-12] = 1e-12
    ax = pa[:, None, 0] - p0[None, :, 0]
    ay = pa[:, None, 1] - p0[None, :, 1]
    t = (ax * d[None, :, 0] + ay * d[None, :, 1]) / l2[None, :]
    np.clip(t, 0.0, 1.0, out=t)
    qx = p0[None, :, 0] + t * d[None, :, 0]
    qy = p0[None, :, 1] + t * d[None, :, 1]
    dist = np.hypot(pa[:, None, 0] - qx, pa[:, None, 1] - qy)
    return float(dist.min(axis=1).max())


def _max_dev(a, b) -> float:
    """两组闭合折线之间的双向最大最近距离（点到线段，不是点到点）。"""
    if len(a) < 2 or len(b) < 2:
        return 0.0
    return max(_one_way(a, b), _one_way(b, a))


def _tol_for(size: float) -> float:
    """安全阀阈值随尺寸放宽。

    描迹本身有 ±0.5px 的二值化边界噪声地板，再叠加源图的抗锯齿，一条
    "完美"的拟合实测也会差 1.0–1.1px。固定 1.0px 会把 r=1400 这种残差
    只有 1e-4 的圆判成不合格。而同样 1px 的偏差放在 2800px 的圆上（0.04%）
    和小图标上（10%）意义完全不同 —— 所以按尺寸给斜率，上限 2.5px。
    """
    return min(TOL_DEV_MAX, TOL_DEV + TOL_DEV_SLOPE * size)


def _deviation(sub: SubPath, cand: SubPath, pts, tol: float) -> float:
    """拟合轮廓与原轮廓的双向最大偏差。

    先用粗采样判；粗采样的弦高会计进偏差里（只会高估、不会低估，所以
    判过就是真过）。粗采样单侧弦高 ≤ CHORD_COARSE，双向最多高估
    2·CHORD_COARSE ≈ 0.7px —— 只有落在这个余量内的"擦边失败"才值得用
    细采样复核；差得远的就是真不合格（八边形差 15px），再算一遍只是白烧
    CPU（细采样是 O(n·m) 的最近点扫描，代价不低）。
    """
    dev = _max_dev(pts, _sample(cand, chord=CHORD_CAND, max_pts=400))
    if dev <= tol:
        return dev
    if dev > tol + 2.0 * CHORD_COARSE + 0.3:
        return dev
    fine = _max_dev(
        _sample(sub, chord=CHORD_FINE, max_pts=600),
        _sample(cand, chord=CHORD_FINE, max_pts=600),
    )
    return min(dev, fine)


def _accept(sub: SubPath, cand: SubPath, pts, tol: float) -> tuple[bool, float]:
    """安全阀：偏差不超过 tol 才认。返回 (是否通过, 实测偏差)。"""
    dev = _deviation(sub, cand, pts, tol)
    return dev <= tol, dev


def _unchanged(sub: SubPath, cand: SubPath, dev: float) -> bool:
    """候选和原路径等价（没省段数、也没挪位置）—— 不算一次吸附。

    像素画那类图每条轮廓本来就是精确矩形，照原样重写一遍没有任何收益，
    却会让界面报出几百处"吸附"，把用户误导成"改了很多"。
    """
    return dev < 1e-3 and len(cand.segs) >= len(sub.segs)


# ---------------------------------------------------------------- 精确几何


def _ring(cx: float, cy: float, rx: float, ry: float, sign: float) -> SubPath:
    """4 段三次贝塞尔闭合环。sign=+1 参数角递增，-1 递减（用来保绕向）。"""
    segs = []
    for k in range(4):
        a0 = sign * k * math.pi / 2.0
        a1 = sign * (k + 1) * math.pi / 2.0
        p0 = (cx + rx * math.cos(a0), cy + ry * math.sin(a0))
        p1 = (cx + rx * math.cos(a1), cy + ry * math.sin(a1))
        t0 = (-rx * math.sin(a0) * sign, ry * math.cos(a0) * sign)
        t1 = (-rx * math.sin(a1) * sign, ry * math.cos(a1) * sign)
        segs.append(
            (
                "C",
                p0[0] + KAPPA * t0[0],
                p0[1] + KAPPA * t0[1],
                p1[0] - KAPPA * t1[0],
                p1[1] - KAPPA * t1[1],
                p1[0],
                p1[1],
            )
        )
    segs.append(("Z",))
    return SubPath(start=(cx + rx, cy), segs=segs)


def _rect_sub(
    x0: float, y0: float, x1: float, y1: float, positive: bool
) -> SubPath:
    """精确 4 点矩形。positive=True 时角点顺序对应正面积（与原绕向一致）。"""
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if not positive:
        corners.reverse()
    segs = [("L", x, y) for x, y in corners[1:]]
    segs.append(("Z",))
    return SubPath(start=corners[0], segs=segs)


# ---------------------------------------------------------------- 整体拟合


def _fit_subpath(sub: SubPath, st: SnapStats) -> tuple[str, SubPath | None]:
    """尝试把整个子路径替换成圆 / 椭圆 / 矩形。返回 (类型, 新子路径或 None)。"""
    anchors = _anchors(sub)
    if len(anchors) < 3:
        return "", None
    pts = _sample(sub, chord=CHORD_COARSE)
    if len(pts) < 3:
        return "", None

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    bw, bh = x1 - x0, y1 - y0
    if bw < MIN_SIDE or bh < MIN_SIDE:
        return "", None

    area, perim = _area_perim(pts)
    if perim < 1e-6:
        return "", None
    aa = abs(area)
    circ = 4.0 * math.pi * aa / (perim * perim)
    aspect = bw / bh
    positive = area > 0.0
    sign = 1.0 if positive else -1.0
    tol = _tol_for(max(bw, bh))

    # 1) 圆
    if circ >= CIRC_MIN and ASPECT_LO <= aspect <= ASPECT_HI:
        fit = _fit_circle(pts)
        if fit is not None:
            cx, cy, r, resid = fit
            if resid <= RESID_MAX and r >= MIN_SIDE / 2.0:
                cand = _ring(cx, cy, r, r, sign)
                ok, dev = _accept(sub, cand, pts, tol)
                if ok:
                    if _unchanged(sub, cand, dev):
                        return "", None
                    return "circle", cand
                st.rejected += 1

    # 2) 轴对齐椭圆（半径直接取包围盒半宽 / 半高）
    # 这里刻意不看圆度：长宽比 2:1 的椭圆圆度只有 0.84、4:1 只有 0.54，
    # 用圆度当门槛等于把细长椭圆永远排除在外。改用「面积比 A/πab≈1」做粗筛
    # （O(1)，先判）+「归一化半径残差≈0」做精判：
    #   椭圆 0.99–1.01 / 残差 0.002      圆 1.0000 / 0.0001
    #   六边形 0.958 / 0.083 → 残差挡掉   八边形 1.054 / 0.040 → 安全阀挡掉
    #   矩形 1.273、圆角矩形 1.249、胶囊 1.205 → 面积比挡掉
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    rx, ry = bw / 2.0, bh / 2.0
    fill_e = aa / (math.pi * rx * ry) if rx > 0 and ry > 0 else 0.0
    if rx >= MIN_SIDE / 2.0 and ry >= MIN_SIDE / 2.0 and ELL_FILL_LO <= fill_e <= ELL_FILL_HI:
        resid, mean = _ellipse_resid(pts, cx, cy, rx, ry)
        if resid <= RESID_MAX and abs(mean - 1.0) <= RESID_MAX:
            cand = _ring(cx, cy, rx, ry, sign)
            ok, dev = _accept(sub, cand, pts, tol)
            if ok:
                if _unchanged(sub, cand, dev):
                    return "", None
                return "ellipse", cand
            st.rejected += 1

    # 3) 矩形
    fill = aa / (bw * bh)
    if fill >= RECT_FILL and _edge_dev(pts, x0, y0, x1, y1) <= RECT_EDGE:
        cand = _rect_sub(x0, y0, x1, y1, positive)
        ok, dev = _accept(sub, cand, pts, tol)
        if ok:
            if _unchanged(sub, cand, dev):
                return "", None
            return "rect", cand
        st.rejected += 1
    return "", None


# ---------------------------------------------------------------- 正交吸附


def _cluster(vals: list[float], tol: float = TOL_EDGE) -> list[float]:
    """把相差小于 tol 的坐标并成一组（组内跨度不超过 tol），返回对齐后的坐标。"""
    out = list(vals)
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    i = 0
    n = len(order)
    while i < n:
        base = vals[order[i]]
        j = i + 1
        total = base
        cnt = 1
        while j < n and vals[order[j]] - base < tol:
            total += vals[order[j]]
            cnt += 1
            j += 1
        if cnt > 1:
            mean = total / cnt
            for k in range(i, j):
                out[order[k]] = mean
        i = j
    return out


def _rebuild(sub: SubPath, old, new) -> SubPath:
    """按新锚点重写子路径。贝塞尔控制点跟着两端锚点的位移走，保持局部形状。"""
    segs = []
    for i, s in enumerate(sub.segs):
        if s[0] == "Z":
            segs.append(s)
            continue
        if i + 1 >= len(old) or i + 1 >= len(new):
            segs.append(s)
            continue
        d1 = (new[i][0] - old[i][0], new[i][1] - old[i][1])
        d2 = (new[i + 1][0] - old[i + 1][0], new[i + 1][1] - old[i + 1][1])
        if s[0] == "L":
            segs.append(("L", new[i + 1][0], new[i + 1][1]))
        else:
            segs.append(
                (
                    "C",
                    s[1] + d1[0],
                    s[2] + d1[1],
                    s[3] + d2[0],
                    s[4] + d2[1],
                    new[i + 1][0],
                    new[i + 1][1],
                )
            )
    return SubPath(start=(new[0][0], new[0][1]), segs=segs)


def _seg_is_straight(p0, p1, p2, p3) -> bool:
    """三次贝塞尔是否"实际上是一条直线"：两个控制点都贴着首尾弦。

    不能只看段类型 —— potrace 把直边也写成 C 段（圆角矩形实测 0L/12C），
    按"全是 L 段"过滤会把单色路线里真正需要拍直的边全部漏掉。
    """
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return max(
            math.hypot(p1[0] - p0[0], p1[1] - p0[1]),
            math.hypot(p2[0] - p0[0], p2[1] - p0[1]),
        ) <= STRAIGHT_TOL
    ux, uy = dx / length, dy / length
    d1 = abs((p1[0] - p0[0]) * uy - (p1[1] - p0[1]) * ux)
    d2 = abs((p2[0] - p0[0]) * uy - (p2[1] - p0[1]) * ux)
    return max(d1, d2) <= STRAIGHT_TOL


def _straight_share(sub: SubPath) -> float:
    """"实际是直线"的段占总周长的比例。

    正交吸附只对以直边为主的轮廓有意义：纯曲线（圆、椭圆、手绘弧）没有
    "直角"可修，硬把锚点往网格上推只会让墨量系统性偏移。
    段长用三次贝塞尔的经典估计 (|p0p1|+|p1p2|+|p2p3|+|p0p3|)/2，直线段时
    它恰好退化成弦长，不会出现"直段长度 > 总长"这种自相矛盾。
    """
    total = 0.0
    straight = 0.0
    cur = (float(sub.start[0]), float(sub.start[1]))
    for s in sub.segs:
        if s[0] == "Z":
            d = math.hypot(cur[0] - sub.start[0], cur[1] - sub.start[1])
            total += d
            straight += d
            cur = (float(sub.start[0]), float(sub.start[1]))
            continue
        if s[0] == "L":
            d = math.hypot(s[1] - cur[0], s[2] - cur[1])
            total += d
            straight += d
            cur = (s[1], s[2])
            continue
        p0, p1, p2, p3 = cur, (s[1], s[2]), (s[3], s[4]), (s[5], s[6])
        d = (
            math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            + math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            + math.hypot(p3[0] - p2[0], p3[1] - p2[1])
            + math.hypot(p3[0] - p0[0], p3[1] - p0[1])
        ) / 2.0
        total += d
        if _seg_is_straight(p0, p1, p2, p3):
            straight += d
        cur = p3
    return straight / total if total > 1e-9 else 1.0


def _snap_ortho(sub: SubPath) -> SubPath | None:
    """把近似水平 / 垂直的边掰成严格水平 / 垂直。没有可改的就返回 None。"""
    old = _anchors(sub)
    n = len(old)
    if n < 3 or n > MAX_ANCHORS:
        return None
    if _straight_share(sub) < STRAIGHT_SHARE:
        return None

    xs = _cluster([p[0] for p in old])
    ys = _cluster([p[1] for p in old])
    new = [(xs[i], ys[i]) for i in range(n)]

    closed = any(s[0] == "Z" for s in sub.segs)
    last = n if closed else n - 1
    for i in range(last):
        j = (i + 1) % n
        ax, ay = new[i]
        bx, by = new[j]
        dx, dy = bx - ax, by - ay
        # 只处理"差一点点"的边，真正的斜边不动
        if 0.0 < abs(dx) < TOL_EDGE:
            mx = (ax + bx) / 2.0
            new[i] = (mx, ay)
            new[j] = (mx, by)
        ax, ay = new[i]
        bx, by = new[j]
        dx, dy = bx - ax, by - ay
        if 0.0 < abs(dy) < TOL_EDGE:
            my = (ay + by) / 2.0
            new[i] = (ax, my)
            new[j] = (bx, my)

    if new == old:
        return None

    # 面积守恒闸：把一条描边两侧的锚点各推 0.5px，笔画宽度就变了 10%
    # （文字实测墨量掉 10%）。形状真该被拍直时面积几乎不动（<1%），
    # 会明显改变面积的说明这条路径本来就不是矩形边，放过它。
    a_old, _ = _area_perim(old)
    a_new, _ = _area_perim(new)
    if abs(a_old) > 1e-6 and abs(a_new - a_old) / abs(a_old) > ORTHO_AREA_TOL:
        return None

    # 快速安全阀：新旧锚点的最大位移就是两条折线（含贝塞尔，控制点跟着走）
    # 之间 Hausdorff 距离的上界 —— 贝塞尔点 t 处是控制点的凸组合，位移不超过
    # 控制点位移的最大值。位移在阈值内就直接收，省掉一次昂贵的双向最近点扫描。
    max_disp = 0.0
    for (ox, oy), (nx, ny) in zip(old, new):
        d = math.hypot(nx - ox, ny - oy)
        if d > max_disp:
            max_disp = d
    xs = [p[0] for p in old]
    ys = [p[1] for p in old]
    tol = _tol_for(max(max(xs) - min(xs), max(ys) - min(ys)))
    if max_disp > tol:
        cand = _rebuild(sub, old, new)
        ok, _dev = _accept(sub, cand, _sample(sub, chord=CHORD_FINE), tol)
        return cand if ok else None
    return _rebuild(sub, old, new)


# ---------------------------------------------------------------- 对外入口


def snap_drawing(dr: Drawing) -> SnapStats:
    """对整张图做几何吸附（原地修改 dr），返回统计。

    每个子路径独立处理，VPath 的 fill / evenodd / opacity 原样保留 ——
    evenodd 路径里的多个子路径各自拟合，绝不合并。
    """
    st = SnapStats()
    for vp in dr.paths:
        subs = []
        for sub in vp.subs:
            st.total += 1
            kind, cand = _fit_subpath(sub, st)
            if cand is not None:
                if kind == "circle":
                    st.circles += 1
                elif kind == "ellipse":
                    st.ellipses += 1
                elif kind == "rect":
                    st.rects += 1
                subs.append(cand)
                continue
            ortho = _snap_ortho(sub)
            if ortho is not None:
                st.ortho += 1
                subs.append(ortho)
            else:
                subs.append(sub)
        vp.subs = subs
    return st
