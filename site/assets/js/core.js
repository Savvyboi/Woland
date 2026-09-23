// Shared plumbing: data loading, formatting, page chrome, article cards, citations.
import { t, tl, lang, setLang, applyI18n, LANGS, LOCALES } from "./i18n.js";

export { t, tl };
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Build DOM safely: strings become text nodes, never HTML. */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "style" && typeof v === "object") {
      for (const [sk, sv] of Object.entries(v)) {
        if (sk.startsWith("--")) node.style.setProperty(sk, sv);
        else node.style[sk] = sv;
      }
    }
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

// ── Data ────────────────────────────────────────────────────────────────────
const memo = new Map();

export function getJSON(path) {
  if (!memo.has(path)) {
    memo.set(path, fetch(`data/${path}`).then((r) => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    }).catch((e) => { memo.delete(path); throw e; }));
  }
  return memo.get(path);
}

let pako = null;
async function gunzip(buf) {
  if (typeof DecompressionStream !== "undefined") {
    const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
    return await new Response(stream).text();
  }
  if (!pako) pako = await import("https://cdn.jsdelivr.net/npm/pako@2.1.0/+esm");
  return pako.ungzip(new Uint8Array(buf), { to: "string" });
}

/** gzip-compressed JSON (search index shards). */
export function getGz(path) {
  if (!memo.has(path)) {
    memo.set(path, fetch(`data/${path}`).then(async (r) => {
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return JSON.parse(await gunzip(await r.arrayBuffer()));
    }).catch((e) => { memo.delete(path); throw e; }));
  }
  return memo.get(path);
}

export let META = null;
let outletMap = new Map();
let narrMap = new Map();
export const GROUPS = ["state", "official", "mass", "foreign", "hardline"];

export async function loadMeta() {
  if (META) return META;
  META = await getJSON("meta.json");
  outletMap = new Map(META.outlets.map((o, i) => [o.id, { ...o, idx: i }]));
  narrMap = new Map(META.narratives.map((n) => [n.id, n]));
  return META;
}
export const outlet = (id) => outletMap.get(id) || { id, name: id, name_ru: id, lang: "ru", group: "state" };
export const outletAt = (i) => META.outlets[i];
export const narrative = (id) => narrMap.get(id);
export const narrativeAt = (i) => META.narratives[i];
export const groupVar = (g) => `var(--g-${g})`;

// ── Formatting ──────────────────────────────────────────────────────────────
const LOC = () => LOCALES[lang] || "en-GB";
export const fmtInt = (n) => new Intl.NumberFormat(LOC()).format(Math.round(n || 0));
export function fmtPct(x, digits) {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const d = digits ?? (x < 0.01 ? 2 : x < 0.1 ? 1 : 0);
  return new Intl.NumberFormat(LOC(), { style: "percent", minimumFractionDigits: d, maximumFractionDigits: d }).format(x);
}
export function fmtCompact(n) {
  return new Intl.NumberFormat(LOC(), { notation: n >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
}
const mskDate = (d, o) => new Intl.DateTimeFormat(LOC(), { timeZone: "Europe/Moscow", ...o }).format(d);
export const dayDate = (iso) => new Date(`${iso}T12:00:00+03:00`);
export function fmtDay(iso, long = false) {
  return mskDate(dayDate(iso), long ? { weekday: "long", day: "numeric", month: "long", year: "numeric" }
    : { day: "numeric", month: "short", year: "numeric" });
}
export const fmtDayShort = (iso) => mskDate(dayDate(iso), { day: "numeric", month: "short" });
export function fmtStamp(ts) {
  return mskDate(new Date(ts * 1000), { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) + " MSK";
}
export const mskISO = (ts) => new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Moscow" }).format(new Date(ts * 1000));
export function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
export function roman(n) {
  const map = [[1000, "M"], [900, "CM"], [500, "D"], [400, "CD"], [100, "C"], [90, "XC"], [50, "L"], [40, "XL"], [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
  let s = "";
  for (const [v, r] of map) while (n >= v) { s += r; n -= v; }
  return s;
}
/** Relative change of a share against its baseline, as {cls, text}. */
export function delta(share, base) {
  if (base === null || base === undefined) return { cls: "na", text: "–", v: null };
  if (base === 0) return share > 0 ? { cls: "up", text: `▲ ${t("today.new")}`, v: Infinity } : { cls: "flat", text: "·", v: 0 };
  const r = share / base - 1;
  if (Math.abs(r) < 0.05) return { cls: "flat", text: "≈", v: r };
  const pct = new Intl.NumberFormat(LOC(), { style: "percent", maximumFractionDigits: 0, signDisplay: "always" }).format(r);
  return { cls: r > 0 ? "up" : "down", text: `${r > 0 ? "▲" : "▼"} ${pct}`, v: r };
}

// ── Links ───────────────────────────────────────────────────────────────────
export function archiveUrl(url, ts) {
  const stamp = ts ? new Date(ts * 1000).toISOString().replace(/[-:T]/g, "").slice(0, 14) : "2";
  return `https://web.archive.org/web/${stamp}/${url}`;
}
export function translateUrl(url) {
  return `https://translate.google.com/translate?sl=auto&tl=${lang}&u=${encodeURIComponent(url)}`;
}
export function archiveSearch(params) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""));
  return `archive.html?${q}`;
}

// ── Chrome: navigation, language, theme, footer ─────────────────────────────
export function theme() { return document.documentElement.dataset.theme === "day" ? "day" : "night"; }

export function initChrome(page) {
  const nav = $(".toc");
  if (nav) for (const a of $$("a", nav)) if (a.dataset.page === page) a.setAttribute("aria-current", "page");
  const sel = $("#lang");
  if (sel) {
    sel.replaceChildren(...Object.entries(LANGS).map(([k, v]) => el("option", { value: k, selected: k === lang }, v)));
    sel.addEventListener("change", () => {
      setLang(sel.value);
      const u = new URL(location.href);
      u.searchParams.delete("lang");
      location.href = u.toString();
    });
  }
  const tb = $("#theme");
  if (tb) {
    const paint = () => {
      const day = theme() === "day";
      tb.textContent = day ? "☾" : "☀";
      tb.setAttribute("aria-label", `${t("theme.toggle")} (${day ? t("theme.day") : t("theme.night")})`);
      tb.title = t("theme.toggle");
    };
    paint();
    tb.addEventListener("click", () => {
      const next = theme() === "day" ? "night" : "day";
      if (next === "day") document.documentElement.dataset.theme = "day";
      else delete document.documentElement.dataset.theme;
      try { localStorage.setItem("woland.theme", next); } catch (_) { /* ignore */ }
      paint();
      document.dispatchEvent(new CustomEvent("themechange"));
    });
  }
  applyI18n();
}

export function fillFooter() {
  const repo = $("#repo");
  if (repo && META?.repo) repo.href = META.repo;
  else if (repo) repo.hidden = true;
  const f = $("#updated");
  if (f && META?.generated) {
    f.textContent = t("footer.updated", { date: new Intl.DateTimeFormat(LOC(), { dateStyle: "long", timeStyle: "short" }).format(new Date(META.generated)) });
  }
}

export function showError(container, err) {
  console.error(err);
  container.replaceChildren(el("p", { class: "notice" }, t("error.load")));
}

// ── Articles ────────────────────────────────────────────────────────────────
/** Normalise a search-index document array. */
export function fromIndex(a) {
  return { o: outletAt(a[0])?.id, ts: a[1], t: a[2], te: a[3], d: a[4], u: a[5], ks: a[6] || [],
           sn: a[7] || {}, h: a[8], r: a[9], a: a[10] };
}
/** Normalise a digest example. */
export function fromExample(ex, dayIso, narrId) {
  const ts = Math.floor(new Date(`${dayIso}T${ex.p || "12:00"}:00+03:00`).getTime() / 1000);
  const k = narrId ? narrative(narrId)?.idx : undefined;
  return { o: ex.o, ts, t: ex.t, te: ex.te, u: ex.u, id: ex.id, ks: k !== undefined ? [k] : [],
           sn: ex.s && k !== undefined ? { [k]: ex.s } : {} };
}

function highlight(text, terms) {
  if (!terms || !terms.size || !text) return [text];
  const out = [];
  const re = /[\p{L}\p{N}]+/gu;
  let last = 0, m;
  while ((m = re.exec(text))) {
    const w = m[0].toLowerCase().replace(/ё/g, "е");
    if (terms.has(w)) {
      if (m.index > last) out.push(text.slice(last, m.index));
      out.push(el("mark", {}, m[0]));
      last = m.index + m[0].length;
    }
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function articleCard(doc, opts = {}) {
  const o = outlet(doc.o);
  const blocked = o.eu_blocked;
  const meta = el("div", { class: "meta" },
    el("span", { class: "outlet" }, el("span", { class: "swatch", style: { background: groupVar(o.group) }, "aria-hidden": "true" }), o.name),
    el("time", { datetime: new Date(doc.ts * 1000).toISOString() }, fmtStamp(doc.ts)),
    doc.a ? el("span", {}, doc.a) : null,
    blocked ? el("span", { class: "badge eu", title: t("article.eu") }, "EU ⊘") : null,
    o.method === "feed" ? el("span", { class: "badge feed" }, t("article.feed")) : null,
  );
  const title = el("h3", {}, el("a", { href: doc.u, rel: "noopener noreferrer nofollow", target: "_blank", lang: o.lang },
    ...highlight(doc.t, opts.terms)));
  const kids = [meta, title];
  if (doc.te && o.lang !== "en") {
    kids.push(el("p", { class: "tr", lang: "en" }, el("abbr", { class: "mt", title: t("article.mt.title") }, t("article.mt")),
      ...highlight(doc.te, opts.terms)));
  }
  if (doc.d && !opts.noLead) kids.push(el("p", { class: "lead", lang: o.lang }, ...highlight(doc.d, opts.terms)));
  for (const [k, s] of Object.entries(doc.sn || {})) {
    const n = narrativeAt(Number(k));
    if (!n || (opts.only !== undefined && Number(k) !== opts.only)) continue;
    kids.push(el("p", { class: "snip", lang: o.lang }, el("span", { class: "sr-only" }, `${t("article.body")}: `), s,
      el("span", { class: "n", style: { color: "var(--text-3)", fontSize: ".8em", marginLeft: ".5em" } }, `— ${tl(n.label)}`)));
  }
  if (doc.ks?.length && !opts.noTags) {
    const tags = doc.ks.map((k) => narrativeAt(k)).filter(Boolean)
      .sort((a, b) => (a.family === b.family ? 0 : a.family === "framing" ? -1 : 1))
      .map((n) => el("a", { class: `tag ${n.family}`, href: `narratives.html#${n.id}` }, tl(n.label)));
    kids.push(el("div", { class: "tags" }, tags));
  }
  const links = el("div", { class: "links" },
    el("a", { href: doc.u, rel: "noopener noreferrer nofollow", target: "_blank" },
      `${t("article.original")} ↗`, blocked ? el("span", { class: "sr-only" }, ` (${t("article.eu")})`) : null),
    el("a", { href: archiveUrl(doc.u, doc.ts), rel: "noopener noreferrer", target: "_blank" }, `${t("article.archive")} ↗`),
    o.lang !== lang ? el("a", { href: translateUrl(doc.u), rel: "noopener noreferrer nofollow", target: "_blank" }, `${t("article.translate")} ↗`) : null,
    el("button", { class: "linkish", type: "button", onclick: () => openCite(doc) }, t("article.cite")),
  );
  kids.push(links);
  return el("li", { class: "article" }, kids);
}

// ── Citations ───────────────────────────────────────────────────────────────
function siteUrl() {
  return (META?.base_url || location.origin + location.pathname.replace(/[^/]*$/, "")).replace(/\/$/, "");
}
export function citations(doc) {
  const o = outlet(doc.o);
  const d = new Date(doc.ts * 1000);
  const y = mskISO(doc.ts).slice(0, 4);
  const monthEn = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Moscow", month: "long" }).format(d);
  const dayN = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Moscow", day: "numeric" }).format(d);
  const arch = archiveUrl(doc.u, doc.ts);
  const tr = doc.te && o.lang !== "en" ? ` [${doc.te}]` : "";
  const retrieved = doc.r ? `Retrieved ${doc.r} via Woland` : "Via Woland";
  const fp = doc.h ? `, content fingerprint ${doc.h}` : "";
  const apa = `${o.name}. (${y}, ${monthEn} ${dayN}). ${doc.t}${tr}. ${doc.u} (archived: ${arch}). ${retrieved} (${siteUrl()})${fp}.`;
  const chicago = `${o.name}. “${doc.t}”${tr}. ${monthEn} ${dayN}, ${y}. ${doc.u}. ${retrieved}${fp}.`;
  const key = `${doc.o}${mskISO(doc.ts).replace(/-/g, "")}${(doc.h || "").slice(0, 6)}`;
  const esc = (s) => String(s).replace(/([{}\\&%#_$])/g, "\\$1");
  const bib = `@misc{${key},
  author       = {{${esc(o.name)}}},
  title        = {${esc(doc.t)}},
  year         = {${y}},
  month        = {${monthEn.slice(0, 3).toLowerCase()}},
  howpublished = {\\url{${doc.u}}},
  note         = {${doc.te && o.lang !== "en" ? `English (machine translation): ${esc(doc.te)}. ` : ""}${esc(retrieved)}${esc(fp)}. Archived: \\url{${arch}}}
}`;
  const record = JSON.stringify({ outlet: o.name, published: new Date(doc.ts * 1000).toISOString(), title: doc.t,
    title_en_mt: doc.te || undefined, url: doc.u, archive: arch, retrieved: doc.r, fingerprint: doc.h }, null, 2);
  return { APA: apa, Chicago: chicago, BibTeX: bib, [t("cite.record")]: record };
}

let dialog = null;
export function openCite(doc) {
  if (!dialog) {
    dialog = el("dialog", { "aria-labelledby": "cite-h" });
    document.body.append(dialog);
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  }
  const blocks = Object.entries(citations(doc)).map(([label, text]) => {
    const pre = el("pre", {}, text);
    const btn = el("button", { class: "btn copy", type: "button" }, t("cite.copy"));
    btn.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(text); btn.textContent = t("cite.copied"); }
      catch (_) { const r = document.createRange(); r.selectNodeContents(pre); getSelection().removeAllRanges(); getSelection().addRange(r); }
    });
    return el("div", { class: "cite-block" }, el("label", {}, label), pre, btn);
  });
  dialog.replaceChildren(
    el("h2", { id: "cite-h" }, t("cite.title")),
    el("p", { class: "syntax" }, t("cite.note")),
    ...blocks,
    el("form", { method: "dialog" }, el("button", { class: "btn btn-gilt" }, t("cite.close"))),
  );
  dialog.showModal();
}

// ── CSV ─────────────────────────────────────────────────────────────────────
export function downloadCSV(filename, header, rows) {
  const q = (v) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const text = "﻿" + [header, ...rows].map((r) => r.map(q).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = el("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function debounce(fn, ms = 250) {
  let h;
  return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
}
