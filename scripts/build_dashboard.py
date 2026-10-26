"""Build outputs/dashboard_offline.html: the interactive browser dashboard as one self-contained file.

Inlines data/*.csv (as JSON) and web/model.js (JavaScript port of src/cirdesign) into web/template.html.
The result runs offline: double-click it. Keep it next to outputs/LCI_inventory.xlsx so the
"Download Excel workbook" button finds the workbook.

Usage:  python scripts/build_dashboard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cirdesign.data import load_all  # noqa: E402

WEB = ROOT / "web"
OUT = ROOT / "outputs" / "dashboard_offline.html"


def model_data() -> dict:
    """The four input tables, in the shape web/model.js expects."""
    T = load_all()

    def records(df):
        return json.loads(df.to_json(orient="records"))

    return {
        "sources": records(T["sources"]),
        "designs": records(T["designs"].reset_index()),
        "strategies": records(T["strategies"].reset_index()),
        "bms": records(T["business_models"].reset_index()),
    }


def render() -> str:
    page = (WEB / "template.html").read_text(encoding="utf-8")
    page = page.split("-->", 1)[1].lstrip() if page.startswith("<!--") else page  # drop the template-only note
    page = page.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
    page = page.replace("__DATA__", json.dumps(model_data())).replace("__MODEL__", (WEB / "model.js").read_text(encoding="utf-8"))
    head, body = page.split('<div class="app">', 1)
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'{head}</head>\n<body>\n<div class="app">{body}</body>\n</html>\n')


def build() -> Path:
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(build())
