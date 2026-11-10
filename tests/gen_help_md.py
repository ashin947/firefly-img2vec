"""从 firefly/help_text.py 生成 使用说明.md（保持两处内容一致）。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from firefly.help_text import HELP  # noqa: E402

HEAD = (
    "# 萤火虫 使用说明\n\n"
    "> 本文件由 `firefly/help_text.py` 生成，与程序里「使用说明」按钮显示的内容完全一致。\n"
    "> 修改说明请改 `help_text.py`，然后跑一次 `python tests/gen_help_md.py`。\n\n"
)
text = HEAD + HELP
for p in (ROOT / "使用说明.md", ROOT / "dist" / "firefly" / "使用说明.md"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
print(f"wrote {len(text)} chars to {2} file(s)")
