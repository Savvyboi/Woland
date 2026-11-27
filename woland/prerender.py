"""What a page shows before its scripts run: the Today page's summary of the latest complete day, written into
index.html when the site is built, and the title, description and preview image that link previews (Signal,
Mastodon, Bluesky, Slack), search engines and web archives read.

The site's pages fill themselves in from data/ with JavaScript; without it they showed only "Consulting the
archive". The summary is in English (the pages' own language before a script picks the reader's), built from
the same digest and the same interface strings (site/assets/js/i18n.js) as the page; today.js replaces it
when it has loaded the day."""
from __future__ import annotations

import json
import re
from datetime import date
from html import escape, unescape
from math import sqrt
from pathlib import Path

CARD = "assets/img/og-card.png"  # 1200 × 630 (tools/og_card.py)
RISING_SHOWN = 5


def en_strings(i18n_js: Path) -> dict[str, str]:
    """The English interface strings of site/assets/js/i18n.js."""
    src = i18n_js.read_text(encoding="utf-8")
    block = src[src.index("\n  en: {"):src.index("\n  fi: {")]
    return {k: json.loads(f'"{v}"') for k, v in re.findall(r'"([\w.-]+)":\s*"((?:[^"\\]|\\.)*)"', block)}


def fill(template: str, **values) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), template)


# Numbers and days as the page writes them in English (core.js: fmtInt, fmtPct, fmtDay, delta)
def fmt_int(n: float) -> str:
    return f"{round(n or 0):,}"


def fmt_small(x: float | None) -> str:
    """today.js fmtN: "<1" for a fraction of one."""
    return "–" if x is None else "<1" if 0 < x < 1 else fmt_int(x)


def fmt_pct(x: float | None, digits: int | None = None) -> str:
    if x is None:
        return "–"
    d = digits if digits is not None else (2 if x < 0.01 else 1 if x < 0.1 else 0)
    return f"{x * 100:.{d}f}%"


def fmt_day(iso: str, long: bool = False) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%A} {d.day} {d:%B %Y}" if long else f"{d.day} {d:%b %Y}"


def notable(r: dict, total: int) -> bool:
    """today.js notable(): at least ten articles and far beyond the usual share (3 s.d. above a Poisson
    expectation), so that a small framing's large percentage change is not presented as news."""
    if r.get("base") is None or r["n"] < 10:
        return False
    e = r["base"] * total
    return (r["n"] - e) / sqrt(e) >= 3 and r["n"] >= 1.25 * e if e > 0 else True


def rise(r: dict) -> float:
    return float("inf") if not r["base"] else r["share"] / r["base"] - 1


def summary(dg: dict, day: str, open_day: bool, labels: dict[str, str], families: dict[str, str],
            outlets: dict[str, str], s: dict[str, str], examples: dict | None = None) -> dict:
    """The facts both the page and its link preview give: totals, rising framings, top framing, top stories."""
    framings = [r for r in dg["narratives"] if families.get(r["id"]) == "framing"]
    publishing = sum(1 for v in dg["totals"].values() if v > 0)
    base_days = max(0, (dg.get("days") or 1) - 1)
    rising = [] if open_day or base_days < 7 else \
        sorted((r for r in framings if notable(r, dg["total"])), key=rise, reverse=True)[:3]
    top = max(framings, key=lambda r: r["n"], default=None)
    stories = []
    for side in ("ru", "en"):
        for item in (dg.get("rising") or {}).get(side) or []:
            ex = item.get("ex") or {}
            if ex.get("t") and len([x for x in stories if x["side"] == side]) < (RISING_SHOWN if side == "ru" else 3):
                stories.append({"side": side, "words": item.get("w", ""), "n": item.get("n", 0), "base": item.get("base"),
                                "t": ex["t"], "te": ex.get("te", ""), "u": ex.get("u", ""),
                                "outlet": outlets.get(ex.get("o", ""), ex.get("o", ""))})
    if not stories and examples:  # no rising words (too little history): a headline of each top framing
        for r in sorted(framings, key=lambda r: r["n"], reverse=True):
            shown = {st["u"] for st in stories}
            ex = next((e for e in examples.get(r["id"]) or [] if e.get("t") and e.get("u") not in shown), None)
            if r["n"] and ex and len(stories) < RISING_SHOWN:
                stories.append({"side": "framing", "words": labels[r["id"]], "n": r["n"], "base": None,
                                "t": ex["t"], "te": ex.get("te", ""), "u": ex.get("u", ""),
                                "outlet": outlets.get(ex.get("o", ""), ex.get("o", ""))})
    return {"day": day, "open": open_day, "total": dg["total"], "framed": dg.get("framed", 0),
            "publishing": publishing, "base_days": base_days, "rising": rising,
            "top": top if top and top["n"] else None, "stories": stories, "labels": labels, "s": s}


def lede(x: dict) -> str:
    s, labels = x["s"], x["labels"]
    text = fill(s["today.lede"], day=fmt_day(x["day"], True), total=fmt_int(x["total"]), outlets=fmt_int(x["publishing"]),
                framed=fmt_pct(x["framed"] / x["total"] if x["total"] else 0, 0))
    if x["open"]:
        more = s["today.lede.open"]
    elif x["base_days"] < 7:
        more = s["today.lede.norising"]
    elif x["rising"]:
        items = [f"{labels[r['id']]} ({fill(s['today.lede.item'], n=fmt_int(r['n']), share=fmt_pct(r['share']), base=fmt_pct(r['base']))})"
                 for r in x["rising"]]
        listed = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
        more = fill(s["today.lede.rising.one" if len(items) == 1 else "today.lede.rising"], n=x["base_days"], list=listed)
    else:
        more = fill(s["today.lede.steady"], n=x["base_days"])
    return f"{text} {more}"


def today_html(x: dict) -> str:
    """The Today page's summary, in the page's own classes; today.js replaces it."""
    s, labels = x["s"], x["labels"]
    tiles = [(s["today.tiles.articles"], "today.tiles.articles", fmt_int(x["total"]), ""),
             (s["today.tiles.outlets"], "today.tiles.outlets", fmt_int(x["publishing"]), ""),
             (s["today.tiles.framed"], "today.tiles.framed", fmt_pct(x["framed"] / x["total"] if x["total"] else 0, 0),
              fill(s["today.tiles.framed.note"], n=fmt_int(x["framed"])))]
    if x["top"]:
        top = x["top"]
        tiles.append((s["today.tiles.top"], "today.tiles.top",
                      f'<a href="narratives.html#{escape(top["id"])}">{escape(labels[top["id"]])}</a>',
                      f"{fmt_int(top['n'])} · {fmt_pct(top['share'])}"))
    out = ['<div class="prerender">',
           f'<p class="lede">{escape(lede(x))} <a href="method.html#matching">{escape(s["today.lede.how"])}</a></p>',
           '<div class="tiles">']
    for label, key, value, note in tiles:
        value = value if value.startswith("<a ") else escape(value)
        out.append(f'<div class="tile"><div class="label" data-i18n="{key}">{escape(label)}</div>'
                   f'<div class="value">{value}</div>' + (f'<div class="note">{escape(note)}</div>' if note else "") + "</div>")
    out.append("</div>")
    rising = [st for st in x["stories"] if st["side"] != "framing"]
    if x["stories"] and not rising:
        out.append(f'<section class="section"><div class="section-head"><h2 data-i18n="today.examples">{escape(s["today.examples"])}</h2>'
                   '</div><ul class="prerender-stories">')
    elif x["stories"]:
        out.append(f'<section class="section"><div class="section-head"><h2 data-i18n="today.rising">{escape(s["today.rising"])}</h2>'
                   f'<span class="hint" data-i18n="today.rising.hint">{escape(s["today.rising.hint"])}</span></div><ul class="prerender-stories">')
    if x["stories"]:
        for st in x["stories"]:
            lang = "en" if st["side"] == "en" or (st["side"] == "framing" and not st["te"]) else "ru"
            head = f'<a href="{escape(st["u"])}" lang="{lang}">{escape(st["t"])}</a>' if st["u"] else f'<span lang="{lang}">{escape(st["t"])}</span>'
            tr = f'<br><span class="tr">{escape(st["te"])}</span>' if st["te"] and lang == "ru" else ""
            usual = (fill(s["today.rising.explain"], n=fmt_int(st["n"]), base=fmt_small(st["base"])) if st["side"] != "framing"
                     else f"{fmt_int(st['n'])} {s['col.articles'].lower()}")
            out.append(f'<li><b>{escape(st["words"])}</b> · {escape(usual)}'
                       f'<br>{head} <small>{escape(st["outlet"])}</small>{tr}</li>')
        out.append("</ul></section>")
    out.append(f'<noscript><p class="notice" data-i18n="noscript">{escape(s["noscript"])}</p></noscript>')
    out.append("</div>")
    return "\n".join(out)


def description(x: dict) -> str:
    """One or two sentences for link previews and search results."""
    text = (f"{fmt_day(x['day'])}: {fmt_int(x['total'])} articles from {x['publishing']} Russian state and pro-Kremlin "
            f"outlets; {fmt_pct(x['framed'] / x['total'] if x['total'] else 0, 0)} match a propaganda framing.")
    if x["rising"]:
        text += " Rising: " + ", ".join(x["labels"][r["id"]] for r in x["rising"]) + "."
    elif x["top"]:
        text += f" Most used: {x['labels'][x['top']['id']]}."
    return text


def social_tags(title: str, desc: str, url: str, image: str) -> str:
    """Open Graph and Twitter card tags (og:type and the site's default description are in the head partial)."""
    tags = [("property", "og:site_name", "Woland"), ("property", "og:title", title),
            ("property", "og:description", desc), ("name", "twitter:card", "summary_large_image"),
            ("name", "twitter:title", title), ("name", "twitter:description", desc),
            ("property", "og:image", image), ("property", "og:image:width", "1200"),
            ("property", "og:image:height", "630"),
            ("property", "og:image:alt", "Woland: a chronicle of the Russian state press"),
            ("name", "twitter:image", image)]
    if url:
        tags.append(("property", "og:url", url))
    return "".join(f'<meta {a}="{k}" content="{escape(v)}">\n' for a, k, v in tags)


def set_meta(html: str, attr: str, key: str, value: str) -> str:
    """Replace the content of an existing <meta> (the head partial's defaults)."""
    rx = re.compile(rf'<meta {attr}="{re.escape(key)}" content="[^"]*">')
    return rx.sub(lambda _: f'<meta {attr}="{key}" content="{escape(value)}">', html, count=1)


def page_tags(html: str, page: str, base_url: str) -> str:
    """Every page: absolute og:url and preview image where the site's address is known, and its title for
    og:title (the head partial's og:title stays as the site's name where a page has no title of its own)."""
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    title = title.group(1).strip() if title else "Woland"
    desc = re.search(r'<meta name="description" content="([^"]*)">', html)
    desc = desc.group(1) if desc else ""
    base = base_url.rstrip("/")
    url = f"{base}/{'' if page == 'index.html' else page}" if base else ""
    image = f"{base}/{CARD}" if base else CARD
    html = re.sub(r'<meta property="og:(title|description)" content="[^"]*">\n?', "", html)
    return html.replace("</head>", social_tags(unescape(title), unescape(desc), url, image) + "</head>", 1)


def apply_today(index: Path, x: dict, base_url: str) -> None:
    """Write the summary and the day's title and description into the built index.html."""
    html = index.read_text(encoding="utf-8")
    title = f"Woland — {fmt_day(x['day'])}: today in the Russian state press"
    desc = description(x)
    html = re.sub(r"<title>.*?</title>", f"<title>{escape(title)}</title>", html, count=1, flags=re.S)
    html = set_meta(html, "name", "description", desc)
    for key, value in (("og:title", title), ("og:description", desc), ("twitter:title", title), ("twitter:description", desc)):
        html = set_meta(html, "property" if key.startswith("og:") else "name", key, value)
    loading = re.compile(r'(<div id="today">)<p class="loading"[^>]*>.*?</p>(</div>)', re.S)
    html, n = loading.subn(lambda m: m.group(1) + today_html(x) + m.group(2), html, count=1)
    if not n:
        raise ValueError("index.html: no <div id=\"today\"> holding the loading message")
    index.write_text(html, encoding="utf-8", newline="\n")
