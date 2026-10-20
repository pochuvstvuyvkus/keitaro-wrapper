"""Build the GitHub Pages demo into _site/.

The demo is the same frontend (app/static) with demo.js answering the API calls in the
browser, so it needs no server and never talks to Keitaro.

    uv run python scripts/build_demo.py && python -m http.server -d _site 8100
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.keitaro.payloads import country_list  # noqa: E402

STATIC = ROOT / "app" / "static"
SITE = ROOT / "_site"
APP_SCRIPT = '<script src="static/app.js"></script>'


def main() -> None:
    shutil.rmtree(SITE, ignore_errors=True)
    shutil.copytree(STATIC, SITE / "static")
    (SITE / "static" / "countries.json").write_text(
        json.dumps(country_list(), ensure_ascii=False), encoding="utf-8"
    )
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    if APP_SCRIPT not in index:
        raise SystemExit("index.html: app.js script tag not found")
    index = index.replace(APP_SCRIPT, f'<script src="static/demo.js"></script>\n  {APP_SCRIPT}')
    index = index.replace("<title>Keitaro wrapper</title>", "<title>Keitaro wrapper · демо</title>")
    (SITE / "index.html").write_text(index, encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"demo site: {SITE}")


if __name__ == "__main__":
    main()
