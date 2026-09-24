// Runs the website's own search code (site/assets/js/search.js) in Node against a built site.
// usage: node search_harness.mjs <built site dir> '<JSON list of queries>'
// Each query is an object for search() — {q, from, to, outlets: [ids], lang, narr, order}.
// Prints, per query, the total and the first hits (outlet, headline, URL).
import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [site, queries] = process.argv.slice(2);

// The browser globals the modules touch.
globalThis.location = { search: "" };
if (typeof navigator === "undefined") globalThis.navigator = { languages: ["en"], language: "en" };
globalThis.fetch = async (url) => {
  try {
    const body = await readFile(path.join(site, decodeURIComponent(String(url))));
    return new Response(body, { status: 200 });
  } catch {
    return new Response("not found", { status: 404 });
  }
};

const core = await import(pathToFileURL(path.join(site, "assets/js/core.js")));
const { search, loadDocs } = await import(pathToFileURL(path.join(site, "assets/js/search.js")));
await core.loadMeta();

const out = [];
for (const q of JSON.parse(queries)) {
  try {
    const res = await search({ order: "new", ...q, outlets: q.outlets ? new Set(q.outlets) : null });
    const docs = await loadDocs(res.hits.slice(0, 100));
    out.push({ total: res.total, hits: docs.map((d) => ({ o: d.o, t: d.t, te: d.te, u: d.u, ks: d.ks, f: d.f })),
               days: Object.fromEntries(res.byDay), forms: [...res.forms].sort() });
  } catch (e) {
    out.push({ error: e.code || String(e) });
  }
}
console.log(JSON.stringify(out));
