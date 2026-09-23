// Chapter IV: the guests at the ball — every outlet, its owner, its habits and its collection health.
import {
  $, el, t, tl, META, loadMeta, getJSON, initChrome, fillFooter, fmtInt, fmtPct, fmtDay, narrative,
  groupVar, archiveSearch, showError, GROUPS, addDays,
} from "./core.js";
import { sparkline } from "./charts.js";

initChrome("outlets");
const root = $("#outlets");
const todayMsk = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Moscow" }).format(new Date());
const sum = (a) => a.reduce((x, y) => x + y, 0);

function leansOn(id, series) {
  const tot = series.totals[id];
  if (!tot) return [];
  const allTot = sum(Object.values(series.totals).map(sum));
  const mine = sum(tot);
  if (!mine) return [];
  const out = [];
  for (const n of META.narratives.filter((x) => x.family === "framing")) {
    const by = series.nar[n.id] || {};
    const h = by[id] ? sum(by[id]) : 0;
    if (h < 5) continue;
    const allH = sum(Object.values(by).map(sum));
    const r = (h / mine) / (allH / allTot);
    if (r >= 1.5) out.push({ n, r, share: h / mine });
  }
  return out.sort((a, b) => b.r - a.r).slice(0, 3);
}

function coverageStrip(id, cov) {
  const days = [];
  for (let i = 20; i >= 0; i--) days.push(addDays(todayMsk, -i));
  const by = cov[id] || {};
  return el("div", { class: "cov", role: "img", "aria-label": t("outlets.coverage") }, days.map((d) => {
    const v = by[d];
    const code = v ? v[3] : "m";
    const label = { c: t("cov.c"), p: t("cov.p"), f: t("cov.f"), m: t("cov.m") }[code];
    return el("span", { class: code, title: `${fmtDay(d)}: ${label}${v ? ` · ${fmtInt(v[0])}${v[2] ? ` / ${fmtInt(v[2])}` : ""}` : ""}` });
  }));
}

function card(o, series, cov) {
  const tot = series.totals[o.id] || [];
  const last30 = tot.slice(-30);
  const perDay = o.days ? o.n / o.days : 0;
  const badges = el("div", { class: "facts" },
    el("span", { class: "badge", style: { color: "var(--text-2)" } }, o.lang === "ru" ? "RU" : "EN"),
    o.eu_blocked ? el("span", { class: "badge eu", title: t("article.eu") }, t("article.eu")) : null,
    o.method === "feed" ? el("span", { class: "badge feed" }, t("article.feed")) : null,
    !o.enabled ? el("span", { class: "badge feed" }, t("outlets.disabled")) : null);
  const leans = leansOn(o.id, series);
  return el("article", { class: "outlet-card", id: o.id },
    el("h3", {}, el("span", { class: "group-key", style: { background: groupVar(o.group) }, "aria-hidden": "true" }), o.name,
      el("span", { class: "ru", lang: "ru" }, o.name_ru)),
    badges,
    el("p", { class: "about" }, tl(o.about)),
    o.n ? el("div", { class: "facts" },
      el("span", {}, el("b", {}, fmtInt(o.n)), ` ${t("outlets.articles")}`),
      el("span", {}, el("b", {}, fmtInt(perDay)), ` ${t("outlets.perday")}`),
      o.first ? el("span", {}, `${t("outlets.since")} ${fmtDay(o.first)}`) : null) : null,
    last30.length > 1 ? sparkline(last30, { width: 220, height: 30, label: `${o.name}: ${t("outlets.articles")}` }) : null,
    el("div", { class: "facts" }, t(`outlets.method.${o.method}`), " · ",
      el("a", { href: o.home, rel: "noopener noreferrer nofollow", target: "_blank" }, o.home.replace(/^https?:\/\//, ""))),
    leans.length ? el("div", { class: "facts" }, el("span", { title: t("outlets.top.hint") }, `${t("outlets.top")}:`),
      ...leans.map((x) => el("a", { class: "tag framing", href: `narratives.html#${x.n.id}` }, `${tl(x.n.label)} ×${x.r.toFixed(1)}`))) : null,
    o.enabled ? el("div", {}, el("div", { class: "facts", style: { marginBottom: ".25rem" } }, t("outlets.coverage")), coverageStrip(o.id, cov)) : null,
    o.n ? el("a", { href: archiveSearch({ o: o.id }), style: { font: ".85rem var(--sans)" } }, `${t("nav.archive")} →`) : null);
}

function health() {
  const rows = [...(META.runs || [])].reverse();
  if (!rows.length) return null;
  return el("section", { class: "section" },
    el("div", { class: "section-head" }, el("h2", {}, t("outlets.health"))),
    el("div", { class: "plate" }, el("table", { class: "table-view" },
      el("thead", {}, el("tr", {}, el("th", {}, t("health.when")), el("th", {}, t("health.mode")), el("th", {}, t("health.new")),
        el("th", { style: { textAlign: "left" } }, t("health.problems")))),
      el("tbody", {}, rows.map((r) => el("tr", {},
        el("td", {}, new Intl.DateTimeFormat(document.documentElement.lang, { dateStyle: "medium", timeStyle: "short" }).format(new Date(r.at))),
        el("td", {}, t(`mode.${r.mode}`)),
        el("td", {}, fmtInt(r.new)),
        el("td", { style: { textAlign: "left" } }, Object.keys(r.problems || {}).length
          ? Object.entries(r.problems).map(([k, v]) => `${k}: ${v}`).join(" · ") : t("health.none"))))))));
}

async function main() {
  try {
    await loadMeta();
    fillFooter();
    const [series, cov] = await Promise.all([getJSON("series.json"), getJSON("coverage.json")]);
    const kids = [el("p", { class: "lede dropcap" }, t("outlets.lede", { n: META.outlets.filter((o) => o.enabled).length }))];
    kids.push(el("div", { class: "cov-legend" }, ["c", "p", "f", "m"].map((k) =>
      el("span", { style: { "--k": { c: "#0ca30c", p: "#fab219", f: "#7d8aa8", m: "transparent" }[k] } }, t(`cov.${k}`)))));
    for (const g of GROUPS) {
      const list = META.outlets.filter((o) => o.group === g);
      if (!list.length) continue;
      kids.push(el("section", { class: "section" },
        el("div", { class: "section-head" }, el("h2", {}, el("span", { class: "group-key", style: { background: groupVar(g) } }), t(`group.${g}`))),
        el("div", { class: "grid-3" }, list.map((o) => card(o, series, cov)))));
    }
    kids.push(health());
    root.replaceChildren(...kids.filter(Boolean));
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  } catch (e) {
    showError(root, e);
  }
}
main();
