#!/usr/bin/env python3
"""Compare two exhibitor lists, e.g. your scrape against a browser walk or an alternate-language page.

Usage:
    python3 compare_records.py A.json B.json [--key company:name] [--fields country,stand_listed:col3]
                               [--order] [--casefold]

A and B hold a list of records, or an object with a "records" list (the --json output of
ifp_project_series.py and the output of walk_pages.js both work). --key is the field that names an
exhibitor, as A_field:B_field when the two differ (default: the first of company / name /
company_name / exhibitor present on each side). --fields lists more fields to compare for exhibitors
found in both. --order also checks that both lists run in the same order. Values are compared after
collapsing whitespace and removing invisible characters; list values are joined with "; ";
--casefold also ignores letter case.

Prints counts, exhibitors missing from B, extra in B, duplicates, field differences and order
differences. Exit status 0 means no differences.
"""
import argparse
import collections
import json
import re
import sys

INVISIBLE_RE = re.compile("[\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
NAME_KEYS = ("company", "name", "company_name", "exhibitor")


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("records") or data.get("rows") or []
    return data


def norm(value, casefold):
    if isinstance(value, list):
        value = "; ".join(str(v) for v in value)
    text = re.sub(r"\s+", " ", INVISIBLE_RE.sub("", "" if value is None else str(value))).strip()
    return text.casefold() if casefold else text


def pair(spec):
    a, _, b = spec.partition(":")
    return a, b or a


def pick_key(records):
    for key in NAME_KEYS:
        if records and key in records[0]:
            return key
    sys.exit(f"no name field found; pass --key (fields: {sorted(records[0]) if records else []})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--key")
    ap.add_argument("--fields", default="")
    ap.add_argument("--order", action="store_true")
    ap.add_argument("--casefold", action="store_true")
    args = ap.parse_args()

    a_recs, b_recs = load(args.a), load(args.b)
    key_a, key_b = pair(args.key) if args.key else (pick_key(a_recs), pick_key(b_recs))
    a_keys = [norm(r.get(key_a), args.casefold) for r in a_recs]
    b_keys = [norm(r.get(key_b), args.casefold) for r in b_recs]
    a_count, b_count = collections.Counter(a_keys), collections.Counter(b_keys)
    problems = 0

    print(f"A: {len(a_recs)} records ({args.a}, key '{key_a}')")
    print(f"B: {len(b_recs)} records ({args.b}, key '{key_b}')")
    missing = sorted((a_count - b_count).elements())
    extra = sorted((b_count - a_count).elements())
    for label, items in (("in A but not in B", missing), ("in B but not in A", extra)):
        print(f"{label}: {len(items)}")
        for item in items[:50]:
            print(f"   {item!r}")
        problems += len(items)
    for label, counts in (("A", a_count), ("B", b_count)):
        dupes = {k: n for k, n in counts.items() if n > 1}
        if dupes:
            print(f"repeated names in {label}: {dupes}")

    b_first = {}
    for k, r in zip(b_keys, b_recs):
        b_first.setdefault(k, r)
    diffs = []
    for field in filter(None, args.fields.split(",")):
        fa, fb = pair(field)
        for k, r in zip(a_keys, a_recs):
            if k in b_first:
                va, vb = norm(r.get(fa), args.casefold), norm(b_first[k].get(fb), args.casefold)
                if va != vb:
                    diffs.append((k, fa, va, vb))
    print(f"field differences: {len(diffs)}")
    for k, field, va, vb in diffs[:50]:
        print(f"   {k!r} {field}: A={va!r} B={vb!r}")
    problems += len(diffs)

    if args.order:
        out_of_order = [(i + 1, x, y) for i, (x, y) in enumerate(zip(a_keys, b_keys)) if x != y]
        print(f"positions where the order differs: {len(out_of_order)}")
        for pos, x, y in out_of_order[:20]:
            print(f"   #{pos}: A={x!r} B={y!r}")
        problems += len(out_of_order)

    print("RESULT:", "identical" if not problems else f"{problems} difference(s)")
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
