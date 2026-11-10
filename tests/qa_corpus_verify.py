"""QA 独立回归：真实语料 15 张，吸附开 / 关各跑一次，输出对比表。

计时口径（第 2 轮修正）：亚秒级整图耗时里 PDF 栅格化/进程调度的抖动比信号大
（同一配置 7 次实测 0.387~0.525s），单次测量会周期性误报。改为：
  * 整图耗时：报告单次值，但 15% 阈值只对「基准 >1.0s」的图生效；
  * 吸附阶段耗时：直接对同一份 IR 连测 3 次取 min，避开整图噪声。

产物：
  _test/qa/corpus_off/  吸附关闭的 SVG/PDF
  _test/qa/corpus_on/   吸附开启的 SVG/PDF
  _test/qa/corpus_qa.csv / .json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firefly import geom  # noqa: E402
from firefly.convert import Options, convert  # noqa: E402
from firefly.ir import parse_svg, prune_specks  # noqa: E402

CORPUS = ROOT.parent / "research" / "feasibility" / "input" / "corpus"
OUT = ROOT / "_test" / "qa"
TIME_GATE_SEC = 1.0   # 只对基准 >=1s 的图检查 15% 增幅
TIME_GATE_PCT = 15.0


def snap_ms(svg_path: Path, color: bool, reps: int = 3) -> float:
    """吸附阶段耗时（min of reps）：解析一次，重复计时，避开整图噪声。"""
    txt = svg_path.read_text(encoding="utf-8")
    best = float("inf")
    for _ in range(reps):
        dr = parse_svg(txt)
        if color:
            prune_specks(dr, ref=max(dr.width, dr.height))
        t0 = time.perf_counter()
        geom.snap_drawing(dr)
        best = min(best, (time.perf_counter() - t0) * 1000.0)
    return best


def main() -> int:
    rows = []
    imgs = sorted(CORPUS.glob("*.*"))
    print(f"语料 {len(imgs)} 张")
    print(f"{'图片':<22}{'路线':<6}{'SSIM关':>8}{'SSIM开':>8}{'Δ':>9}{'等级':>8}"
          f"{'耗时关':>8}{'耗时开':>8}{'耗时判定':>10}{'吸附ms':>8}{'体积Δ%':>8}{'子路径':>8}")
    for p in imgs:
        r_off = convert(p, OUT / "corpus_off", Options(snap=False))
        r_on = convert(p, OUT / "corpus_on", Options(snap=True))
        if not (r_off.ok and r_on.ok):
            print(f"{p.name:<22} 失败 off={r_off.error} on={r_on.error}")
            rows.append({"img": p.name, "ok": False,
                         "err_off": r_off.error, "err_on": r_on.error})
            continue
        ds = r_on.ssim - r_off.ssim
        dt = (r_on.seconds - r_off.seconds) / max(1e-6, r_off.seconds) * 100
        dv = (r_on.svg_bytes - r_off.svg_bytes) / max(1, r_off.svg_bytes) * 100
        color = r_on.mode == "彩色"
        ms = snap_ms(OUT / "corpus_off" / (p.stem + ".svg"), color=color)
        gated = r_off.seconds >= TIME_GATE_SEC
        time_ok = (not gated) or dt <= TIME_GATE_PCT
        row = {
            "img": p.name, "ok": True, "mode": r_on.mode, "preset": r_on.preset,
            "ssim_off": r_off.ssim, "ssim_on": r_on.ssim, "d_ssim": round(ds, 4),
            "grade_off": r_off.grade, "grade_on": r_on.grade,
            "sec_off": r_off.seconds, "sec_on": r_on.seconds, "d_sec_pct": round(dt, 1),
            "time_gated": gated, "time_ok": time_ok, "snap_ms": round(ms, 1),
            "svg_off": r_off.svg_bytes, "svg_on": r_on.svg_bytes,
            "d_svg_pct": round(dv, 1), "pdf_off": r_off.pdf_bytes, "pdf_on": r_on.pdf_bytes,
            "subpaths_off": r_off.subpaths, "subpaths_on": r_on.subpaths,
            "snapped": r_on.snapped, "flat_mae_off": r_off.flat_mae,
            "flat_mae_on": r_on.flat_mae, "note": r_on.note,
        }
        rows.append(row)
        tag = ("+%.0f%% %s" % (dt, "OK" if time_ok else "FAIL")) if gated else "n/a(<1s)"
        print(f"{p.name:<22}{r_on.mode:<6}{r_off.ssim:>8.4f}{r_on.ssim:>8.4f}{ds:>+9.4f}"
              f"{r_off.grade + '->' + r_on.grade:>8}{r_off.seconds:>8.2f}{r_on.seconds:>8.2f}"
              f"{tag:>10}{ms:>8.1f}{dv:>+8.1f}{r_on.snapped:>8}")

    (OUT / "corpus_qa.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    with (OUT / "corpus_qa.csv").open("w", encoding="utf-8") as f:
        keys = list(rows[0]) if rows else []
        f.write(",".join(keys) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(k, "")) for k in keys) + "\n")

    ok = [r for r in rows if r.get("ok")]
    bad_grade = [r["img"] for r in ok if r["grade_on"] != r["grade_off"]]
    bad_ssim = [(r["img"], r["d_ssim"]) for r in ok if r["d_ssim"] < -0.005]
    slow = [(r["img"], r["d_sec_pct"]) for r in ok if not r["time_ok"]]
    print("\n等级退化:", bad_grade or "无")
    print("SSIM 下降 >0.005:", bad_ssim or "无")
    print(f"耗时增幅 >{TIME_GATE_PCT}%（仅基准>{TIME_GATE_SEC}s）:", slow or "无")
    print("RESULT:", "OK" if not (bad_grade or bad_ssim or slow) else "FAIL")
    return 0 if not (bad_grade or bad_ssim or slow) else 1


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"总耗时 {time.time() - t0:.1f}s")
    sys.exit(rc)
