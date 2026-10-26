"""Build outputs/circular-design-advisor-offline.zip: the offline dashboard, workbook viewer and Excel file in one download.

Browsers show an .html file opened from a GitHub "raw" link as source code, so the zip is the
reliable way to hand the offline pages to someone: unzip, then double-click the .html file.

Usage:  python scripts/package_offline.py   (after build_dashboard.py and build_lci_viewer.py)
"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "circular-design-advisor-offline.zip"
FILES = ["dashboard_offline.html", "lci_workbook.html", "LCI_inventory.xlsx"]
README = """Circular Design Advisor - offline pack

Double-click dashboard_offline.html for the interactive dashboard,
or lci_workbook.html to browse the LCI workbook. Keep the three files
in the same folder. No internet or Python needed.

Illustrative data. Source: https://github.com/malleshkomal/circular-design-advisor
"""


def build() -> Path:
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in [("README.txt", README.encode())] + [(f, (ROOT / "outputs" / f).read_bytes()) for f in FILES]:
            info = zipfile.ZipInfo(f"circular-design-advisor-offline/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    return OUT


if __name__ == "__main__":
    print(build())
