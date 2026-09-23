# Woland — a chronicle of the Russian state press

> *«Рукописи не горят.»* — Manuscripts don't burn.

Woland reads the Russian state and pro-Kremlin press every day, from **1 September 2026** onwards, and keeps
a searchable, citable record of what it published: every headline, its lead, when it appeared, and which
propaganda framings it invokes. It is made for researchers, journalists and activists, and runs entirely on
GitHub: GitHub Actions collects, the repository stores, GitHub Pages publishes.

The website has five chapters (and an interface in English, Finnish and Swedish):

| | Page | What it shows |
|---|---|---|
| I | **Today** — *Black Magic and Its Exposure* | the day's volume, which framings were used and how that compares with the previous weeks, words suddenly rising in headlines, who published what |
| II | **Narratives** — *There Were Doings at Griboyedov's* | one framing or topic over time: overall, by type of outlet, at home vs. abroad, by outlet, outlet × day heatmap, recent examples, and the exact patterns used |
| III | **Archive** — *Manuscripts Don't Burn* | full-text search over every headline and lead (all word forms; English queries also hit machine-translated Russian headlines), timeline, per-outlet counts, CSV export |
| IV | **Outlets** — *Satan's Great Ball* | the 23 outlets: owner, language, EU-blocking status, how Woland reads them, what they lean on, collection health |
| ❦ | **Method** — *Epilogue* | methodology, limitations, citation, data access, legal notes, the full lexicon |

Every article can be opened in the original, in the Internet Archive (important: many of these sites are
blocked in the EU) and cited in APA, Chicago or BibTeX, with a content fingerprint.

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
5. Open the **Actions** tab, pick **Nightly collection** and press **Run workflow**. The first run fills in
   everything since 1 September 2026; it can take a few hours (it stops itself after five and the next run
   carries on where it left off). When it finishes, it publishes the site.
6. The site appears at `https://<you>.github.io/woland/`.

From then on everything is automatic:

| Workflow | When | What |
|---|---|---|
| `collect.yml` — Nightly collection | 04:17 Moscow time | collects the previous day, repairs any gap back to the start date, commits `data/`, rebuilds and publishes the site |
| `poll.yml` — Hourly feeds | every hour | reads the feeds that only hold a few hours of news (TASS, Gazeta.ru, Zvezda, the Kremlin) |
| `deploy.yml` — Build and publish | after the nightly run, and when code changes | builds `_site/` and deploys it to Pages |
| `test.yml` — Tests | on every push | unit tests, including checks that the browser and the indexer tokenise identically |

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
  sitemaps, sitemap indexes, date archive pages or feeds (`config/outlets.yaml`). Each article page is read
  for its metadata and body. Woland identifies itself as `WolandMonitor`, obeys `robots.txt`, pauses between
  requests, and **never** tries to get around JavaScript bot checks or CAPTCHAs: outlets that use them (TASS's
  Russian service, Gazeta.ru, and the Kremlin's article pages) are read through their own public feeds only.
* **Framings** (`config/lexicon.yaml`, `woland/lexicon.py`) — 24 propaganda framings and 21 neutral topics, each
  a list of Russian and English word patterns (`нацист*`, `киевск* режим*`, `сво`). Headlines and leads are
  matched at build time, so lexicon edits apply to the whole archive; full-text matches are recorded when an
  article is collected, with a short snippet as evidence.
* **Translation** (`woland/translate.py`) — Russian headlines are translated to English offline with the
  open Argos Translate / OPUS-MT model through CTranslate2. No API keys, no cost.
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

Other commands: `backfill 2026-09-01 2026-09-10` (a date range), `poll`, `translate`, `probe ria --date 2026-09-23`
(tries one outlet and prints what would be stored). `--outlets ria,tass --limit 20` narrows any run.

**In the EU:** internet providers block many of these domains at the DNS level under the sanctions broadcasting
ban. For local testing you can set `WOLAND_DOH=1`, which resolves names through Cloudflare's DNS-over-HTTPS.
GitHub's runners are in the United States and do not need it. Consider whether this is appropriate for your
own situation.

## Configuration

* **Outlets** — `config/outlets.yaml`. Every source type and option is explained at the top of the file.
  To add an outlet, copy an entry with a similar site structure, then check it with
  `python -m woland probe <id> --date <yesterday>`.
* **Lexicon** — `config/lexicon.yaml`. Headline and lead matches are recomputed for the whole archive at the
  next build. Body-text matches cannot be recomputed for new patterns (the text is not stored); removed or
  narrowed patterns are dropped automatically because stored snippets are re-checked.
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
| `d` | lead / summary, at most 240 characters |
| `s`, `g`, `a` | section, tags (≤ 8), author |
| `w` | words in the body text (0 = the body could not be read) |
| `h` | content fingerprint: first 16 hex digits of SHA-256 over the normalised text |
| `r` | when Woland retrieved it (UTC) |
| `kb` | framings found **only** in the body text, each with a snippet of ≤ ~170 characters |
| `via` | `page` (article page read) or `feed` (outlet's own feed) |

`data/state/coverage.json` records, for every outlet and day, how many articles were stored, how many the
outlet's own listings announced, and whether the day is complete. `data/state/runs.json` keeps the latest
run summaries. The repository grows by roughly 2–3 MB of compressed history a day; after a year or two,
consider moving older years to a release archive.

## Limitations

* Framing detection is lexical. Articles quoting, reporting or rebutting a claim are counted too — every
  number links to the articles so they can be checked.
* Feed-only outlets (TASS Russian, Gazeta.ru, the Kremlin) have partial or headline-level coverage; TASS's
  Russian service starts on the day hourly reading begins, because its feed cannot be read retroactively.
* Regnum answers 403 to every automated request and is disabled. Other sites may start blocking GitHub's
  servers; the Outlets page shows collection health per day.
* Machine translations are serviceable, not authoritative.

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
