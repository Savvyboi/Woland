// Runs the website's lexicon matching (site/assets/js/lexicon.js) on the texts of tests/test_lexicon_parity.py.
// usage: node lexicon_harness.mjs < '{"narratives": …, "contexts": …, "cases": [{lang, text, extra}, …]}'
// Prints, per text: the first counted match of each narrative (whole text, and with the full-text window of
// 50 characters) and every counted match of each narrative (as highlighted). Offsets are counted in Unicode
// characters, as in Python, not in the UTF-16 units of JavaScript strings.
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const L = await import(pathToFileURL(path.join(here, "..", "..", "site", "assets", "js", "lexicon.js")));

const { narratives, contexts, cases } = JSON.parse(await new Response(process.stdin).text());
const lex = L.compileLexicon(narratives, contexts);

function codePoints(text) {
  const at = new Array(text.length + 1);
  let n = 0;
  for (let i = 0; i <= text.length; i++) {
    at[i] = n;
    const c = text.charCodeAt(i);
    if (!(c >= 0xd800 && c <= 0xdbff && i + 1 < text.length)) n++;
  }
  return ([a, b]) => [at[a], at[b]];
}

const out = cases.map(({ lang, text, extra = "" }) => {
  const cp = codePoints(text);
  const conv = (hits) => Object.fromEntries(Object.entries(hits).map(([id, s]) => [id, cp(s)]));
  const ids = [...new Set((lex[lang] || []).map(([id]) => id))];
  const all = {};
  for (const id of ids) {
    const s = L.spans(lex, text, lang, id, extra);
    if (s.length) all[id] = s.map(cp);
  }
  return { find: conv(L.find(lex, text, lang, extra)), window: conv(L.find(lex, text, lang, extra, 50)), spans: all };
});
console.log(JSON.stringify(out));
