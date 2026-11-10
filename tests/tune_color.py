"""调参：比较彩色路线参数组合的 SSIM 与体积。"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firefly import emit, engines, quality  # noqa: E402
from firefly.convert import open_image  # noqa: E402
from firefly.ir import parse_svg  # noqa: E402
from firefly.preprocess import flatten_white  # noqa: E402

CORPUS = Path(r"D:\开发\research\feasibility\input\corpus")
IDS = ["s2_flat_icon", "s5_chart", "s9_alpha_png", "r1_volcano_jpg", "s8_pixel_art"]

BASE = dict(colormode="color", hierarchical="stacked", filter_speckle=4, layer_difference=16,
            corner_threshold=60, length_threshold=4.0, splice_threshold=45)
GRID = {
    "spline_p8c8": dict(mode="spline", color_precision=8, path_precision=8),
    "spline_p4c6": dict(mode="spline", color_precision=6, path_precision=4),
    "spline_p3c6": dict(mode="spline", color_precision=6, path_precision=3),
    "polygon_p3c6": dict(mode="polygon", color_precision=6, path_precision=3),
}


def main():
    import vtracer

    rows = []
    for cid in IDS:
        src = next(CORPUS.glob(cid + ".*"))
        im = open_image(src)
        rgb = flatten_white(im)
        w, h = rgb.size
        with engines.TempDir() as tmp:
            png = tmp / "s.png"
            rgb.save(png)
            for name, extra in GRID.items():
                out = tmp / f"{name}.svg"
                params = dict(BASE, **extra)
                vtracer.convert_image_to_svg_py(str(png), str(out), **params)
                size = out.stat().st_size
                dr = parse_svg(out.read_text(encoding="utf-8", errors="replace"))
                emit.emit_pdf(dr, tmp / f"{name}.pdf")
                qc = quality.check(rgb, tmp / f"{name}.pdf", w, h)
                rows.append({
                    "id": cid, "params": name, "ssim": qc["ssim"], "flat_mae": qc["flat_mae"],
                    "svg_kb": round(size / 1024, 1), "ratio": round(size / src.stat().st_size, 3),
                    "subpaths": dr.n_subpaths,
                })
                print(f"{cid:<14}{name:<14}{qc['ssim']:.4f}{qc['flat_mae']:>8.2f}{rows[-1]['svg_kb']:>9.1f}KB{rows[-1]['ratio']:>8.2f}", flush=True)
    with open(ROOT / "_test" / "tune_color.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)


if __name__ == "__main__":
    main()
