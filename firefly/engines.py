"""引擎封装：potrace 只用 CLI 子进程（arm's-length），vtracer 用 Python wheel。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

POTRACE_PRESETS = {
    "平滑优先": ["-t", "2", "-a", "1.3", "-O", "0.4"],
    "标准": ["-t", "2", "-a", "1.0", "-O", "0.2"],
    "细节优先": ["-t", "0", "-a", "0.6", "-O", "0.1"],
}

VTRACER_PRESETS = {
    "平涂图标": dict(
        colormode="color",
        hierarchical="stacked",
        mode="polygon",
        filter_speckle=6,
        color_precision=6,
        layer_difference=24,
        corner_threshold=60,
        length_threshold=4.5,
        path_precision=3,
    ),
    "标准": dict(
        colormode="color",
        hierarchical="stacked",
        mode="polygon",
        filter_speckle=4,
        color_precision=6,
        layer_difference=16,
        corner_threshold=60,
        length_threshold=4.0,
        path_precision=3,
    ),
    "平滑曲线": dict(
        colormode="color",
        hierarchical="stacked",
        mode="spline",
        filter_speckle=4,
        color_precision=6,
        layer_difference=16,
        corner_threshold=60,
        length_threshold=4.0,
        splice_threshold=45,
        path_precision=4,
    ),
    "细节优先": dict(
        colormode="color",
        hierarchical="stacked",
        mode="spline",
        filter_speckle=2,
        color_precision=8,
        layer_difference=8,
        corner_threshold=60,
        length_threshold=3.0,
        splice_threshold=45,
        path_precision=8,
    ),
    # 文字 / 图表 / 带标注的插画。关掉碎块过滤 + 最高颜色精度，
    # 笔画不会被"吃"成锯齿；代价是路径数暴涨，靠 ir.prune_specks 在
    # 几何层把亚像素碎块剪掉，才把体积压回可用范围。
    "高保真": dict(
        colormode="color",
        hierarchical="stacked",
        mode="polygon",
        filter_speckle=0,
        color_precision=8,
        layer_difference=6,
        corner_threshold=90,
        length_threshold=2.0,
        path_precision=4,
    ),
}


def app_root() -> Path:
    """开发时是仓库根，PyInstaller 下是 _MEIPASS。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def potrace_exe() -> str | None:
    env = os.environ.get("IMG2VEC_POTRACE")
    cands = []
    if env:
        cands.append(Path(env))
    root = app_root()
    cands += [
        root / "bin" / "potrace" / "potrace.exe",
        root / "bin" / "potrace.exe",
        root / "bin" / "potrace" / "potrace",
    ]
    for c in cands:
        if c.is_file():
            return str(c)
    return shutil.which("potrace")


def _no_window():
    if sys.platform == "win32":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


def trace_mono(pbm_path, out_svg, preset="标准", timeout=120):
    """调用 potrace CLI，返回其 SVG 文本。"""
    exe = potrace_exe()
    if not exe:
        raise RuntimeError("找不到 potrace 可执行文件（bin/potrace/potrace.exe）")
    args = [exe, "-b", "svg", "-o", str(out_svg)] + POTRACE_PRESETS.get(
        preset, POTRACE_PRESETS["标准"]
    ) + [str(pbm_path)]
    proc = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, **_no_window()
    )
    if proc.returncode != 0:
        raise RuntimeError(f"potrace 失败（{proc.returncode}）：{proc.stderr.strip()[:400]}")
    return Path(out_svg).read_text(encoding="utf-8", errors="replace")


def trace_color(img_path, out_svg, preset="标准", timeout=600):
    """vtracer 彩色描迹，返回 SVG 文本。"""
    import vtracer

    params = dict(VTRACER_PRESETS.get(preset, VTRACER_PRESETS["标准"]))
    while True:
        try:
            vtracer.convert_image_to_svg_py(str(img_path), str(out_svg), **params)
            break
        except TypeError:
            if not params:
                raise
            params.pop(next(iter(params)))
    return Path(out_svg).read_text(encoding="utf-8", errors="replace")


class TempDir:
    def __enter__(self):
        self.path = Path(tempfile.mkdtemp(prefix="img2vec_"))
        return self.path

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)
        return False
