// Static full-text search over the monthly index shards built by woland/build.py.
//   search/<month>/m.json.gz      {n, days: [[date, firstDoc], …], o: outlet code per document}
//   search/<month>/i/<b>.json.gz  {f: {form: stem}, p: {stem: delta-encoded postings}}
//   search/<month>/k.json.gz      {narrativeIndex: delta-encoded postings}
//   search/<month>/d/<n>.json.gz  documents, 100 per block
// The browser never stems: shards map every word form seen in the corpus to its stem.
import { META, getGz, fromIndex } from "./core.js";
import { norm, tokenize, bucket as shardOf } from "./textkit.js";

export { norm };
const RU_ENDINGS = ["иями", "ями", "ами", "иях", "ях", "ах", "ией", "ей", "ой", "ий", "ый", "ая", "яя", "ое", "ее", "ые", "ие",
  "ых", "их", "ую", "юю", "ов", "ев", "ом", "ем", "ам", "ям", "ия", "ья", "ье", "ьи", "ью", "а", "я", "о", "е", "ы", "и", "у", "ю", "ь"];
const EN_ENDINGS = ["ing", "ies", "ied", "es", "ed", "ly", "s", "'s"];

// English spellings of the same place or name: a search for one finds the others. The English-language
// outlets write "Kiev" and "Kharkov", the machine translations mostly "Kharkiv" and "Zaporizhzhia".
const SPELLINGS = [
  ["kyiv", "kiev"], ["kharkiv", "kharkov"], ["odesa", "odessa"], ["zaporizhzhia", "zaporozhye", "zaporizhia"],
  ["luhansk", "lugansk"], ["donbas", "donbass"], ["mykolaiv", "nikolaev", "nikolayev"], ["dnipro", "dnepr", "dnieper"],
  ["dnipropetrovsk", "dnepropetrovsk"], ["chernihiv", "chernigov"], ["lviv", "lvov"], ["bakhmut", "artemovsk", "artyomovsk"],
  ["zelensky", "zelenskyy", "zelenskiy"], ["kherson", "herson"], ["sumy", "sumi"],
];
const VARIANTS = new Map(SPELLINGS.flatMap((group) => group.map((w) => [w, group.filter((x) => x !== w)])));

const bucket = (s) => shardOf(s, META.search.nb);

function decode(deltas) {
  const out = new Int32Array(deltas.length);
  let acc = 0;
  for (let i = 0; i < deltas.length; i++) { acc += deltas[i]; out[i] = acc; }
  return out;
}
function intersect(a, b) {
  const out = [];
  let i = 0, j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { out.push(a[i]); i++; j++; } else if (a[i] < b[j]) i++; else j++;
  }
  return Int32Array.from(out);
}
function union(a, b) {
  const out = [];
  let i = 0, j = 0;
  while (i < a.length || j < b.length) {
    if (j >= b.length || (i < a.length && a[i] < b[j])) out.push(a[i++]);
    else if (i >= a.length || b[j] < a[i]) out.push(b[j++]);
    else { out.push(a[i]); i++; j++; }
  }
  return Int32Array.from(out);
}
function minus(a, b) {
  const set = new Set(b);
  return a.filter((x) => !set.has(x));
}

/** Parse a query into clauses: [{neg, alts: [[token, …], …]}] — alternatives are ORed, tokens ANDed. */
export function parseQuery(q) {
  const stop = new Set(META.search.stop || []);
  const raw = (q || "").replace(/[«»"“”„]/g, " ").split(/\s+/).filter(Boolean);
  const clauses = [];
  let joinNext = false;
  for (const part of raw) {
    if (part === "OR" || part === "|" || part === "ИЛИ") { joinNext = clauses.length > 0; continue; }
    const neg = part.startsWith("-") && part.length > 1;
    const body = neg ? part.slice(1) : part;
    const prefix = body.endsWith("*");
    const toks = tokenize(body).filter((w) => !stop.has(w));
    if (!toks.length) { joinNext = false; continue; }
    const alt = toks.map((w, i) => ({ w, prefix: prefix && i === toks.length - 1 }));
    const alts = [alt];
    if (toks.length === 1 && !prefix) for (const v of VARIANTS.get(toks[0]) || []) alts.push([{ w: v, prefix: false }]);
    if (joinNext && !neg && clauses.length && !clauses[clauses.length - 1].neg) clauses[clauses.length - 1].alts.push(...alts);
    else clauses.push({ neg, alts });
    joinNext = false;
  }
  return clauses;
}

async function shard(month, b) { return (await getGz(`search/${month}/i/${b}.json.gz`)) || { f: {}, p: {} }; }

/** What a word the corpus has never seen in this exact form might be, most likely first: the word,
 *  the word without a grammatical ending, then shorter cuts (index stems are words minus 0–4 letters). */
function guesses(w) {
  const out = [w];
  const ends = /[а-я]/.test(w) ? RU_ENDINGS : EN_ENDINGS;
  for (const e of ends) if (w.length - e.length >= 3 && w.endsWith(e)) out.push(w.slice(0, -e.length));
  for (let k = 1; k <= 4 && w.length - k >= 4; k++) out.push(w.slice(0, -k));
  return [...new Set(out)];
}

/** Postings of one token in one month, plus the word forms to highlight. */
async function tokenPostings(month, tok, forms) {
  const w = tok.w;
  if (tok.prefix) {
    if (w.length < 4) throw Object.assign(new Error("minchars"), { code: "minchars" });
    const sh = await shard(month, bucket(w));
    const stems = new Set(Object.keys(sh.p).filter((st) => st.startsWith(w)));
    for (const [f, st] of Object.entries(sh.f)) if (f.startsWith(w)) { stems.add(st); forms.add(f); }
    let acc = new Int32Array(0);
    for (const st of stems) {
      const home = bucket(st) === bucket(w) ? sh : await shard(month, bucket(st));
      if (home.p[st]) acc = union(acc, decode(home.p[st]));
      forms.add(st);
    }
    return acc;
  }
  const sh = await shard(month, bucket(w));
  const candidates = [];
  for (const g of guesses(w)) {  // each guess may be a known word form (→ its stem) or itself a stem
    const gs = bucket(g) === bucket(w) ? sh : await shard(month, bucket(g));
    if (gs.f[g]) candidates.push(gs.f[g]);
    candidates.push(g);
  }
  for (const st of candidates) {
    const home = bucket(st) === bucket(w) ? sh : await shard(month, bucket(st));
    if (home.p[st]) {
      forms.add(w);
      forms.add(st);
      for (const [f, s2] of Object.entries(home.f)) if (s2 === st) forms.add(f);
      if (home !== sh) for (const [f, s2] of Object.entries(sh.f)) if (s2 === st) forms.add(f);
      return decode(home.p[st]);
    }
  }
  return new Int32Array(0);
}

async function clausePostings(month, clause, forms) {
  let acc = null;
  for (const alt of clause.alts) {
    let a = null;
    for (const tok of alt) {
      const p = await tokenPostings(month, tok, clause.neg ? new Set() : forms);
      a = a === null ? p : intersect(a, p);
      if (!a.length) break;
    }
    acc = acc === null ? a : union(acc, a);
  }
  return acc || new Int32Array(0);
}

function monthsBetween(from, to) {
  return META.search.months.filter((m) => (!from || m >= from.slice(0, 7)) && (!to || m <= to.slice(0, 7)));
}

/**
 * Run a query. Returns totals, a per-day timeline (hits and all articles under the same filters),
 * per-outlet counts, and the ordered hit list [{month, i}].
 */
export async function search({ q, from, to, outlets, lang, narr, order = "new" }) {
  const clauses = parseQuery(q);
  const positive = clauses.filter((c) => !c.neg);
  const forms = new Set();
  const codes = META.search.codes;
  let allowed = null;
  if (outlets && outlets.size) allowed = new Set([...outlets].map((id) => codes[META.outlets.findIndex((o) => o.id === id)]));
  if (lang) {
    const langCodes = new Set(META.outlets.map((o, i) => (o.lang === lang ? codes[i] : null)).filter(Boolean));
    allowed = allowed ? new Set([...allowed].filter((c) => langCodes.has(c))) : langCodes;
  }
  const months = monthsBetween(from, to);
  const perMonth = await Promise.all(months.map(async (month) => {
    const m = await getGz(`search/${month}/m.json.gz`);
    if (!m || !m.n) return null;
    const dayIdx = m.days.map(([d, s], k) => ({ d, s, e: k + 1 < m.days.length ? m.days[k + 1][1] : m.n }));
    const lo = from ? (dayIdx.find((x) => x.d >= from)?.s ?? m.n) : 0;
    const hiDay = to ? [...dayIdx].reverse().find((x) => x.d <= to) : null;
    const hi = to ? (hiDay ? hiDay.e : 0) : m.n;
    let set;
    if (positive.length) {
      set = null;
      for (const c of positive) {
        const p = await clausePostings(month, c, forms);
        set = set === null ? p : intersect(set, p);
        if (!set.length) break;
      }
    } else {
      set = new Int32Array(Math.max(0, hi - lo)).map((_, k) => lo + k);
    }
    for (const c of clauses.filter((c) => c.neg)) if (set.length) set = minus(set, await clausePostings(month, c, forms));
    if (narr !== null && narr !== undefined && narr !== "") {
      const k = await getGz(`search/${month}/k.json.gz`);
      set = k && k[narr] ? intersect(set, decode(k[narr])) : new Int32Array(0);
    }
    const hits = [];
    const byDay = new Map(), dayTotals = new Map(), byOutlet = new Map();
    for (const x of dayIdx) {
      if ((from && x.d < from) || (to && x.d > to)) continue;
      let tot = 0;
      if (allowed) { for (let i = x.s; i < x.e; i++) if (allowed.has(m.o[i])) tot++; } else tot = x.e - x.s;
      dayTotals.set(x.d, tot);
      byDay.set(x.d, 0);
    }
    let di = 0;
    for (const i of set) {
      if (i < lo || i >= hi) continue;
      if (allowed && !allowed.has(m.o[i])) continue;
      while (di + 1 < dayIdx.length && dayIdx[di + 1].s <= i) di++;
      const d = dayIdx[di].d;
      byDay.set(d, (byDay.get(d) || 0) + 1);
      const oc = codes.indexOf(m.o[i]);
      byOutlet.set(oc, (byOutlet.get(oc) || 0) + 1);
      hits.push(i);
    }
    return { month, hits, byDay, dayTotals, byOutlet };
  }));
  const res = { total: 0, byDay: new Map(), dayTotals: new Map(), byOutlet: new Map(), hits: [], forms, clauses };
  const ordered = perMonth.filter(Boolean).sort((a, b) => (order === "old" ? a.month.localeCompare(b.month) : b.month.localeCompare(a.month)));
  for (const pm of ordered) {
    res.total += pm.hits.length;
    const list = order === "old" ? pm.hits : [...pm.hits].reverse();
    for (const i of list) res.hits.push({ month: pm.month, i });
    for (const [d, v] of pm.dayTotals) res.dayTotals.set(d, v);
    for (const [d, v] of pm.byDay) res.byDay.set(d, v);
    for (const [o, v] of pm.byOutlet) res.byOutlet.set(o, (res.byOutlet.get(o) || 0) + v);
  }
  return res;
}

/** Load the documents for a slice of hits, in order. */
export async function loadDocs(hits) {
  const block = META.search.block;
  const need = new Map();
  for (const h of hits) need.set(`${h.month}/${Math.floor(h.i / block)}`, null);
  await Promise.all([...need.keys()].map(async (k) => {
    const [month, b] = k.split("/");
    need.set(k, await getGz(`search/${month}/d/${b}.json.gz`));
  }));
  return hits.map((h) => {
    const blockDocs = need.get(`${h.month}/${Math.floor(h.i / block)}`);
    const a = blockDocs && blockDocs[h.i % block];
    return a ? fromIndex(a) : null;
  }).filter(Boolean);
}
