// Chapter I: the day's chronicle.
import {
  $, el, t, tl, META, loadMeta, getJSON, initChrome, fillFooter, fmtInt, fmtPct, fmtDay, fmtDayShort, delta, outlet,
  narrative, groupVar, articleCard, fromExample, archiveSearch, showError, addDays, isOpenDay,
} from "./core.js";
import { lang } from "./i18n.js";
import { sparkline, barList } from "./charts.js";

initChrome("today");
const root = $("#today");

function ledeDay(iso) {
  const d = new Date(`${iso}T12:00:00+03:00`);
  if (lang === "fi") return new Intl.DateTimeFormat("fi-FI", { timeZone: "Europe/Moscow", day: "numeric", month: "numeric", year: "numeric" }).format(d);
  if (lang === "sv") return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Moscow", day: "numeric", month: "long", year: "numeric" }).format(d);
  return fmtDay(iso, true);
}

function section(title, hint, ...body) {
  return el("section", { class: "section" },
    el("div", { class: "section-head" }, el("h2", {}, title), hint ? el("span", { class: "hint" }, hint) : null), ...body);
}

const fmtN = (x) => (x === null || x === undefined ? "–" : x < 1 && x > 0 ? "<1" : fmtInt(x));

/** Worth naming in the lede: at least ten articles, and far more than the usual share would give on a day
 *  of this size (three standard deviations above a Poisson expectation) — so that a small framing's
 *  large percentage change is not presented as news. */
function notable(r, total) {
  if (r.base === null || r.base === undefined || r.n < 10) return false;
  const e = r.base * total;
  return e > 0 ? (r.n - e) / Math.sqrt(e) >= 3 && r.n >= 1.25 * e : true;
}

/** Relative change, with the share and daily count it is measured against beside it. */
function changeCell(r, total, compare) {
  if (!compare || r.base === null || r.base === undefined) return el("span", { class: "delta na" }, "–");
  const dl = delta(r.share, r.base);
  const expected = Math.round(r.base * total);
  return el("span", { class: "change", title: t("today.expected", { n: fmtInt(r.n), e: fmtInt(expected) }) },
    el("span", { class: `delta ${dl.cls}` }, dl.text),
    el("small", {}, t("today.usual", { share: fmtPct(r.base), n: fmtN(r.base_n) })));
}

/** A sentence for screen readers (and a tooltip) saying what a 30-day sparkline shows. */
function trendText(name, r, days) {
  const s = r.spark || [];
  if (s.length < 2) return name;
  let hi = 0;
  s.forEach((v, i) => { if (v > s[hi]) hi = i; });
  return t("trend.label", { name, first: fmtPct(s[0]), from: fmtDayShort(days[0]), last: fmtPct(s[s.length - 1]),
    to: fmtDayShort(days[s.length - 1]), max: fmtPct(s[hi]), maxday: fmtDayShort(days[hi]) });
}

function trendTable(r, days) {
  const s = r.spark || [], n = r.spark_n || [];
  return el("details", { class: "trend-table" }, el("summary", {}, t("today.trend.table")),
    el("div", { class: "table-wrap" }, el("table", { class: "table-view" },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, t("table.day")), el("th", { scope: "col" }, t("col.articles")),
        el("th", { scope: "col" }, t("col.share")))),
      el("tbody", {}, s.map((v, i) => el("tr", { class: isOpenDay(days[i]) ? "open" : null },
        el("th", { scope: "row" }, fmtDay(days[i]), isOpenDay(days[i]) ? el("small", {}, ` ${t("day.open.short")}`) : null),
        el("td", {}, n[i] === undefined ? "–" : fmtInt(n[i])), el("td", {}, fmtPct(v))))))));
}

function ledger(rows, day, family, dg, compare) {
  const baseDays = Math.max(0, (dg.days || 1) - 1);
  const days = (rows[0]?.spark || []).map((_, i) => addDays(dg.spark_from || day, i));
  const openFrom = days.findIndex((d) => isOpenDay(d));
  const table = el("table", { class: "ledger" },
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, t(family === "framing" ? "col.framing" : "col.topic")),
      el("th", { scope: "col", class: "num" }, t("col.articles")),
      el("th", { scope: "col" }, t("col.share")),
      el("th", { scope: "col", class: "num" }, compare ? t("col.change", { n: Math.min(28, baseDays) }) : t("col.change0")),
      el("th", { scope: "col", class: "hide-sm" }, t("col.trend")))));
  const body = el("tbody");
  const maxShare = Math.max(1e-9, ...rows.map((r) => r.share));
  for (const r of rows) {
    const n = narrative(r.id);
    const detailsId = `ex-${r.id}`;
    const btn = el("button", { class: "expand", type: "button", "aria-expanded": "false", "aria-controls": detailsId },
      el("span", { class: "name" }, tl(n.label), family === "framing" ? el("small", {}, tl(n.about)) : null));
    const label = trendText(tl(n.label), r, days);
    const row = el("tr", { class: "row" },
      el("td", {}, btn),
      el("td", { class: "num" }, fmtInt(r.n)),
      el("td", {}, el("div", { style: { display: "flex", alignItems: "center", gap: ".6rem" } },
        el("div", { class: "share-bar", style: { flex: "1" }, "aria-hidden": "true" },
          el("span", { style: { width: `${(r.share / maxShare) * 100}%` } })),
        el("span", { class: "num", style: { minWidth: "3.2rem" } }, fmtPct(r.share)))),
      el("td", { class: "num" }, changeCell(r, dg.total, compare)),
      el("td", { class: "hide-sm" }, sparkline(r.spark, { label, openFrom: openFrom < 0 ? null : openFrom })));
    const details = el("tr", { class: "details", id: detailsId, hidden: true },
      el("td", { colspan: "5" },
        el("ul", { class: "articles" }, r.ex.map((ex) => articleCard(fromExample(ex, day, r.id), { only: n.idx, noLead: true }))),
        el("p", {}, el("a", { href: archiveSearch({ k: r.id, from: day, to: day }) }, t("today.more", { n: fmtInt(r.n) }))),
        el("p", { class: "syntax" }, label),
        trendTable(r, days)));
    btn.addEventListener("click", () => {
      const open = details.hidden;
      details.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
    });
    body.append(row, details);
  }
  table.append(body);
  return table;
}

// ── Rising words ────────────────────────────────────────────────────────────
// A reader may put away the words that come back every day (airports closing, the weather): the choice is
// kept in this browser only.
const HIDDEN_KEY = "woland.rising.hidden";
function hiddenWords() {
  try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_KEY) || "[]")); } catch (_) { return new Set(); }
}
function setHidden(set) {
  try { localStorage.setItem(HIDDEN_KEY, JSON.stringify([...set])); } catch (_) { /* not kept */ }
}

function risingList(items, day, holder) {
  if (!items || !items.length) return holder.replaceChildren(el("p", { class: "empty" }, t("today.rising.none")));
  const hidden = hiddenWords();
  const keyOf = (it) => `${it.k || it.w}`;
  const shown = items.filter((it) => !hidden.has(keyOf(it)));
  const put = items.filter((it) => hidden.has(keyOf(it)));
  const redraw = () => risingList(items, day, holder);
  const item = (it, isHidden) => el("li", { class: isHidden ? "put-away" : null },
    el("a", { class: "w", href: archiveSearch({ q: it.q || it.w, from: day, to: day }) }, it.w),
    el("span", { class: "n" }, t("today.rising.explain", { n: fmtInt(it.n), base: fmtN(it.base) })),
    el("span", { class: "x", title: t("today.rising.x", { x: it.x }) }, `×${it.x >= 10 ? Math.round(it.x) : it.x}`),
    el("button", { class: "linkish hide-word", type: "button",
      "aria-label": t(isHidden ? "today.rising.unhide.label" : "today.rising.hide.label", { w: it.w }),
      onclick: () => {
        const set = hiddenWords();
        if (isHidden) set.delete(keyOf(it)); else set.add(keyOf(it));
        setHidden(set);
        redraw();
      } }, t(isHidden ? "today.rising.unhide" : "today.rising.hide")),
    it.ex ? el("span", { class: "ex" },
      el("a", { href: it.ex.u, target: "_blank", rel: "noopener noreferrer nofollow", lang: outlet(it.ex.o).lang }, it.ex.t),
      it.ex.te ? el("span", { lang: "en" }, ` — ${it.ex.te}`) : null,
      el("span", { style: { color: "var(--text-3)" } }, ` · ${outlet(it.ex.o).name}`)) : null);
  const kids = [el("ul", { class: "words" }, shown.map((it) => item(it, false)))];
  if (put.length) {
    const box = el("details", { class: "put-away-list" }, el("summary", {}, t("today.rising.hidden", { n: fmtInt(put.length) })),
      el("ul", { class: "words" }, put.map((it) => item(it, true))));
    kids.push(box);
  }
  holder.replaceChildren(...kids);
}

// ── Coverage of the day ─────────────────────────────────────────────────────
function coverageOfDay(dg, day, series) {
  const i = series.days.indexOf(day);
  const missing = [], empty = [];
  for (const o of META.outlets.filter((x) => x.enabled)) {
    if (dg.totals[o.id]) continue;
    const code = (series.cov?.[o.id] || "")[i];
    (code === "m" || !code ? missing : empty).push(o.name);
  }
  const listed = Object.entries(dg.listed || {}).filter(([, v]) => v).map(([o, v]) => ({ o: outlet(o).name, v }));
  return { missing, empty, listed };
}

function render(dg, day, series) {
  const kids = [];
  const open = isOpenDay(day);
  const baseDays = Math.max(0, (dg.days || 1) - 1);
  const compare = !open && baseDays >= 3;
  if (open) kids.push(el("p", { class: "notice" }, t("today.partial"), " ",
    META.complete_through ? el("a", { href: `?d=${META.complete_through}` }, t("today.partial.link", { day: fmtDay(META.complete_through) })) : null));
  const outletsPublishing = Object.values(dg.totals).filter((v) => v > 0).length;
  const framings = dg.narratives.filter((r) => narrative(r.id)?.family === "framing");
  const topics = dg.narratives.filter((r) => narrative(r.id)?.family === "topic");
  const rising = framings.filter((r) => notable(r, dg.total)).map((r) => ({ r, d: delta(r.share, r.base) }))
    .sort((a, b) => b.d.v - a.d.v).slice(0, 3);
  const lede = el("p", { class: "lede dropcap" },
    t("today.lede", { day: ledeDay(day), total: fmtInt(dg.total), outlets: fmtInt(outletsPublishing),
      framed: fmtPct(dg.total ? dg.framed / dg.total : 0, 0) }), " ",
    el("a", { href: "method.html#matching" }, t("today.lede.how")), " ");
  if (open) lede.append(t("today.lede.open"));
  else if (baseDays < 7) lede.append(t("today.lede.norising"));
  else if (rising.length) {
    const [before, after] = t("today.lede.rising", { n: baseDays }).split("{list}");
    const parts = new Intl.ListFormat(lang === "en" ? "en-GB" : lang, { type: "conjunction" })
      .formatToParts(rising.map((x) => `${tl(narrative(x.r.id).label)} (${t("today.lede.item", { n: fmtInt(x.r.n), share: fmtPct(x.r.share), base: fmtPct(x.r.base) })})`));
    lede.append(before, ...parts.map((p) => (p.type === "element" ? el("em", {}, p.value) : p.value)), after);
  } else lede.append(t("today.lede.steady", { n: baseDays }));
  kids.push(lede);

  const cov = coverageOfDay(dg, day, series);
  const covNotes = [];
  if (cov.missing.length) covNotes.push(t("today.cov.missing", { list: cov.missing.join(", ") }));
  if (cov.listed.length) covNotes.push(t("today.cov.listed", { list: cov.listed.map((x) => `${x.o} ${fmtInt(x.v)}`).join(", ") }));
  if (covNotes.length) kids.push(el("p", { class: "cov-note" }, covNotes.join(" "), " ", el("a", { href: "outlets.html" }, `${t("nav.outlets")} →`)));

  const top = [...framings].sort((a, b) => b.n - a.n)[0];
  kids.push(el("div", { class: "tiles" },
    el("div", { class: "tile" }, el("div", { class: "label" }, t("today.tiles.articles")), el("div", { class: "value" }, fmtInt(dg.total))),
    el("div", { class: "tile" }, el("div", { class: "label" }, t("today.tiles.outlets")), el("div", { class: "value" }, fmtInt(outletsPublishing)),
      cov.missing.length ? el("div", { class: "note" }, t("today.tiles.notcollected", { n: fmtInt(cov.missing.length) })) : null),
    el("div", { class: "tile" }, el("div", { class: "label" }, t("today.tiles.framed")), el("div", { class: "value" }, fmtPct(dg.total ? dg.framed / dg.total : 0, 0)),
      el("div", { class: "note" }, t("today.tiles.framed.note", { n: fmtInt(dg.framed) }))),
    top && top.n ? el("div", { class: "tile" }, el("div", { class: "label" }, t("today.tiles.top")),
      el("div", { class: "value", style: { fontSize: "1.25rem", fontFamily: "var(--serif)" } },
        el("a", { href: `narratives.html#${top.id}`, style: { color: "var(--text)" } }, tl(narrative(top.id).label))),
      el("div", { class: "note" }, `${fmtInt(top.n)} · ${fmtPct(top.share)}`)) : null));

  const used = framings.filter((r) => r.n > 0).sort((a, b) => b.n - a.n);
  const unused = framings.filter((r) => r.n === 0);
  kids.push(section(t("today.narratives"), t(compare ? "today.narratives.hint" : "today.narratives.hint.open"),
    el("figure", { class: "plate", style: { padding: ".4rem .8rem" } }, ledger(used, day, "framing", dg, compare)),
    unused.length ? el("p", { class: "syntax" }, "∅ ", unused.map((r) => tl(narrative(r.id).label)).join(" · ")) : null));

  const ruBox = el("div"), enBox = el("div");
  kids.push(section(t("today.rising"), t("today.rising.hint"),
    open ? el("p", { class: "syntax" }, t("today.rising.open")) : null,
    el("div", { class: "grid-2" },
      el("figure", { class: "plate" }, el("figcaption", {}, el("span", { class: "plate-title" }, t("today.rising.ru"))), ruBox),
      el("figure", { class: "plate" }, el("figcaption", {}, el("span", { class: "plate-title" }, t("today.rising.en"))), enBox))));
  risingList(dg.rising?.ru, day, ruBox);
  risingList(dg.rising?.en, day, enBox);

  const topicRows = topics.filter((r) => r.n > 0).sort((a, b) => b.n - a.n);
  kids.push(section(t("today.topics"), t(compare ? "today.topics.hint" : "today.narratives.hint.open"),
    el("figure", { class: "plate", style: { padding: ".4rem .8rem" } }, ledger(topicRows, day, "topic", dg, compare))));

  const vol = el("div");
  const items = Object.entries(dg.totals).sort((a, b) => b[1] - a[1]).map(([id, v]) => {
    const o = outlet(id);
    const listed = (dg.listed || {})[id];
    return { label: o.name, value: v, href: archiveSearch({ o: id, from: day, to: day }), color: groupVar(o.group),
      title: `${o.name} (${t(`group.${o.group}`)})${o.method === "feed" ? ` · ${t("article.feed")}` : ""}${listed ? ` · ${t("today.listed.n", { n: fmtInt(listed) })}` : ""}` };
  });
  barList(vol, items, fmtInt);
  const legend = el("div", { class: "legend" }, ["state", "official", "mass", "foreign", "hardline"].map((g) =>
    el("span", { class: "item" }, el("span", { class: "key box", style: { background: groupVar(g) } }), t(`group.${g}`))));
  const absent = [
    cov.missing.length ? el("p", { class: "syntax" }, el("b", {}, `${t("cov.m.long")}: `), cov.missing.join(" · ")) : null,
    cov.empty.length ? el("p", { class: "syntax" }, el("b", {}, `${t("heat.none")}: `), cov.empty.join(" · ")) : null,
  ];
  kids.push(section(t("today.volume"), t("today.volume.hint"), el("figure", { class: "plate" }, legend, vol, ...absent)));
  root.replaceChildren(...kids);
}

function renderNav(days, day) {
  const nav = $("#daynav");
  const i = days.indexOf(day);
  nav.replaceChildren(
    i > 0 ? el("a", { href: `?d=${days[i - 1]}` }, t("today.prev")) : el("span"),
    el("span", { class: "current" }, fmtDay(day, true), isOpenDay(day) ? el("small", { class: "open-mark" }, t("day.open.short")) : null),
    i < days.length - 1 ? el("a", { href: `?d=${days[i + 1]}` }, t("today.next")) : el("span"));
}

async function main() {
  try {
    await loadMeta();
    fillFooter();
    if (!META.last) { root.replaceChildren(el("p", { class: "empty" }, t("empty.nodata"))); return; }
    const series = await getJSON("series.json");
    const days = series.days;
    let day = new URLSearchParams(location.search).get("d");
    if (!day || !days.includes(day)) {
      // the latest day whose collection is finished; later ones are one click away
      day = days.includes(META.complete_through) ? META.complete_through : days[days.length - 1];
    }
    renderNav(days, day);
    render(await getJSON(`days/${day}.json`), day, series);
    document.title = `Woland — ${fmtDay(day)}`;
  } catch (e) {
    showError(root, e);
  }
}
main();
