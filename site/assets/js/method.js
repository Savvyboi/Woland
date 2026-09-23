// Epilogue: method, data, citation — plus the full lexicon, generated from the data.
import { $, $$, el, t, tl, META, loadMeta, initChrome, fillFooter, showError } from "./core.js";
import { lang } from "./i18n.js";

initChrome("method");

async function main() {
  const prose = $$("article.prose[data-lang]");
  const mine = prose.find((a) => a.dataset.lang === lang) || prose[0];
  for (const a of prose) a.hidden = a !== mine;
  const url = location.origin + location.pathname.replace(/[^/]*$/, "");
  for (const s of $$(".site-url")) s.textContent = url;
  try {
    await loadMeta();
    fillFooter();
    $("#lexicon-h").textContent = `${t("narratives.framings")} · ${t("narratives.topics")}`;
    const table = el("table", { class: "table-view", style: { fontSize: ".85rem" } },
      el("thead", {}, el("tr", {}, el("th", {}, t("col.framing")), el("th", { style: { textAlign: "left" } }, t("narratives.patterns.ru")),
        el("th", { style: { textAlign: "left" } }, t("narratives.patterns.en")))),
      el("tbody", {}, META.narratives.map((n) => el("tr", {},
        el("td", { style: { verticalAlign: "top" } }, el("a", { href: `narratives.html#${n.id}` }, tl(n.label)),
          el("div", { style: { color: "var(--text-3)", fontSize: ".78rem" } }, n.family === "framing" ? t("col.framing") : t("col.topic"))),
        el("td", { lang: "ru", style: { textAlign: "left", fontFamily: "var(--mono)", fontSize: ".78rem", verticalAlign: "top" } }, (n.patterns.ru || []).join(" · ")),
        el("td", { lang: "en", style: { textAlign: "left", fontFamily: "var(--mono)", fontSize: ".78rem", verticalAlign: "top" } }, (n.patterns.en || []).join(" · "))))));
    $("#lexicon").replaceChildren(el("div", { class: "table-wrap", style: { maxHeight: "none" } }, table));
  } catch (e) {
    showError($("#lexicon"), e);
  }
}
main();
