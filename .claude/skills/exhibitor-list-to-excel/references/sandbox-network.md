# Network trouble in sandboxes (Claude Code cloud and similar)

Symptom, then cause, then what to do.

**curl: `CONNECT tunnel failed, response 403`; a fetch tool: `getaddrinfo ENOTFOUND <host>` for a
real site.** The environment's network policy does not allow that host. Do not retry or route
around it. Tell the user exactly which host or hosts to allow: in Claude Code on the web that is the
environment's settings, Network access, then add the host under allowed domains or pick full
access. Name every host you already know you will need in one go: the list page's host, the host
of a third-party directory widget, and the script and CDN hosts the page loads if you will walk it
in a browser. In Claude Code cloud, `curl -sS "$HTTPS_PROXY/__agentproxy/status"` lists recent
proxy failures by host, and `/root/.ccr/README.md` explains each failure class.

**Headless Chromium gets status 502 with the body `upstream request failed`, while curl on the
same URL works.** Chromium's requests are failing inside the egress proxy. Feed the browser through
curl: `page.route('**/*', ...)`, fetch each allowed request with curl and `route.fulfill` the
result. `scripts/walk_pages.js` does this by default (`--fetch curl`).

**The page loads in the browser but its pagination never appears** (for example, no DataTables
info element). Look for synchronous `<script src="http://...">` tags from third-party hosts: one
that never loads blocks the rest of the page's scripts. Abort requests to hosts other than the site
and its own script and CDN hosts (`walk_pages.js` does).

**Playwright says an element is hidden or not visible.** The site's CSS hides it from Playwright's
point of view. Wait with `state: 'attached'` and click with `element.click()` inside
`page.evaluate`.

**A large download is cut off ("connection reset", "unexpected EOF").** Retry once and check the
proxy status for the host before deciding the site refused.

**TLS errors (`certificate verify failed`).** The tool is not using the sandbox's CA bundle. Point
it at the bundle (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS`); Claude Code cloud
sets these for common tools. Never turn verification off.
