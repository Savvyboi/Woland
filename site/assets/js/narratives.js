// Chapter II: one narrative at a time — over time, by outlet type, at home and abroad, by outlet.
import {
  $, el, t, tl, META, loadMeta, getJSON, initChrome, fillFooter, fmtInt, fmtPct, outlet, narrative,
  groupVar, articleCard, fromExample, archiveSearch, showError, GROUPS,
} from "./core.js";
import { lineChart, heatmap, barList, withTable, tableOf } from "./charts.js";

initChrome("narratives");
const side = $("#side");
const main = $("#narrative");
let series = null;
let range = new URLSearchParams(location.search).get("r") || "30";

const sum = (arr) => arr.reduce((a, b) => a + b, 0);

function windowDays() {
  const n = series.days.length;
  const k = range === "all" ? n : Math.min(n, Number(range));
  return { start: n - k, days: series.days.slice(n - k) };
}

/** Daily counts for a set of outlets: {hits[], totals[]} over the window. */
function counts(nid, outletIds, start) {
  const by = series.nar[nid] || {};
  const len = series.days.length - start;
  const hits = new Array(len).fill(0), totals = new Array(len).fill(0);
  for (const o of outletIds) {
    const h = by[o], tt = series.totals[o];
    if (!tt) continue;
    for (let i = 0; i < len; i++) { hits[i] += h ? h[start + i] : 0; totals[i] += tt[start + i]; }
  }
  return { hits, totals };
}
const ratio = (h, tt) => h.map((v, i) => (tt[i] ? v / tt[i] : null));
function rolling(h, tt, w = 7) {
  return h.map((_, i) => {
    let a = 0, b = 0;
    for (let j = Math.max(0, i - w + 1); j <= i; j++) { a += h[j]; b += tt[j]; }
    return b ? a / b : null;
  });
}

function plate(no, title, sub, ...body) {
  const tools = el("span", { class: "plate-tools" });
  return el("figure", { class: "plate" },
    el("figcaption", {}, el("span", { class: "plate-no" }, `${t("plate")} ${no}`), el("span", { class: "plate-title" }, title), tools,
      sub ? el("span", { class: "plate-sub" }, sub) : null), ...body);
}

function renderSide(current) {
  const { start } = windowDays();
  const all = Object.keys(series.totals);
  const block = (family, title) => {
    const items = META.narratives.filter((n) => n.family === family).map((n) => {
      const c = counts(n.id, all, start);
      return { n, total: sum(c.hits) };
    }).sort((a, b) => b.total - a.total);
    return [el("h3", {}, title), el("ul", {}, items.map(({ n, total }) => el("li", {},
      el("a", { href: `#${n.id}`, "aria-current": n.id === current ? "true" : "false" },
        el("span", {}, tl(n.label)), el("span", { class: "cnt" }, fmtInt(total))))))];
  };
  side.replaceChildren(...block("framing", t("narratives.framings")), ...block("topic", t("narratives.topics")));
}

function rangeControl() {
  const seg = el("div", { class: "seg", role: "group", "aria-label": t("range.label") });
  for (const r of ["7", "30", "90", "all"]) {
    const b = el("button", { type: "button", "aria-pressed": String(r === range) }, t(`range.${r}`));
    b.addEventListener("click", () => {
      range = r;
      const u = new URL(location.href);
      u.searchParams.set("r", r);
      history.replaceState(null, "", u);
      route();
    });
    seg.append(b);
  }
  return el("div", { class: "filters" }, el("div", { class: "field" }, t("range.label"), seg));
}

async function renderNarrative(id) {
  const n = narrative(id);
  const { start, days } = windowDays();
  const allIds = Object.keys(series.totals);
  const all = counts(id, allIds, start);
  const fmt = (v) => fmtPct(v, v < 0.01 ? 2 : 1);
  const kids = [];
  kids.push(el("h2", { style: { font: "500 2.1rem/1.15 var(--display)", margin: "0 0 .3rem" } }, tl(n.label)));
  if (n.about) kids.push(el("p", { style: { color: "var(--text-2)", margin: "0 0 .4rem", maxWidth: "46rem" } }, tl(n.about)));
  kids.push(el("p", { class: "syntax" }, t("narratives.total", { n: fmtInt(sum(all.hits)) }), " · ",
    el("a", { href: archiveSearch({ k: id, from: days[0], to: days[days.length - 1] }) }, `${t("nav.archive")} →`)));
  kids.push(rangeControl());

  // Plate I — share over time
  const daily = ratio(all.hits, all.totals);
  const avg = rolling(all.hits, all.totals);
  const c1 = el("div");
  const p1 = plate("I", t("narratives.share", { name: tl(n.label) }), t("narratives.share.sub"), c1);
  kids.push(p1);

  // Plate II — small multiples by outlet group
  const sm = el("div", { class: "small-multiples" });
  const p2 = plate("II", t("narratives.groups"), t("narratives.groups.sub"), sm);
  kids.push(el("div", { class: "section" }, p2));

  // Plate III — at home and abroad
  const ru = counts(id, allIds.filter((o) => outlet(o).lang === "ru"), start);
  const en = counts(id, allIds.filter((o) => outlet(o).lang === "en"), start);
  const c3 = el("div");
  const p3 = plate("III", t("narratives.audience"), t("narratives.audience.sub"), c3);

  // Plate V — by outlet over the period
  const perOutlet = allIds.map((o) => {
    const h = (series.nar[id] || {})[o];
    const tt = series.totals[o];
    const hs = h ? sum(h.slice(start)) : 0, ts = sum(tt.slice(start));
    return { o, hs, ts, share: ts ? hs / ts : 0 };
  }).filter((x) => x.ts >= 20).sort((a, b) => b.share - a.share);
  const c5 = el("div");
  const p5 = plate("IV", t("narratives.byoutlet"), t("narratives.byoutlet.sub"), c5);
  kids.push(el("div", { class: "section grid-2" }, p3, p5));

  // Plate IV — heatmap
  const c4 = el("div");
  const p4 = plate("V", t("narratives.heat"), t("narratives.heat.sub"), c4);
  kids.push(el("div", { class: "section" }, p4));

  // definition
  const pats = (lang) => (n.patterns?.[lang] || []).map((p) => el("span", { lang }, p));
  kids.push(el("div", { class: "lexicon-card" },
    el("strong", {}, t("narratives.definition")),
    el("p", { class: "pats" }, el("b", {}, `${t("narratives.patterns.ru")}: `), pats("ru")),
    el("p", { class: "pats" }, el("b", {}, `${t("narratives.patterns.en")}: `), pats("en")),
    el("p", { class: "syntax", style: { margin: 0 } }, t("narratives.patterns.note"))));

  // examples from the latest digests
  const exList = el("ul", { class: "articles" });
  kids.push(el("section", { class: "section" }, el("div", { class: "section-head" }, el("h2", {}, t("narratives.examples"))), exList));
  main.replaceChildren(...kids);

  lineChart(c1, { days, yFormat: fmt, series: [
    { label: t("series.daily"), color: "var(--gilt-dim)", values: daily, dots: true, line: false, r: 2.5 },
    { label: t("series.avg7"), color: "var(--gilt)", values: avg, width: 2.5 },
  ] });
  withTable(p1, c1, () => tableOf(days, [{ label: t("series.daily"), values: daily }, { label: t("series.avg7"), values: avg }], fmt));

  const allAvg = rolling(all.hits, all.totals);
  const groupTables = [];
  for (const g of GROUPS) {
    const ids = allIds.filter((o) => outlet(o).group === g);
    if (!ids.length) continue;
    const c = counts(id, ids, start);
    groupTables.push({ g, label: t(`group.${g}`), values: rolling(c.hits, c.totals) });
  }
  // small multiples share one y-scale, so panels can be compared at a glance
  const smMax = Math.max(1e-9, ...allAvg.filter((v) => v !== null), ...groupTables.flatMap((x) => x.values.filter((v) => v !== null)));
  for (const gt of groupTables) {
    const box = el("div");
    sm.append(el("div", {}, el("div", { class: "sm-title" }, el("span", { class: "group-key", style: { background: groupVar(gt.g) } }), gt.label), box));
    lineChart(box, { days, height: 130, legend: false, yFormat: fmt, yMax: smMax, series: [
      { label: t("series.all"), color: "var(--muted-series)", values: allAvg, width: 1.5 },
      { label: gt.label, color: groupVar(gt.g), values: gt.values },
    ] });
  }
  withTable(p2, sm, () => tableOf(days, [{ label: t("series.all"), values: allAvg }, ...groupTables], fmt));

  const ruAvg = rolling(ru.hits, ru.totals), enAvg = rolling(en.hits, en.totals);
  lineChart(c3, { days, height: 200, yFormat: fmt, series: [
    { label: t("lang.ru"), color: "var(--s1)", values: ruAvg },
    { label: t("lang.en"), color: "var(--s2)", values: enAvg },
  ] });
  withTable(p3, c3, () => tableOf(days, [{ label: t("lang.ru"), values: ruAvg }, { label: t("lang.en"), values: enAvg }], fmt));

  barList(c5, perOutlet.map((x) => ({ label: outlet(x.o).name, value: x.share, color: groupVar(outlet(x.o).group),
    href: archiveSearch({ k: id, o: x.o, from: days[0], to: days[days.length - 1] }),
    title: `${fmtInt(x.hs)} / ${fmtInt(x.ts)}` })), fmt);

  const rows = perOutlet.map((x) => {
    const h = (series.nar[id] || {})[x.o] || [];
    const tt = series.totals[x.o];
    return { label: outlet(x.o).name, values: days.map((_, i) => (tt[start + i] ? (h[start + i] || 0) / tt[start + i] : null)),
      sub: days.map((_, i) => `${fmtInt(h[start + i] || 0)} / ${fmtInt(tt[start + i])}`) };
  });
  heatmap(c4, { days, rows, format: fmt });
  withTable(p4, c4, () => tableOf(days, rows.map((r) => ({ label: r.label, values: r.values })), fmt));

  // examples
  const seen = new Set();
  const recent = days.slice(-7).reverse();
  for (const d of recent) {
    let dg;
    try { dg = await getJSON(`days/${d}.json`); } catch (_) { continue; }
    const row = dg.narratives.find((x) => x.id === id);
    for (const ex of row?.ex || []) {
      if (seen.has(ex.u) || seen.size >= 12) continue;
      seen.add(ex.u);
      exList.append(articleCard(fromExample(ex, d, id), { only: n.idx }));
    }
    if (seen.size >= 12) break;
  }
  if (!seen.size) exList.append(el("li", { class: "empty" }, "—"));
}

function route() {
  const id = decodeURIComponent(location.hash.slice(1));
  const n = narrative(id) ? id : META.narratives.find((x) => x.family === "framing").id;
  renderSide(n);
  renderNarrative(n).catch((e) => showError(main, e));
  document.title = `Woland — ${tl(narrative(n).label)}`;
}

async function start() {
  try {
    await loadMeta();
    fillFooter();
    if (!META.last) { main.replaceChildren(el("p", { class: "empty" }, t("empty.nodata"))); return; }
    series = await getJSON("series.json");
    window.addEventListener("hashchange", () => { route(); main.scrollIntoView({ block: "start" }); });
    route();
  } catch (e) {
    showError(main, e);
  }
}
start();
