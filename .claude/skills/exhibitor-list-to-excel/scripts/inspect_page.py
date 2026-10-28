#!/usr/bin/env python3
"""First look at a saved exhibitor-list page: where the data lives and how it is paginated.

Usage:
    python3 -I inspect_page.py page.html

Prints tables and their row counts, the most repeated element classes (list rows / cards), field
labels, count text such as "Showing 1 to 20 of 573", pagination links and buttons, DataTables /
List.js style setups (and whether they load rows from a server), embedded JSON data, iframes and
script hosts (third-party directory widgets), API-looking URLs in scripts, filter dropdowns,
hidden inputs and links that look like exhibitor detail pages. Nothing is executed or fetched,
so it is safe on untrusted downloads. Text that JavaScript writes at runtime is not in the file:
a missing counter here does not mean the site has none.
"""
import collections
import re
import sys
from urllib.parse import urlparse

from bs4 import BeautifulSoup

COUNT_RES = [
    re.compile(r"\b(?:showing|displaying|viewing)\s+\d[\d,]*\s*(?:to|-|–)\s*\d[\d,]*\s+of\s+\d[\d,]*[^.\n]{0,30}", re.I),
    re.compile(r"\b\d[\d,]*\s+(?:exhibitors?|companies|participants|brands|results|records|entries|members)\b", re.I),
    re.compile(r"\bpage\s+\d+\s+of\s+\d+\b", re.I),
]
PAGE_LINK_RE = re.compile(r"[?&](?:page|pg|p|paged|start|offset|from|skip|pageNumber|currentPage)=\d+|/page/\d+", re.I)
NEXT_TEXT_RE = re.compile(r"^\s*(next|next page|›|»|>|>>|load more|show more|view more|more results)\s*$", re.I)
DETAIL_HREF_RE = re.compile(r"(exhibitor|company|companies|profile|participant|brand|booth|stand|vendor)s?[/_=-]", re.I)
API_RE = re.compile(r"""["'`]((?:https?:)?/[^"'`\s]*(?:api|ajax|json|graphql|exhibitor|search|algolia|list)[^"'`\s]*)["'`]""", re.I)
TABLE_LIB_RE = re.compile(r"\.\s*(dataTable|DataTable)\s*\(\s*\{", re.S)
SERVER_SIDE_RE = re.compile(r"\b(ajax|sAjaxSource|serverSide|bServerSide|fnServerData)\b")
APP_ROOT_IDS = ("app", "root", "__next", "__nuxt", "react-root", "vue-app")


def text_of(el, limit=80):
    return re.sub(r"\s+", " ", el.get_text(" ")).strip()[:limit]


def section(title):
    print(f"\n== {title} ==")


def main(path):
    html = open(path, encoding="utf-8", errors="replace").read()
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script")
    inline = "\n".join(s.string or s.get_text() for s in scripts if not s.get("src"))

    section("Page")
    print(f"size: {len(html):,} bytes | title: {text_of(soup.title, 150) if soup.title else '-'}")
    for h in soup.find_all(["h1", "h2"])[:6]:
        print(f"{h.name}: {text_of(h, 120)}")

    section("Tables (most rows first)")
    tables = sorted(soup.find_all("table"), key=lambda t: -len(t.find_all("tr")))
    for t in tables[:8]:
        body = t.find("tbody") or t
        heads = [text_of(th, 30) for th in t.find_all("th")][:12]
        print(f"table id={t.get('id')} class={' '.join(t.get('class') or [])!r}: "
              f"{len(body.find_all('tr', recursive=False)) or len(t.find_all('tr'))} rows, headers {heads}")
    if not tables:
        print("none")

    section("Most repeated element classes (list rows / cards)")
    classes = collections.Counter()
    sample = {}
    for el in soup.find_all(True, class_=True):
        key = f"{el.name}.{'.'.join(el.get('class'))}"
        classes[key] += 1
        sample.setdefault(key, el)
    for key, n in [kv for kv in classes.most_common(40) if kv[1] >= 5][:20]:
        print(f"{n:6d}  {key[:70]:70s}  e.g. {text_of(sample[key], 50)!r}")

    section("Field labels (text ending in ':' inside headings, dt, strong, b, label, th)")
    labels = collections.Counter(text_of(el, 40) for el in soup.find_all(["h3", "h4", "h5", "h6", "dt", "strong", "b", "label", "th"])
                                 if 1 < len(text_of(el, 40)) <= 40 and text_of(el, 40).endswith(":"))
    print(", ".join(f"{k} x{v}" for k, v in labels.most_common(25)) or "none")

    section("Count text found in the HTML")
    visible = soup.get_text(" ")
    found = collections.Counter(m.group(0).strip() for rx in COUNT_RES for m in rx.finditer(visible))
    print("\n".join(f"{v}x  {k}" for k, v in found.most_common(10)) or "none (counters written by JavaScript only appear in a browser)")

    section("Pagination clues")
    links = [a.get("href", "") for a in soup.find_all("a", href=True)]
    paged = collections.Counter(PAGE_LINK_RE.sub(lambda m: re.sub(r"\d+", "N", m.group(0)), h) for h in links if PAGE_LINK_RE.search(h))
    for pattern, n in paged.most_common(8):
        print(f"page link pattern ({n}x): {pattern[:120]}")
    for el in soup.find_all(["a", "button", "link"]):
        if el.get("rel") and "next" in el.get("rel"):
            print(f"rel=next: {el.get('href')}")
        elif NEXT_TEXT_RE.match(el.get_text() or ""):
            print(f"{el.name} {text_of(el)!r} href={el.get('href')} class={el.get('class')}")
    pagers = {f"{el.name}.{'.'.join(el.get('class'))}" for el in soup.find_all(True, class_=re.compile(r"pagin|pager", re.I))}
    if pagers:
        print("pager elements:", ", ".join(sorted(pagers)[:8]))
    for m in TABLE_LIB_RE.finditer(inline):
        options = inline[m.end() - 1:m.end() + 700]
        server = SERVER_SIDE_RE.findall(options)
        size = re.search(r'"?(iDisplayLength|pageLength)"?\s*:\s*(\d+)', options)
        print(f"DataTables setup: page size {size.group(2) if size else '?'}; "
              + (f"loads rows from a server ({', '.join(sorted(set(server)))})" if server else "no server loading: all rows are in the HTML"))
    for lib, rx in (("List.js", r"new\s+List\s*\("), ("Isotope", r"isotope\s*\("), ("MixItUp", r"mixitup\s*\("),
                    ("infinite scroll", r"infinite-?scroll|IntersectionObserver")):
        if re.search(rx, inline + " ".join(s.get("src", "") for s in scripts), re.I):
            print(f"{lib} found")
    for root_id in APP_ROOT_IDS:
        root = soup.find(id=root_id)
        if root is not None:
            print(f"app root #{root_id} with {len(text_of(root, 10_000))} chars of text (empty means the list is rendered by JavaScript)")

    section("Embedded data")
    for s in scripts:
        kind = s.get("type", "")
        if kind in ("application/json", "application/ld+json") or s.get("id") in ("__NEXT_DATA__", "__NUXT_DATA__"):
            body = s.string or ""
            types = re.findall(r'"@type"\s*:\s*"([^"]+)"', body)[:6] if kind == "application/ld+json" else []
            print(f"<script type={kind!r} id={s.get('id')}>: {len(body):,} chars {('types ' + ', '.join(types)) if types else ''}")
    for var in ("__NUXT__", "__INITIAL_STATE__", "__APOLLO_STATE__", "__PRELOADED_STATE__", "initialData", "exhibitors"):
        m = re.search(rf"\b{var}\s*=\s*[\[{{]", inline)
        if m:
            print(f"inline variable {var} = ... at offset {m.start()}")
    big = [len(m.group(0)) for m in re.finditer(r'\[\s*\{\s*"[A-Za-z_]+"\s*:.{200,}?\}\s*\]', inline, re.S)]
    if big:
        print(f"{len(big)} inline JSON arrays of objects (largest {max(big):,} chars)")

    section("Frames and script hosts (third-party directory widgets show up here)")
    for f in soup.find_all("iframe"):
        print(f"iframe: {f.get('src') or f.get('data-src')}")
    hosts = collections.Counter(urlparse(s["src"]).hostname or "(same site)" for s in scripts if s.get("src"))
    print(", ".join(f"{h} x{n}" for h, n in hosts.most_common()) or "no external scripts")

    section("API-looking URLs in scripts and attributes")
    urls = collections.Counter(m.group(1) for m in API_RE.finditer(inline))
    for el in soup.find_all(True):
        for attr in ("data-url", "data-src", "data-api", "data-endpoint", "action"):
            if el.get(attr) and re.search(r"api|ajax|json|exhibitor|search", el.get(attr), re.I):
                urls[el.get(attr)] += 1
    print("\n".join(f"{u[:140]}" for u, _ in urls.most_common(20)) or "none")

    section("Filters and hidden inputs")
    for sel in soup.find_all("select"):
        opts = [text_of(o, 30) for o in sel.find_all("option")]
        print(f"select id={sel.get('id')} name={sel.get('name')}: {len(opts)} options, e.g. {opts[:6]}")
    for inp in soup.find_all("input", type="hidden")[:15]:
        print(f"hidden input name={inp.get('name')} id={inp.get('id')} value={str(inp.get('value'))[:60]!r}")

    section("Links that look like exhibitor detail pages")
    detail = [h for h in links if DETAIL_HREF_RE.search(h)]
    print(f"{len(detail)} links, {len(set(detail))} distinct")
    for h in list(dict.fromkeys(detail))[:8]:
        print(f"  {h[:140]}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
