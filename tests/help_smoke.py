"""验证「使用说明」窗口能打开且内容完整（无显示环境风险的部分）。"""

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firefly.gui import App  # noqa: E402
from firefly.help_text import HELP  # noqa: E402


def main() -> int:
    app = App()
    app.update_idletasks()
    app._help()
    app.update_idletasks()

    tops = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
    if not tops:
        print("FAIL: 没有弹出说明窗口")
        return 1
    win = tops[0]

    texts = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Text):
                texts.append(c)
            walk(c)

    walk(win)
    if not texts:
        print("FAIL: 说明窗口里没有文本控件")
        return 1
    body = texts[0].get("1.0", "end-1c")
    ok = len(body) == len(HELP)
    print(f"窗口标题: {win.title()}")
    print(f"正文字符数: {len(body)} (源 {len(HELP)})  一致: {ok}")
    print(f"首行: {body.splitlines()[0]}")
    print(f"末行: {body.rstrip().splitlines()[-1]}")

    for kw in ("界面逐块说明", "等级怎么读", "常见问题", "命令行用法", "已知限制"):
        if kw not in body:
            print(f"FAIL: 缺少章节 {kw}")
            ok = False

    win.destroy()
    app.destroy()
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
