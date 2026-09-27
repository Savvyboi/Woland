// Runs the website's citation code (site/assets/js/core.js) in Node against a built site.
// usage: node cite_harness.mjs <built site dir> '<JSON list of {month, i} hits>'
// Prints, per document: its record (as the citation dialog and the CSV export give it) and its BibTeX key.
import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [site, hits] = process.argv.slice(2);
globalThis.location = { search: "", origin: "https://example.org", pathname: "/woland/" };
if (typeof navigator === "undefined") globalThis.navigator = { languages: ["en"], language: "en" };
globalThis.fetch = async (url) => {
  try {
    return new Response(await readFile(path.join(site, decodeURIComponent(String(url)))), { status: 200 });
  } catch {
    return new Response("not found", { status: 404 });
  }
};

const core = await import(pathToFileURL(path.join(site, "assets/js/core.js")));
const { loadDocs } = await import(pathToFileURL(path.join(site, "assets/js/search.js")));
await core.loadMeta();
const out = [];
for (const d of await loadDocs(JSON.parse(hits))) {
  const id = await core.recordId(d);
  const bib = core.citations(d, id).BibTeX;
  out.push({ record: core.recordOf(d, id), key: bib.match(/^@misc\{([^,]+),/)[1], bib });
}
console.log(JSON.stringify(out));
