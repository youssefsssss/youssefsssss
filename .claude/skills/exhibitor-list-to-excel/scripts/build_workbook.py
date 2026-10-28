#!/usr/bin/env python3
"""Build a formatted Excel workbook from scraped exhibitor records.

Usage:
    python3 build_workbook.py spec.json out.xlsx

The spec is JSON:

    {
      "title": "Food Africa 2026 - Exhibitors",            # heading on the Summary sheet
      "source_url": "https://foodafrica-expo.com/exhibitors-list",
      "snapshot": "2026-10-28 05:02 UTC",                   # optional, defaults to now (UTC)
      "sheet_name": "Exhibitors",                           # optional
      "columns": [                                          # sheet column order
        {"key": "no", "header": "No.", "width": 7},
        {"key": "company", "header": "Company Name", "width": 45, "wrap": true},
        {"key": "website", "header": "Website", "link": "url"},
        {"key": "email", "header": "Email", "link": "email"}
      ],
      "records": [{"no": 1, "company": "...", "profiles": ["a", "b"]}],   # lists are joined with "; "
      "summary_by": ["country", {"key": "hall", "order": "key", "blank": "Not stated"}],
      "facts": [["Pages on site", 29]],                     # optional extra rows under the totals
      "notes": ["How the data was collected, caveats"]      # optional
    }

Each "summary_by" entry adds a count table to the Summary sheet (by count, or "order": "key"
for alphabetical). Values of list fields are counted per tag. Width and wrap are optional;
they are guessed from the content when left out.

Every string is written as text, so a value such as "=SUM(A1)" or "+20 2 2528" can never
become a formula. Problems worth a look (case-only variants, duplicate rows, stray
whitespace, invisible characters) are printed as warnings; the workbook is still written.
"""
import collections
import datetime
import json
import re
import statistics
import sys

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
LINK_FONT = Font(color="0563C1", underline="single")
INVISIBLE_RE = re.compile("[\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SEPARATOR = "; "


def warn(message):
    print(f"WARNING: {message}", file=sys.stderr)


def cell_value(value):
    if isinstance(value, (list, tuple)):
        value = SEPARATOR.join(str(v) for v in value if v not in (None, ""))
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value)
        return value if value != "" else None
    return value


def write_text_safe(cell, value):
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"  # never let a leading "=", "+", "-" or "@" turn into a formula


def link_target(kind, value):
    if not isinstance(value, str):
        return None
    if kind == "url" and re.match(r"^https?://", value, re.IGNORECASE):
        return value
    if kind == "email" and EMAIL_RE.match(value):
        return f"mailto:{value}"
    return None


def guess_width(header, values):
    lengths = [len(str(v)) for v in values if v not in (None, "")]
    typical = statistics.quantiles(lengths, n=10)[-1] if len(lengths) >= 10 else max(lengths, default=0)
    return max(8, min(60, max(len(header), int(typical)) + 2))


def lint(spec):
    records, columns = spec["records"], spec["columns"]
    keys = [c["key"] for c in columns]
    for key in keys:
        if not any(r.get(key) not in (None, "", []) for r in records):
            warn(f"column '{key}' is empty in every record")
    seen = collections.Counter(json.dumps([r.get(k) for k in keys if k != "no"], ensure_ascii=False) for r in records)
    dupes = sum(c - 1 for c in seen.values() if c > 1)
    if dupes:
        warn(f"{dupes} record(s) are exact duplicates of another record (kept)")
    for r in records:
        for k in keys:
            values = r.get(k) if isinstance(r.get(k), list) else [r.get(k)]
            for v in values:
                if isinstance(v, str) and (v != v.strip() or INVISIBLE_RE.search(v) or "\u00a0" in v):
                    warn(f"record {r.get('no', '?')}: '{k}' has stray whitespace or invisible characters: {v!r}")
    for entry in spec.get("summary_by", []):
        key = entry if isinstance(entry, str) else entry["key"]
        variants = collections.defaultdict(set)
        for r in records:
            for v in (r.get(key) if isinstance(r.get(key), list) else [r.get(key)]):
                if isinstance(v, str) and v:
                    variants[v.casefold()].add(v)
        for spellings in variants.values():
            if len(spellings) > 1:
                warn(f"'{key}' values differ only by letter case and will be counted apart: {sorted(spellings)}")


def style_header(ws, row, ncols):
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def table_name(sheet_name):
    name = re.sub(r"[^A-Za-z0-9_]", "_", sheet_name)
    return name if name[:1].isalpha() else f"T_{name}"


def write_records(wb, spec):
    columns, records = spec["columns"], spec["records"]
    ws = wb.active
    ws.title = spec.get("sheet_name", "Exhibitors")[:31]
    for idx, col in enumerate(columns, start=1):
        ws.cell(row=1, column=idx, value=col.get("header", col["key"]))
    top, wrap = Alignment(vertical="top"), Alignment(vertical="top", wrap_text=True)
    for r_idx, rec in enumerate(records, start=2):
        for c_idx, col in enumerate(columns, start=1):
            cell = ws.cell(row=r_idx, column=c_idx)
            value = cell_value(rec.get(col["key"]))
            write_text_safe(cell, value)
            cell.alignment = wrap if col.get("wrap") else top
            target = link_target(col.get("link"), value)
            if target:
                cell.hyperlink = target
                cell.font = LINK_FONT
    for idx, col in enumerate(columns, start=1):
        values = [cell_value(r.get(col["key"])) for r in records]
        width = col.get("width") or guess_width(col.get("header", col["key"]), values)
        ws.column_dimensions[get_column_letter(idx)].width = width
        if "wrap" not in col and width >= 60:
            for row in range(2, len(records) + 2):
                ws.cell(row=row, column=idx).alignment = wrap
    style_header(ws, 1, len(columns))
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = spec.get("freeze", "C2" if len(columns) >= 3 else "A2")
    if records:
        table = Table(displayName=table_name(ws.title),
                      ref=f"A1:{get_column_letter(len(columns))}{len(records) + 1}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
        ws.add_table(table)


def write_summary(wb, spec):
    records, columns = spec["records"], spec["columns"]
    headers = {c["key"]: c.get("header", c["key"]) for c in columns}
    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 70
    ws["A1"] = spec.get("title", "Exhibitors")
    ws["A1"].font = Font(bold=True, size=14)
    snapshot = spec.get("snapshot") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    facts = [("Source", spec.get("source_url", "")), ("Snapshot taken", snapshot), ("Total exhibitors", len(records))]
    facts += [tuple(f) for f in spec.get("facts", [])]
    row = 3
    for label, value in facts:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        cell = ws.cell(row=row, column=2)
        write_text_safe(cell, cell_value(value))
        cell.alignment = Alignment(horizontal="left")
        target = link_target("url", value)
        if target:
            cell.hyperlink = target
            cell.font = LINK_FONT
        row += 1

    notes = spec.get("notes", [])
    if notes:
        row += 1
        ws.cell(row=row, column=1, value="Notes").font = Font(bold=True)
        for note in notes:
            row += 1
            write_text_safe(ws.cell(row=row, column=1), note)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
            ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[row].height = 15 * max(1, -(-len(note) // 115))

    for entry in spec.get("summary_by", []):
        entry = {"key": entry} if isinstance(entry, str) else entry
        key = entry["key"]
        blank = entry.get("blank", "Not stated")
        counts = collections.Counter()
        is_list = False
        for r in records:
            value = r.get(key)
            if isinstance(value, list):
                is_list = True
                counts.update([v for v in value if v] or [blank])
            else:
                counts[value if value not in (None, "") else blank] += 1
        if entry.get("order") == "key":
            items = sorted(counts.items(), key=lambda kv: (kv[0] == blank, str(kv[0]).casefold()))
        else:
            items = sorted(counts.items(), key=lambda kv: (kv[0] == blank, -kv[1], str(kv[0]).casefold()))
        row += 2
        ws.cell(row=row, column=1, value=entry.get("label", headers.get(key, key)))
        ws.cell(row=row, column=2, value="Exhibitors")
        style_header(ws, row, 2)
        if is_list:
            ws.cell(row=row, column=3, value="(an exhibitor can have several)").font = Font(italic=True)
        for value, count in items:
            row += 1
            write_text_safe(ws.cell(row=row, column=1), cell_value(value))
            ws.cell(row=row, column=2, value=count)


def build(spec, out_path):
    lint(spec)
    wb = Workbook()
    write_records(wb, spec)
    write_summary(wb, spec)
    wb.save(out_path)
    return out_path


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)
    build(spec, sys.argv[2])
    print(f"{len(spec['records'])} records written to {sys.argv[2]}")


if __name__ == "__main__":
    main()
