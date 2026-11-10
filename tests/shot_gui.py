"""把真实 Tk 窗口截图存成 PNG，供人眼/视觉模型核对。

用法：python tests/shot_gui.py [输出路径]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab  # noqa: E402

from firefly.gui import App  # noqa: E402

CORPUS = ROOT.parent / "research" / "feasibility" / "input" / "corpus"
NAMES = ["s4_tech_drawing", "s1_bw_logo", "s2_flat_icon", "s6_text",
         "s10_gradient", "s5_chart", "r4_pasted_png", "s9_alpha_png"]


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_test" / "gui.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    app = App()
    app.out_dir.set(str(ROOT / "_test" / "shot"))
    for name in NAMES:
        hit = next(CORPUS.glob(name + ".*"), None)
        if hit:
            app.files.append(str(hit))
    app._refresh_files()
    app.v_status.set("3 / 12  s4_tech_drawing.png")
    app.pb.config(maximum=12, value=3)

    # 造几行结果，好检查 A/B/C 配色
    demo = [
        ("s4_tech_drawing.png", "单色", "A", "0.9935", "0.78×", "接近原图", "gA"),
        ("s1_bw_logo.png", "单色", "A", "0.9958", "0.19×", "接近原图", "gA"),
        ("s2_flat_icon.png", "彩色", "A", "0.9965", "0.05×", "接近原图", "gA"),
        ("s6_text.png", "彩色", "B", "0.9699", "4.75×", "文字已成轮廓，不能选中/搜索", "gB"),
        ("s10_gradient.png", "彩色", "C", "0.9467", "—", "渐变出色带，不适合矢量化", "gC"),
    ]
    for name, mode, g, ssim, ratio, note, tag in demo:
        app.tree.insert("", "end", text=name,
                        values=(mode, g, ssim, ratio, note), tags=(tag,))

    app.update_idletasks()
    app.update()
    app.lift()
    app.attributes("-topmost", True)
    app.update()
    app.after(400)
    app.update()

    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    img.save(out)
    print(f"窗口 {w}x{h} -> {out}  {out.stat().st_size // 1024} KB")

    app.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
