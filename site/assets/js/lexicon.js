// The lexicon's matching rules, as in woland/lexicon.py: used to show which words of a headline or lead
// made Woland count an article under a framing or topic. Kept free of browser APIs so the test-suite can
// check that Python and the browser agree.

const W = "[\\p{L}\\p{N}_]";                 // Python's \w
const isWord = (ch) => /[\p{L}\p{N}_]/u.test(ch);
const esc = (s) => s.replace(/[\\^$.*+?()[\]{}|/]/g, "\\$&");

/** Python's normalize(): lower case, ё → е, unified spaces and dashes. */
export function normalize(s) {
  return s.toLowerCase().replace(/ё/g, "е").replace(/ /g, " ").replace(/[‑‐]/g, "-");
}

/** normalize() one UTF-16 unit at a time, so that offsets stay valid in the original text. */
export function normSameLength(s) {
  let out = "";
  for (let i = 0; i < s.length; i++) {
    const n = normalize(s[i]);
    out += n.length === 1 ? n : s[i];
  }
  return out;
}

/** A pattern as a regular expression: * is any ending, ~ up to three words (as in pattern_regex). */
export function patternSource(pattern) {
  const words = normalize(pattern).split(/\s+/).filter(Boolean);
  let src = "";
  words.forEach((w, i) => {
    if (w === "~") {
      src += "(?:\\S+\\s+){0,3}[^\\p{L}\\p{N}_\\s]*";
      return;
    }
    src += w.endsWith("*") ? `${esc(w.slice(0, -1))}${W}*` : esc(w);
    if (i < words.length - 1) src += "[\\s ]+";
  });
  const tail = words[words.length - 1].endsWith("*") ? "" : `(?!${W})`;
  return `(?<!${W})${src}${tail}`;
}

const alternation = (patterns, flags = "gu") => (patterns && patterns.length
  ? new RegExp(patterns.map((p) => `(?:${patternSource(p)})`).join("|"), flags) : null);

function windowEdge(t, i, limit, left) {
  i = Math.max(0, Math.min(t.length, i));
  if (left) while (i > 0 && i < limit && isWord(t[i - 1])) i++;
  else while (i > limit && i < t.length && isWord(t[i])) i--;
  return i;
}

class Group {
  constructor(match, ctx = [], not = []) {
    this.rx = alternation(match);
    this.ctx = alternation(ctx, "u");  // only tested, never iterated: no global state
    this.not = alternation(not);
  }

  /** Every counted match in the normalised text t: [[start, end], …]. */
  all(t, extra, window, firstOnly = false) {
    const out = [];
    const excl = this.not ? [...t.matchAll(this.not)].map((m) => [m.index, m.index + m[0].length]) : [];
    for (const m of t.matchAll(this.rx)) {
      const a = m.index, b = a + m[0].length;
      if (excl.some(([c, d]) => c <= a && b <= d)) continue;
      if (this.ctx) {
        let around = t.slice(0, a) + " ".repeat(b - a) + t.slice(b);
        if (window !== null && window !== undefined) {
          around = around.slice(windowEdge(t, a - window, a, true), windowEdge(t, b + window, b, false));
        }
        if (!this.ctx.test(around) && !(extra && this.ctx.test(extra))) continue;
      }
      out.push([a, b]);
      if (firstOnly) break;
    }
    return out;
  }
}

/**
 * Compile the narratives of meta.json: {ru: [[id, [Group…]], …], en: …}.
 * Context names in `with` are resolved against meta.contexts (which include the topics).
 */
export function compileLexicon(narratives, contexts = {}) {
  const out = { ru: [], en: [] };
  for (const lang of ["ru", "en"]) {
    for (const n of narratives) {
      const pats = (n.patterns && n.patterns[lang]) || [];
      const plain = pats.filter((p) => typeof p === "string");
      const groups = plain.length ? [new Group(plain)] : [];
      for (const p of pats) {
        if (typeof p === "string") continue;
        const ctx = (p.with || []).flatMap((c) => (contexts[c] && contexts[c][lang]) || []);
        groups.push(new Group(p.match, ctx, p.not || []));
      }
      if (groups.length) out[lang].push([n.id, groups]);
    }
  }
  return out;
}

/** narrative id → [start, end] of its first counted occurrence (the Python Lexicon.find). */
export function find(lex, text, lang, extra = "", window = null) {
  const hits = {};
  if (!text) return hits;
  const t = normSameLength(text);
  const e = extra ? normalize(extra) : "";
  for (const [id, groups] of lex[lang] || []) {
    let best = null;
    for (const g of groups) {
      const [span] = g.all(t, e, window, true);
      if (span && (!best || span[0] < best[0])) best = span;
    }
    if (best) hits[id] = best;
  }
  return hits;
}

/** Every counted occurrence of one narrative in text, for highlighting: [[start, end], …] in order. */
export function spans(lex, text, lang, id, extra = "") {
  if (!text) return [];
  const entry = (lex[lang] || []).find(([nid]) => nid === id);
  if (!entry) return [];
  const t = normSameLength(text);
  const e = extra ? normalize(extra) : "";
  return entry[1].flatMap((g) => g.all(t, e, null)).sort((x, y) => x[0] - y[0]);
}
