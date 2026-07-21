"""Generate examples/example_sheet.xlsx from example_sheet.csv.

Run once if you want to use Excel mode with the sample data:

    python examples/make_example_workbook.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Properties"
    with open(HERE / "example_sheet.csv", newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            ws.append(row)
    target = HERE / "example_sheet.xlsx"
    wb.save(target)
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
