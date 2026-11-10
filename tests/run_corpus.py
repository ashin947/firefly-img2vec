"""语料回归：对 given 目录下所有图片跑转换，输出 CSV 到 stdout 并写 out/corpus.csv。"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firefly.convert import Options, convert  # noqa: E402

IN_DIR = ROOT.parent / "research" / "feasibility" / "input" / "corpus"
OUT_DIR = ROOT / "_test" / "corpus"
FIELDS = [
    "id", "mode", "grade", "ssim", "flat_mae", "ratio", "subpaths",
    "svg_bytes", "pdf_bytes", "seconds", "note", "error",
]


def main():
    files = sorted(p for p in IN_DIR.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif"})
    opts = Options()
    rows = []
    for f in files:
        t = time.time()
        r = convert(f, OUT_DIR, opts)
        rows.append({
            "id": f.stem,
            "mode": r.mode,
            "grade": r.grade,
            "ssim": r.ssim,
            "flat_mae": r.flat_mae,
            "ratio": round(r.svg_bytes / r.src_bytes, 3) if r.src_bytes else 0,
            "subpaths": r.subpaths,
            "svg_bytes": r.svg_bytes,
            "pdf_bytes": r.pdf_bytes,
            "seconds": round(time.time() - t, 2),
            "note": r.note,
            "error": r.error,
        })
        print(f"{f.stem:<20}{r.mode or '-':<6}{r.grade:<3}{r.ssim:>7.4f}{rows[-1]['ratio']:>7.2f}{r.subpaths:>7}  {r.note or r.error}", flush=True)
    (ROOT / "_test").mkdir(parents=True, exist_ok=True)
    with open(ROOT / "_test" / "corpus.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
