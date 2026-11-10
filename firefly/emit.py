"""双发射器：同一个 Drawing 分别输出 SVG 与 PDF（不串联）。"""

from __future__ import annotations

from pathlib import Path

PT_PER_PX = 0.75  # 96 dpi 的 px -> PDF pt


def _n(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _d(sub):
    out = [f"M{_n(sub.start[0])} {_n(sub.start[1])}"]
    for s in sub.segs:
        if s[0] == "L":
            out.append(f"L{_n(s[1])} {_n(s[2])}")
        elif s[0] == "C":
            out.append(
                f"C{_n(s[1])} {_n(s[2])} {_n(s[3])} {_n(s[4])} {_n(s[5])} {_n(s[6])}"
            )
        elif s[0] == "Z":
            out.append("Z")
    return "".join(out)


def emit_svg(dr, path):
    w, h = _n(dr.width), _n(dr.height)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"'
        f' viewBox="0 0 {w} {h}" shape-rendering="geometricPrecision">',
    ]
    for p in dr.paths:
        attrs = f'fill="{p.fill}"'
        if p.evenodd:
            attrs += ' fill-rule="evenodd"'
        if p.opacity < 0.999:
            attrs += f' fill-opacity="{p.opacity:.3f}"'
        parts.append(f'<path d="{"".join(_d(s) for s in p.subs)}" {attrs}/>')
    parts.append("</svg>")
    text = "\n".join(parts) + "\n"
    Path(path).write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def emit_pdf(dr, path):
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas as rl

    c = rl.Canvas(str(path), pagesize=(dr.width * PT_PER_PX, dr.height * PT_PER_PX))
    c.setPageCompression(1)
    c.translate(0, dr.height * PT_PER_PX)
    c.scale(PT_PER_PX, -PT_PER_PX)
    alpha = any(p.opacity < 0.999 for p in dr.paths)
    for p in dr.paths:
        pth = c.beginPath()
        for sub in p.subs:
            pth.moveTo(sub.start[0], sub.start[1])
            closed = False
            for s in sub.segs:
                if s[0] == "L":
                    pth.lineTo(s[1], s[2])
                elif s[0] == "C":
                    pth.curveTo(s[1], s[2], s[3], s[4], s[5], s[6])
                elif s[0] == "Z":
                    closed = True
            if closed:
                pth.close()
        c.setFillColor(HexColor(p.fill))
        if alpha:
            c.setFillAlpha(p.opacity)
        try:
            c.drawPath(pth, stroke=0, fill=1, fillMode=0 if p.evenodd else 1)
        except TypeError:
            c.drawPath(pth, stroke=0, fill=1)
    c.showPage()
    c.save()
    return Path(path).stat().st_size
