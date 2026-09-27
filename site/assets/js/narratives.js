// Chapter II: one narrative at a time — over time, by outlet type, at home and abroad, by outlet.
import {
  $, el, t, tl, META, loadMeta, getJSON, initChrome, fillFooter, fmtInt, fmtPct, fmtDay, outlet, narrative,
  groupVar, articleCard, fromExample, archiveSearch, showError, GROUPS, isOpenDay,
} from "./core.js";
import { lineChart, heatmap, barList, withTable, tableOf } from "./charts.js";

initChrome("narratives");
const side = $("#side");
const main = $("#narrative");
let series = null;
const params = new URLSearchParams(location.search);
let range = params.get("r") || "30";
let includeOpen = params.get("open") === "1";   // days still being collected: left out unless asked for
let panel = params.get("p") === "same" ? "same" : "all";

const sum = (arr) => arr.reduce((a, b) => a + b, 0);

function setParam(k, v) {
  const u = new URL(location.href);
  if (v === null) u.searchParams.delete(k); else u.searchParams.set(k, v);
  history.replaceState(null, "", u);
}

/** The days in view: the chosen period, ending with the last completed day unless open days are included. */
function windowDays() {
  const n = series.days.length;
  let last = n - 1;
  if (!includeOpen) while (last > 0 && isOpenDay(series.days[last])) last--;
  const k = range === "all" ? last + 1 : Math.min(last + 1, Number(range));
  const start = last + 1 - k;
  const days = series.days.slice(start, last + 1);
  const openAt = days.findIndex((d) => isOpenDay(d));
  return { start, end: last + 1, days, openFrom: openAt < 0 ? null : openAt };
}

/** The outlets in view: all of them, or only those collected on every day of the period. */
function outletIds(start, end) {
  const all = Object.keys(series.totals);
  if (panel !== "same") return { ids: all, dropped: [] };
  const ids = [], dropped = [];
  for (const o of all) {
    const codes = (series.cov?.[o] || "").slice(start, end);
    if (codes.length === end - start && !codes.includes("m")) ids.push(o); else dropped.push(o);
  }
  return { ids, dropped };
}

/** Daily counts for a set of outlets over [start, end): matching articles, all articles, outlets publishing. */
function counts(nid, outletIds_, start, end) {
  const by = series.nar[nid] || {};
  const len = end - start;
  const hits = new Array(len).fill(0), totals = new Array(len).fill(0), outlets = new Array(len).fill(0);
  for (const o of outletIds_) {
    const h = by[o], tt = series.totals[o];
    if (!tt) continue;
    for (let i = 0; i < len; i++) {
      hits[i] += h ? h[start + i] : 0;
      totals[i] += tt[start + i];
      outlets[i] += tt[start + i] > 0 ? 1 : 0;
    }
  }
  return { hits, totals, outlets };
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
  const { start, end } = windowDays();
  const { ids } = outletIds(start, end);
  const block = (family, title) => {
    const items = META.narratives.filter((n) => n.family === family).map((n) => {
      const c = counts(n.id, ids, start, end);
      return { n, total: sum(c.hits) };
    }).sort((a, b) => b.total - a.total);
    return [el("h3", {}, title), el("ul", {}, items.map(({ n, total }) => el("li", {},
      el("a", { href: `#${n.id}`, "aria-current": n.id === current ? "true" : "false" },
        el("span", {}, tl(n.label)), el("span", { class: "cnt" }, fmtInt(total))))))];
  };
  side.replaceChildren(...block("framing", t("narratives.framings")), ...block("topic", t("narratives.topics")));
}

function seg(label, options, value, onPick) {
  const box = el("div", { class: "seg", role: "group", "aria-label": label });
  for (const [v, text] of options) {
    const b = el("button", { type: "button", "aria-pressed": String(v === value) }, text);
    b.addEventListener("click", () => onPick(v));
    box.append(b);
  }
  return el("div", { class: "field" }, label, box);
}

function controls(w, dropped) {
  const openDays = series.days.filter((d) => isOpenDay(d));
  const openBox = el("input", { type: "checkbox", id: "incl-open", checked: includeOpen || null });
  openBox.addEventListener("change", () => { includeOpen = openBox.checked; setParam("open", includeOpen ? "1" : null); route(); });
  const bar = el("div", { class: "filters" },
    seg(t("range.label"), ["7", "30", "90", "all"].map((r) => [r, t(`range.${r}`)]), range,
      (r) => { range = r; setParam("r", r); route(); }),
    seg(t("panel.label"), [["all", t("panel.all")], ["same", t("panel.same")]], panel,
      (p) => { panel = p; setParam("p", p === "same" ? "same" : null); route(); }),
    openDays.length ? el("label", { class: "field check" }, openBox,
      t("narratives.includeopen", { days: openDays.map((d) => fmtDay(d)).join(", ") })) : null);
  const notes = [t("narratives.through", { from: fmtDay(w.days[0]), to: fmtDay(w.days[w.days.length - 1]) })];
  if (openDays.length && !includeOpen) notes.push(t("narratives.openleftout", { days: openDays.map((d) => fmtDay(d)).join(", ") }));
  if (w.openFrom !== null) notes.push(t("narratives.openshown"));
  if (panel === "same") {
    notes.push(dropped.length ? t("panel.same.dropped", { list: dropped.map((o) => outlet(o).name).join(", ") }) : t("panel.same.none"));
  } else {
    notes.push(t("panel.all.note"));
  }
  return [bar, el("p", { class: "syntax window-note" }, notes.join(" "))];
}

/** A pattern group as the lexicon writes it: the words, and when they count. */
function patternList(n, lang) {
  return (n.patterns?.[lang] || []).map((p) => {
    if (typeof p === "string") return el("span", { lang }, p);
    const conds = [];
    if (p.with?.length) conds.push(t("pattern.with", { list: p.with.map((c) => tl(META.contexts?.[c]?.label) || c).join(", ") }));
    if (p.not?.length) conds.push(t("pattern.not", { list: p.not.join(" · ") }));
    return el("span", { class: "group", lang }, p.match.join(" · "), el("small", { lang: document.documentElement.lang }, ` — ${conds.join("; ")}`));
  });
}

function auditLine(n) {
  const c = n.checked;
  if (!c || !c.n) return el("p", { class: "audit none" }, t("narratives.unchecked"));
  const link = META.repo ? el("a", { href: `${META.repo}/blob/main/docs/lexicon-audit.md` }, t("narratives.audit.link")) : null;
  return el("p", { class: "audit" }, t("narratives.checked", { fit: fmtInt(c.fit), n: fmtInt(c.n), date: fmtDay(c.date) }), " ", link);
}

async function renderNarrative(id) {
  const n = narrative(id);
  const w = windowDays();
  const { start, end, days, openFrom } = w;
  const { ids: allIds, dropped } = outletIds(start, end);
  const all = counts(id, allIds, start, end);
  const fmt = (v) => fmtPct(v, v < 0.01 ? 2 : 1);
  const openNote = (i) => (openFrom !== null && i >= openFrom ? t("day.open.short") : "");
  const kids = [];
  kids.push(el("h2", { style: { font: "500 2.1rem/1.15 var(--display)", margin: "0 0 .3rem" } }, tl(n.label)));
  if (n.about) kids.push(el("p", { style: { color: "var(--text-2)", margin: "0 0 .4rem", maxWidth: "46rem" } }, tl(n.about)));
  kids.push(el("p", { class: "syntax" }, t("narratives.total", { n: fmtInt(sum(all.hits)), all: fmtInt(sum(all.totals)) }), " · ",
    el("a", { href: archiveSearch({ k: id, from: days[0], to: days[days.length - 1] }) }, `${t("nav.archive")} →`)));
  kids.push(...controls(w, dropped));

  // Plate I — share over time, with what it is a share of
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
  const ru = counts(id, allIds.filter((o) => outlet(o).lang === "ru"), start, end);
  const en = counts(id, allIds.filter((o) => outlet(o).lang === "en"), start, end);
  const c3 = el("div");
  const p3 = plate("III", t("narratives.audience"), t("narratives.audience.sub"), c3);

  // Plate IV — by outlet over the period
  const perOutlet = allIds.map((o) => {
    const h = (series.nar[id] || {})[o];
    const tt = series.totals[o];
    const hs = h ? sum(h.slice(start, end)) : 0, ts = sum(tt.slice(start, end));
    return { o, hs, ts, share: ts ? hs / ts : 0 };
  }).filter((x) => x.ts >= 20).sort((a, b) => b.share - a.share);
  const c5 = el("div");
  const p5 = plate("IV", t("narratives.byoutlet"), t("narratives.byoutlet.sub"), c5);
  kids.push(el("div", { class: "section grid-2" }, p3, p5));

  // Plate V — heatmap
  const c4 = el("div");
  const p4 = plate("V", t("narratives.heat"), t("narratives.heat.sub"), c4);
  kids.push(el("div", { class: "section" }, p4));

  // definition
  kids.push(el("div", { class: "lexicon-card" },
    el("strong", {}, t("narratives.definition")),
    auditLine(n),
    el("p", { class: "pats" }, el("b", {}, `${t("narratives.patterns.ru")}: `), patternList(n, "ru")),
    el("p", { class: "pats" }, el("b", {}, `${t("narratives.patterns.en")}: `), patternList(n, "en")),
    el("p", { class: "syntax", style: { margin: 0 } }, t("narratives.patterns.note"), " ",
      el("a", { href: "method.html#matching" }, `${t("nav.method")} →`))));

  // examples from the latest digests
  const exList = el("ul", { class: "articles" });
  kids.push(el("section", { class: "section" }, el("div", { class: "section-head" }, el("h2", {}, t("narratives.examples"))), exList));
  main.replaceChildren(...kids);

  lineChart(c1, { days, yFormat: fmt, openFrom,
    tipExtra: (i) => t("narratives.denominator", { h: fmtInt(all.hits[i]), n: fmtInt(all.totals[i]), k: fmtInt(all.outlets[i]) }),
    series: [
      { label: t("series.daily"), color: "var(--gilt-dim)", values: daily, dots: true, line: false, r: 2.5 },
      { label: t("series.avg7"), color: "var(--gilt)", values: avg, width: 2.5 },
    ] });
  withTable(p1, c1, () => tableOf(days, [
    { label: t("col.matching"), values: all.hits, fmt: fmtInt },
    { label: t("col.all"), values: all.totals, fmt: fmtInt },
    { label: t("col.outlets"), values: all.outlets, fmt: fmtInt },
    { label: t("series.daily"), values: daily },
    { label: t("series.avg7"), values: avg },
  ], fmt, openNote));

  const allAvg = rolling(all.hits, all.totals);
  const groupTables = [];
  for (const g of GROUPS) {
    const gids = allIds.filter((o) => outlet(o).group === g);
    if (!gids.length) continue;
    const c = counts(id, gids, start, end);
    groupTables.push({ g, label: t(`group.${g}`), values: rolling(c.hits, c.totals), c });
  }
  // small multiples share one y-scale, so panels can be compared at a glance
  const smMax = Math.max(1e-9, ...allAvg.filter((v) => v !== null), ...groupTables.flatMap((x) => x.values.filter((v) => v !== null)));
  for (const gt of groupTables) {
    const box = el("div");
    sm.append(el("div", {}, el("div", { class: "sm-title" }, el("span", { class: "group-key", style: { background: groupVar(gt.g) } }), gt.label), box));
    lineChart(box, { days, height: 130, legend: false, yFormat: fmt, yMax: smMax, openFrom,
      tipExtra: (i) => t("narratives.denominator", { h: fmtInt(gt.c.hits[i]), n: fmtInt(gt.c.totals[i]), k: fmtInt(gt.c.outlets[i]) }),
      series: [
        { label: t("series.all"), color: "var(--muted-series)", values: allAvg, width: 1.5 },
        { label: gt.label, color: groupVar(gt.g), values: gt.values },
      ] });
  }
  withTable(p2, sm, () => tableOf(days, [{ label: t("series.all"), values: allAvg }, ...groupTables], fmt, openNote));

  const ruAvg = rolling(ru.hits, ru.totals), enAvg = rolling(en.hits, en.totals);
  lineChart(c3, { days, height: 200, yFormat: fmt, openFrom,
    tipExtra: (i) => `${t("lang.ru")}: ${t("narratives.denominator", { h: fmtInt(ru.hits[i]), n: fmtInt(ru.totals[i]), k: fmtInt(ru.outlets[i]) })} · ${t("lang.en")}: ${t("narratives.denominator", { h: fmtInt(en.hits[i]), n: fmtInt(en.totals[i]), k: fmtInt(en.outlets[i]) })}`,
    series: [
      { label: t("lang.ru"), color: "var(--s1)", values: ruAvg },
      { label: t("lang.en"), color: "var(--s2)", values: enAvg },
    ] });
  withTable(p3, c3, () => tableOf(days, [{ label: t("lang.ru"), values: ruAvg }, { label: t("lang.en"), values: enAvg }], fmt, openNote));

  barList(c5, perOutlet.map((x) => ({ label: outlet(x.o).name, value: x.share, color: groupVar(outlet(x.o).group),
    href: archiveSearch({ k: id, o: x.o, from: days[0], to: days[days.length - 1] }),
    title: `${fmtInt(x.hs)} / ${fmtInt(x.ts)}` })), fmt);
  withTable(p5, c5, () => el("table", { class: "table-view" },
    el("thead", {}, el("tr", {}, el("th", { scope: "col" }, t("col.outlet")), el("th", { scope: "col" }, t("col.matching")),
      el("th", { scope: "col" }, t("col.all")), el("th", { scope: "col" }, t("col.share")))),
    el("tbody", {}, perOutlet.map((x) => el("tr", {}, el("th", { scope: "row" }, outlet(x.o).name),
      el("td", {}, fmtInt(x.hs)), el("td", {}, fmtInt(x.ts)), el("td", {}, fmt(x.share)))))));

  const rows = perOutlet.map((x) => {
    const h = (series.nar[id] || {})[x.o] || [];
    const tt = series.totals[x.o];
    const codes = series.cov?.[x.o] || "";
    return { label: outlet(x.o).name, values: days.map((_, i) => (tt[start + i] ? (h[start + i] || 0) / tt[start + i] : null)),
      states: days.map((_, i) => codes[start + i]),
      sub: days.map((_, i) => `${fmtInt(h[start + i] || 0)} / ${fmtInt(tt[start + i])}`) };
  });
  heatmap(c4, { days, rows, format: fmt, isOpen: isOpenDay });
  withTable(p4, c4, () => tableOf(days, rows.map((r) => ({ label: r.label,
    values: r.values.map((v, i) => (r.states[i] === "m" ? "m" : v)),
    fmt: (v) => (v === "m" ? t("cov.m.short") : fmt(v)) })), fmt, openNote));

  // examples from the latest days in view
  const seen = new Set();
  const recent = days.slice(-7).reverse();
  for (const d of recent) {
    let dg;
    try { dg = await getJSON(`days/${d}.json`); } catch (_) { continue; }
    const row = dg.narratives.find((x) => x.id === id);
    for (const ex of row?.ex || []) {
      if (seen.has(ex.u) || seen.size >= 12) continue;
      if (panel === "same" && !allIds.includes(ex.o)) continue;
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
