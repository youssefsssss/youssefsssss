# Verification: proving the list is complete

## Checklist

Each of these should hold, or have an explanation you can give the user:

1. The number of rows equals the site's own total (counter, API total, or page arithmetic).
2. A second, independent read (browser walk, other-language list, API) sees the same names, the
   same count and the same order: `compare_records.py` exits 0, or every difference is a
   normalisation you made on purpose and can name.
3. Every field label in the markup maps to a column; there are no labels you ignored.
4. Values the markup repeats (table cell and popup) agree with each other.
5. There are no duplicate rows, or the duplicates are explained.
6. Other places on the site that could list exhibitors were checked, and you can list them.
7. The workbook reloads with the same values, the Summary numbers match the data, and it opens in
   LibreOffice.
8. The data was downloaded again right before the final build, and the snapshot time is recorded.

## Independent multi-agent check (optional)

When the user stresses completeness and you can run sub-agents (a Workflow tool the user opted
into, or an Agent tool), several independent checkers with different methods, followed by a
skeptic for each reported issue, catch what a single pass misses. In the Food Africa run this found
an invisible right-to-left mark in one name, a country counted twice because of letter case, and a
non-breaking space. All of these were invisible to the original parser's own checks.

Give every checker: the list URL; the workbook path (read-only); its own work folder; the network
notes from `sandbox-network.md`; a cap of a few dozen requests to the site; and the rule that
differences in runs of whitespace are cosmetic. Do not give them your conclusions. Ask each one to
build its own extraction first and only then open the workbook.

Checkers that earned their keep:

| Checker | Method |
|---|---|
| static-html | Re-extract from the raw HTML with a different parser (lxml, regex) and compare every field of every row, page numbers and order included |
| browser-walk | Walk the site's own pagination in a browser, open detail popups for a sample spread over all pages, compare |
| mirror | Extract from another language version of the list and compare |
| completeness-critic | Look for exhibitors listed anywhere else on the site: menus, sitemap, downloads, pavilion and co-located event pages, URL variants, filter parameters |
| workbook-integrity | Summary numbers against the data, derived columns against the raw text, text integrity (mojibake, invisible characters, formula-like strings), opening in LibreOffice, a live spot-check of 25 rows |

Then, for each checker that reported something, a skeptic re-checks every claim with its own code
and marks it real or not. Fix what is real. For refuted claims, a clarifying note in the workbook
can still help the user.

Skeleton for a Workflow tool script (adapt the prompts; keep the structured outputs):

```js
export const meta = { name: 'verify-exhibitor-workbook', description: 'Independent checks of an exhibitor workbook against the live site',
  phases: [{ title: 'Verify' }, { title: 'Refute' }] }
const CHECKS = [ /* { key, prompt, schema, claims: result => [strings] } for each checker above */ ]
const results = await pipeline(CHECKS,
  c => agent(`${c.prompt}\n\n${CONTEXT(c.key)}`, { label: c.key, phase: 'Verify', schema: c.schema }),
  (res, c) => {
    const claims = res ? c.claims(res) : []
    if (!claims.length) return { key: c.key, result: res, verdicts: [] }
    return agent(`Try to refute each claim with your own checks; real=true only if your evidence confirms it.\n${claims.map((x, i) => `${i + 1}. ${x}`).join('\n')}\n\n${CONTEXT('refute-' + c.key)}`,
      { label: `refute:${c.key}`, phase: 'Refute', schema: REFUTE_SCHEMA }).then(v => ({ key: c.key, result: res, verdicts: v && v.verdicts }))
  })
return results
```
