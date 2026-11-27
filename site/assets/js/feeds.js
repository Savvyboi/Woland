// The feed builder: a dialog that shows the Atom feed of what is on screen (a framing, an outlet, a country),
// lets the reader pick any other, copy its address, and download whole groups of feeds as OPML subscription
// lists. Everything comes from data/feeds.json, which woland/build.py (write_feeds, write_opml) writes with
// the feeds themselves, so every address shown exists.
import { el, t, tl, getJSON, fmtInt, outlet, narrative, GROUPS } from "./core.js";
import { lang, LOCALES } from "./i18n.js";

const KINDS = ["framing", "topic", "outlet", "country", "search"];
let catalog = null;
let dialog = null;

function load() {
  catalog = catalog || getJSON("feeds.json").catch(() => null);
  return catalog;
}

let regionNames = null;
function regionName(code, fallback) {
  try {
    regionNames = regionNames || new Intl.DisplayNames([LOCALES[lang] || "en-GB"], { type: "region" });
    return regionNames.of(code) || fallback;
  } catch (_) { return fallback; }
}

/** The feeds of one kind, sorted by label: [{kind, id, path, label, n}]. Framings and topics share the
 *  framing feeds and are told apart by family. */
export function feedsOf(feeds, kind) {
  const f = feeds?.feeds || {};
  const src = kind === "topic" ? "framing" : kind;
  let rows = Object.entries(f[src] || {}).map(([id, n]) => ({ kind: src, id, n, path: `feeds/${src}/${id}.xml` }));
  if (src === "framing") rows = rows.filter((r) => narrative(r.id) && narrative(r.id).family === (kind === "topic" ? "topic" : "framing"));
  const label = {
    framing: (id) => tl(narrative(id).label),
    outlet: (id) => outlet(id).name,
    country: (id) => regionName(id, (feeds.countries || {})[id] || id),
    search: (id) => tl((feeds.searches || []).find((s) => s.id === id)?.label || id),
  }[src];
  return rows.map((r) => ({ ...r, label: label(r.id) })).sort((a, b) => a.label.localeCompare(b.label, LOCALES[lang]));
}

const absolute = (path) => new URL(path, location.href).href;

function bundleLabel(b) {
  if (b.group) return t("feeds.bundle.group", { group: t(`group.${b.group}`) });
  return t(`feeds.bundle.${b.id}`);
}

/** Open the feed builder with `pick` ({kind, id}) chosen, if it has a feed. */
export async function openFeeds(pick = null) {
  if (!dialog) {
    dialog = el("dialog", { class: "feeds-dialog", "aria-labelledby": "feeds-h" });
    document.body.append(dialog);
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  }
  const feeds = await load();
  const close = el("form", { method: "dialog" }, el("button", { class: "btn btn-gilt" }, t("cite.close")));
  if (!feeds) {
    dialog.replaceChildren(el("h2", { id: "feeds-h" }, t("feeds.title")), el("p", {}, t("feeds.none")), close);
    dialog.showModal();
    return;
  }
  if (pick?.kind === "framing" && narrative(pick.id)?.family === "topic") pick = { ...pick, kind: "topic" };
  const kinds = KINDS.filter((k) => feedsOf(feeds, k).length);
  let kind = pick && kinds.includes(pick.kind) ? pick.kind : kinds[0];
  const kindSel = el("select", { id: "feeds-kind" }, kinds.map((k) => el("option", { value: k, selected: k === kind }, t(`feeds.kind.${k}`))));
  const itemSel = el("select", { id: "feeds-item" });
  const url = el("input", { id: "feeds-url", type: "text", readonly: true, spellcheck: "false" });
  const copy = el("button", { class: "btn copy", type: "button" }, t("cite.copy"));
  const open = el("a", { class: "feeds-open", type: "application/atom+xml", target: "_blank", rel: "noopener" }, `${t("feeds.open")} ↗`);
  const count = el("small", { class: "feeds-n" });

  const fillItems = (want) => {
    const rows = feedsOf(feeds, kind);
    itemSel.replaceChildren(...rows.map((r) => el("option", { value: r.id, selected: r.id === want }, r.label)));
    if (!rows.some((r) => r.id === want)) itemSel.selectedIndex = 0;
    show();
  };
  const show = () => {
    const r = feedsOf(feeds, kind).find((x) => x.id === itemSel.value);
    if (!r) return;
    url.value = absolute(r.path);
    open.href = r.path;
    count.textContent = t("feeds.n", { n: fmtInt(r.n), days: fmtInt((feeds.days || []).length) });
    copy.textContent = t("cite.copy");
  };
  kindSel.addEventListener("change", () => { kind = kindSel.value; fillItems(null); });
  itemSel.addEventListener("change", show);
  url.addEventListener("focus", () => url.select());
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(url.value); copy.textContent = t("cite.copied"); }
    catch (_) { url.focus(); url.select(); }
  });
  fillItems(pick && pick.kind === kind ? pick.id : null);

  const order = (b) => ["all", "framings", "topics", "outlets"].indexOf(b.id) + 1 || (b.group ? 5 + GROUPS.indexOf(b.group) : 20);
  const bundles = (feeds.bundles || []).slice().sort((a, b) => order(a) - order(b) || a.id.localeCompare(b.id));
  dialog.replaceChildren(
    el("h2", { id: "feeds-h" }, t("feeds.title")),
    el("p", { class: "syntax" }, t("feeds.about", { n: fmtInt(feeds.entries || 40), days: fmtInt((feeds.days || []).length || 7) })),
    el("div", { class: "feeds-pick" },
      el("label", { class: "field", for: "feeds-kind" }, t("feeds.kind"), kindSel),
      el("label", { class: "field", for: "feeds-item" }, t("feeds.item"), itemSel)),
    el("div", { class: "feeds-url" }, el("label", { for: "feeds-url" }, t("feeds.url")), url, el("div", { class: "feeds-act" }, copy, open, count)),
    el("h3", {}, t("feeds.bundles")),
    el("p", { class: "syntax" }, t("feeds.bundles.about")),
    el("ul", { class: "feeds-bundles" }, bundles.map((b) => el("li", {},
      el("a", { href: b.path, download: `woland-${b.id}.opml`, type: "text/x-opml" }, bundleLabel(b)),
      el("small", {}, ` ${t("feeds.bundle.n", { n: fmtInt(b.n) })}`)))),
    close,
  );
  dialog.showModal();
}

/** A button that opens the feed builder on `pick()` (a function, so that it reads the page's state when
 *  pressed). */
export function feedButton(pick = () => null, label = null) {
  const b = el("button", { type: "button", class: "btn feeds-btn", "aria-haspopup": "dialog" }, label || t("feeds.button"));
  b.addEventListener("click", () => openFeeds(pick()));
  return b;
}

/** A link to one feed that opens the feed builder on it; without scripts, or opened in a new tab, it is the
 *  feed itself. */
export function feedLink(kind, id, label, attrs = {}) {
  const src = kind === "topic" ? "framing" : kind;
  const a = el("a", { href: `feeds/${src}/${id}.xml`, type: "application/atom+xml", "aria-haspopup": "dialog", ...attrs }, label);
  a.addEventListener("click", (e) => {
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
    e.preventDefault();
    openFeeds({ kind, id });
  });
  return a;
}
