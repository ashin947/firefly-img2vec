"""验证输出确实是矢量：PDF 无内嵌位图，SVG 只有 path。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pypdf import PdfReader  # noqa: E402

from firefly.convert import Options, convert  # noqa: E402

# 语料不在本仓库里，而是同级目录 research/feasibility/input/corpus。
# 从 ROOT 相对解析，换机器 / 换盘符都不用改代码。
CORPUS = ROOT.parent / "research" / "feasibility" / "input" / "corpus"
CASES = [("s1_bw_logo", "单色线条"), ("s2_flat_icon", "彩色平涂"), ("s4_tech_drawing", "单色线条")]
OUT = ROOT / "_test" / "vector"


def main() -> int:
    if not CORPUS.is_dir():
        print(f"找不到语料目录：{CORPUS}")
        print("（应从 tests/check_vector.py 所在的仓库根向上一级去找 "
              "research/feasibility/input/corpus）")
        return 2
    bad = 0
    for cid, mode in CASES:
        found = sorted(CORPUS.glob(cid + ".*"))
        if not found:
            print(f"{cid}: 语料缺失（{CORPUS} 下找不到 {cid}.*）")
            bad += 1
            continue
        src = found[0]
        r = convert(src, OUT, Options(mode={"单色线条": "单色", "彩色平涂": "彩色"}[mode]))
        if not r.ok:
            print(f"{cid}: 转换失败 {r.error}")
            bad += 1
            continue
        reader = PdfReader(r.pdf)
        images = 0
        for page in reader.pages:
            res = page.get("/Resources") or {}
            xo = res.get("/XObject") or {}
            for name in xo:
                if xo[name].get("/Subtype") == "/Image":
                    images += 1
        svg = Path(r.svg).read_text(encoding="utf-8")
        has_image = "<image" in svg
        n_path = svg.count("<path")
        ok = images == 0 and not has_image and n_path > 0
        bad += 0 if ok else 1
        print(f"{cid:<16} 等级 {r.grade}  PDF 图像对象 {images}  SVG <image> {has_image}  "
              f"path {n_path}  {r.svg_bytes}B/{r.pdf_bytes}B  {'OK' if ok else 'FAIL'}")
    print("OK" if bad == 0 else "FAIL")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
