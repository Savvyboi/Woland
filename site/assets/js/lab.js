// The Query Lab: SQL over the monthly Parquet snapshots (data/parquet/, woland/parquet.py) in the browser, with
// DuckDB-Wasm. DuckDB (from jsDelivr) and its Parquet extension (which DuckDB loads from extensions.duckdb.org),
// about 10 MB compressed, are fetched only when the reader first runs a query; no other page loads them. The snapshots are read in ranges over HTTP, so a query that needs a few columns of
// one month downloads little more than those.
import { $, el, t, getJSON, initChrome, fillFooter, loadMeta, fmtInt, fmtDay, showError, downloadCSV } from "./core.js";

initChrome("lab");
const root = $("#lab");

const DUCKDB = "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.32.0/+esm";
const SHOWN = 500;   // result rows shown; downloads hold them all

// `complete` is the view of completed days without machine-written items, which the site's own figures use
const PRESETS = [
  ["spikes", `-- each framing's share of an outlet's articles, by week (completed days only)
WITH weeks AS (
  SELECT outlet, date_trunc('week', day) AS week, count(*) AS total FROM complete GROUP BY ALL
), hits AS (
  SELECT outlet, date_trunc('week', day) AS week, f AS framing, count(*) AS articles
  FROM complete, unnest(framings) AS u(f) GROUP BY ALL
)
SELECT outlet, framing, week, articles, round(100.0 * articles / total, 2) AS pct_of_outlet_week
FROM hits JOIN weeks USING (outlet, week)
WHERE articles >= 10
ORDER BY pct_of_outlet_week DESC
LIMIT 200;`],
  ["pivot", `-- which framings come with which countries: articles that match both
SELECT c AS country, f AS framing, count(*) AS articles
FROM complete, unnest(countries) AS uc(c), unnest(framings) AS uf(f)
WHERE c <> 'RU'
GROUP BY ALL
ORDER BY articles DESC
LIMIT 200;`],
  ["unread", `-- how much of each outlet Woland could read: pages read, headline only, read from the Internet Archive
SELECT outlet,
       count(*) AS articles,
       round(100.0 * count(*) FILTER (WHERE words IS NOT NULL) / count(*), 1) AS pct_page_read,
       count(*) FILTER (WHERE headline_only) AS headline_only,
       count(*) FILTER (WHERE archive_capture IS NOT NULL) AS from_archive
FROM complete
GROUP BY outlet
ORDER BY pct_page_read;`],
  ["abroad", `-- the foreign-facing outlets against the rest, day by day: articles, and the share matching a framing
SELECT day,
       CASE WHEN outlet_group = 'foreign' THEN 'foreign-facing' ELSE 'domestic' END AS audience,
       count(*) AS articles,
       round(100.0 * count(*) FILTER (WHERE len(framings) > 0) / count(*), 1) AS pct_framed
FROM complete
GROUP BY ALL
ORDER BY day, audience;`],
  ["anon", `-- how often headlines quote an unnamed expert, analyst or source ("role"), by outlet
SELECT outlet,
       count(*) FILTER (WHERE speaker IS NOT NULL) AS quoting,
       count(*) FILTER (WHERE speaker_kind = 'role') AS unnamed,
       round(100.0 * count(*) FILTER (WHERE speaker_kind = 'role')
             / nullif(count(*) FILTER (WHERE speaker IS NOT NULL), 0), 1) AS pct_unnamed
FROM complete
GROUP BY outlet
HAVING count(*) FILTER (WHERE speaker IS NOT NULL) >= 50
ORDER BY pct_unnamed DESC;`],
];

let db = null;
let conn = null;

async function connect(manifest) {
  const duckdb = await import(DUCKDB);
  const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
  // a worker cannot be started from another origin's script directly: start one that imports it
  const workerUrl = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }));
  const worker = new Worker(workerUrl);
  const d = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING), worker);
  try {
    await d.instantiate(bundle.mainModule, bundle.pthreadWorker);
    const names = [];
    for (const f of manifest.files) {
      await d.registerFileURL(f.file, new URL(`data/parquet/${f.file}`, location.href).href, duckdb.DuckDBDataProtocol.HTTP, false);
      names.push(`'${f.file}'`);
    }
    const c = await d.connect();
    await c.query(`CREATE VIEW articles AS SELECT * FROM read_parquet([${names.join(", ")}])`);
    const through = manifest.complete_through ? `day <= DATE '${manifest.complete_through}' AND ` : "";
    await c.query(`CREATE VIEW complete AS SELECT * FROM articles WHERE ${through}NOT machine`);
    db = d;
    conn = c;
  } catch (e) {
    await d.terminate().catch(() => {});   // the next run starts afresh
    throw e;
  } finally {
    URL.revokeObjectURL(workerUrl);
  }
}

// Arrow values as plain JSON: 64-bit integers as numbers, times and days as ISO text, lists as arrays
function plain(v, type) {
  if (v === null || v === undefined) return null;
  const ty = String(type);
  if (typeof v === "bigint") return Number.isSafeInteger(Number(v)) ? Number(v) : String(v);
  if (ty.startsWith("Timestamp")) return new Date(Number(v)).toISOString().replace(".000Z", "Z");
  if (ty.startsWith("Date")) return new Date(Number(v)).toISOString().slice(0, 10);
  if (v && typeof v.toArray === "function") return [...v.toArray()].map((x) => plain(x, ""));
  if (v instanceof Uint8Array) return [...v];
  return v;
}

function tableOf(result) {
  const fields = result.schema.fields;
  const rows = result.toArray().map((r) => fields.map((f) => plain(r[f.name], f.type)));
  return { cols: fields.map((f) => f.name), rows };
}

const cell = (v) => (v === null ? el("span", { class: "null" }, "null") : Array.isArray(v) ? v.join(", ") : String(v));

function render(manifest) {
  const sql = el("textarea", { id: "lab-sql", spellcheck: "false", rows: 12, "aria-label": t("lab.sql") }, PRESETS[0][1]);
  const run = el("button", { type: "button", class: "btn btn-gilt" }, t("lab.run"));
  const status = el("p", { class: "lab-status syntax", role: "status", "aria-live": "polite" });
  const out = el("div", { class: "lab-out" });
  const dl = el("div", { class: "lab-dl" });
  let last = null;

  const presets = el("div", { class: "lab-presets", role: "group", "aria-label": t("lab.presets") },
    PRESETS.map(([id, text]) => {
      const b = el("button", { type: "button", class: "btn" }, t(`lab.preset.${id}`));
      b.addEventListener("click", () => { sql.value = text; go(); });
      return b;
    }));

  async function go() {
    run.disabled = true;
    try {
      if (!conn) {
        status.textContent = t("lab.loading");
        await connect(manifest);
      }
      status.textContent = t("lab.running");
      const t0 = performance.now();
      const res = tableOf(await conn.query(sql.value));
      last = res;
      status.textContent = t("lab.done", { n: fmtInt(res.rows.length), s: ((performance.now() - t0) / 1000).toFixed(1) })
        + (res.rows.length > SHOWN ? ` ${t("lab.shown", { n: fmtInt(SHOWN) })}` : "");
      out.replaceChildren(el("div", { class: "plate table-wrap" }, el("table", { class: "table-view lab-table" },
        el("thead", {}, el("tr", {}, res.cols.map((c) => el("th", { scope: "col" }, c)))),
        el("tbody", {}, res.rows.slice(0, SHOWN).map((r) => el("tr", {}, r.map((v) => el("td", {}, cell(v)))))))));
      dl.hidden = !res.rows.length;
    } catch (e) {
      status.textContent = `${t("lab.error")} ${e.message || e}`;
      out.replaceChildren();
      dl.hidden = true;
    } finally {
      run.disabled = false;
    }
  }
  run.addEventListener("click", go);
  sql.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); go(); } });

  const csv = el("button", { type: "button", class: "btn" }, t("lab.csv"));
  csv.addEventListener("click", () => last && downloadCSV("woland-query.csv", last.cols,
    last.rows.map((r) => r.map((v) => (Array.isArray(v) ? v.join("|") : v)))));
  const json = el("button", { type: "button", class: "btn" }, t("lab.json"));
  json.addEventListener("click", () => {
    if (!last) return;
    const text = JSON.stringify(last.rows.map((r) => Object.fromEntries(last.cols.map((c, i) => [c, r[i]]))), null, 1);
    const a = el("a", { href: URL.createObjectURL(new Blob([text], { type: "application/json" })), download: "woland-query.json" });
    document.body.append(a);
    a.click();
    a.remove();
  });
  dl.append(csv, json);
  dl.hidden = true;

  const total = manifest.files.reduce((s, f) => s + f.rows, 0);
  const mb = (b) => (b / 1e6).toFixed(1);
  root.replaceChildren(
    el("p", { class: "lede dropcap" }, t("lab.lede", { n: fmtInt(total), months: fmtInt(manifest.files.length) })),
    el("p", { class: "syntax" }, t("lab.views", { through: manifest.complete_through ? fmtDay(manifest.complete_through) : "–" })),
    el("section", { class: "section" },
      el("div", { class: "section-head" }, el("h2", {}, t("lab.presets"))), presets,
      el("label", { class: "lab-label", for: "lab-sql" }, t("lab.sql")), sql,
      el("div", { class: "lab-actions" }, run, el("small", {}, t("lab.keys")), dl), status, out),
    el("section", { class: "section" },
      el("div", { class: "section-head" }, el("h2", {}, t("lab.files"))),
      el("p", {}, t("lab.files.about")),
      el("ul", { class: "lab-files" }, manifest.files.map((f) => el("li", {},
        el("a", { href: `data/parquet/${f.file}`, download: f.file }, f.file),
        el("small", {}, ` ${t("lab.file", { n: fmtInt(f.rows), mb: mb(f.bytes) })}${f.open ? ` · ${t("day.open.short")}` : ""}`),
        el("code", { class: "sha" }, f.sha256.slice(0, 16))))),
      el("p", { class: "syntax" }, el("a", { href: "data/parquet/manifest.json" }, "manifest.json"), " · ", t("lab.local"))),
    el("section", { class: "section" },
      el("details", {}, el("summary", {}, t("lab.columns")),
        el("div", { class: "table-wrap" }, el("table", { class: "table-view lab-cols" },
          el("thead", {}, el("tr", {}, el("th", { scope: "col" }, t("lab.col.name")), el("th", { scope: "col" }, t("lab.col.type")),
            el("th", { scope: "col", style: { textAlign: "left" } }, t("lab.col.about")))),
          el("tbody", {}, manifest.columns.map((c) => el("tr", {}, el("td", {}, el("code", {}, c.name)), el("td", {}, c.type),
            el("td", { style: { textAlign: "left" } }, c.about)))))))),
    el("p", { class: "syntax" }, t("lab.caveat"), " ", el("a", { href: "method.html#matching" }, `${t("nav.method")} →`)),
  );
}

async function start() {
  try {
    await loadMeta();
    fillFooter();
    const manifest = await getJSON("parquet/manifest.json").catch(() => null);
    if (!manifest || !manifest.files?.length) {
      root.replaceChildren(el("p", {}, t("lab.none")));
      return;
    }
    render(manifest);
  } catch (e) {
    showError(root, e);
  }
}
start();
