"""命令行入口（无 GUI，便于批处理和自测）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import engines
from .convert import Options, convert


def build_parser():
    ap = argparse.ArgumentParser(prog="img2vec", description="位图转真矢量 SVG/PDF")
    ap.add_argument("inputs", nargs="*", help="输入图片（png/jpg/bmp/webp/tif…）")
    ap.add_argument("-o", "--out", default="out", help="输出目录")
    ap.add_argument("--mode", default="自动", choices=["自动", "单色", "彩色"])
    ap.add_argument("--binarize", default="otsu", choices=["otsu", "sauvola"])
    ap.add_argument("--window", type=int, default=51, help="Sauvola 窗口（奇数，需显式给）")
    ap.add_argument("--mono-preset", default="标准", choices=list(engines.POTRACE_PRESETS))
    ap.add_argument("--color-preset", default="标准", choices=list(engines.VTRACER_PRESETS))
    ap.add_argument("--invert", action="store_true", help="反色后再描迹（白字黑底用）")
    ap.add_argument("--no-snap", action="store_true",
                    help="关闭几何吸附（默认开启：把近似圆/方/正交边吸附成精确几何）")
    ap.add_argument("--supersample", type=int, default=1, choices=[1, 2, 3],
                    help="超采样倍数：2/3 先放大再描迹，边缘更顺；体积与耗时同倍增长")
    ap.add_argument("--no-qc", action="store_true", help="跳过质量检查")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.inputs:
        build_parser().print_help()
        return 2
    opts = Options(
        mode=args.mode,
        binarize=args.binarize,
        window=args.window,
        mono_preset=args.mono_preset,
        color_preset=args.color_preset,
        invert=args.invert,
        snap=not args.no_snap,
        supersample=args.supersample,
        do_qc=not args.no_qc,
    )
    bad = 0
    print(f"{'文件':<22}{'路线':<8}{'等级':<5}{'SSIM':>7}{'体积比':>8}  说明")
    for src in args.inputs:
        r = convert(src, args.out, opts, progress=None)
        if not r.ok:
            bad += 1
            print(f"{Path(src).name:<22}{'-':<8}{'失败':<5}{'-':>7}{'-':>8}  {r.error}")
            continue
        ratio = (r.svg_bytes / r.src_bytes) if r.src_bytes else 0.0
        print(
            f"{Path(src).name:<22}{r.mode:<8}{r.grade:<5}{r.ssim:>7.4f}{ratio:>8.2f}  "
            f"{r.preset} {r.note}"
        )
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
