"""转换编排：分类 -> 引擎 -> IR -> SVG/PDF -> 质量门。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from . import emit, engines, geom, preprocess, quality
from .ir import parse_svg, prune_specks, scale_drawing


@dataclass
class Options:
    mode: str = "自动"            # 自动 / 单色 / 彩色
    binarize: str = "otsu"        # otsu / sauvola
    window: int = 51
    mono_preset: str = "标准"
    color_preset: str = "标准"
    invert: bool = False
    snap: bool = True             # 几何吸附（圆/方不歪）
    supersample: int = 1          # 超采样倍数：1=关，2/3=先放大再描迹，边缘更顺
    do_qc: bool = True


@dataclass
class Result:
    src: str
    ok: bool = False
    error: str = ""
    mode: str = ""
    preset: str = ""
    svg: str = ""
    pdf: str = ""
    svg_bytes: int = 0
    pdf_bytes: int = 0
    src_bytes: int = 0
    subpaths: int = 0
    snapped: int = 0
    grade: str = "-"
    ssim: float = 0.0
    flat_mae: float = 0.0
    note: str = ""
    seconds: float = 0.0


def open_image(path):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    im.load()
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    return im


def _stats(im):
    rgb = preprocess.flatten_white(im)
    small = rgb.copy()
    small.thumbnail((320, 320), Image.LANCZOS)
    a = np.asarray(small, dtype=np.int16).reshape(-1, 3)
    if len(a) == 0:
        return 0.0, 1
    sat = a.max(axis=1) - a.min(axis=1)
    q = (a // 16).astype(np.int32)
    return float((sat > 16).mean()), int(len(np.unique(q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2])))


def classify(im) -> str:
    """判断走单色还是彩色路线。"""
    sat_frac, ncol = _stats(im)
    if sat_frac < 0.02 or ncol <= 24:
        return "mono"
    return "color"


def convert(src, out_dir, opts: Options, progress=None) -> Result:
    t0 = time.time()
    src = Path(src)
    res = Result(src=str(src))
    res.src_bytes = src.stat().st_size if src.exists() else 0

    def say(msg):
        if progress:
            progress(msg)

    try:
        im = open_image(src)
        w, h = im.size
        mode = opts.mode
        if mode in ("", "自动", None):
            mode = classify(im)
            say(f"自动判定：{'单色线条' if mode == 'mono' else '彩色'}")
        mode = "mono" if mode in ("单色", "单色线条", "mono") else "color"

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        svg_path = out_dir / (src.stem + ".svg")
        pdf_path = svg_path.with_suffix(".pdf")

        with engines.TempDir() as tmp:
            ss = 1
            if mode == "mono":
                res.mode, res.preset = "单色", opts.mono_preset
                say("二值化…")
                gray = preprocess.to_gray(preprocess.flatten_white(im))
                mask = preprocess.binarize(gray, opts.binarize, opts.window)
                if opts.invert:
                    mask = ~mask
                pbm = tmp / "mask.pbm"
                preprocess.save_pbm(mask, pbm)
                say("potrace 描迹…")
                svg_text = engines.trace_mono(pbm, tmp / "mono.svg", opts.mono_preset)
            else:
                res.mode, res.preset = "彩色", opts.color_preset
                png = tmp / "src.png"
                # 透明像素合到白底：vtracer 直接吃 RGBA 会把 alpha 也当色层，路径数暴涨
                src_img = preprocess.flatten_white(im)
                ss = max(1, int(opts.supersample or 1))
                if ss > 1:
                    # 源图边缘只有 1px 抗锯齿，原生分辨率描迹会把这 1px 台阶原样
                    # 描成折线。先放大再描、最后把坐标缩回来，边缘就顺了。
                    say(f"超采样 ×{ss}…")
                    src_img = src_img.resize((w * ss, h * ss), Image.LANCZOS)
                src_img.save(png)
                say("vtracer 描迹…")
                svg_text = engines.trace_color(png, tmp / "color.svg", opts.color_preset)

            say("解析几何 IR…")
            dr = parse_svg(svg_text)
            if not dr.paths:
                raise RuntimeError("描迹结果为空（可能阈值把图判成全黑/全白）")
            if mode == "color":
                if ss > 1:
                    scale_drawing(dr, 1.0 / ss)
                prune_specks(dr, ref=max(w, h))
            # 两条路线都要吸附：折线多边形（vtracer）和带抖动的贝塞尔（potrace）
            # 都会把圆切成 N 边形、把直边切成波浪，这里换成精确几何。
            if opts.snap:
                say("几何吸附…")
                res.snapped = geom.snap_drawing(dr).fitted
            res.subpaths = dr.n_subpaths

            say("输出 SVG / PDF…")
            res.svg_bytes = emit.emit_svg(dr, svg_path)
            res.pdf_bytes = emit.emit_pdf(dr, pdf_path)
            res.svg, res.pdf = str(svg_path), str(pdf_path)

            if opts.do_qc:
                say("质量检查…")
                qc = quality.check(im, pdf_path, w, h)
                res.grade, res.ssim = qc["grade"], qc["ssim"]
                res.flat_mae, res.note = qc["flat_mae"], qc["note"]
            if res.snapped:
                sn = f"吸附 {res.snapped} 处"
                res.note = f"{res.note}；{sn}" if res.note else sn
            if res.src_bytes and res.svg_bytes / res.src_bytes >= 3:
                big = f"SVG 体积是原图的 {res.svg_bytes / res.src_bytes:.1f} 倍"
                res.note = f"{res.note}；{big}" if res.note else big
        res.ok = True
    except Exception as exc:  # 单张失败不应中断批量
        res.error = f"{type(exc).__name__}: {exc}"
        for p in (res.svg, res.pdf):
            if p and Path(p).exists():
                Path(p).unlink(missing_ok=True)
        res.svg = res.pdf = ""
    res.seconds = round(time.time() - t0, 2)
    return res
