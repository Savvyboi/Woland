# Woland — a chronicle of the Russian state press

> *«Рукописи не горят.»* — Manuscripts don't burn.

Woland reads the Russian state and pro-Kremlin press every day, from **1 September 2026** onwards, and keeps
a searchable, citable record of what it published: every headline, its lead, when it appeared, and which
propaganda framings its words match. It is made for researchers, journalists and activists, and runs entirely on
GitHub: GitHub Actions collects, the repository stores, GitHub Pages publishes.

The website has five chapters (and an interface in English, Finnish and Swedish):

| | Page | What it shows |
|---|---|---|
| I | **Today** — *Black Magic and Its Exposure* | the last completed day: its volume, which framings its articles matched and how that compares with the previous weeks (beside the usual share), which outlets were not collected, words suddenly rising in headlines (grouped into events), who published what |
| II | **Narratives** — *There Were Doings at Griboyedov's* | one framing or topic over time, on completed days: overall (with the articles and outlets behind every share), by type of outlet, at home vs. abroad, by outlet, outlet × day heatmap (not collected ≠ no articles), optionally only the outlets collected every day; recent examples, the exact patterns and how many of a sample of matches fit the definition |
| III | **Archive** — *Manuscripts Don't Burn* | full-text search over every headline and lead (all word forms; English queries also hit machine-translated Russian headlines and either spelling of place names), active filters as chips, timeline, per-outlet counts, CSV export |
| IV | **Outlets** — *Satan's Great Ball* | the 23 outlets: owner, language, EU-blocking status, how Woland reads them, what is known about gaps, headline-only records, what they lean on, collection day by day, the log of collection runs |
| ❦ | **Method** — *Epilogue* | methodology, limitations, citation, data access, legal notes, the full lexicon |

Every article can be opened in the original, in the Internet Archive (important: many of these sites are
blocked in the EU) and cited in APA, Chicago or BibTeX, with a content fingerprint; its *Details* show how Woland
obtained it and which words made it count under a framing.

---

## Setting it up on GitHub (about ten minutes)

1. **Create a public repository** on GitHub, for example `woland` (GitHub Pages is free for public repositories).
2. **Push this folder** to it:
   ```bash
   git remote add origin https://github.com/<you>/woland.git
   git push -u origin main
   ```
3. In the repository, go to **Settings → Pages** and set **Source: GitHub Actions**.
4. Go to **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, and save.
5. Open the **Actions** tab, pick **Nightly collection** and press **Run workflow**. The repository already
   holds everything collected since 1 September 2026, so this first run only fills the gaps (Sputnik, which
   Finnish networks block, was to be collected from GitHub's servers, but on 27 September 2026 it did not
   answer them either: see `TODO.md`). In a fresh fork
   without `data/`, the first run fills in everything; that takes a few hours (it stops itself after four and
   a half and the next run carries on where it left off). When it finishes, it publishes the site.
6. The site appears at `https://<you>.github.io/woland/`. Run **Check outlets** once to see, from GitHub's
   servers, which outlets can be read.

From then on everything is automatic:

| Workflow | When | What |
|---|---|---|
| `collect.yml` — Nightly collection | 04:17 Moscow time | collects the previous day, looks again at the past week, repairs any older gap back to the start date, commits `data/`, checks it, rebuilds and publishes the site |
| `poll.yml` — Hourly feeds | every hour or so | reads the feeds that only hold a few hours of news (TASS, TASS English, Rossiyskaya Gazeta, Zvezda, the Kremlin); scheduled every 15 minutes because GitHub starts scheduled jobs late or drops them, a run skips its turn when the feeds were read less than 40 minutes before |
| `deploy.yml` — Build and publish | after the nightly run, and when code changes | builds `_site/` and deploys it to Pages |
| `test.yml` — Tests | on every push | the test-suite (see *Tests* below) |
| `check.yml` — Check outlets | Mondays, or by hand | can every outlet still be read from GitHub's servers? A table in the run summary; the run fails if an outlet is broken |

> GitHub suspends scheduled workflows in repositories with no activity for 60 days. Woland commits data every
> day, which counts as activity, but if collection ever stops, re-enable the workflows from the Actions tab.

## How it works

```
  outlets' sitemaps, feeds, date archives
                 │  discover URLs for each Moscow day
                 ▼
  article pages ──► headline, lead, time, section, tags, author, body text
                 │  tag framings (headline, lead, body) · translate Russian headlines offline
                 ▼
  data/articles/YYYY/MM/DD/<outlet>.jsonl        ← committed to the repository every night
                 │  python -m woland build
                 ▼
  _site/: pages + daily digests + time series + a static full-text index  ──►  GitHub Pages
```

* **Collection** (`woland/collect.py`, `discover.py`, `extract.py`) — per outlet, URLs come from date-based
  sitemaps, sitemap indexes, date archive and "show more" listing pages or feeds (`config/outlets.yaml`); for
  older gaps also from the Internet Archive's list of captured pages. Each article page is then read from the
  outlet for its metadata and body. Woland identifies itself as `WolandMonitor`, obeys `robots.txt`, pauses
  between requests, backs off when a site says it is being asked too often, and **never** tries to get around
  bot checks or CAPTCHAs: TASS's Russian service, which refuses automated readers, is read through its own
  public feed only, and so is the Kremlin, whose feed carries the full texts.
* **Framings** (`config/lexicon.yaml`, `woland/lexicon.py`) — 24 propaganda framings and 22 neutral topics, each
  a list of Russian and English word patterns (`нацист*`, `киевск* режим*`, `сво`). A pattern can count only
  *with* a context (`теракт*` only next to words about Ukraine and the war) or *not* inside given phrases
  (`вброс*` but not `вброс* бюллетен*`). Headlines and leads are matched at build time, so lexicon edits apply to
  the whole archive; full-text matches are recorded when an article is collected, with a short snippet as
  evidence. `site/assets/js/lexicon.js` applies the same rules in the browser to show which words matched. A
  random sample of each framing's matches was read in September 2026: [`docs/lexicon-audit.md`](docs/lexicon-audit.md).
* **Translation** (`woland/translate.py`, `woland/glossary.py`) — Russian headlines are translated to English
  offline with the open Argos Translate / OPUS-MT model through CTranslate2. No API keys, no cost. Names and terms
  the model gets wrong (Witkoff, Kallas, the SVO) are corrected by `config/glossary.yaml` when the site is built;
  `data/` keeps the model's own output.
* **Rising words** (`woland/build.py`, `woland/textproc.py`) — headline words grouped by dictionary form
  (pymorphy3 for Russian, Snowball stems otherwise) and, when they share most of their headlines, into one event.
* **The site** (`site/`, `woland/build.py`) — plain HTML, CSS and JavaScript modules; no framework, no build
  tool. Search runs in the browser against a static inverted index sharded by month and by word, so only a
  few small gzip files are downloaded per query. Unchanged months are cached between builds.

## Running it on your own computer

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
.venv/bin/python -m woland collect --catch-up 2     # the last few days
.venv/bin/python -m woland build                    # → _site/
python -m http.server 8000 --directory _site         # open http://localhost:8000
```

Other commands: `backfill 2026-09-01 2026-09-10` (a date range; add `--wayback` for the Internet Archive sources),
`poll`, `translate`, `probe ria --date 2026-09-23` (tries one outlet and prints what would be stored), `check`
(discovers yesterday's articles for every outlet and reads a few: a health table) and `mtcheck` (what the
translation glossary corrects, and translations of its names that still look wrong), `sample enemies-within --seed 3`
(a random sample of a framing's matches to read, as in `docs/lexicon-audit.md`) and `reindex` (rebuilds the URL
index). `--outlets ria,tass --limit 20` narrows any run. Collection runs may work side by side on different
outlets (state files are merged per outlet and day, not overwritten).

### Tests

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q                       # everything offline; Node.js is needed for the site tests
WOLAND_LIVE=1 .venv/bin/python -m pytest -m live -q # also read every outlet for real
```

* `tests/test_discovery.py` — listings, paged feeds, sitemap indexes and Internet Archive lookups, against canned pages
* `tests/test_collect.py` — what is kept or rejected, saving progress, merging state, which days are planned
* `tests/test_site.py` — builds a small site and runs the website's own search and citation code on it in Node
  (word forms, `*`, `-`, `OR`, filters, English queries over corrected translations and either spelling, unique
  BibTeX keys, record ids), checks completed days and coverage codes; checks that every interface string exists in
  English, Finnish and Swedish and that every JavaScript module parses
* `tests/test_data.py` — every record in `data/` is well-formed, filed under the right day and outlet, and unique
* `tests/test_woland.py` — dates, lexicon (contexts, exclusions, and the same matches in Python and the browser),
  the translation glossary, rising-word lemmas, extraction, tokeniser parity between Python and the browser, a build
* `tests/test_live.py` — the real outlets (off unless `WOLAND_LIVE=1`)

**In the EU:** internet providers block many of these domains at the DNS level under the sanctions broadcasting
ban. For local testing you can set `WOLAND_DOH=1`, which resolves names through Cloudflare's DNS-over-HTTPS.
GitHub's runners are in the United States and do not need it. Consider whether this is appropriate for your
own situation.

## Configuration

* **Outlets** — `config/outlets.yaml`. Every source type and option is explained at the top of the file.
  To add an outlet, copy an entry with a similar site structure, then check it with
  `python -m woland probe <id> --date <yesterday>` and `python -m woland check --outlets <id>`.
* **Lexicon** — `config/lexicon.yaml` (the syntax, contexts and exclusions are explained at its top). Headline
  and lead matches are recomputed for the whole archive at the next build. Body-text matches cannot be recomputed
  for new patterns (the text is not stored); removed or narrowed patterns are dropped automatically because stored
  snippets are re-checked. After changing a framing, read a fresh sample of its matches and update its `checked`
  entry (see `docs/lexicon-audit.md`).
* **Translation glossary** — `config/glossary.yaml`: a Russian name or term, what the model writes instead, and
  the right English. Applied at the next build; check with `python -m woland mtcheck`.
* **Outlet notes** — the optional `note` of an outlet in `config/outlets.yaml` (in English, Finnish and Swedish)
  is shown on the Outlets page: what readers should know about its coverage.
* **Start date** — `WOLAND_START` (default `2026-09-01`).
* **Search window** — GitHub Pages sites must stay under 1 GB. The search index is published for the latest
  `WOLAND_SEARCH_MONTHS` months (default 18, roughly 40 MB a month); daily digests and charts always cover
  everything, and all articles remain in `data/`.

## Data

`data/articles/YYYY/MM/DD/<outlet>.jsonl`, one article per line:

| field | meaning |
|---|---|
| `id` | stable id, `<outlet>:<hash of URL>` |
| `o`, `u` | outlet id, URL |
| `p`, `m` | published / modified (ISO 8601, Moscow time) |
| `t`, `te` | headline as published; English machine translation (Russian outlets) |
| `d` | lead: the outlet's own summary or, where it gives none (or only a "read more" stub), the article's opening paragraph; at most 240 characters |
| `s`, `g`, `a` | section, tags (≤ 8), author |
| `w` | words in the body text (0 = the body could not be read) |
| `h` | content fingerprint: first 16 hex digits of SHA-256 over the normalised text |
| `r` | when Woland retrieved it (UTC) |
| `kb` | framings found **only** in the body text, each with a snippet of ≤ ~170 characters |
| `via` | `page` (article page read) or `feed` (from the outlet's own feed, sitemap or listing only: for feed-only outlets always; for the others a *headline-only* record, kept when the page could not be read and completed by a later run) |

`data/state/coverage.json` records, for every outlet and day, how many articles were stored, how many the
outlet's own listings announced, how many are still headline only (`h`), and whether the day is complete.
`data/state/runs.json` keeps the latest run summaries. `data/state/urls/<outlet>.txt` lists every URL stored (a
key and its day), so that an article is stored once even if its site re-dates it months later. An article is always filed under the Moscow day it was published, even when it turned up
while another day was being collected. The repository grows by roughly 2–3 MB of compressed history a day; after a year or two,
consider moving older years to a release archive.

## Limitations

* Framing detection is lexical: the site reports *pattern matches*. Articles quoting, reporting or rebutting a
  claim are counted too — every number links to the articles, and each article shows the words that matched. In a
  check of 25 random matches per framing (three rounds, the last on 28 September 2026), 545 of 600 fit the
  definitions, from 14 of 25 ("Western fakes") to 25 of 25 (`docs/lexicon-audit.md`); that check still needs a
  specialist's review. `python -m woland sample <framing>` draws a fresh sample to read.
* The current day, and the previous one until the nightly run has gathered it, are *still being collected*: the
  site leaves them out of comparisons and averages unless asked, and marks them where they are shown.
* TASS's Russian service is read from its feed only (headline, lead, time) and starts on the day hourly reading
  begins: its pages, sitemaps and even `robots.txt` answer 403, the Internet Archive's copies are the same 403,
  and the feed holds only its latest 100 items (about three hours of a weekday). GitHub starts the hourly job late
  or not at all when it is busy, so hours are missing (listed in TASS's note on the Outlets page); the job is
  therefore scheduled every quarter of an hour and skips the turns it does not need. TASS's English service
  (tass.com) is complete.
* Gazeta.ru sends every visitor through an optional Sber ID sign-in first. Woland holds the cookie that the
  page's own script gives every visitor who is not signed in (`cookies` in `outlets.yaml`) — it declines to sign
  in, like any anonymous reader — and reads the pages in full.
* Zvezda and Komsomolskaya Pravda keep only a day or two in their own listings, so early September 2026 was
  filled in from the Internet Archive's captures (about 70% of Zvezda's and 60% of KP's online news).
  AiF's sitemaps are regenerated only now and then; its paged news list covers the days in between.
* Nothing found is thrown away: when a page cannot be read (the site refuses, asks Woland to slow down, or the
  night's time runs out), the article is kept as its listing or feed describes it — headline, lead if any, time —
  marked *headline only* on the site, and its day stays open so that later runs read the page and complete it.
  MK (which allows about 15 pages a minute; a run spends at most 90 minutes on it) and Rossiyskaya Gazeta (whose
  Qrator shield answers bursts with a CAPTCHA, which Woland never solves; it only slows down) are completed this
  way over several nights.
* Regnum answers 403 to every automated request (robots.txt and feed included) and the Internet Archive only
  has error pages for its news, so it is disabled. Sputnik is blocked from Finnish networks and did not answer
  GitHub's servers either on 27 September 2026; neither did MK, which answers from Finland. A site that does not
  answer is left alone for a quarter of an hour after three failed connections, so that it does not hold up the
  run. Other sites may start blocking; `check.yml` and the Outlets page show it.
* Machine translations are serviceable, not authoritative.

What is still open — data gaps, planned fixes, reviews that need a person — is listed in [`TODO.md`](TODO.md).

## Legal and ethical notes

Several of these outlets fall under the EU broadcasting ban (Council Regulation (EU) 833/2014, art. 2f).
Woland stores and shows headlines, short leads and short snippets, with links, in order to analyse and
document them; it does not republish articles. This is not legal advice — if you run or reuse Woland in the
EU, check the rules that apply to you. Headlines and excerpts remain the property of their publishers.

## Licences and credits

* Code: MIT (see `LICENSE`). Woland's own data (structure, translations, tagging): CC BY 4.0.
* Epigraphs and chapter titles: Mikhail Bulgakov, *The Master and Margarita*.
* Translation model: [Argos Translate](https://github.com/argosopentech/argos-translate) (MIT), trained on OPUS data.
* Typefaces: Cormorant Garamond, PT Serif, PT Sans and PT Mono (SIL Open Font License), via Google Fonts.
