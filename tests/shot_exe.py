"""截取「打包后的 firefly.exe」真实窗口，用于最终验收。

与 shot_gui.py 的区别：这个测的是冻结产物（dist\\firefly\\firefly.exe），
不是源码，能验证图标/资源/字体在打包后是否仍然正常。

用法：python tests/shot_exe.py [输出路径]
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "firefly" / "firefly.exe"


def find_window(pid: int) -> int | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_test" / "exe.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not EXE.exists():
        print(f"FAIL 找不到 {EXE}")
        return 1

    proc = subprocess.Popen([str(EXE)])
    hwnd = None
    for _ in range(60):
        time.sleep(0.5)
        if proc.poll() is not None:
            print("FAIL 进程提前退出")
            return 1
        hwnd = find_window(proc.pid)
        if hwnd:
            break
    if not hwnd:
        proc.kill()
        print("FAIL 等不到窗口")
        return 1

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.SetForegroundWindow(hwnd)
    time.sleep(1.2)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    img = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    img.save(out)
    print(f"exe 窗口 {rect.right - rect.left}x{rect.bottom - rect.top} -> {out}")
    proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
