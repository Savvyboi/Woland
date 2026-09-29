// Chapter III: the searchable archive.
import {
  $, el, t, tl, META, loadMeta, initChrome, fillFooter, fmtInt, fmtPct, fmtDay, outlet, narrative,
  groupVar, articleCard, showError, addDays, downloadCSV, GROUPS, isOpenDay, recordOf, recordId,
} from "./core.js";
import { search, loadDocs } from "./search.js";
import { columnChart, barList, withTable, tableOf } from "./charts.js";

initChrome("archive");
const form = $("#search-form");
const status = $("#status");
const area = $("#results-area");
const PAGE = 20;
const EXPORT_MAX = 2000;
const EMPTY = { q: "", from: "", to: "", o: "", l: "", k: "", order: "new" };
let current = null, shown = 0, norm = "count";

function fillSelects() {
  const o = $("#outlet");
  o.replaceChildren(el("option", { value: "" }, t("archive.alloutlets")),
    ...GROUPS.map((g) => el("optgroup", { label: t(`group.${g}`) },
      META.outlets.filter((x) => x.group === g && (x.n > 0 || x.enabled)).map((x) => el("option", { value: x.id }, x.name)))));
  $("#lang-f").replaceChildren(el("option", { value: "" }, t("archive.alllangs")),
    el("option", { value: "ru" }, t("lang.ru")), el("option", { value: "en" }, t("lang.en")));
  $("#narr").replaceChildren(el("option", { value: "" }, t("archive.any")),
    ...["framing", "topic"].map((f) => el("optgroup", { label: t(f === "framing" ? "narratives.framings" : "narratives.topics") },
      META.narratives.filter((n) => n.family === f).map((n) => el("option", { value: n.id }, tl(n.label))))));
  $("#order").replaceChildren(el("option", { value: "new" }, t("archive.sort.new")), el("option", { value: "old" }, t("archive.sort.old")));
  for (const id of ["from", "to"]) { $(`#${id}`).min = META.start; $(`#${id}`).max = META.last; }
}

function readParams() {
  const p = new URLSearchParams(location.search);
  return { q: p.get("q") || "", from: p.get("from") || "", to: p.get("to") || "", o: p.get("o") || "",
    l: p.get("l") || "", k: p.get("k") || "", order: p.get("order") || "new" };
}
function writeForm(s) {
  $("#q").value = s.q; $("#from").value = s.from; $("#to").value = s.to; $("#outlet").value = s.o;
  $("#lang-f").value = s.l; $("#narr").value = s.k; $("#order").value = s.order;
}
function readForm() {
  return { q: $("#q").value.trim(), from: $("#from").value, to: $("#to").value, o: $("#outlet").value,
    l: $("#lang-f").value, k: $("#narr").value, order: $("#order").value };
}
const isEmpty = (s) => !s.q && !s.from && !s.to && !s.o && !s.l && !s.k;

/** What the current search is, as removable chips. */
function renderChips(s) {
  let box = $("#chips");
  if (!box) {
    box = el("div", { class: "chips", id: "chips", role: "group", "aria-label": t("archive.chips") });
    $("#filters").after(box);
  }
  const chips = [];
  const chip = (label, value, key) => {
    const b = el("button", { type: "button", class: "chip", "aria-label": t("archive.chip.remove", { what: `${label}: ${value}` }) },
      el("span", { class: "k" }, `${label}: `), value, el("span", { class: "x", "aria-hidden": "true" }, " ×"));
    b.addEventListener("click", () => { const s2 = { ...readForm(), [key]: key === "order" ? "new" : "" }; writeForm(s2); go(s2); });
    chips.push(b);
  };
  if (s.q) chip(t("archive.chip.words"), s.q, "q");
  if (s.from) chip(t("archive.from"), fmtDay(s.from), "from");
  if (s.to) chip(t("archive.to"), fmtDay(s.to), "to");
  if (s.o) chip(t("archive.outlets"), outlet(s.o).name, "o");
  if (s.l) chip(t("archive.language"), t(`lang.${s.l}`), "l");
  if (s.k) chip(narrative(s.k)?.family === "topic" ? t("col.topic") : t("col.framing"), tl(narrative(s.k)?.label), "k");
  if (s.order === "old") chip(t("archive.sort"), t("archive.sort.old"), "order");
  box.hidden = !chips.length;
  box.replaceChildren(...chips);
}

/** What a result count covers: words are looked for in headlines and leads, a framing also in full texts. */
function scopeNote(s) {
  const notes = [];
  if (s.q) notes.push(t("archive.scope.words"));
  if (s.k) notes.push(t("archive.scope.framing"));
  if (s.q && s.k) notes.push(t("archive.scope.both"));
  const open = (s.to || META.last) > (META.complete_through || META.last);
  if (open) notes.push(t("archive.scope.open", { day: fmtDay(META.complete_through) }));
  return notes.join(" ");
}

function daysBetween(a, b) {
  const out = [];
  for (let d = a; d <= b; d = addDays(d, 1)) out.push(d);
  return out;
}

function renderCharts(res, s) {
  const first = s.from || META.first, last = s.to || META.last;
  const days = daysBetween(first < META.first ? META.first : first, last > META.last ? META.last : last);
  const counts = days.map((d) => res.byDay.get(d) || 0);
  const shares = days.map((d, i) => { const tt = res.dayTotals.get(d); return tt ? counts[i] / tt : 0; });
  const totals = days.map((d) => res.dayTotals.get(d) || 0);
  const plate = $("#timeline-plate");
  const box = $("#timeline");
  const draw = () => {
    const fresh = el("div", { dataset: { clickable: "1" } });
    box.replaceChildren(fresh);
    columnChart(fresh, { days, values: norm === "count" ? counts : shares, isOpen: isOpenDay,
      format: norm === "count" ? fmtInt : (v) => fmtPct(v, 1), label: t("archive.timeline.sub") });
    fresh.addEventListener("pick", (e) => { const s2 = { ...readForm(), from: e.detail, to: e.detail }; writeForm(s2); go(s2); });
  };
  const seg = $("#norm");
  seg.replaceChildren(...["count", "share"].map((k) => {
    const b = el("button", { type: "button", "aria-pressed": String(norm === k) }, t(k === "count" ? "archive.count" : "archive.share"));
    b.addEventListener("click", () => { norm = k; [...seg.children].forEach((c) => c.setAttribute("aria-pressed", String(c === b))); draw(); });
    return b;
  }));
  draw();
  $("#pl1").textContent = `${t("plate")} I`;
  $("#pl2").textContent = `${t("plate")} II`;
  plate.querySelectorAll(".table-wrap").forEach((n) => n.remove());
  [...plate.querySelectorAll(".plate-tools .linkish")].forEach((n) => n.remove());
  withTable(plate, box, () => tableOf(days, [
    { label: t("archive.count"), values: counts, fmt: fmtInt },
    { label: t("col.all"), values: totals, fmt: fmtInt },
    { label: t("archive.share"), values: shares, fmt: (v) => fmtPct(v, 1) },
  ], fmtInt, (i) => (isOpenDay(days[i]) ? t("day.open.short") : "")));
  const by = [...res.byOutlet.entries()].sort((a, b) => b[1] - a[1]).map(([i, v]) => {
    const o = META.outlets[i];
    return { label: o.name, value: v, color: groupVar(o.group), title: t(`group.${o.group}`),
      href: `?${new URLSearchParams({ ...Object.fromEntries(Object.entries(s).filter(([, x]) => x)), o: o.id })}` };
  });
  barList($("#byoutlet"), by, fmtInt);
}

async function showMore() {
  const btn = $("#more");
  btn.disabled = true;
  const docs = await loadDocs(current.hits.slice(shown, shown + PAGE));
  const list = $("#results");
  for (const d of docs) list.append(articleCard(d, { terms: current.forms }));
  shown += PAGE;
  btn.hidden = shown >= current.total;
  btn.disabled = false;
}

// The export carries the same fields as the record in the citation dialog (core.js: recordOf).
const CSV_FIELDS = ["id", "published", "outlet", "outlet_id", "language", "title", "title_en_mt", "lead", "url", "archive",
  "archive_capture_read", "framings", "topics", "in_text_only", "source", "body_words", "video", "retrieved", "fingerprint"];

async function exportCSV() {
  const btn = $("#export");
  btn.disabled = true;
  const hits = current.hits.slice(0, EXPORT_MAX);
  const rows = [];
  for (let i = 0; i < hits.length; i += 200) {
    btn.textContent = `${t("archive.export")} … ${Math.round((i / hits.length) * 100)}%`;
    for (const d of await loadDocs(hits.slice(i, i + 200))) {
      const rec = recordOf(d, await recordId(d));
      rows.push(CSV_FIELDS.map((k) => (Array.isArray(rec[k]) ? rec[k].join("; ") : rec[k])));
    }
  }
  downloadCSV(`woland-${new Date().toISOString().slice(0, 10)}.csv`, CSV_FIELDS, rows);
  btn.disabled = false;
  exportLabel();
}
function exportLabel() {
  const n = Math.min(current.total, EXPORT_MAX);
  $("#export").textContent = `${t("archive.export")}${current.total > EXPORT_MAX ? ` (${t("archive.export.note", { n: fmtInt(n) })})` : ""}`;
}

async function go(s, push = true) {
  if (push) {
    const qs = new URLSearchParams(Object.entries(s).filter(([k, v]) => v && !(k === "order" && v === "new")));
    history.pushState(null, "", `${location.pathname}${qs.toString() ? `?${qs}` : ""}`);
  }
  renderChips(s);
  if (isEmpty(s)) {
    area.hidden = true;
    status.textContent = t("archive.idle", { start: fmtDay(META.start) });
    return;
  }
  status.textContent = `${t("archive.searching")}…`;
  area.style.opacity = ".5";
  try {
    const narrIdx = s.k ? narrative(s.k)?.idx : null;
    current = await search({ q: s.q, from: s.from, to: s.to, outlets: s.o ? new Set([s.o]) : null,
      lang: s.l || null, narr: narrIdx ?? null, order: s.order });
  } catch (e) {
    area.style.opacity = "";
    if (e.code === "minchars") { status.textContent = t("archive.minchars"); area.hidden = true; return; }
    showError(status, e);
    return;
  }
  area.style.opacity = "";
  if (!current.total) {
    area.hidden = true;
    status.replaceChildren(t("archive.none"), " ", el("span", { class: "syntax" }, scopeNote(s)));
    return;
  }
  area.hidden = false;
  status.textContent = "";
  $("#count").textContent = current.total === 1 ? t("archive.results.one") : t("archive.results", { n: fmtInt(current.total) });
  $("#scope").textContent = scopeNote(s);
  exportLabel();
  renderCharts(current, s);
  $("#results").replaceChildren();
  shown = 0;
  await showMore();
}

async function start() {
  try {
    await loadMeta();
    fillFooter();
    fillSelects();
    if (!META.last) { status.textContent = t("empty.nodata"); return; }
    const s = readParams();
    writeForm(s);
    form.addEventListener("submit", (e) => { e.preventDefault(); go(readForm()); });
    for (const id of ["from", "to", "outlet", "lang-f", "narr", "order"]) $(`#${id}`).addEventListener("change", () => go(readForm()));
    $("#clear").addEventListener("click", () => { writeForm(EMPTY); go({ ...EMPTY }); });
    $("#more").addEventListener("click", showMore);
    $("#export").addEventListener("click", exportCSV);
    window.addEventListener("popstate", () => { const p = readParams(); writeForm(p); go(p, false); });
    go(s, false);
  } catch (e) {
    showError(status, e);
  }
}
start();
