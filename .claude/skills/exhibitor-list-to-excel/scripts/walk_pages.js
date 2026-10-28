#!/usr/bin/env node
// Walk every page of a list that is paginated in the browser (DataTables and similar) using the
// site's own "next" control, and record what each page shows. Compare the result with your scrape
// (compare_records.py) to prove the count, the rows and their order match what visitors see.
//
// Usage:
//   node walk_pages.js --url URL --out walk.json [options]
//
// Options (defaults fit DataTables, found through its "<table id>_info" element):
//   --rows SELECTOR      rows on the current page              (default: "#<table> tbody tr")
//   --next SELECTOR      the next-page control                 (default: "#<table>_paginate .next")
//   --info SELECTOR      the "Showing x to y of z" text         (default: "#<table>_info")
//   --name SELECTOR      element in a row holding the name      (default: first line of the first cell)
//   --columns a,b,c      names for the row's cells, in order    (default: name,col2,col3,...)
//   --fetch curl|browser how the page and its resources load   (default: curl)
//   --max-pages N        safety stop                           (default: 500)
//
// Why --fetch curl: in some sandboxes headless Chromium's own requests get "502 upstream request
// failed" from the egress proxy although curl works. In curl mode the page, its own site and the
// hosts of its <script>/<link> tags are fetched with curl and handed to the browser; images, fonts,
// media, trackers and every other host are skipped. That also stops a synchronous third-party
// script from stalling page load (one did, and the site's pagination never initialised).
// Use --fetch browser where Chromium can reach the site directly.
const { chromium } = require('playwright');
const { execFile } = require('child_process');
const fs = require('fs');

const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';
const TRACKERS = /(googletagmanager|google-analytics|doubleclick|facebook|hotjar|clarity\.ms|linkedin|twitter|tiktok|hubspot|recaptcha|gstatic)\./;

function parseArgs(argv) {
  const args = { fetch: 'curl', maxPages: 500 };
  for (let i = 2; i < argv.length; i += 2) {
    const key = argv[i].replace(/^--/, '').replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    args[key] = argv[i + 1];
  }
  if (!args.url || !args.out) {
    console.error('usage: node walk_pages.js --url URL --out walk.json [--rows SEL --next SEL --info SEL --name SEL --columns a,b --fetch curl|browser]');
    process.exit(2);
  }
  args.maxPages = Number(args.maxPages);
  return args;
}

function curl(url) {
  return new Promise((resolve, reject) => {
    execFile('curl', ['-sS', '-L', '--compressed', '-m', '60', '-A', UA, '-w', '\n%{http_code}|%{content_type}', url],
      { maxBuffer: 128 * 1024 * 1024, encoding: 'buffer' }, (err, stdout) => {
        if (err) return reject(err);
        const nl = stdout.lastIndexOf(10);
        const [status, type] = stdout.slice(nl + 1).toString().split('|');
        resolve({ status: Number(status), contentType: type || 'application/octet-stream', body: stdout.slice(0, nl) });
      });
  });
}

async function routeThroughCurl(page, url) {
  const first = await curl(url);
  const html = first.body.toString('utf8');
  const allowed = new Set([new URL(url).hostname]);
  for (const m of html.matchAll(/<(?:script|link)\b[^>]*?(?:src|href)=["'](https:\/\/[^"'\/]+)/gi)) {
    const host = new URL(m[1]).hostname;
    if (!TRACKERS.test(host)) allowed.add(host);
  }
  await page.route('**/*', async route => {
    const req = route.request();
    const host = new URL(req.url()).hostname;
    if (req.method() !== 'GET' || !allowed.has(host) || ['image', 'font', 'media'].includes(req.resourceType())) {
      return route.abort();
    }
    try {
      const r = req.url() === url ? first : await curl(req.url());
      return route.fulfill({ status: r.status, contentType: r.contentType, body: r.body });
    } catch (e) {
      return route.abort();
    }
  });
  return [...allowed];
}

(async () => {
  const args = parseArgs(process.argv);
  const browser = await chromium.launch();
  const page = await browser.newPage({ userAgent: UA });
  const hosts = args.fetch === 'curl' ? await routeThroughCurl(page, args.url) : null;
  await page.goto(args.url, { waitUntil: 'domcontentloaded', timeout: 120000 });

  if (!args.rows) {
    // DataTables: find "<table id>_info" and derive the other selectors from the table id.
    // Some sites' CSS makes these controls count as hidden to Playwright, so wait for "attached".
    const info = await page.waitForSelector('[id$="_info"].dataTables_info', { state: 'attached', timeout: 60000 })
      .catch(() => null);
    if (!info) throw new Error('No DataTables info element found; pass --rows, --next and --info selectors.');
    const table = (await info.getAttribute('id')).replace(/_info$/, '');
    args.rows = `#${table} tbody tr`;
    args.next = args.next || `#${table}_paginate .next`;
    args.info = args.info || `#${table}_info`;
  } else {
    await page.waitForSelector(args.rows, { state: 'attached', timeout: 60000 });
  }
  const columns = args.columns ? args.columns.split(',') : null;

  const readPage = () => page.$$eval(args.rows, (trs, opts) => trs.map(tr => {
    const clean = s => (s || '').replace(/\s+/g, ' ').trim();
    const cells = [...tr.querySelectorAll(':scope > td, :scope > th')].map(td => clean(td.innerText));
    const nameEl = opts.name ? tr.querySelector(opts.name) : null;
    const firstLine = ((tr.querySelector('td, th') || tr).innerText || '').split('\n').map(clean).find(Boolean) || '';
    return { name: nameEl ? clean(nameEl.innerText) : firstLine, cells };
  }), { name: args.name || null });
  const readInfo = () => args.info ? page.evaluate(sel => {
    const el = document.querySelector(sel);
    return el ? el.textContent.replace(/\s+/g, ' ').trim() : '';
  }, args.info) : Promise.resolve('');

  // What the first rows and the info text say right now; it changes when a new page is drawn.
  const signature = () => page.evaluate(({ rowsSel, infoSel }) => {
    const clean = s => (s || '').replace(/\s+/g, ' ').trim();
    const rows = [...document.querySelectorAll(rowsSel)].slice(0, 3).map(tr => clean(tr.textContent));
    const info = infoSel && document.querySelector(infoSel) ? clean(document.querySelector(infoSel).textContent) : '';
    return JSON.stringify(rows) + info;
  }, { rowsSel: args.rows, infoSel: args.info || null });

  const records = [];
  const infos = [];
  for (let n = 1; n <= args.maxPages; n++) {
    const rows = await readPage();
    infos.push(await readInfo());
    rows.forEach((r, i) => {
      const rec = { page: n, position: i + 1, name: r.name };
      (columns || r.cells.map((_, j) => `col${j + 1}`)).forEach((key, j) => {
        if (key && key !== 'name') rec[key] = r.cells[j] ?? '';
      });
      records.push(rec);
    });
    const before = await signature();
    const clicked = await page.evaluate(sel => {
      const next = document.querySelector(sel);
      if (!next || /disabled/.test(next.className) || next.getAttribute('aria-disabled') === 'true') return false;
      next.click();
      return true;
    }, args.next);
    if (!clicked) break;
    let changed = false;
    for (let waited = 0; waited < 30000 && !changed; waited += 200) {
      await page.waitForTimeout(200);
      changed = (await signature()) !== before;
    }
    if (!changed) {
      console.error(`page ${n + 1} never appeared after clicking next; stopping`);
      break;
    }
  }

  const total = await page.evaluate(sel => {
    try {
      const $t = window.jQuery && window.jQuery(sel.split(' ')[0]);
      if (!$t || !$t.length || !$t.dataTable) return null;
      const api = $t.DataTable ? $t.DataTable() : null;
      if (api && api.page && api.page.info) return api.page.info().recordsTotal;
      return $t.dataTable().fnSettings().fnRecordsTotal();
    } catch (e) {
      return null;
    }
  }, args.rows);

  const result = {
    url: args.url, fetch: args.fetch, hosts_allowed: hosts, info_first: infos[0] || '', info_last: infos[infos.length - 1] || '',
    pages: infos.length, rows_seen: records.length, datatables_total: total, records,
  };
  fs.writeFileSync(args.out, JSON.stringify(result, null, 1));
  console.log(`site says: ${result.info_first || '(no info text)'} | last page: ${result.info_last}`);
  console.log(`pages walked: ${result.pages} | rows seen: ${result.rows_seen} | table total: ${total ?? 'n/a'} | saved ${args.out}`);
  await browser.close();
})().catch(e => { console.error(e.message || e); process.exit(1); });
