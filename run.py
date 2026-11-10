"""启动入口。

- 无参数：打开 GUI（双击 / 打包后的 firefly.exe）。
- 带参数：走命令行批处理，例如 `firefly.exe 图.png -o 输出目录`。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from firefly.cli import main as cli_main

        sys.exit(cli_main())
    else:
        from firefly.gui import main as gui_main

        gui_main()
