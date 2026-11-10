"""质量门：把 PDF 栅格化回来和原图比，给出 A/B/C 分级。"""

from __future__ import annotations

import numpy as np
from PIL import Image

from .preprocess import flatten_white, load_rgba

C1 = (0.01 * 255.0) ** 2
C2 = (0.03 * 255.0) ** 2


def _box(a, r):
    k = 2 * r + 1
    p = np.pad(a, r, mode="edge")
    c = np.zeros((p.shape[0] + 1, p.shape[1] + 1))
    c[1:, 1:] = p.cumsum(0).cumsum(1)
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s / float(k * k)


def ssim(a, b, r=3):
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    ma, mb = _box(a, r), _box(b, r)
    va = np.maximum(_box(a * a, r) - ma * ma, 0.0)
    vb = np.maximum(_box(b * b, r) - mb * mb, 0.0)
    cov = _box(a * b, r) - ma * mb
    s = ((2 * ma * mb + C1) * (2 * cov + C2)) / (
        (ma * ma + mb * mb + C1) * (va + vb + C2)
    )
    return float(s.mean())


def rasterize_pdf(pdf_path, width, height):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    scale = width / max(1e-6, float(page.get_width()))
    img = page.render(scale=scale).to_pil().convert("RGB")
    doc.close()
    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    return img


def grade_of(ssim_v, flat_mae):
    if ssim_v >= 0.98 and flat_mae < 1.5:
        return "A"
    if ssim_v >= 0.92 and flat_mae < 8.0:
        return "B"
    return "C"


def check(src_path_or_img, pdf_path, width, height):
    im = src_path_or_img
    if not isinstance(im, Image.Image):
        im = load_rgba(im)
    src = flatten_white(im)
    if src.size != (width, height):
        src = src.resize((width, height), Image.LANCZOS)
    out = rasterize_pdf(pdf_path, width, height)

    gs = np.asarray(src.convert("L"), dtype=np.float64)
    go = np.asarray(out.convert("L"), dtype=np.float64)

    ss = ssim(gs, go)

    mu = _box(gs, 2)
    dev = np.abs(gs - mu)
    flat = dev < 1.0
    frac = float(flat.mean())
    fmae = float(np.abs(gs - go)[flat].mean()) if frac > 0.02 else 0.0

    gy, gx = np.gradient(gs)
    mag = np.hypot(gx, gy)
    smooth = float(((mag > 0.4) & (mag < 3.0)).mean())

    grade = grade_of(ss, fmae)
    notes = []
    if grade == "C":
        notes.append(f"SSIM {ss:.3f} / 平坦区误差 {fmae:.2f} 偏低")
    if smooth > 0.25 and fmae >= 1.5:
        notes.append("含渐变或柔和阴影，可能被压成色块")
    if ss >= 0.98 and fmae < 1.5:
        notes.append("接近原图")
    return {
        "ssim": round(ss, 4),
        "flat_mae": round(fmae, 2),
        "smooth_frac": round(smooth, 3),
        "grade": grade,
        "note": "；".join(notes),
    }
