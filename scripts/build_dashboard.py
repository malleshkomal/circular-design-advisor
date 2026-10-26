"""Build outputs/dashboard_offline.html: the interactive browser dashboard as one self-contained file.

Inlines data/*.csv (as JSON), web/model.js (JavaScript port of src/cirdesign) and
outputs/LCI_inventory.xlsx (its sheet values for the workbook tab, and the file itself for the
download button) into web/template.html. The result is one file that runs offline: double-click it.
Run build_lci_workbook.py first and recalculate the workbook in Excel when the inputs change.

Usage:  python scripts/build_dashboard.py
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cirdesign.data import load_all  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import build_lci_viewer  # noqa: E402

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
    page = (page.replace("__DATA__", json.dumps(model_data()))
                .replace("__WORKBOOK__", json.dumps(build_lci_viewer.sheets(), ensure_ascii=False))
                .replace("__XLSX_B64__", base64.b64encode(build_lci_viewer.XLSX.read_bytes()).decode())
                .replace("__MODEL__", (WEB / "model.js").read_text(encoding="utf-8")))
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
