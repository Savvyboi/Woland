// Chapter V: what the archive shows beyond framing counts — who is quoted, which stories every outlet ran and who
// ran them first, which countries are named, and the outlets' own tags. Built by woland/build.py
// (write_analysis) over completed days only.
import {
  $, el, t, META, loadMeta, getJSON, getGz, initChrome, fillFooter, fmtInt, fmtPct, fmtDay, outlet,
  groupVar, articleCard, fromExample, archiveSearch, showError, debounce,
} from "./core.js";
import { sparkline, barList, columnChart, withTable } from "./charts.js";
import { lang, LOCALES } from "./i18n.js";

initChrome("analysis");
const main = $("#analysis");
const tabsNav = $("#tabs");
const TABS = ["voices", "stories", "countries", "tags"];
const params = new URLSearchParams(location.search);
const state = {
  w: ["7", "30", "all"].includes(params.get("r")) ? params.get("r") : "30",
  vlang: params.get("vl") === "en" ? "en" : "ru",
  kind: params.get("vk") || "all",
  clang: ["ru", "en"].includes(params.get("cl")) ? params.get("cl") : "all",
  outlet: params.get("o") || null,
  day: params.get("d") || null,
};
const KIND_COLOR = { quotes: "var(--s1)", says: "var(--muted-series)", judges: "var(--g-mass)", warns: "var(--g-foreign)",
  reveals: "var(--g-hardline)", advises: "var(--g-official)" };
const sum = (a) => a.reduce((x, y) => x + y, 0);

function setParam(k, v) {
  const u = new URL(location.href);
  if (v === null || v === undefined) u.searchParams.delete(k); else u.searchParams.set(k, v);
  history.replaceState(null, "", u);
}
const tab = () => (TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "voices");

function plate(no, title, sub, ...body) {
  return el("figure", { class: "plate" },
    el("figcaption", {}, el("span", { class: "plate-no" }, `${t("plate")} ${no}`), el("span", { class: "plate-title" }, title),
      el("span", { class: "plate-tools" }), sub ? el("span", { class: "plate-sub" }, sub) : null), ...body);
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

function periodNote(data) {
  const d = data.days;
  if (!d.length) return el("p", { class: "syntax window-note" }, t("analysis.nodays"));
  return el("p", { class: "syntax window-note" }, t("analysis.window", { n: fmtInt(d.length), from: fmtDay(d[0]), to: fmtDay(d[d.length - 1]) }));
}

function periodControl() {
  return seg(t("range.label"), [["7", t("range.7")], ["30", t("range.30")], ["all", t("range.all")]], state.w,
    (w) => { state.w = w; setParam("r", w); route(); });
}

function renderTabs() {
  const cur = tab();
  tabsNav.replaceChildren(...TABS.map((k) => el("a", { href: `#${k}`, "aria-current": k === cur ? "page" : null },
    t(`analysis.tab.${k}`))));
}

const searchLink = (data, extra) => archiveSearch({ ...extra, from: data.days[0], to: data.days[data.days.length - 1] });
const pctOf = (v) => fmtPct(v, v === 0 ? 0 : v < 0.01 ? 2 : v < 0.1 ? 1 : 0);
function change(n, prev) {
  if (prev === null || prev === undefined) return null;
  if (!prev) return n ? el("span", { class: "delta up" }, `▲ ${t("today.new")}`) : null;
  const r = n / prev - 1;
  if (Math.abs(r) < 0.1) return el("span", { class: "delta flat" }, "≈");
  return el("span", { class: `delta ${r > 0 ? "up" : "down"}` },
    `${r > 0 ? "▲" : "▼"} ${new Intl.NumberFormat(LOCALES[lang] || "en-GB", { style: "percent", maximumFractionDigits: 0, signDisplay: "always" }).format(r)}`);
}

// ── Voices ──────────────────────────────────────────────────────────────────
async function renderVoices() {
  const [data, verbs] = await Promise.all([getJSON(`analysis/voices/${state.w}.json`), getJSON("analysis/verbs.json")]);
  const kindOf = (v) => (v === ":" ? "quotes" : verbs.verbs[v] || "says");
  const rows = (data.voices[state.vlang] || []).filter((r) => state.kind === "all" || r.y === state.kind);
  const kinds = data.kinds[state.vlang] || {};
  const outletsOfLang = Object.keys(data.totals).filter((o) => outlet(o).lang === state.vlang);
  const heads = sum(outletsOfLang.map((o) => data.totals[o] || 0));
  const named = sum(Object.values(kinds));
  const kids = [
    el("p", { class: "lede-small" }, t("voices.lede", { n: fmtInt(named), all: fmtInt(heads), share: pctOf(heads ? named / heads : 0) })),
    el("div", { class: "filters" }, periodControl(),
      seg(t("voices.lang"), [["ru", t("lang.ru")], ["en", t("lang.en")]], state.vlang, (v) => { state.vlang = v; setParam("vl", v === "en" ? v : null); route(); }),
      seg(t("voices.kind"), [["all", t("voices.kind.all")], ...["person", "inst", "role", "media"].map((k) => [k, t(`voices.kind.${k}`)])],
        state.kind, (v) => { state.kind = v; setParam("vk", v === "all" ? null : v); route(); })),
    periodNote(data),
  ];

  // Plate I — who is quoted
  const legend = el("p", { class: "kind-legend" }, t("voices.how"), " ",
    ...verbs.kinds.map((k) => el("span", {}, el("i", { style: { background: KIND_COLOR[k] }, "aria-hidden": "true" }), t(`voices.verb.${k}`))));
  const list = el("ol", { class: "voices" });
  const more = el("button", { class: "btn", type: "button" }, t("voices.more"));
  let shown = 0;
  const draw = (n) => {
    for (const r of rows.slice(shown, n)) list.append(voiceRow(r, data, kindOf));
    shown = Math.min(n, rows.length);
    more.hidden = shown >= rows.length;
  };
  more.addEventListener("click", () => draw(shown + 40));
  const p1 = plate("I", t("voices.who"), t("voices.who.sub"), legend, list, more);
  kids.push(p1);
  if (!rows.length) list.append(el("li", { class: "empty" }, "—"));

  // Plate II — voices without a name, by outlet
  const share = Object.entries(data.outlets).filter(([o, k]) => outlet(o).lang === state.vlang && sum(Object.values(k)) >= 30)
    .map(([o, k]) => ({ o, role: k.role || 0, all: sum(Object.values(k)) })).sort((a, b) => b.role / b.all - a.role / a.all);
  const c2 = el("div");
  const p2 = plate("II", t("voices.unnamed"), t("voices.unnamed.sub"), c2);
  // Plate III — what kind of speaker each outlet quotes
  const c3 = el("div");
  const p3 = plate("III", t("voices.mix"), t("voices.mix.sub"), c3);
  kids.push(el("div", { class: "section grid-2" }, p2, p3));
  kids.push(el("p", { class: "syntax" }, t("voices.method"), " ", el("a", { href: "method.html#analysis" }, `${t("nav.method")} →`)));
  main.replaceChildren(...kids);
  draw(40);

  barList(c2, share.map((x) => ({ label: outlet(x.o).name, value: x.role / x.all, color: groupVar(outlet(x.o).group),
    title: `${fmtInt(x.role)} / ${fmtInt(x.all)}` })), pctOf);
  withTable(p2, c2, () => simpleTable([t("col.outlet"), t("voices.kind.role"), t("voices.all"), t("col.share")],
    share.map((x) => [outlet(x.o).name, fmtInt(x.role), fmtInt(x.all), pctOf(x.role / x.all)])));
  const mixRows = share.slice().sort((a, b) => b.all - a.all);
  c3.replaceChildren(el("ul", { class: "stack-list" }, mixRows.map((x) => {
    const k = data.outlets[x.o];
    return el("li", {}, el("span", { class: "lab" }, outlet(x.o).name),
      stackBar(["person", "inst", "role", "media"].map((kind) => ({ v: k[kind] || 0, color: `var(--k-${kind})`, label: t(`voices.kind.${kind}`) }))),
      el("span", { class: "val" }, fmtInt(x.all)));
  })), el("p", { class: "kind-legend" }, ...["person", "inst", "role", "media"].map((kind) =>
    el("span", {}, el("i", { style: { background: `var(--k-${kind})` }, "aria-hidden": "true" }), t(`voices.kind.${kind}`)))));
  withTable(p3, c3, () => simpleTable([t("col.outlet"), ...["person", "inst", "role", "media"].map((k) => t(`voices.kind.${k}`))],
    mixRows.map((x) => [outlet(x.o).name, ...["person", "inst", "role", "media"].map((k) => fmtInt(data.outlets[x.o][k] || 0))])));
}

function stackBar(parts) {
  const total = sum(parts.map((p) => p.v)) || 1;
  return el("span", { class: "stack", role: "img", "aria-label": parts.filter((p) => p.v).map((p) => `${p.label} ${pctOf(p.v / total)}`).join(", ") },
    parts.filter((p) => p.v).map((p) => el("span", { style: { width: `${(p.v / total) * 100}%`, background: p.color }, title: `${p.label}: ${fmtInt(p.v)} (${pctOf(p.v / total)})` })));
}

function simpleTable(head, rows) {
  return el("table", { class: "table-view" },
    el("thead", {}, el("tr", {}, head.map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", {}, rows.map((r) => el("tr", {}, el("th", { scope: "row" }, r[0]), r.slice(1).map((c) => el("td", {}, c))))));
}

function voiceRow(r, data, kindOf) {
  const byKind = {};
  for (const [v, n] of Object.entries(r.v)) byKind[kindOf(v)] = (byKind[kindOf(v)] || 0) + n;
  const verbsShown = Object.entries(r.v).slice(0, 4).map(([v, n]) => `${v === ":" ? t("voices.colon") : v} ${pctOf(n / r.n)}`).join(" · ");
  const top = Object.entries(r.o).slice(0, 3).map(([o, n]) => `${outlet(o).name} ${fmtInt(n)}`).join(", ");
  const details = el("details", {},
    el("summary", {},
      el("span", { class: "who" }, el("b", { lang: state.vlang }, r.name), el("small", {}, t(`voices.kind.${r.y}`))),
      el("span", { class: "n" }, fmtInt(r.n)),
      sparkline(r.d, { width: 90, height: 22, label: t("voices.perday") }),
      stackBar(Object.entries(byKind).map(([k, v]) => ({ v, color: KIND_COLOR[k], label: t(`voices.verb.${k}`) }))),
      el("span", { class: "outs" }, top)));
  details.addEventListener("toggle", () => {
    if (!details.open || details.children.length > 1) return;
    const ex = r.ex;
    details.append(el("div", { class: "voice-more" },
      el("p", { class: "syntax" }, el("b", {}, `${t("voices.verbs")}: `), el("span", { lang: state.vlang }, verbsShown)),
      el("p", { class: "syntax" }, el("b", {}, `${t("voices.outlets")}: `), Object.entries(r.o).map(([o, n]) => `${outlet(o).name} ${fmtInt(n)}`).join(", ")),
      ex ? el("ul", { class: "articles" }, articleCard(fromExample(ex, ex.d), { noTags: true })) : null,
      el("p", { class: "syntax" }, el("a", { href: searchLink(data, { q: r.y === "person" ? r.name.split(" ").pop() : r.name, l: state.vlang }) }, `${t("voices.search")} →`))));
  });
  return el("li", {}, details);
}

// ── Stories ─────────────────────────────────────────────────────────────────
async function renderStories() {
  const data = await getJSON(`analysis/stories/${state.w}.json`);
  const days = data.days;
  const day = days.includes(state.day) ? state.day : days[days.length - 1];
  const kids = [
    el("p", { class: "lede-small" }, t("stories.lede", { min: fmtInt(data.min), n: fmtInt(sum(data.per_day)), days: fmtInt(days.length) })),
    el("div", { class: "filters" }, periodControl()),
    periodNote(data),
  ];
  // Plate I — the day's stories
  const dayBox = el("div");
  const i = days.indexOf(day);
  const nav = el("p", { class: "daynav" },
    el("button", { class: "linkish", type: "button", disabled: i <= 0 || null, onclick: () => { state.day = days[i - 1]; setParam("d", state.day); route(); } }, t("today.prev")),
    el("strong", {}, day ? fmtDay(day, true) : "—"),
    el("button", { class: "linkish", type: "button", disabled: i >= days.length - 1 || null, onclick: () => { state.day = days[i + 1]; setParam("d", state.day); route(); } }, t("today.next")));
  kids.push(plate("I", t("stories.day"), t("stories.day.sub", { min: fmtInt(data.min) }), nav, dayBox));
  // Plate II — who goes first
  const c2 = el("div");
  const p2 = plate("II", t("stories.first"), t("stories.first.sub"), c2);
  // Plate III — how many stories a day
  const c3 = el("div");
  const p3 = plate("III", t("stories.count"), t("stories.count.sub", { min: fmtInt(data.min) }), c3);
  kids.push(el("div", { class: "section grid-2" }, p2, p3));
  // Plate IV — who follows whom
  const c4 = el("div", { class: "table-wrap" });
  kids.push(el("div", { class: "section" }, plate("IV", t("stories.follow"), t("stories.follow.sub"), c4)));
  kids.push(el("p", { class: "syntax" }, t("stories.method"), " ", el("a", { href: "method.html#analysis" }, `${t("nav.method")} →`)));
  main.replaceChildren(...kids);

  const rows = Object.entries(data.outlets).filter(([, v]) => v.j >= 10).map(([o, v]) => ({ o, ...v }))
    .sort((a, b) => b.l / b.j - a.l / a.j);
  const mins = (m) => (m === null || m === undefined ? "–" : m < 60 ? t("stories.min", { n: fmtInt(m) }) : t("stories.hours", { h: fmtInt(Math.floor(m / 60)), m: String(m % 60).padStart(2, "0") }));
  c2.replaceChildren(simpleTable([t("col.outlet"), t("stories.joined"), t("stories.led"), t("stories.behind")],
    rows.map((r) => [el("span", {}, el("span", { class: "swatch", style: { background: groupVar(outlet(r.o).group) }, "aria-hidden": "true" }), outlet(r.o).name),
      fmtInt(r.j), `${fmtInt(r.l)} (${pctOf(r.l / r.j)})`, r.lag ? `${mins(r.lag[1])} (${mins(r.lag[0])}–${mins(r.lag[2])})` : "–"])));
  if (days.length) columnChart(c3, { days, values: data.per_day, format: fmtInt, label: t("stories.count") });
  withTable(p3, c3, () => simpleTable([t("table.day"), t("stories.count"), t("stories.big")],
    days.map((d, k) => [fmtDay(d), fmtInt(data.per_day[k]), fmtInt(data.big[k])])));

  // the follow matrix: the outlets that led most, by the outlets that followed them
  const leaders = Object.entries(data.pairs).map(([o, by]) => [o, sum(Object.values(by))]).sort((a, b) => b[1] - a[1]).slice(0, 10).map((x) => x[0]);
  const followers = rows.map((r) => r.o);
  const max = Math.max(1, ...leaders.flatMap((a) => followers.map((b) => (data.pairs[a] || {})[b] || 0)));
  c4.replaceChildren(el("table", { class: "table-view matrix" },
    el("thead", {}, el("tr", {}, el("th", { scope: "col" }, t("stories.matrix.corner")), followers.map((b) => el("th", { scope: "col", title: outlet(b).name }, outlet(b).short || outlet(b).name)))),
    el("tbody", {}, leaders.map((a) => el("tr", {}, el("th", { scope: "row" }, outlet(a).name),
      followers.map((b) => {
        const v = a === b ? null : (data.pairs[a] || {})[b] || 0;
        return el("td", { style: v ? { background: `color-mix(in srgb, var(--gilt) ${Math.round((v / max) * 70)}%, transparent)` } : {},
          title: v ? t("stories.matrix.cell", { a: outlet(a).name, b: outlet(b).name, n: fmtInt(v) }) : "" }, v === null ? "" : v ? fmtInt(v) : "·");
      }))))));

  if (!day) { dayBox.replaceChildren(el("p", { class: "empty" }, "—")); return; }
  let list = [];
  try { list = (await getGz(`analysis/stories/day/${day}.json.gz`)) || []; } catch (_) { /* no file */ }
  const ul = el("ol", { class: "stories" });
  for (const st of list.slice(0, 60)) ul.append(storyItem(st, day));
  dayBox.replaceChildren(list.length ? ul : el("p", { class: "empty" }, "—"));
}

function minutesOf(hhmm) { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; }

function storyItem(st, day) {
  const first = st.m[0];
  const head = first.te || first.t;
  const t0 = minutesOf(first.p);
  const details = el("details", {},
    el("summary", {}, el("span", { class: "n" }, fmtInt(st.n)), el("span", { class: "head", lang: first.te ? "en" : outlet(first.o).lang }, head),
      el("span", { class: "first" }, t("stories.firstby", { o: outlet(first.o).name, time: first.p }))));
  details.addEventListener("toggle", () => {
    if (!details.open || details.children.length > 1) return;
    details.append(el("ol", { class: "timeline" }, st.m.map((m, k) => {
      const lag = minutesOf(m.p) - t0;
      return el("li", {},
        el("span", { class: "when" }, m.p, k ? el("small", {}, ` +${lag < 60 ? t("stories.min", { n: lag }) : t("stories.hours", { h: Math.floor(lag / 60), m: String(lag % 60).padStart(2, "0") })}`) : null),
        el("span", { class: "outlet" }, el("span", { class: "swatch", style: { background: groupVar(outlet(m.o).group) }, "aria-hidden": "true" }), outlet(m.o).name),
        el("span", { class: "what" }, el("a", { href: m.u, rel: "noopener noreferrer nofollow", target: "_blank", lang: outlet(m.o).lang }, m.t),
          m.te && outlet(m.o).lang !== "en" ? el("small", { lang: "en" }, el("abbr", { class: "mt", title: t("article.mt.title") }, t("article.mt")), m.te) : null));
    })), st.a > st.n ? el("p", { class: "syntax" }, t("stories.more", { n: fmtInt(st.a), k: fmtInt(st.n) })) : null);
  });
  return el("li", {}, details);
}

// ── Countries ───────────────────────────────────────────────────────────────
let world = null;
async function loadWorld() {
  if (!world) world = await fetch("assets/data/world.json").then((r) => r.json());
  return world;
}
const regionNames = (() => { try { return new Intl.DisplayNames([lang], { type: "region" }); } catch (_) { return null; } })();
const countryName = (code) => { try { return regionNames?.of(code) || code; } catch (_) { return code; } };

async function renderCountries() {
  const [data, map] = await Promise.all([getJSON(`analysis/countries/${state.w}.json`), loadWorld()]);
  const inLang = (o) => state.clang === "all" || outlet(o).lang === state.clang;
  const total = sum(Object.entries(data.totals).filter(([o]) => inLang(o)).map(([, n]) => n));
  const rows = Object.entries(data.countries).map(([code, c]) => {
    const n = sum(Object.entries(c.o).filter(([o]) => inLang(o)).map(([, v]) => v));
    return { code, n, share: total ? n / total : 0, d: c.d, prev: state.clang === "all" ? c.prev : null, o: c.o, name: data.names?.[code] };
  }).filter((r) => r.n > 0).sort((a, b) => b.n - a.n);
  const kids = [
    el("p", { class: "lede-small" }, t("countries.lede", { all: fmtInt(total) })),
    el("div", { class: "filters" }, periodControl(),
      seg(t("voices.lang"), [["all", t("series.all")], ["ru", t("lang.ru")], ["en", t("lang.en")]], state.clang,
        (v) => { state.clang = v; setParam("cl", v === "all" ? null : v); route(); })),
    periodNote(data),
  ];
  const c1 = el("div", { class: "map-wrap" });
  const p1 = plate("I", t("countries.map"), t("countries.map.sub"), c1);
  kids.push(p1);
  const c2 = el("div");
  const p2 = plate("II", t("countries.list"), t("countries.list.sub"), c2);
  kids.push(el("div", { class: "section" }, p2));
  kids.push(el("p", { class: "syntax" }, t("countries.method"), " ", el("a", { href: "method.html#analysis" }, `${t("nav.method")} →`)));
  main.replaceChildren(...kids);

  drawMap(c1, map, rows);
  withTable(p1, c1, () => simpleTable([t("countries.country"), t("unit.articles"), t("col.share")],
    rows.map((r) => [countryName(r.code), fmtInt(r.n), pctOf(r.share)])));
  const top = rows.slice(0, 40);
  c2.replaceChildren(el("ol", { class: "country-list" }, top.map((r) => el("li", {},
    el("a", { class: "lab", href: searchLink(data, { q: r.name || countryName(r.code), ...(state.clang !== "all" ? { l: state.clang } : {}) }) }, countryName(r.code)),
    el("span", { class: "track", "aria-hidden": "true" }, el("span", { class: "fill", style: { width: `${(r.n / (top[0]?.n || 1)) * 100}%` } })),
    el("span", { class: "val" }, fmtInt(r.n), el("small", {}, ` ${pctOf(r.share)}`)),
    sparkline(r.d, { width: 80, height: 20, label: t("voices.perday") }),
    change(r.n, r.prev)))));
}

function drawMap(container, map, rows) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${map.w} ${map.h}`);
  svg.setAttribute("class", "world");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", t("countries.map"));
  const by = new Map(rows.map((r) => [r.code, r]));
  // colour by rank, in seven steps, so that Ukraine and the United States do not wash out everyone else
  const ranked = rows.filter((r) => r.code !== "RU");
  const step = (r) => {
    const i = ranked.indexOf(r);
    if (i < 0) return 0;
    return Math.max(1, 6 - Math.floor((i / Math.max(1, ranked.length)) * 6));
  };
  const tip = el("div", { class: "tooltip", role: "status" });
  tip.hidden = true;
  for (const [code, d] of Object.entries(map.c)) {
    const r = by.get(code);
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    p.setAttribute("class", code === "RU" ? "home" : "");
    p.setAttribute("fill", code === "RU" ? "var(--ink-3)" : r ? `var(--seq-${step(r)})` : "var(--seq-0)");
    p.setAttribute("tabindex", r ? "0" : "-1");
    const label = r ? `${countryName(code)}: ${fmtInt(r.n)} ${t("unit.articles")} (${pctOf(r.share)})` : countryName(code);
    const title = document.createElementNS(NS, "title");
    title.textContent = code === "RU" ? `${label} — ${t("countries.home")}` : label;
    p.append(title);
    const show = (e) => {
      tip.textContent = title.textContent;
      tip.hidden = false;
      const box = container.getBoundingClientRect();
      const x = (e.clientX ?? (p.getBoundingClientRect().left + 10)) - box.left, y = (e.clientY ?? p.getBoundingClientRect().top) - box.top;
      tip.style.left = `${Math.min(x + 12, box.width - 180)}px`;
      tip.style.top = `${Math.max(0, y - 30)}px`;
    };
    p.addEventListener("mousemove", show);
    p.addEventListener("focus", show);
    p.addEventListener("mouseleave", () => { tip.hidden = true; });
    p.addEventListener("blur", () => { tip.hidden = true; });
    svg.append(p);
  }
  const scale = el("div", { class: "scale" }, t("countries.fewer"),
    el("span", { class: "ramp" }, [1, 2, 3, 4, 5, 6].map((k) => el("span", { style: { background: `var(--seq-${k})` } }))), t("countries.more"),
    el("span", { class: "key-home" }, t("countries.home")));
  container.replaceChildren(svg, scale, tip);
}

// ── Tags ────────────────────────────────────────────────────────────────────
async function renderTags() {
  const data = await getJSON(`analysis/tags/${state.w}.json`);
  const ids = Object.keys(data.outlets).filter((o) => (data.outlets[o].tags_n || data.outlets[o].sections_n))
    .sort((a, b) => outlet(a).name.localeCompare(outlet(b).name));
  const o = ids.includes(state.outlet) ? state.outlet : (ids.includes("ria") ? "ria" : ids[0]);
  const sel = el("select", { id: "tag-outlet" }, ids.map((id) => el("option", { value: id, selected: id === o || null }, outlet(id).name)));
  sel.addEventListener("change", () => { state.outlet = sel.value; setParam("o", sel.value); route(); });
  const kids = [
    el("p", { class: "lede-small" }, t("tags.lede")),
    el("div", { class: "filters" }, periodControl(), el("label", { class: "field", for: "tag-outlet" }, t("col.outlet"), sel)),
    periodNote(data),
  ];
  const e = o ? data.outlets[o] : null;
  const block = (field, no) => {
    const items = e?.[field] || [];
    const box = el("div");
    const fig = plate(no, t(`tags.${field}`), t(`tags.${field}.sub`, { n: fmtInt(e?.[`${field}_n`] || 0), all: fmtInt(data.totals[o] || 0) }), box);
    if (!items.length) box.append(el("p", { class: "empty" }, t("tags.none")));
    else {
      const max = items[0][1];
      box.append(el("ol", { class: "country-list tag-list" }, items.map(([name, n, prev]) => el("li", {},
        el("span", { class: "lab", lang: outlet(o).lang }, name),
        el("span", { class: "track", "aria-hidden": "true" }, el("span", { class: "fill", style: { width: `${(n / max) * 100}%` } })),
        el("span", { class: "val" }, fmtInt(n)), change(n, prev)))));
    }
    return fig;
  };
  kids.push(el("div", { class: "section grid-2" }, block("tags", "I"), block("sections", "II")));
  kids.push(el("p", { class: "syntax" }, t("tags.method"), " ", el("a", { href: "method.html#analysis" }, `${t("nav.method")} →`)));
  main.replaceChildren(...kids);
}

// ── routing ─────────────────────────────────────────────────────────────────
const RENDER = { voices: renderVoices, stories: renderStories, countries: renderCountries, tags: renderTags };
function route() {
  renderTabs();
  const k = tab();
  document.title = `Woland — ${t(`analysis.tab.${k}`)} · ${t("title.analysis")}`;
  RENDER[k]().catch((e) => showError(main, e));
}

async function start() {
  try {
    await loadMeta();
    fillFooter();
    if (!META.last) { main.replaceChildren(el("p", { class: "empty" }, t("empty.nodata"))); return; }
    window.addEventListener("hashchange", route);
    window.addEventListener("resize", debounce(() => { if (tab() === "stories") route(); }, 400));
    route();
  } catch (e) {
    showError(main, e);
  }
}
start();
