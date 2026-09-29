// Chapter IV: the guests at the ball — every outlet, its owner, its habits and its collection health.
import {
  $, el, t, tl, META, loadMeta, getJSON, initChrome, fillFooter, fmtInt, fmtDay, fmtDayShort,
  groupVar, archiveSearch, showError, GROUPS, isOpenDay,
} from "./core.js";
import { lang, LOCALES } from "./i18n.js";
import { sparkline } from "./charts.js";

initChrome("outlets");
const root = $("#outlets");
const sum = (a) => a.reduce((x, y) => x + y, 0);
const STRIP = 21;  // days in each outlet's collection strip

/** Framings an outlet uses far more than the press as a whole (completed days only). */
function leansOn(id, series, upto) {
  const tot = series.totals[id];
  if (!tot) return [];
  const cut = (a) => a.slice(0, upto);
  const allTot = sum(Object.values(series.totals).map((v) => sum(cut(v))));
  const mine = sum(cut(tot));
  if (!mine) return [];
  const out = [];
  for (const n of META.narratives.filter((x) => x.family === "framing")) {
    const by = series.nar[n.id] || {};
    const h = by[id] ? sum(cut(by[id])) : 0;
    if (h < 5) continue;
    const allH = sum(Object.values(by).map((v) => sum(cut(v))));
    const r = (h / mine) / (allH / allTot);
    if (r >= 1.5) out.push({ n, r, share: h / mine });
  }
  return out.sort((a, b) => b.r - a.r).slice(0, 3);
}

const STATUS = { c: "cov.c", p: "cov.p", f: "cov.f", m: "cov.m" };

/** The last days of collection as coloured cells, and the same as a table for keyboards and screen readers. */
function coverage(o, series, cov) {
  const days = series.days.slice(-STRIP);
  const off = series.days.length - days.length;
  const codes = series.cov?.[o.id] || "";
  const by = cov[o.id] || {};
  const gaps = series.gaps?.[o.id] || {};
  const hours = (g) => g.map(([a, b]) => `${a}–${b}`).join(", ");
  const info = days.map((d, i) => {
    const code = codes[off + i] || "m";
    const v = by[d];
    return { d, code, open: isOpenDay(d), n: series.totals[o.id]?.[off + i] || 0, found: v ? v[1] : null, published: v ? v[2] : null,
      gaps: gaps[d] || [] };
  });
  const label = (x) => `${t(STATUS[x.code])}${x.open ? `, ${t("day.open.short")}` : ""}` +
    (x.gaps.length ? ` · ${t("outlets.gaps.day", { list: hours(x.gaps) })}` : "");
  const strip = el("div", { class: "cov", "aria-hidden": "true" }, info.map((x) =>
    el("span", { class: `${x.code}${x.open ? " open" : ""}`,
      title: `${fmtDay(x.d)}: ${label(x)} · ${fmtInt(x.n)}${x.found ? ` / ${fmtInt(x.found)}` : ""}` })));
  const table = el("details", { class: "cov-table" },
    el("summary", {}, t("outlets.coverage.table")),
    el("div", { class: "table-wrap" }, el("table", { class: "table-view" },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, t("table.day")), el("th", { scope: "col" }, t("outlets.status")),
        el("th", { scope: "col" }, t("col.articles")), el("th", { scope: "col" }, t("outlets.found")))),
      el("tbody", {}, info.slice().reverse().map((x) => el("tr", {},
        el("th", { scope: "row" }, fmtDay(x.d)), el("td", {}, label(x)), el("td", {}, fmtInt(x.n)),
        el("td", {}, x.found ? fmtInt(x.found) : "–")))))));
  const counts = { c: 0, p: 0, f: 0, m: 0 };
  info.forEach((x) => { counts[x.code] = (counts[x.code] || 0) + 1; });
  // a feed-only outlet's days are as complete as its feed was read: say so rather than "complete"
  const summary = counts.f
    ? t("outlets.coverage.summary.feed", { f: counts.f, m: counts.m, n: info.length })
    : t("outlets.coverage.summary", { c: counts.c, p: counts.p, m: counts.m, n: info.length });
  const lost = info.filter((x) => x.gaps.length).reverse();
  return el("div", {}, el("div", { class: "facts", style: { marginBottom: ".25rem" } },
    t("outlets.coverage", { n: info.length }), el("span", { class: "sr-only" }, ` — ${summary}`)), strip,
    el("p", { class: "facts cov-sum", "aria-hidden": "true" }, summary),
    lost.length ? el("p", { class: "facts" }, el("span", { title: t("outlets.gaps.hint") }, `${t("outlets.gaps")}: `),
      lost.map((x) => `${fmtDayShort(x.d)} ${hours(x.gaps)}`).join(" · ")) : null,
    table);
}

function card(o, series, cov, upto) {
  const tot = series.totals[o.id] || [];
  const recent = tot.slice(Math.max(0, upto - 30), upto);
  const perDay = o.days ? o.n / o.days : 0;
  const badges = el("div", { class: "facts" },
    el("span", { class: "badge", style: { color: "var(--text-2)" } }, o.lang === "ru" ? "RU" : "EN"),
    o.eu_blocked ? el("span", { class: "badge eu", title: t("article.eu") }, t("article.eu")) : null,
    o.method === "feed" ? el("span", { class: "badge feed" }, t("article.feed")) : null,
    !o.enabled ? el("span", { class: "badge feed" }, t("outlets.disabled")) : null);
  const leans = leansOn(o.id, series, upto);
  const collected = o.n > 0;
  const days = series.days.slice(Math.max(0, upto - 30), upto);
  const sparkLabel = recent.length > 1
    ? t("outlets.spark", { name: o.name, from: fmtDayShort(days[0]), to: fmtDayShort(days[days.length - 1]),
      min: fmtInt(Math.min(...recent)), max: fmtInt(Math.max(...recent)) }) : "";
  return el("article", { class: "outlet-card", id: o.id },
    el("h3", {}, el("span", { class: "group-key", style: { background: groupVar(o.group) }, "aria-hidden": "true" }), o.name,
      el("span", { class: "ru", lang: "ru" }, o.name_ru)),
    badges,
    el("p", { class: "about" }, tl(o.about)),
    collected ? el("div", { class: "facts" },
      el("span", {}, el("b", {}, fmtInt(o.n)), ` ${t("outlets.articles")}`),
      el("span", {}, el("b", {}, fmtInt(perDay)), ` ${t("outlets.perday")}`),
      o.first ? el("span", {}, `${t("outlets.since")} ${fmtDay(o.first)}`) : null,
      o.listed ? el("span", { title: t("article.listed.title") }, el("b", {}, fmtInt(o.listed)), ` ${t("outlets.listed")}`) : null)
      : o.enabled ? el("p", { class: "facts notyet" }, t("outlets.notyet")) : null,
    o.note ? el("p", { class: "note" }, tl(o.note)) : null,
    recent.length > 1 && collected ? sparkline(recent, { width: 220, height: 30, label: sparkLabel }) : null,
    el("div", { class: "facts" }, o.enabled && collected ? [t(`outlets.method.${o.method}`), " · "] : null,
      el("a", { href: o.home, rel: "noopener noreferrer nofollow", target: "_blank" }, o.home.replace(/^https?:\/\//, ""))),
    leans.length ? el("div", { class: "facts" }, el("span", { title: t("outlets.top.hint") }, `${t("outlets.top")}:`),
      ...leans.map((x) => el("a", { class: "tag framing", href: `narratives.html#${x.n.id}` }, `${tl(x.n.label)} ×${x.r.toFixed(1)}`))) : null,
    o.enabled ? coverage(o, series, cov) : null,
    collected ? el("a", { href: archiveSearch({ o: o.id }), style: { font: ".85rem var(--sans)" } }, `${t("nav.archive")} →`) : null);
}

function duration(s) {
  if (s === null || s === undefined) return "–";
  if (s < 90) return t("dur.s", { n: Math.round(s) });
  const m = Math.round(s / 60);
  return m < 90 ? t("dur.m", { n: m }) : t("dur.h", { h: Math.floor(m / 60), m: m % 60 });
}

function health() {
  // listed by when each run started (runs.json records them as they finish, and runs overlap)
  const rows = [...(META.runs || [])].sort((a, b) => (b.at || "").localeCompare(a.at || ""));
  if (!rows.length) return null;
  const when = new Intl.DateTimeFormat(LOCALES[lang] || "en-GB", { timeZone: "Europe/Moscow", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return el("section", { class: "section" },
    el("div", { class: "section-head" }, el("h2", {}, t("outlets.health")), el("span", { class: "hint" }, t("outlets.health.hint"))),
    el("div", { class: "plate table-wrap" }, el("table", { class: "table-view" },
      el("caption", { class: "sr-only" }, t("outlets.health")),
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, t("health.when")), el("th", { scope: "col" }, t("health.mode")),
        el("th", { scope: "col" }, t("health.outlets")), el("th", { scope: "col" }, t("health.duration")),
        el("th", { scope: "col" }, t("health.new")), el("th", { scope: "col", style: { textAlign: "left" } }, t("health.problems")))),
      el("tbody", {}, rows.map((r) => el("tr", {},
        el("td", {}, el("time", { datetime: r.at }, when.format(new Date(r.at)))),
        el("td", {}, t(`mode.${r.mode}`)),
        el("td", { title: (r.outlets || []).join(", ") }, fmtInt((r.outlets || []).length)),
        el("td", {}, duration(r.seconds)),
        el("td", {}, fmtInt(r.new)),
        el("td", { style: { textAlign: "left" } }, Object.keys(r.problems || {}).length
          ? Object.entries(r.problems).map(([k, v]) => `${k}: ${v}`).join(" · ") : t("health.none"))))))));
}

async function main() {
  try {
    await loadMeta();
    fillFooter();
    const [series, cov] = await Promise.all([getJSON("series.json"), getJSON("coverage.json")]);
    let upto = series.days.length;
    while (upto > 1 && isOpenDay(series.days[upto - 1])) upto--;  // completed days only for averages
    const kids = [el("p", { class: "lede dropcap" }, t("outlets.lede", { n: META.outlets.filter((o) => o.enabled).length }))];
    kids.push(el("div", { class: "cov-legend" },
      ["c", "p", "f", "m"].map((k) => el("span", { class: `k-${k}` }, t(`cov.${k}`))),
      el("span", { class: "k-open" }, t("day.open.short"))));
    for (const g of GROUPS) {
      const list = META.outlets.filter((o) => o.group === g);
      if (!list.length) continue;
      kids.push(el("section", { class: "section" },
        el("div", { class: "section-head" }, el("h2", {}, el("span", { class: "group-key", style: { background: groupVar(g) } }), t(`group.${g}`))),
        el("div", { class: "grid-3" }, list.map((o) => card(o, series, cov, upto)))));
    }
    kids.push(health());
    root.replaceChildren(...kids.filter(Boolean));
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  } catch (e) {
    showError(root, e);
  }
}
main();
