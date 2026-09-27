// Epilogue: method, data, citation — plus the full lexicon, generated from the data.
import { $, $$, el, t, tl, META, loadMeta, initChrome, fillFooter, showError, fmtInt, fmtDay } from "./core.js";
import { lang } from "./i18n.js";

initChrome("method");

/** A narrative's patterns in one language: plain ones, then each conditional group with its conditions. */
function patterns(n, l) {
  const pats = n.patterns?.[l] || [];
  const plain = pats.filter((p) => typeof p === "string");
  const groups = pats.filter((p) => typeof p !== "string");
  return [
    plain.length ? el("div", {}, plain.join(" · ")) : null,
    ...groups.map((g) => {
      const conds = [];
      if (g.with?.length) conds.push(t("pattern.with", { list: g.with.map((c) => tl(META.contexts?.[c]?.label) || c).join(", ") }));
      if (g.not?.length) conds.push(t("pattern.not", { list: g.not.join(" · ") }));
      return el("div", { class: "group" }, g.match.join(" · "), el("small", { lang }, ` — ${conds.join("; ")}`));
    }),
  ];
}

async function main() {
  const prose = $$("article.prose[data-lang]");
  const mine = prose.find((a) => a.dataset.lang === lang) || prose[0];
  for (const a of prose) a.hidden = a !== mine;
  // the page holds every language: only the one shown carries the anchors (method.html#matching …)
  for (const a of mine.querySelectorAll("[data-anchor]")) a.id = a.dataset.anchor;
  if (location.hash) document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();
  const url = location.origin + location.pathname.replace(/[^/]*$/, "");
  for (const s of $$(".site-url")) s.textContent = url;
  try {
    await loadMeta();
    fillFooter();
    for (const a of $$(".repo-link")) { if (META.repo) a.href = `${META.repo}/blob/main/${a.dataset.path}`; }
    $("#lexicon-h").textContent = `${t("narratives.framings")} · ${t("narratives.topics")}`;
    const cell = { textAlign: "left", fontFamily: "var(--mono)", fontSize: ".78rem", verticalAlign: "top" };
    const table = el("table", { class: "table-view lexicon-table", style: { fontSize: ".85rem" } },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, t("col.framing")),
        el("th", { scope: "col", style: { textAlign: "left" } }, t("narratives.patterns.ru")),
        el("th", { scope: "col", style: { textAlign: "left" } }, t("narratives.patterns.en")),
        el("th", { scope: "col", style: { textAlign: "left" } }, t("col.checked")))),
      el("tbody", {}, META.narratives.map((n) => el("tr", {},
        el("th", { scope: "row", style: { verticalAlign: "top", textAlign: "left" } }, el("a", { href: `narratives.html#${n.id}` }, tl(n.label)),
          el("div", { style: { color: "var(--text-3)", fontSize: ".78rem", fontWeight: 400 } }, n.family === "framing" ? t("col.framing") : t("col.topic"))),
        el("td", { lang: "ru", style: cell }, patterns(n, "ru")),
        el("td", { lang: "en", style: cell }, patterns(n, "en")),
        el("td", { style: { textAlign: "left", verticalAlign: "top", fontSize: ".78rem" } },
          n.checked?.n ? t("method.checked.cell", { fit: fmtInt(n.checked.fit), n: fmtInt(n.checked.n), date: fmtDay(n.checked.date) })
            : n.family === "framing" ? t("method.unchecked.cell") : "")))));
    $("#lexicon").replaceChildren(el("div", { class: "table-wrap", style: { maxHeight: "none" } }, table));
  } catch (e) {
    showError($("#lexicon"), e);
  }
}
main();
