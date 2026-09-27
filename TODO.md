# Woland — to do

Open work for future sessions, most urgent first. State of the archive when this list was written
(28 September 2026, after GitHub's first nightly run): 165,796 articles from 21 outlets, 1–28 September 2026.

| Outlet | Articles | Note |
|---|---:|---|
| RIA, RT (both), Izvestia, Vesti, Lenta, Life, Gazeta.ru, AiF, Parlamentskaya Gazeta, TASS English, Tsargrad, Ukraina.ru, InoSMI, Rossiyskaya Gazeta, the Kremlin (both) | | complete from their own sitemaps and listings |
| MK | 14,343 | **nothing since 26 September**: GitHub cannot reach it (below); 6,324 records still *headline only* |
| KP | 6,066 | early September: only what the Internet Archive captured (~60% of online news) |
| Zvezda | 1,936 | early September from the Internet Archive (~70%); **22–23 September missing** |
| TASS (Russian) | 1,163 | feed only, from 24 September; hours lost on 25–27 September (the feed was read too rarely) |
| Sputnik | 0 | no answer from Finland (blocked) nor from GitHub (27 September) |
| Regnum | — | disabled: 403 to everything, including robots.txt and its feed |

## 1. Unreachable outlets and GitHub's schedule (decided 28 September 2026)

- [ ] **MK does not answer GitHub's servers.** On 27 September every connection from GitHub timed out (28
      requests, 34 minutes); from Finland MK answers normally. Decided: accept the gap (MK's note on the Outlets
      page says so), and read its pages as the Internet Archive captured them if that proves viable. MK stays in
      the nightly run, so collection resumes by itself if MK answers again; a host that does not answer now costs
      a few minutes, not half an hour. The weekly *Check outlets* run (Mondays 09:05 Moscow time) shows whether
      the block lasts.
- [ ] **Sputnik answers neither Finland nor GitHub.** Decided: the Internet Archive's copies of its pages if
      viable (the same route as for MK).
- [ ] **Hourly feeds ran five times in twenty hours** on 27 September: GitHub starts scheduled jobs late or drops
      them. The poll is now scheduled every 15 minutes and skips a turn when the feeds were read less than
      40 minutes before (`--min-gap`). Decided: carry on with that, without an outside trigger (a cron service
      calling the `workflow_dispatch` API with a token). Watch TASS for gaps: a poll whose stats show 100 stored
      and none known read a feed that had rolled over.
- [ ] The nightly run (01:17 UTC) started at 06:36 UTC on 27 September. Late runs cost nothing but a later
      site; a nightly run that waits behind a poll is cancelled if another poll is queued meanwhile (GitHub keeps
      one pending run per concurrency group) — the next night catches up.

## 2. Data gaps

- [ ] **TASS (Russian) gaps**: 25 September 04:08–21:09; 26 September 04:25–07:33, 10:55–13:25, 16:19–17:40;
      27 September 11:26–12:18 (Moscow time; listed in TASS's note in `config/outlets.yaml`). The feed holds the
      latest 100 items and cannot be paged. Better than a hand-kept note: when a feed-only outlet's read shares
      no item with what is stored (all 100 new), record the gap in `coverage.json` and show it on the Outlets
      page.
- [ ] **TASS (Russian)**: pages, sitemaps and robots.txt answer 403 from Finland, and the Internet Archive's
      copies are 403 pages too. See whether *Check outlets* can read them from GitHub; if the sitemaps
      (`tass.ru/sitemap/sitemap_news*.xml`) are readable there, September could still be discovered, and with
      pages readable it could become a normal page outlet (`fetch: true`). Never get around a bot check.
- [ ] **Regnum**: re-test from GitHub (`python -m woland check --outlets regnum`). If it answers, enable it in
      `config/outlets.yaml` and backfill.
- [ ] **Zvezda 22–23 September**: the Internet Archive had not captured them. Nightly runs retry them (they
      are thin days); if they never appear, note the gap on the Method page.
- [ ] **KP early September**: ~60% of its online news came from the Internet Archive walk. KP's own
      listings reach back only two days, and `/content/api/` is closed by robots.txt. Look for another
      public listing (rubric pages, print issues under `/daily/<issue>/`).
- [ ] **Tsargrad**: 1–8 September has ~250–470 articles a day against ~650–780 later. Check whether its
      monthly sitemap (`tsargrad.tv/xml/sitemap-2026-9.xml.gz`) is incomplete for early September, and
      whether another listing fills it.
- [ ] **Kremlin**: most September records have no lead (the feed's summary is empty). New records take the
      opening paragraph of the feed's full text; September could be redone by re-reading the paged feed
      (`kremlin.ru/events/all/feed/page/{n}`) with the current `build_record`.
- [ ] **Izvestia**: ~1,500 video items have no text and so no lead. Decide whether to mark video items
      (URL `/…/video/…`) in the data and on the site.

## 3. Engineering

- [ ] **Repository size.** September is ~115 MB of JSONL (~45 MB in git), plus a 4.6 MB URL index
      (`data/state/urls/`, appended to). At ~1.5 GB a year, plan to move older years into release assets and
      keep `WOLAND_SEARCH_MONTHS` (default 18) under the Pages 1 GB limit (the September site is 54 MB).
- [ ] **Actions versions.** The runs warn that `actions/checkout@v4`, `setup-python@v5`, `cache@v4`,
      `configure-pages@v5`, `upload-pages-artifact@v3` and `deploy-pages@v4` target Node 20 (GitHub forces
      them onto Node 24; checkout is at v7 by now). Upgrade them one at a time and watch a run: the
      collection jobs push with checkout's stored credentials. (`runs-on` is pinned to `ubuntu-24.04` since
      `ubuntu-latest` moves to Ubuntu 26 from 19 October 2026.)
- [ ] **The first run with the new code** builds `data/state/urls/<outlet>.txt` for each outlet it collects
      (the index that keeps a URL from being stored twice, now for good rather than 45 days). The data test
      checks it against the day files; `python -m woland reindex` rebuilds it if a run of older code wrote
      articles without it.

Done on 28 September: one URL one record (the URL index); coverage merged per outlet-day; headline-only
records retried until read or gone (also on complete days: `h` in coverage); coverage counted for every day a
run writes to; per-outlet time budgets (`budget`, MK 90 minutes); a host that does not answer is left alone
for 15 minutes after three failed connections; backfilled days judged against the days around them.

## 4. Analysis and content (needs a person with the expertise)

- [ ] **Lexicon review.** Three rounds of reading 25 random matches per framing (27–28 September 2026, by an AI
      assistant): 545 of 600 fit — see `docs/lexicon-audit.md`, every excerpt and verdict in
      `docs/lexicon-audit-sample.csv`. It needs a specialist's second reading, and decisions on its "still to
      do" list: Trump's "fake news" and debunked domestic rumours under "Western fakes" (14 of 25), removals
      from the foreign-agent register, opposite and mirror claims under "Nuclear threats", whether the
      "genocide of the Soviet people" campaign is its own framing. `python -m woland sample <framing> --seed N`
      draws a fresh sample; after changing a framing, read one and update its `checked` entry.
- [ ] **Translation glossary** (`config/glossary.yaml`, 25 entries): run `python -m woland mtcheck` now and then.
      It reports only the entries' own words; names missing from the glossary have to be spotted in the
      translations. Most "still without it" lines are translations that dropped the word altogether.
- [ ] **Finnish and Swedish** need a native speaker's check: `site/assets/js/i18n.js` and the FI/SV halves of
      `site/method.html` — including the paragraphs added on 25–26 September (sites that refuse automated
      readers, the Internet Archive, *headline only* records, where leads come from), the strings
      `article.listed` / `article.listed.title`, everything added on 27 September (the Method sections on
      matching, measures, machine translation, searching and citing; the strings for article details,
      citations, completed days, coverage, rising words, archive filters and the collection log; the outlet
      notes (`note` in `config/outlets.yaml`) and the context labels in `config/lexicon.yaml`), and on 28
      September: `narratives.patterns.note` (the `~`), the Method page's sentence on the chance test for rising
      words, and the MK, Sputnik and TASS notes.
- [ ] **Legal**: most of these outlets fall under the EU broadcasting ban. Woland shows headlines, leads
      (≤ 240 characters) and snippets (≤ ~170) for analysis; the README flags this, but it is not legal
      advice.

## 5. Site

- [ ] **Load time** (measured 28 September from Finland on the live site; sizes compressed): Today ~104 KB and
      loaded in ~1.2 s, Narratives ~145 KB, Outlets ~70 KB; the new build adds ~15 KB (Today ~118 KB). Fonts
      come on top on a first visit: the site asks Google Fonts for 10 styles (20 files in Cyrillic and Latin,
      585 KB), a page uses about seven (~430 KB) — four times the page itself, though `display=swap` shows the
      text at once.
      An archive search downloads ~600 KB (22 files; "Finland": the month's index file and 20 blocks of ~23 KB,
      one per result shown), ~0.6 s here, ~3 s on a slow mobile link. Possible gains: fewer font styles
      (Cormorant 500i/600 and PT Mono appear rarely), smaller search blocks (more files).
