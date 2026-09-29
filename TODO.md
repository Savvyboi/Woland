# Woland — to do

Open work for future sessions, most urgent first. State of the archive when this list was last updated
(29 September 2026, late evening): 179,975 articles from 21 outlets, 1–29 September 2026.

| Outlet | Articles | Note |
|---|---:|---|
| RIA, RT (both), Izvestia, Vesti, Lenta, Life, Gazeta.ru, AiF, Parlamentskaya Gazeta, TASS English, Tsargrad, Ukraina.ru, InoSMI, Rossiyskaya Gazeta, the Kremlin (both) | | complete from their own sitemaps and listings |
| MK | 15,678 | GitHub cannot reach it since 27 September: read from the Internet Archive's copies (§1); 5,253 records still *headline only* |
| KP | 7,046 | early September: only what the Internet Archive captured (~60% of online news) |
| Zvezda | 2,086 | early September from the Internet Archive (~70%); **22–23 September missing** |
| TASS (Russian) | 2,364 | feeds only, from 24 September; hours lost on 25–29 September, listed on the Outlets page (§1) |
| Sputnik | 602 | answers neither Finland nor GitHub: some 15–30 a day from the Internet Archive's copies |
| Regnum | — | disabled: 403 to everything, including robots.txt and its feed |

## 1. Collection on GitHub (watch the next runs)

- [ ] **The changes of 29 September** (first runs after the push): Actions upgraded to their Node 24 majors
      (checkout v7, setup-python v7, cache v6, setup-node v7, configure-pages v6, upload-pages-artifact v5,
      deploy-pages v5); every data commit goes through `.github/commit-data.sh`, which configures the merge
      driver (`woland/merge.py`) and pushes with checkout v7's stored credentials; the check commits
      `data/state/check.json`. Look at the first poll, nightly and check runs (the API lists them without a
      token: `https://api.github.com/repos/Savvyboi/Woland/actions/runs`).
- [ ] **Hourly feeds run about every six hours.** On 28–29 September GitHub started the 15-minute schedule about
      four times a day (01:19, 07:00, 13:59, 19:19 UTC on the 29th), and the two runs queued behind the nightly
      run lost their reads: they committed on top of the commit that was current when they were *queued*, and
      the rebase conflicted (fixed: checkout at the branch tip, as `deploy.yml` already did, and the merge
      driver). Decided on 28 September: no outside trigger. Since 29 September TASS is read from its feed for
      news aggregators, which reaches back about twelve hours on a weekday, so a reading every six hours loses
      nothing; the Outlets page lists any hours lost (see §2). If they reappear, reconsider an outside trigger.
- [ ] **MK's backlog from the Internet Archive.** web.archive.org answers GitHub: the nightly run of 28 September
      read 1,189 new articles from the copies and completed 84; that of 29 September 146 new and 987 completed
      (181 pages had no copy yet, retried later). About 5,250 headline-only records remain: some five more
      nights at MK's 90-minute budget. MK stays in the run as it is, so it is read directly again once it answers.
- [ ] The nightly run (01:17 UTC) started at 06:36 and 06:54 UTC on 27–29 September: late runs cost nothing but a
      later site.

## 2. Data gaps

- [ ] **TASS (Russian) pages from GitHub.** The check now also tries, for feed-only outlets, an article page,
      `robots.txt` and the sitemap (report only), and keeps its results in `data/state/check.json`. From
      Finland all three answered 403 — except once, on 29 September, when all three answered 200 and minutes
      later 403 again: TASS's shield lets requests through now and then, which is no invitation. If
      `check.json` shows them readable from GitHub week after week, the sitemaps
      (`tass.ru/sitemap/sitemap_news*.xml`) could fill 24–29 September. Never get around a bot check.
- [ ] **Regnum**: re-tested by the same check (disabled outlets are checked too). If it answers, enable it in
      `config/outlets.yaml` and backfill.
- [ ] **Zvezda 22–23 September**: the Internet Archive had not captured them. Nightly runs retry them (they
      are thin days); if they never appear, note the gap on the Method page (the outlet note says so already).
- [ ] **KP early September**: ~60% of its online news came from the Internet Archive walk. KP's own
      listings reach back only two days, and `/content/api/` is closed by robots.txt. Look for another
      public listing (rubric pages, print issues under `/daily/<issue>/`).
- [ ] **Tsargrad**: 1–8 September has ~250–470 articles a day against ~650–780 later. Check whether its
      monthly sitemap (`tsargrad.tv/xml/sitemap-2026-9.xml.gz`) is incomplete for early September, and
      whether another listing fills it.
- [ ] **Izvestia**: ~1,500 video items have no text and so no lead. Decide whether to mark video items
      (URL `/…/video/…`) in the data and on the site.

Done on 29 September:
- **TASS read from three feeds** (`config/outlets.yaml`): `rss/yandex.xml`, its feed for news aggregators (the
  latest ~650 items, back to 10:00 at 23:00 on a Tuesday, with full texts: everything but sport and science;
  robots.txt allows it), the sport section's (`v2.xml?sections=` + TASS's section id in base64, `MjE3Ng==` =
  2176; others: 22 world, 23 politics, 24 society, 25 economy, 27 incidents, 28 culture; an unknown id returns
  the main feed) and the main feed (100 items, ~3 hours; the only one with science). Framings are now found in
  TASS's texts too. A local reading at 23:20 Moscow time recovered 498 articles of 29 September.
- **Hours lost are listed automatically**: a silence of more than 45 minutes between stored TASS articles (sport
  and science aside) — never seen while the feed was read in time (at most ~27 minutes, at night) — is shown on
  the Outlets page and in the day's coverage note on Today (`gaps` in `outlets.yaml`, `feed_gaps` in `build.py`).
  The hand-kept list in TASS's note is gone.
- **Kremlin leads**: a feed-only outlet's stored articles are completed when a feed describes them better
  (`fill_day`: lead, and text count, fingerprint and body matches if the text was missing). Re-reading the
  Kremlin's paged feeds filled the leads of all 170 September records that had none, and found 5 articles
  that had been missed.

## 3. Engineering

- [ ] **Repository size.** September is ~150 MB of JSONL on disk (13 MB packed in git, plus loose objects), the
      URL index ~5 MB. At ~1.8 GB of JSONL a year, plan to move older years into release assets and keep
      `WOLAND_SEARCH_MONTHS` (default 18) under the Pages 1 GB limit (the September site is 58 MB).
- [ ] **Two runs writing at once** can now merge (`woland/merge.py`), but all data-writing workflows still share
      the `woland-data` concurrency group, so GitHub's own runs never do. If the polls are ever moved to a group
      of their own (so that they read feeds during the nightly run), one rare case is not handled: the same new
      article filed under two different days by the two runs (feed time and page time on either side of
      midnight) would be stored twice, and `tests/test_data.py` would say so after the nightly commit.

Done on 29 September: checkout at the branch tip for the poll and the nightly run (a run queued behind another
committed on a stale base, and its data was lost); a merge driver for data files (`.gitattributes`,
`woland/merge.py`: records by URL, coverage by outlet and day, the URL index by key); all data commits through
`.github/commit-data.sh`; Actions upgraded; the check reads pages as the collector does (from the Internet
Archive's copy when an outlet does not answer), so MK and Sputnik no longer fail it, and commits its results.

## 4. Analysis and content (needs a person with the expertise)

- [ ] **Lexicon review.** Three rounds of reading 25 random matches per framing (27–28 September 2026, by an AI
      assistant): 545 of 600 fit — see `docs/lexicon-audit.md`, every excerpt and verdict in
      `docs/lexicon-audit-sample.csv`. It needs a specialist's second reading, and decisions on its "still to
      do" list: Trump's "fake news" and debunked domestic rumours under "Western fakes" (14 of 25), removals
      from the foreign-agent register, opposite and mirror claims under "Nuclear threats", whether the
      "genocide of the Soviet people" campaign is its own framing. `python -m woland sample <framing> --seed N`
      draws a fresh sample; after changing a framing, read one and update its `checked` entry. TASS's texts are
      matched since 30 September: its body matches were not part of the audited samples.
- [ ] **Translation glossary** (`config/glossary.yaml`, 25 entries): run `python -m woland mtcheck` now and then.
      It reports only the entries' own words; names missing from the glossary have to be spotted in the
      translations. Most "still without it" lines are translations that dropped the word altogether.
- [ ] **Finnish and Swedish** need a native speaker's check: `site/assets/js/i18n.js` and the FI/SV halves of
      `site/method.html` — including the paragraphs added on 25–26 September (sites that refuse automated
      readers, the Internet Archive, *headline only* records, where leads come from), the strings
      `article.listed` / `article.listed.title`, everything added on 27 September (the Method sections on
      matching, measures, machine translation, searching and citing; the strings for article details,
      citations, completed days, coverage, rising words, archive filters and the collection log; the outlet
      notes (`note` in `config/outlets.yaml`) and the context labels in `config/lexicon.yaml`), on 28
      September: `narratives.patterns.note` (the `~`), the Method page's sentence on the chance test for rising
      words, and the MK, Sputnik and TASS notes; and on 29 September: TASS's new note, the Method page's TASS
      paragraph and coverage item, and the strings `today.cov.gaps`, `outlets.gaps`, `outlets.gaps.hint`,
      `outlets.gaps.day`.
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
