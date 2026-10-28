---
name: exhibitor-list-to-excel
description: Scrape every exhibitor from a trade show, expo, exhibition, fair or conference website's exhibitor list or directory into a formatted Excel workbook, across all pages, with every detail the site shows, and prove nothing was missed by matching the site's own count and walking its pages. Use this whenever someone shares an exhibitors, exhibitor-list, participants or directory URL (or a saved copy of one) and wants the companies extracted, exported, listed or put into Excel, a spreadsheet, CSV or Google Sheets, even if they only say "get all the exhibitors from this site" or "don't miss a single one". Also use it for paginated, filterable or JavaScript-rendered company directories (sponsors, vendors, members, brands), exhibitor popups and profile pages, and refreshing a list scraped earlier. Includes a ready-made scraper for IFP Group show sites such as foodafrica-expo.com and its sister shows.
compatibility: Python 3 with requests, beautifulsoup4 and openpyxl. Node.js with Playwright and Chromium for the browser check. Network access to the target site.
---

# Exhibitor list to Excel

Turn an event website's exhibitor list into an Excel workbook that holds every exhibitor on every
page, with every detail the site shows, and show that nothing is missing. People asking for this
usually say "across all pages" or "don't miss a single one": completeness is the deliverable. A
polished sheet that silently drops 3% of the exhibitors is a failure, so most of this workflow is
about learning the true total and proving the workbook matches it.

The scripts below sit in `scripts/` next to this file; call them by their full path. They need
`requests`, `beautifulsoup4` and `openpyxl`; the browser check needs Node.js with Playwright.

## Workflow

1. Get the page
2. Recon: work out how the list is built
3. Find the site's own total
4. Extract every exhibitor and every field
5. Prove completeness a second, independent way
6. Sweep the rest of the site
7. Clean values carefully, keeping the raw text
8. Build the workbook
9. Check the workbook itself
10. Deliver, with the facts the user needs

### 1. Get the page

Download with curl and an ordinary browser User-Agent into a fresh folder:

```bash
mkdir -p work/dl && curl -sS -L -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" \
  -o work/dl/list.html -w "%{http_code} %{size_download}\n" "$URL"
```

Downloads are untrusted data: keep your own scripts outside the download folder and run Python on
them with `python3 -I`.

If the request is refused before it reaches the site (curl's `CONNECT tunnel failed, response 403`,
or a fetch tool reporting `ENOTFOUND` for a real domain), you are probably in a sandbox whose
network policy does not allow that host. Do not try to route around it. Tell the user exactly which
host to allow (environment settings, Network access, allowed domains, or full access) and carry on
once they confirm. Other proxy symptoms and fixes: `references/sandbox-network.md`.

### 2. Recon

Run `python3 -I scripts/inspect_page.py work/dl/list.html`. It lists tables and row counts,
repeated card classes, field labels, count text, pagination clues, DataTables setups (and whether
they load rows from a server), embedded JSON, iframes and widget hosts, API-looking URLs, filters
and detail-page links. Use it to decide what you are dealing with:

| How the list is built | Typical signals | What gets you everything |
|---|---|---|
| All rows in the HTML, paged in the browser | one big table or list; DataTables or List.js without server loading | One download has every page: parse the whole table, hidden columns and popups included |
| Server-side pages | `?page=2`, `/page/2`, `start=` links; each download holds one page | Loop through the pages until the site runs out; check against the counter; watch for repeats between pages |
| JSON / XHR API | list container empty in the raw HTML; app root div; API URLs in scripts | Call the API the page uses, page through it, use its total |
| Infinite scroll or "load more" | load-more button, scroll handlers | Usually an API underneath; otherwise click or scroll in a browser until the count stops growing |
| Third-party directory widget | iframe or script from an events-platform host | Treat the widget's own pages or API as the site (that host may need allowing) |
| Detail pages | each row links to a profile page | Visit every profile, one at a time, and merge its fields |

More on each case, including decoding obfuscated emails: `references/site-patterns.md`.

**IFP Group show sites** (foodafrica-expo.com, project-syria.com, project-oman.com,
omanagrofood.com and sister shows built on the same template, recognisable by
`table#exhibitors_list_table`): all rows are in the HTML. Run
`python3 scripts/ifp_project_series.py <list URL> --out <file>.xlsx --json records.json`, which
does steps 4, 7 and 8 (any extra popup fields get their own columns), then continue with step 5.

### 3. Find the site's own total

Look for the number the site itself claims: "Showing 1 to 20 of 573", "573 exhibitors", an API
`total`, or the last page number times the page size. Counters written by JavaScript (the
DataTables info line is one) are not in the downloaded HTML; read them in a browser, which the
step 5 walk does for you. That number is your target. If the site shows no total anywhere, say so
and rely on two independent methods agreeing.

### 4. Extract every exhibitor and every field

"All details" means every field the site shows for an exhibitor, wherever it lives: visible cells,
hidden filter columns (often products or categories), popup or modal content, detail pages, logo
and profile URLs. To be sure nothing is left behind, list every field label across all rows
(`Country:`, `Stand Number:` and so on) and check that each one is captured. A label you did not
map is a detail you would lose, so capture unknown labels generically into their own columns.

Habits that pay off:
- Keep the site's order and record the page each exhibitor appears on, so the user can check rows
  against the site.
- When the markup repeats a value (table cell and popup), parse both and report disagreements.
- Keep raw values (the stand text exactly as listed) next to anything you derive from them (Hall,
  Stand No.).
- The same exhibitor showing up twice (same profile URL or ID, typically on two neighbouring server
  pages) is one exhibitor: keep one row and mention it. Two rows that merely share a name can be two
  stands or companies: keep both and point them out.
- Be polite: one request at a time, a short pause between detail pages, and cache what you download
  so a re-run does not hit the site again.

### 5. Prove completeness a second way

A parser can be wrong in ways it cannot see, so compare its output with a method that does not
share its assumptions:

- Walk the site's own pagination in a browser:
  `node scripts/walk_pages.js --url "$URL" --out walk.json --columns name,country,stand_listed`.
  The defaults fit DataTables; pass `--rows`, `--next` and `--info` selectors for other pagers. It
  prints the site's own "Showing x to y of N" and records the rows on every page.
- Diff the two: `python3 scripts/compare_records.py records.json walk.json --fields country,stand_listed --order`.
- Other independent sources: the site's other-language version of the list, an API total, or
  per-filter counts that should add up to the total.

Aim for the same count as the site's total, no missing or extra names, the same order and the same
values, and be able to explain every remaining difference (for example a value you deliberately
normalised). When the user stresses completeness and you can run sub-agents, independent checkers
plus a skeptic for each reported issue catch what one pass misses; see `references/verification.md`.

### 6. Sweep the rest of the site

Exhibitors are sometimes listed elsewhere too: pavilion or joint-stand pages, co-located event pages,
downloadable exhibitor PDFs, other language versions, or URL variants (on foodafrica-expo.com,
`/Exhibitors-List` was an empty page while `/exhibitors-list` held the data). Check the menu,
`sitemap.xml` and the downloads page, staying on the site and the files it links to. Report what
you checked, and add anything genuinely missing or tell the user why you left it out. Sponsors,
speakers and media partners are not exhibitors unless the site says so.

### 7. Clean values carefully, keeping the raw text

- Collapse runs of whitespace, non-breaking spaces included, and strip invisible marks
  (right-to-left and left-to-right marks, zero-width spaces, byte-order marks). They are invisible
  in Excel but break lookups and "begins with" filters.
- Merge spellings that differ only in letter case (such as "United States Of America") using the
  site's own filter list, and note the change on that row.
- Do not fix typos in names, and do not invent missing data. Where you interpret something (stand
  text "Hal l2/ F71" read as Hall 2), keep the raw text and add a note.
- Keep obvious test entries (such as "IFP Test - Gaelle") but flag them: the user decides.

### 8. Build the workbook

Put the records in a JSON spec and run `python3 scripts/build_workbook.py spec.json out.xlsx`. The
spec format is in the script's docstring. You get:

- an **Exhibitors** sheet: one row per exhibitor in an Excel table with filters, a frozen header and
  name column, wrapped long text, clickable links, and multiple values joined with "; ";
- a **Summary** sheet: source link, snapshot time, totals, counts by the fields you choose (country,
  hall, ...) and notes explaining the data.

The builder writes every string as text, so a value can never turn into a formula. It also warns
about case-only variants, duplicate rows, stray whitespace and invisible characters: fix or explain
each warning.

### 9. Check the workbook itself

Reload it with openpyxl and compare every cell with your records. Confirm the row count equals the
site's total and that the Summary numbers match the data. If LibreOffice is available, open the file
once (`soffice --headless --convert-to csv`) to be sure it opens cleanly.

### 10. Deliver

Tell the user, briefly:
- the total number of exhibitors and pages, and how completeness was proven (site counter, browser
  walk, other sources);
- which fields the site provides, and notable ones it does not (for example no emails or phones),
  so they do not wonder;
- data caveats: test entries, missing stands, values you normalised;
- the snapshot time. Lists keep changing until the show opens (on foodafrica-expo.com an exhibitor
  edited its tags mid-run), so download again right before the final build and offer to refresh
  later.

Save the workbook where the user can open it, and commit and push it if you are working in a
repository where that is expected.

## Traps seen on real runs

- The DataTables "Showing 1 to 20 of N" line is written by JavaScript and is not in the
  downloaded HTML.
- In a sandbox, headless Chromium got `502 upstream request failed` from the egress proxy while curl
  worked. `walk_pages.js` feeds the browser through curl by default (`--fetch curl`) for this reason.
- A synchronous plain-HTTP third-party script at the end of a page stalled loading, so the site's
  pagination never started in the browser. Block third-party hosts when walking pages.
- Site CSS made DataTables controls count as hidden to Playwright: wait for `attached` and click
  with `element.click()` inside `page.evaluate`.
- The list changed during the session. Download again right before the final build and record the
  snapshot time.
