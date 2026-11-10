"""GUI 冒烟测试：无人值守跑一遍「添加→转换→结果表」，成功则打印 OK。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firefly.gui import App  # noqa: E402

CORPUS = ROOT.parent / "research" / "feasibility" / "input" / "corpus"
NAMES = ["s1_bw_logo", "s2_flat_icon", "s4_tech_drawing", "s9_alpha_png"]


def main() -> int:
    app = App()
    app.out_dir.set(str(ROOT / "_test" / "gui"))
    for name in NAMES:
        found = sorted(CORPUS.glob(name + ".*"))
        if not found:
            print(f"FAIL 找不到语料 {name}.*（{CORPUS}）")
            return 1
        app.files.append(str(found[0]))
    app._refresh_files()
    if not app.files:
        print("FAIL 没有加入任何文件")
        return 1
    print("文件列表行数:", len(app.tree_files.get_children()))

    app._start()
    t0 = time.time()
    while time.time() - t0 < 300:
        app.update()
        if app.worker and not app.worker.is_alive() and app.q.empty():
            break
        time.sleep(0.05)
    app.update()

    rows = app.tree.get_children()
    print(f"结果行数: {len(rows)}")
    for r in rows:
        print(" ", app.tree.item(r, "text"), app.tree.item(r, "values"))
    ok = len(rows) == len(NAMES)
    for r in rows:
        vals = app.tree.item(r, "values")
        if vals and vals[1] == "失败":
            ok = False
    print("进度:", app.pb["value"], "/", app.pb["maximum"])
    print("按钮状态:", app.btn_start["state"], app.btn_cancel["state"])
    app.destroy()
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
