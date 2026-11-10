"""二值化与预处理（只用 numpy + Pillow）。"""

from __future__ import annotations

import numpy as np
from PIL import Image


def load_rgba(path):
    im = Image.open(path)
    im.load()
    if im.mode not in ("RGBA", "LA"):
        im = im.convert("RGBA")
    return im


def flatten_white(im):
    """RGBA -> 白底 RGB。"""
    if im.mode != "RGBA":
        return im.convert("RGB")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[3])
    return bg


def to_gray(rgb):
    return np.asarray(rgb.convert("L"), dtype=np.float64)


def _box_mean_var(a, r):
    """局部均值/方差，积分图实现，边界 replicate。"""
    k = 2 * r + 1
    p = np.pad(a, r, mode="edge")
    c = np.zeros((p.shape[0] + 1, p.shape[1] + 1))
    c[1:, 1:] = p.cumsum(0).cumsum(1)
    c2 = np.zeros_like(c)
    c2[1:, 1:] = (p * p).cumsum(0).cumsum(1)
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    s2 = c2[k:, k:] - c2[:-k, k:] - c2[k:, :-k] + c2[:-k, :-k]
    n = float(k * k)
    mean = s / n
    var = np.maximum(s2 / n - mean * mean, 0.0)
    return mean, var


def otsu(gray):
    hist, _ = np.histogram(gray, bins=256, range=(0.0, 256.0))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total <= 0:
        return 128.0
    omega = np.cumsum(hist) / total
    mu = np.cumsum(hist * np.arange(256)) / total
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    with np.errstate(divide="ignore", invalid="ignore"):
        sigma_b = np.where(denom > 0, (mu_t * omega - mu) ** 2 / denom, 0.0)
    return float(np.argmax(sigma_b))


def sauvola(gray, window=51, k=0.2, r=128.0):
    """局部阈值；窗口必须显式给（研究结论：w51 在干净图上最好）。"""
    rad = max(1, int(window) // 2)
    mean, var = _box_mean_var(gray, rad)
    std = np.sqrt(var)
    thr = mean * (1.0 + k * (std / r - 1.0))
    return gray > thr


def binarize(gray, method="otsu", window=51):
    if method == "sauvola":
        mask = sauvola(gray, window=window)
    else:
        mask = gray > otsu(gray)
    return mask


def save_pbm(mask, path):
    """P4 二进制 PBM，potrace 直接吃。"""
    black = ~np.asarray(mask, dtype=bool)
    h, w = black.shape
    pad = (8 - w % 8) % 8
    if pad:
        black = np.pad(black, ((0, 0), (0, pad)), constant_values=False)
    packed = np.packbits(black, axis=1)
    with open(path, "wb") as f:
        f.write(b"P4\n%d %d\n" % (w, h))
        f.write(packed.tobytes())
