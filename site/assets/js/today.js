// Chapter I: the day's chronicle.
import {
  $, el, t, tl, META, loadMeta, getJSON, initChrome, fillFooter, fmtInt, fmtPct, fmtDay, delta, outlet,
  narrative, groupVar, articleCard, fromExample, archiveSearch, showError, fmtCompact,
} from "./core.js";
import { lang } from "./i18n.js";
import { sparkline, barList } from "./charts.js";

initChrome("today");
const root = $("#today");
const todayMsk = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Moscow" }).format(new Date());

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

function ledger(rows, day, family, baseDays) {
  const table = el("table", { class: "ledger" },
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, t(family === "framing" ? "col.framing" : "col.topic")),
      el("th", { scope: "col", class: "num" }, t("col.articles")),
      el("th", { scope: "col" }, t("col.share")),
      el("th", { scope: "col", class: "num" }, baseDays >= 3 ? t("col.change", { n: Math.min(28, baseDays) }) : t("col.change0")),
      el("th", { scope: "col", class: "hide-sm" }, t("col.trend")))));
  const body = el("tbody");
  const maxShare = Math.max(1e-9, ...rows.map((r) => r.share));
  for (const r of rows) {
    const n = narrative(r.id);
    const dl = baseDays >= 3 ? delta(r.share, r.base) : { cls: "na", text: "–" };
    const detailsId = `ex-${r.id}`;
    const btn = el("button", { class: "expand", type: "button", "aria-expanded": "false", "aria-controls": detailsId },
      el("span", { class: "name" }, tl(n.label), family === "framing" ? el("small", {}, tl(n.about)) : null));
    const row = el("tr", { class: "row" },
      el("td", {}, btn),
      el("td", { class: "num" }, fmtInt(r.n)),
      el("td", {}, el("div", { style: { display: "flex", alignItems: "center", gap: ".6rem" } },
        el("div", { class: "share-bar", style: { flex: "1" }, "aria-hidden": "true" },
          el("span", { style: { width: `${(r.share / maxShare) * 100}%` } })),
        el("span", { class: "num", style: { minWidth: "3.2rem" } }, fmtPct(r.share)))),
      el("td", { class: "num" }, el("span", { class: `delta ${dl.cls}` }, dl.text)),
      el("td", { class: "hide-sm" }, sparkline(r.spark, { label: `${tl(n.label)}, 30 days` })));
    const details = el("tr", { class: "details", id: detailsId, hidden: true },
      el("td", { colspan: "5" },
        el("ul", { class: "articles" }, r.ex.map((ex) => articleCard(fromExample(ex, day, r.id), { only: n.idx, noLead: true }))),
        el("p", {}, el("a", { href: archiveSearch({ k: r.id, from: day, to: day }) }, t("today.more", { n: fmtInt(r.n) })))));
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

function risingList(items, day) {
  if (!items || !items.length) return el("p", { class: "empty" }, t("today.rising.none"));
  return el("ul", { class: "words" }, items.map((it) => el("li", {},
    el("a", { class: "w", href: archiveSearch({ q: it.w, from: day, to: day }) }, it.w),
    el("span", { class: "n" }, t("today.rising.explain", { n: fmtInt(it.n), base: it.base < 1 ? "<1" : fmtInt(it.base) })),
    el("span", { class: "x", title: `×${it.x}` }, `×${it.x >= 10 ? Math.round(it.x) : it.x}`),
    it.ex ? el("span", { class: "ex" },
      el("a", { href: it.ex.u, target: "_blank", rel: "noopener noreferrer nofollow" }, it.ex.t),
      it.ex.te ? el("span", { lang: "en" }, ` — ${it.ex.te}`) : null,
      el("span", { style: { color: "var(--text-3)" } }, ` · ${outlet(it.ex.o).name}`)) : null)));
}

function render(dg, day) {
  const kids = [];
  if (day === todayMsk) kids.push(el("p", { class: "notice" }, t("today.partial")));
  const outletsPublishing = Object.values(dg.totals).filter((v) => v > 0).length;
  const framings = dg.narratives.filter((r) => narrative(r.id)?.family === "framing");
  const topics = dg.narratives.filter((r) => narrative(r.id)?.family === "topic");
  const baseDays = Math.max(0, (dg.days || 1) - 1);
  const rising = framings.filter((r) => r.n >= 5 && r.base !== null).map((r) => ({ r, d: delta(r.share, r.base) }))
    .filter((x) => x.d.v !== null && x.d.v >= 0.25).sort((a, b) => b.d.v - a.d.v).slice(0, 3);
  const lede = el("p", { class: "lede dropcap" },
    t("today.lede", { day: ledeDay(day), total: fmtInt(dg.total), outlets: fmtInt(outletsPublishing),
      framed: fmtPct(dg.total ? dg.framed / dg.total : 0, 0) }), " ");
  if (baseDays < 7) lede.append(t("today.lede.norising"));
  else if (rising.length) {
    const [before, after] = t("today.lede.rising", { n: baseDays }).split("{list}");
    const parts = new Intl.ListFormat(lang === "en" ? "en-GB" : lang, { type: "conjunction" })
      .formatToParts(rising.map((x) => `${tl(narrative(x.r.id).label)} (${x.d.text.replace(/^▲ /, "")})`));
    lede.append(before, ...parts.map((p) => (p.type === "element" ? el("em", {}, p.value) : p.value)), after);
  }
  kids.push(lede);

  const top = [...framings].sort((a, b) => b.n - a.n)[0];
  kids.push(el("div", { class: "tiles" },
    el("div", { class: "tile" }, el("div", { class: "label" }, t("today.tiles.articles")), el("div", { class: "value" }, fmtInt(dg.total))),
    el("div", { class: "tile" }, el("div", { class: "label" }, t("today.tiles.outlets")), el("div", { class: "value" }, fmtInt(outletsPublishing))),
    el("div", { class: "tile" }, el("div", { class: "label" }, t("today.tiles.framed")), el("div", { class: "value" }, fmtPct(dg.total ? dg.framed / dg.total : 0, 0))),
    top && top.n ? el("div", { class: "tile" }, el("div", { class: "label" }, t("today.tiles.top")),
      el("div", { class: "value", style: { fontSize: "1.25rem", fontFamily: "var(--serif)" } },
        el("a", { href: `narratives.html#${top.id}`, style: { color: "var(--text)" } }, tl(narrative(top.id).label))),
      el("div", { class: "note" }, `${fmtInt(top.n)} · ${fmtPct(top.share)}`)) : null));

  const used = framings.filter((r) => r.n > 0).sort((a, b) => b.n - a.n);
  const unused = framings.filter((r) => r.n === 0);
  kids.push(section(t("today.narratives"), t("today.narratives.hint"),
    el("figure", { class: "plate", style: { padding: ".4rem .8rem" } }, ledger(used, day, "framing", baseDays)),
    unused.length ? el("p", { class: "syntax" }, "∅ ", unused.map((r) => tl(narrative(r.id).label)).join(" · ")) : null));

  kids.push(section(t("today.rising"), t("today.rising.hint"),
    el("div", { class: "grid-2" },
      el("figure", { class: "plate" }, el("figcaption", {}, el("span", { class: "plate-title" }, t("today.rising.ru"))), risingList(dg.rising?.ru, day)),
      el("figure", { class: "plate" }, el("figcaption", {}, el("span", { class: "plate-title" }, t("today.rising.en"))), risingList(dg.rising?.en, day)))));

  const topicRows = topics.filter((r) => r.n > 0).sort((a, b) => b.n - a.n);
  kids.push(section(t("today.topics"), t("today.narratives.hint"),
    el("figure", { class: "plate", style: { padding: ".4rem .8rem" } }, ledger(topicRows, day, "topic", baseDays))));

  const vol = el("div");
  const items = Object.entries(dg.totals).sort((a, b) => b[1] - a[1]).map(([id, v]) => {
    const o = outlet(id);
    return { label: o.name, value: v, href: archiveSearch({ o: id, from: day, to: day }), color: groupVar(o.group),
      title: `${o.name} (${t(`group.${o.group}`)})${o.method === "feed" ? ` · ${t("article.feed")}` : ""}` };
  });
  barList(vol, items, fmtInt);
  const legend = el("div", { class: "legend" }, ["state", "official", "mass", "foreign", "hardline"].map((g) =>
    el("span", { class: "item" }, el("span", { class: "key box", style: { background: groupVar(g) } }), t(`group.${g}`))));
  kids.push(section(t("today.volume"), t("today.volume.hint"), el("figure", { class: "plate" }, legend, vol)));
  root.replaceChildren(...kids);
}

function renderNav(days, day) {
  const nav = $("#daynav");
  const i = days.indexOf(day);
  nav.replaceChildren(
    i > 0 ? el("a", { href: `?d=${days[i - 1]}` }, t("today.prev")) : el("span"),
    el("span", { class: "current" }, fmtDay(day, true)),
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
      day = days[days.length - 1];
      if (day === todayMsk && days.length > 1) day = days[days.length - 2];
    }
    renderNav(days, day);
    render(await getJSON(`days/${day}.json`), day);
    document.title = `Woland — ${fmtDay(day)}`;
  } catch (e) {
    showError(root, e);
  }
}
main();
