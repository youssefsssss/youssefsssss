#!/usr/bin/env python3
"""Scrape an IFP Group "Project-Series" exhibitor list (foodafrica-expo.com and sister shows) to Excel.

These sites render the whole list into one HTML table (table#exhibitors_list_table) and page it in
the browser with DataTables, so a single download holds every exhibitor on every page. Each row has
the visible cells, a hidden detail popup (div.company-info) and hidden Profiles / Categories columns
that feed the page's filters. Every labelled popup field is captured, including ones this script has
not seen before (for example "Company Info" on project-syria.com), each in its own column.

Usage:
    python3 ifp_project_series.py https://foodafrica-expo.com/exhibitors-list --out exhibitors.xlsx
    python3 ifp_project_series.py --html saved.html --url https://site/exhibitors-list --out exhibitors.xlsx
    Add --json records.json to keep the extracted records (for compare_records.py).

Checked in October 2026 on foodafrica-expo.com, project-syria.com, project-oman.com and
omanagrofood.com. Read any WARNING lines: they flag values that disagree between the table and the
popup, or anything else that needs a human look.
"""
import argparse
import collections
import datetime
import json
import os
import re
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_workbook  # noqa: E402

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# "Hall 4/ F03", "Hall 25 / I17", "Hall2 / -" and the typo "Hal l2/ F71" all occur on these sites.
HALL_RE = re.compile(r"^H\s*a\s*l\s*l?\s*(\d+)\s*/\s*(.*)$", re.IGNORECASE)
WELL_FORMED_HALL_RE = re.compile(r"^Hall\s*\d+\s*/", re.IGNORECASE)
TEST_ENTRY_RE = re.compile(r"^(IFP\s+)?(test|dummy|demo)\b", re.IGNORECASE)  # IFP is the organizer
TAG_LIMIT = 240  # free-text tags stop at this length on these sites
# Field labels as the site writes them -> record keys used below.
KNOWN_FIELDS = {"country": "country", "stand number": "stand_listed", "profiles": "profiles",
                "categories": "categories"}


def clean(text):
    # Drop invisible marks and collapse whitespace (non-breaking spaces included) to single spaces.
    return re.sub(r"\s+", " ", build_workbook.INVISIBLE_RE.sub("", text or "")).strip()


def label_of(h4):
    return clean(h4.get_text()).rstrip(":").strip()


RESERVED_KEYS = {"no", "company", "page", "logo_url", "line_breaks_in_name", "hall", "stand", "notes",
                 "country_listed"}


def key_for(label):
    if label.lower() in KNOWN_FIELDS:
        return KNOWN_FIELDS[label.lower()]
    key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "field"
    return f"site_{key}" if key in RESERVED_KEYS else key


def field_value(h4):
    """A labelled field's value: the badge list of a tag section, else the text after the label."""
    holder = h4.find_parent("div")
    badges = holder.select("span.company-info-badge") if holder else []
    if badges:
        return [clean(b.get_text()) for b in badges]
    parts = []
    for sibling in h4.next_siblings:
        if getattr(sibling, "name", None) == "h4":
            break
        parts.append(sibling.get_text(" ") if hasattr(sibling, "get_text") else str(sibling))
    return clean(" ".join(parts))


def labelled_fields(node):
    return {label_of(h4): field_value(h4) for h4 in node.find_all("h4")} if node else {}


def plural(n, word="exhibitor"):
    return f"{n} {word}{'' if n == 1 else 's'}"


def split_stand(stand):
    """(hall, stand) parsed from the site's stand text; the original text is kept separately."""
    m = HALL_RE.match(stand)
    if not m:
        return "", stand
    rest = m.group(2).strip()
    return f"Hall {int(m.group(1))}", "" if rest in ("", "-") else rest


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="exhibitors_list_table")
    if table is None:
        sys.exit("table#exhibitors_list_table not found: this is not the IFP Project-Series layout.")
    m = re.search(r'"iDisplayLength"\s*:\s*(\d+)', html)
    page_size = int(m.group(1)) if m else 20
    headers = [clean(th.get_text()) for th in table.find("thead").find_all("th")]
    # The site's own country filter settles spellings that differ only in letter case.
    site_countries = {clean(o.get_text()).casefold(): clean(o.get_text())
                      for o in soup.select("select#cmbCountry option") if o.get("value")}

    records, problems = [], []
    extra_fields = {}  # key -> label, in the order first seen
    for i, tr in enumerate(table.find("tbody").find_all("tr", recursive=False), start=1):
        tds = tr.find_all("td", recursive=False)
        first = tds[0]
        name_el = first.select_one("div.exhibitor-company > span:not(.exhibitor-logo-box)")
        raw_name = name_el.get_text() if name_el else ""
        logo = first.select_one("div.exhibitor-company img")
        rec = {"no": i, "company": clean(raw_name), "page": (i - 1) // page_size + 1,
               "logo_url": logo.get("src", "").strip() if logo else "",
               "line_breaks_in_name": "\n" in raw_name.strip()}

        # Visible cells are keyed by their column header; hidden filter cells by the labels inside them.
        for header, td in zip(headers[1:], tds[1:]):
            if header:
                rec[key_for(header)] = clean(td.get_text())
            for label, value in labelled_fields(td).items():
                rec[key_for(label)] = value

        # The popup repeats most values; it can also hold fields that appear nowhere else.
        info = first.find("div", class_="company-info")
        popup_name = clean(info.find("h3").get_text()) if info and info.find("h3") else ""
        if popup_name != rec["company"]:
            problems.append(f"row {i}: name differs between list ({rec['company']!r}) and popup ({popup_name!r})")
        for label, value in labelled_fields(info).items():
            key = key_for(label)
            if key in rec:
                if rec[key] != value:
                    problems.append(f"row {i}: {label} differs between table ({rec[key]!r}) and popup ({value!r})")
            else:
                rec[key] = value
                if key not in KNOWN_FIELDS.values():
                    extra_fields.setdefault(key, label)

        rec.setdefault("country", "")
        rec.setdefault("stand_listed", "")
        listed = rec["country"]
        rec["country"] = site_countries.get(listed.casefold(), listed)
        rec["country_listed"] = listed if rec["country"] != listed else ""
        rec["hall"], rec["stand"] = split_stand(rec["stand_listed"])
        records.append(rec)

    heading = soup.select_one("h1.pagecontent-title")
    title = clean(soup.title.get_text()) if soup.title else ""
    meta = {"page_size": page_size, "heading": clean(heading.get_text(" ")) if heading else "",
            "show": clean(title.split("|")[0]) if title else "", "extra_fields": extra_fields}
    return records, problems, meta


def notes_for(rec):
    notes = []
    if TEST_ENTRY_RE.search(rec["company"]):
        notes.append("Looks like a test entry; kept because it is on the site's list.")
    if not rec["stand_listed"]:
        notes.append("No stand number listed on the site.")
    elif rec["hall"] and not WELL_FORMED_HALL_RE.match(rec["stand_listed"]):
        notes.append(f"Hall read from the site's stand text '{rec['stand_listed']}'.")
    if rec["line_breaks_in_name"]:
        notes.append("Name spaced as the site displays it (its source text has line breaks mid-word).")
    if rec["country_listed"]:
        notes.append(f"Country written '{rec['country_listed']}' on this row of the site; "
                     "shown as spelled in the site's country filter.")
    tags = (rec.get("profiles") or []) + (rec.get("categories") or [])
    if any(len(tag) >= TAG_LIMIT for tag in tags):
        notes.append(f"A tag on this row stops at {TAG_LIMIT} characters on the site itself (cut off there).")
    return " ".join(notes)


def build_spec(records, meta, url, snapshot):
    extra = meta["extra_fields"]
    columns = [
        {"key": "no", "header": "No.", "width": 7},
        {"key": "company", "header": "Company Name", "width": 45, "wrap": True},
        {"key": "country", "header": "Country", "width": 20},
        {"key": "hall", "header": "Hall", "width": 9},
        {"key": "stand", "header": "Stand No.", "width": 13},
        {"key": "stand_listed", "header": "Stand (as listed on site)", "width": 22},
        *({"key": key, "header": label} for key, label in extra.items()),
        {"key": "profiles", "header": "Profiles", "width": 55, "wrap": True},
        {"key": "categories", "header": "Categories", "width": 40, "wrap": True},
        {"key": "logo_url", "header": "Logo URL", "width": 40, "link": "url"},
        {"key": "page", "header": "Page on Site", "width": 8},
        {"key": "notes", "header": "Notes", "width": 42, "wrap": True},
    ]
    for rec in records:
        rec["notes"] = notes_for(rec)
    countries = {r["country"] for r in records}
    facts = [("Countries", len(countries)),
             (f"Pages on site ({meta['page_size']} per page)", records[-1]["page"] if records else 0),
             ("With profiles or categories", sum(1 for r in records if r.get("profiles") or r.get("categories"))),
             ("With logo", sum(1 for r in records if r["logo_url"]))]
    facts += [(f"With {label}", sum(1 for r in records if r.get(key))) for key, label in extra.items()]
    notes = [
        "The site's list is live: exhibitors can still be added or edited before the show, so this is a "
        "snapshot as of the time above.",
        f"Rows are in the site's own order; 'Page on Site' is the list page ({meta['page_size']} per page) "
        "each exhibitor appears on.",
        "'Hall' and 'Stand No.' are split out of the site's stand text, which is kept unchanged in "
        "'Stand (as listed on site)'. A stand shown as '-' on the site is left blank in 'Stand No.'.",
        "Profiles and Categories are the tags each exhibitor selected (some are free text), separated by '; '.",
    ]
    if extra:
        notes.append("Extra detail fields shown in the site's exhibitor popups: " + ", ".join(extra.values()) + ".")
    if meta["heading"]:
        notes.append(f"The list page's heading reads: \"{meta['heading']}\".")
    code_no_hall = sum(1 for r in records if r["stand_listed"] and not r["hall"])
    no_stand = sum(1 for r in records if not r["stand_listed"])
    if code_no_hall or no_stand:
        notes.append(f"'Not stated' in the hall table covers {plural(code_no_hall)} listed with a stand code "
                     f"but no hall, and {no_stand} with no stand listed.")
    return {
        "title": f"{meta['show'] or urlparse(url).hostname or 'Exhibitors'} – Exhibitors List",
        "source_url": url,
        "snapshot": snapshot,
        "columns": columns,
        "records": records,
        "summary_by": ["country", {"key": "hall", "order": "key", "blank": "Not stated"}],
        "facts": facts,
        "notes": notes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", nargs="?", default="", help="exhibitor list URL (downloaded unless --html is given)")
    parser.add_argument("--url", dest="url_option", help="the same, as an option (handy together with --html)")
    parser.add_argument("--html", help="parse this saved copy of the page instead of downloading it")
    parser.add_argument("--out", help="output .xlsx path (default: <site>_exhibitors.xlsx)")
    parser.add_argument("--json", help="also save the records and workbook spec as JSON here")
    args = parser.parse_args()
    args.url = args.url or args.url_option or ""
    if not args.url and not args.html:
        parser.error("give the list URL, or --html with a saved page")

    if args.html:
        with open(args.html, encoding="utf-8") as f:
            html = f.read()
    else:
        resp = requests.get(args.url, headers={"User-Agent": USER_AGENT}, timeout=120)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        html = resp.text
    snapshot = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    records, problems, meta = parse(html)
    for problem in problems:
        print("WARNING:", problem, file=sys.stderr)
    spec = build_spec(records, meta, args.url, snapshot)
    site = (urlparse(args.url).hostname or "site").removeprefix("www.").split(".")[0]
    out = args.out or f"{site}_exhibitors.xlsx"
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=1)
    build_workbook.build(spec, out)
    per_page = collections.Counter(r["page"] for r in records)
    print(f"{len(records)} exhibitors on {plural(len(per_page), 'page')} of {meta['page_size']} written to {out}")
    if meta["extra_fields"]:
        print("extra popup fields captured:", ", ".join(meta["extra_fields"].values()))


if __name__ == "__main__":
    main()
