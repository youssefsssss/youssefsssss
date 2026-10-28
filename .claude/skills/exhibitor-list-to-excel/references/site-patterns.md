# How exhibitor directories are built, and how to get everything out of each kind

Read the section that matches what `scripts/inspect_page.py` showed. A site can combine patterns
(server-side pages whose rows link to detail pages is the most common one).

## Contents
- A. All rows in the HTML, paged in the browser
- B. Server-side pages
- C. JSON / XHR API behind the page
- D. Infinite scroll and "load more"
- E. Third-party directory widgets
- F. Detail pages and popups
- Emails hidden from scrapers
- What is not a missing exhibitor
- Permission and politeness

## A. All rows in the HTML, paged in the browser

Signals: one large table or list with every row in the downloaded file; a DataTables call
(`$(...).dataTable({...})` or `.DataTable({...})`) with no `ajax`, `sAjaxSource`, `serverSide` or
`bServerSide` option; List.js, Isotope or MixItUp grids; a page size such as `"iDisplayLength": 20`.

How: parse the full table. Look for hidden columns that feed filters (`td.hidden`, `display:none`
cells), popup content kept inside each row (an `onclick` that opens a modal, a hidden `div`), and
`data-*` attributes. The page each exhibitor appears on is `(index // page size) + 1` when the table
is not re-sorted on load (`bSort: false` or `ordering: false`); if it sorts on load, take page
numbers from the browser walk instead.

Verify: `walk_pages.js` with its DataTables defaults.

## B. Server-side pages

Signals: links such as `?page=3`, `/page/3`, `start=40`, `offset=40`; each download holds only one
page; "Page 1 of 12" or "Showing 1-20 of 237".

How:
- Work out the last page from the pager or the counter. Pagers often show only "1 2 3 ... 12 Next",
  so follow the Next link (or count up) rather than trusting the numbered links you can see.
- Fetch pages in order until the site runs out: no rows, a repeat of the previous page, or past the
  counter's last item. Record page and position for every row.
- Compare rows collected with the counter. More rows than the total usually means items shifted
  between pages while you fetched (unstable server-side sorting): the same profile URL or ID on two
  neighbouring pages. Keep one copy and mention it. Fewer rows than the total means a page was
  skipped or cut short: re-fetch the pages around the gap.
- If there is a `per_page`, `limit` or `pageSize` parameter, a larger page size (up to a few
  hundred) means fewer requests and less shifting. Check that it is honoured.

## C. JSON / XHR API behind the page

Signals: the list container is empty in the raw HTML; an app root (`#app`, `#root`, `#__next`);
`__NEXT_DATA__`, `__NUXT__` or other state blobs; API URLs in scripts; Algolia keys.

How:
- Embedded state (`__NEXT_DATA__` and similar) sometimes already holds every exhibitor. Check its
  size and structure first.
- Otherwise find the request the page makes. In a browser, log JSON responses:
  `page.on('response', r => /json/.test(r.headers()['content-type'] || '') && console.log(r.status(), r.url()))`.
  Where the sandbox breaks Chromium's own requests, read the endpoint from the scripts instead
  (`inspect_page.py` lists API-looking URLs) and call it with curl.
- Replay it with curl or requests, page through (page and size, offset, or cursor) and read
  `total` / `count` from the response. Use the API's IDs as keys.
- If the API needs a login or a token the user does not have, stop and ask.

## D. Infinite scroll and "load more"

Usually an API sits underneath (see C): find it and page through it. Otherwise, in a browser, click
"load more" or scroll to the bottom repeatedly until the number of items stops growing for a few
rounds, recording the count each round.

## E. Third-party directory widgets

Signals: an iframe or a widget script from an events-platform host (floor plans, exhibitor
directories, event apps).

How: the data lives on the platform. Open the iframe URL directly and treat it as its own site
(often pattern B or C). In a sandbox, that host may also need allowing, so name it to the user.
Check the platform's terms and robots.txt; public directories are normally fine to read at a
polite rate.

## F. Detail pages and popups

Signals: each row links to `/exhibitor/<slug>`, `/company/123` or similar, or opens a modal with
more fields (website, email, phone, address, description, products, brands, social links, stand).

How:
- Collect every detail URL from the list first. Their count must equal the total.
- Visit them one at a time with a short pause (0.5-1 s), saving each page to disk so a re-run reads
  the cache instead of the site.
- Parse labelled fields generically (label to value: `dt`/`dd`, `th`/`td`, `strong` followed by
  text) so fields you have not seen before land in their own columns.
- Report how many detail pages failed, retry them once, and leave a field blank rather than guessing
  when the page does not show it.

## Emails hidden from scrapers

- HTML entities (`&#109;&#97;&#105;...`) decode with any HTML parser.
- Cloudflare email protection replaces the address with `[email protected]` and an element carrying
  `data-cfemail="..."` (or a link to `/cdn-cgi/l/email-protection#...`). Decode the hex string: the
  first byte is the key, and every following byte XOR the key is one character:

  ```python
  def decode_cfemail(hex_string):
      key = int(hex_string[:2], 16)
      return "".join(chr(int(hex_string[i:i + 2], 16) ^ key) for i in range(2, len(hex_string), 2))
  ```

- Addresses written as `name [at] example [dot] com` can be rebuilt; note on the row that you did.

## What is not a missing exhibitor

Sponsor and partner logos, speakers, media partners and testimonials are not exhibitors unless the
site presents them as such. Mention them separately if they look relevant. Co-located shows with
their own lists: mention them and ask before including.

## Permission and politeness

Public exhibitor lists are published for visitors, and reading them at a modest rate is normal.
Do not get past logins, paywalls or CAPTCHAs; send one request at a time with short pauses when
there are many pages; use an ordinary browser User-Agent. If the site starts refusing requests
(403, 429), stop and tell the user rather than pushing harder.
