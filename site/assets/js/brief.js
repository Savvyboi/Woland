// Chapter VI: the week in the Russian state press, and the feeds that let readers follow Woland without
// visiting it. Built by woland/build.py (write_brief, write_feeds) over completed Monday-to-Sunday weeks.
import {
  $, el, t, tl, META, loadMeta, getJSON, initChrome, fillFooter, fmtInt, fmtPct, fmtDay, fmtDayShort, fmtRatio,
  outlet, narrative, archiveSearch, showError,
} from "./core.js";
import { lang, LOCALES } from "./i18n.js";

initChrome("brief");
const root = $("#brief");

function section(id, title, hint, ...body) {
  return el("section", { class: "section", id },
    el("div", { class: "section-head" }, el("h2", {}, title), hint ? el("span", { class: "hint" }, hint) : null), ...body);
}
function change(n, prev) {
  if (prev === null || prev === undefined) return null;
  if (!prev) return n ? el("span", { class: "delta up" }, `▲ ${t("today.new")}`) : null;
  const r = n / prev - 1;
  if (Math.abs(r) < 0.1) return el("span", { class: "delta flat" }, "≈");
  return el("span", { class: `delta ${r > 0 ? "up" : "down"}` },
    `${r > 0 ? "▲" : "▼"} ${new Intl.NumberFormat(LOCALES[lang] || "en-GB", { style: "percent", maximumFractionDigits: 0, signDisplay: "always" }).format(r)}`);
}
const weekSpan = (b) => `${fmtDayShort(b.from)} – ${fmtDay(b.to)}`;
const headline = (x) => el("a", { href: x.u, rel: "noopener noreferrer nofollow", target: "_blank", lang: outlet(x.o).lang }, x.t);
const translation = (x) => (x.te && outlet(x.o).lang !== "en" ? el("span", { class: "tr", lang: "en" },
  el("abbr", { class: "mt", title: t("article.mt.title") }, t("article.mt")), " ", x.te) : null);

function framings(b) {
  const row = (r) => {
    const n = narrative(r.id);
    return el("li", {},
      el("a", { class: `tag ${n?.family || "framing"}`, href: `narratives.html#${r.id}` }, n ? tl(n.label) : r.id), " ",
      el("span", { class: `delta ${r.x >= 1 ? "up" : "down"}` }, `×${fmtRatio(r.x)}`), " ",
      el("small", {}, t("brief.share", { share: fmtPct(r.share), base: fmtPct(r.base), n: fmtInt(r.n) })));
  };
  const kids = [];
  if (b.rising.length) kids.push(el("ul", { class: "brief-list" }, b.rising.map(row)));
  else kids.push(el("p", { class: "empty" }, t("brief.rising.none")));
  if (b.falling.length) kids.push(el("h3", {}, t("brief.falling")), el("ul", { class: "brief-list" }, b.falling.map(row)));
  return section("framings", t("brief.rising"), t("brief.rising.hint", { n: fmtInt(b.base_weeks) }), ...kids,
    el("p", { class: "syntax" }, t("brief.patterns"), " ", el("a", { href: "method.html#matching" }, `${t("nav.method")} →`)));
}

function events(b) {
  if (!b.events.length) return null;
  return section("events", t("brief.events"), t("brief.events.hint"), el("ol", { class: "brief-list" }, b.events.map((e) =>
    el("li", {},
      el("a", { class: "word", lang: e.lang, href: archiveSearch({ q: e.q, from: e.d, to: e.d }) }, e.w), " ",
      el("small", {}, t("brief.events.n", { n: fmtInt(e.n), day: fmtDayShort(e.d), x: fmtRatio(e.x) })),
      e.ex?.t ? el("div", { class: "ex" }, el("span", { class: "outlet" }, outlet(e.ex.o).name), " ", headline(e.ex), " ", translation(e.ex)) : null))));
}

function stories(b) {
  if (!b.stories.length) return null;
  return section("stories", t("brief.stories"), t("brief.stories.hint"), el("ol", { class: "brief-list" }, b.stories.map((s) =>
    el("li", {},
      headline(s.first), " ", translation(s.first),
      el("div", { class: "ex" }, el("small", {},
        t("brief.stories.n", { n: fmtInt(s.n), first: outlet(s.first.o).name, time: s.first.p || "", day: fmtDayShort(s.d) }), " ",
        el("a", { href: `analysis.html?d=${s.d}#stories` }, `${t("brief.stories.more")} →`)))))));
}

function speakers(b) {
  const list = (lg) => {
    const rows = (b.speakers || {})[lg] || [];
    if (!rows.length) return null;
    return el("div", {}, el("h3", {}, t(`lang.${lg}`)), el("ol", { class: "brief-list" }, rows.map((v) =>
      el("li", {}, el("a", { href: archiveSearch({ q: v.name, from: b.from, to: b.to }) }, v.name), " ",
        el("small", {}, t("brief.speakers.n", { n: fmtInt(v.n) })), " ", change(v.n, v.prev)))));
  };
  return section("speakers", t("brief.speakers"), t("brief.speakers.hint"), el("div", { class: "grid-2" }, list("ru"), list("en")),
    el("p", { class: "syntax" }, el("a", { href: "analysis.html?r=7#voices" }, `${t("brief.analysis")} →`)));
}

function countries(b) {
  if (!b.countries.length) return null;
  const row = (c) => el("li", {}, el("a", { href: archiveSearch({ q: c.name, from: b.from, to: b.to }) }, c.name), " ",
    el("small", {}, fmtInt(c.n)), " ", change(c.n, c.prev));
  return section("countries", t("brief.countries"), t("brief.countries.hint"),
    el("ol", { class: "brief-list" }, b.countries.map(row)),
    b.countries_rose.length ? [el("h3", {}, t("brief.countries.rose")), el("ul", { class: "brief-list" }, b.countries_rose.map(row))] : null);
}

function collected(b) {
  const gaps = Object.entries(b.gaps || {});
  return section("collected", t("brief.collected"), null,
    gaps.length ? el("ul", { class: "brief-list" }, gaps.map(([o, days]) => el("li", {},
      el("a", { href: `outlets.html#${o}` }, outlet(o).name), " ",
      el("small", {}, t("brief.gap.days", { n: fmtInt(days.length), days: days.map(fmtDayShort).join(", ") })))))
      : el("p", {}, t("brief.gap.none")),
    b.machine ? el("p", {}, t("brief.machine", { n: fmtInt(b.machine) }), " ",
      el("a", { href: "method.html#machine" }, `${t("nav.method")} →`)) : null);
}

/** The feeds: the brief, each framing and topic, outlet, country and saved search. */
function follow(feeds) {
  const link = (path, label) => el("a", { href: path, type: "application/atom+xml" }, label);
  const group = (title, items) => (items.length ? el("details", {}, el("summary", {}, `${title} (${fmtInt(items.length)})`),
    el("ul", { class: "feed-list" }, items.map(([path, label, n]) => el("li", {}, link(path, label),
      n !== undefined ? el("small", {}, ` ${t("brief.feed.n", { n: fmtInt(n) })}`) : null)))) : null);
  const f = feeds?.feeds || {};
  const byLabel = (a, b) => a[1].localeCompare(b[1], LOCALES[lang]);
  const fam = (family) => Object.entries(f.framing || {}).filter(([id]) => narrative(id)?.family === family)
    .map(([id, n]) => [`feeds/framing/${id}.xml`, tl(narrative(id).label), n]).sort(byLabel);
  return section("follow", t("brief.follow"), null,
    el("p", {}, t("brief.follow.about", { days: fmtInt((feeds?.days || []).length || 7), n: fmtInt(feeds?.entries || 40) })),
    el("p", {}, link("feeds/brief.xml", t("brief.follow.brief")), " ", el("small", {}, t("brief.follow.brief.hint"))),
    feeds ? [
      group(t("narratives.framings"), fam("framing")),
      group(t("narratives.topics"), fam("topic")),
      group(t("brief.follow.outlets"), Object.entries(f.outlet || {}).map(([id, n]) => [`feeds/outlet/${id}.xml`, outlet(id).name, n]).sort(byLabel)),
      group(t("brief.follow.countries"), Object.entries(f.country || {}).map(([c, n]) => [`feeds/country/${c}.xml`, regionName(c, feeds.countries[c]), n]).sort(byLabel)),
      group(t("brief.follow.searches"), (feeds.searches || []).map((s) => [`feeds/search/${s.id}.xml`, tl(s.label), (f.search || {})[s.id]])),
    ] : null,
    el("p", { class: "syntax" }, t("brief.follow.ask"), " ", META.repo ? el("a", { href: `${META.repo}/issues` }, `${t("brief.follow.ask.link")} →`) : null));
}

let regionNames = null;
function regionName(code, fallback) {
  try {
    regionNames = regionNames || new Intl.DisplayNames([LOCALES[lang] || "en-GB"], { type: "region" });
    return regionNames.of(code) || fallback;
  } catch (_) { return fallback; }
}

function render(index, b, feeds) {
  const pick = el("select", { id: "week", "aria-label": t("brief.week") },
    index.map((w) => el("option", { value: w.week, selected: w.week === b.week }, `${w.week.replace("-W", " · ")} — ${fmtDayShort(w.from)} – ${fmtDayShort(w.to)}`)));
  pick.addEventListener("change", () => {
    const u = new URL(location.href);
    u.searchParams.set("w", pick.value);
    location.href = u.toString();
  });
  const outlets = Object.keys(b.outlets).length;
  const lede = [t("brief.lede", { n: fmtInt(b.total), outlets: fmtInt(outlets), days: fmtInt(b.days) })];
  if (b.prev_total && b.prev_days === b.days) lede.push(" ", t("brief.lede.prev"), " ", change(b.total, b.prev_total));
  document.title = `Woland — ${t("title.brief")} · ${weekSpan(b)}`;
  root.replaceChildren(
    el("div", { class: "brief-head" }, el("label", { class: "field" }, t("brief.week"), pick),
      el("h2", { class: "brief-title" }, weekSpan(b)), el("p", { class: "lede" }, ...lede)),
    framings(b), events(b), stories(b), speakers(b), countries(b), collected(b), follow(feeds));
}

async function start() {
  try {
    await loadMeta();
    fillFooter();
    const [index, feeds] = await Promise.all([getJSON("brief/index.json").catch(() => []), getJSON("feeds.json").catch(() => null)]);
    if (!index.length) {
      root.replaceChildren(el("p", { class: "empty" }, t("brief.none")), follow(feeds));
      return;
    }
    const want = new URLSearchParams(location.search).get("w");
    const week = index.find((w) => w.week === want) || index[0];
    render(index, await getJSON(`brief/${week.week}.json`), feeds);
  } catch (e) {
    showError(root, e);
  }
}
start();
