# Woland — to do

Open work for future sessions, most urgent first. State of the archive when this list was written
(26 September 2026, before the first GitHub run): 159,806 articles from 20 outlets, 1–26 September 2026,
collected by a local backfill from Finland (with `WOLAND_DOH=1` behind the EU DNS block).

| Outlet | Articles | Note |
|---|---:|---|
| RIA, RT (both), Izvestia, Vesti, Lenta, Life, Gazeta.ru, AiF, Parlamentskaya Gazeta, TASS English, Tsargrad, Ukraina.ru, InoSMI, Rossiyskaya Gazeta, the Kremlin (both) | | complete from their own sitemaps and listings |
| MK | 14,343 | 6,324 still *headline only* (MK allows ~15 pages a minute); the nightly runs complete them |
| KP | 5,845 | early September: only what the Internet Archive captured (~60% of online news) |
| Zvezda | 1,765 | early September from the Internet Archive (~70%); **22–23 September missing** |
| TASS (Russian) | 325 | feed only, from 24 September; **25 September ~04:00–22:00 MSK lost** (the local machine slept) |
| Sputnik | 0 | blocked in Finland; to be collected by the GitHub runners |
| Regnum | — | disabled: 403 to everything, including robots.txt and its feed |

## 1. Right after the first push (needs the repository owner)

- [ ] **Settings → Pages → Source: GitHub Actions**, then re-run *Build and publish the site* (the run
      triggered by the push fails until Pages is enabled). The site appears at
      `https://savvyboi.github.io/Woland/`.
- [ ] Run **Check outlets** (Actions → Check outlets → Run workflow). It reads every outlet, disabled ones
      included, from GitHub's servers. Look at the table in the run summary: Sputnik, TASS (Russian),
      Regnum, Rossiyskaya Gazeta and MK behave differently from GitHub than from Finland.
- [ ] Run **Nightly collection** once by hand, or wait for 04:17 Moscow time. The first run should backfill
      Sputnik for September and continue completing MK. Read its summary in `data/state/runs.json` or on
      the Outlets page ("Recent collection runs").
- [ ] Confirm that **Hourly feeds** commits every hour (TASS Russian depends on it).

## 2. Data gaps

- [ ] **Sputnik**: if *Check outlets* shows it working from GitHub, check the first backfill (per-day sitemap
      `sputnikglobe.com/sitemap_article.xml?date_start=…`, same shape as RIA's). If it is blocked there too,
      look for another legitimate source (feeds, the Internet Archive).
- [ ] **TASS (Russian)**: pages, sitemaps and robots.txt answer 403 from Finland, and the Internet Archive's
      copies are 403 pages too. See whether *Check outlets* can read them from GitHub; if the sitemaps
      (`tass.ru/sitemap/sitemap_news*.xml`) are readable there, September could still be discovered, and
      with pages readable it could become a normal page outlet (`fetch: true`). Never get around a bot check.
- [ ] **Regnum**: re-test from GitHub (`python -m woland check --outlets regnum`). If it answers, enable it in
      `config/outlets.yaml` and backfill.
- [ ] **Zvezda 22–23 September**: the Internet Archive had not captured them. The nightly catch-up retries
      (the "thin day" rule in `woland/collect.py: plan()`), with the Internet Archive once these days leave
      the rolling week. If they never appear, note the gap on the Method page.
- [ ] **KP early September**: ~60% of its online news came from the Internet Archive walk. KP's own
      listings reach back only two days, and `/content/api/` is closed by robots.txt. Look for another
      public listing (rubric pages, print issues under `/daily/<issue>/`).
- [ ] **MK**: follow the headline-only count down (`via: "feed"` records in `data/articles/*/*/*/mk.jsonl`).
      If it stalls, the per-run time budget or MK's `rate` (`config/outlets.yaml`, now 4 s) needs tuning.
- [ ] **Tsargrad**: 1–8 September has ~250–470 articles a day against ~650–780 later. Check whether its
      monthly sitemap (`tsargrad.tv/xml/sitemap-2026-9.xml.gz`) is incomplete for early September, and
      whether another listing fills it.
- [ ] **Kremlin**: most September records have no lead (the feed's summary is empty). New records take the
      opening paragraph of the feed's full text; September could be redone by re-reading the paged feed
      (`kremlin.ru/events/all/feed/page/{n}`) with the current `build_record`.
- [ ] **Izvestia**: ~1,500 video items have no text and so no lead. Decide whether to mark video items
      (URL `/…/video/…`) in the data and on the site.

## 3. Engineering

- [ ] **One URL, one record, for good.** Stored URLs are looked up 45 days back (`KNOWN_DAYS` in
      `woland/collect.py`). A page re-dated after longer than that is stored a second time, and
      `tests/test_data.py::test_no_article_is_filed_twice` then fails. Keep a compact per-outlet URL index
      (e.g. `data/state/urls/<outlet>.txt`) instead of reading day files.
- [ ] **Coverage merges per outlet, not per day.** `store.save_coverage(only=…)` replaces an outlet's whole
      entry, so two processes collecting the same outlet on different days can undo each other's day
      entries. Merge per outlet-day.
- [ ] **Headline-only records on "complete" days.** Upgrades happen only for days a run covers; a
      complete day outside the rolling week is never revisited. Let `plan()` reach back to days that still
      hold `via: "feed"` records for page outlets.
- [ ] **Coverage counts for days outside a run's range** (articles filed under another day, upgrades that
      move a record) are not refreshed until a run covers that day.
- [ ] **Per-outlet time budgets.** The nightly budget (270 minutes) is shared: while MK is slow, every night
      runs for the whole budget and the site is published hours later. Give slow outlets their own cap.
- [ ] **Repository size.** September is ~115 MB of JSONL (~45 MB in git). At ~1.5 GB a year, plan to move
      older years into release assets and keep `WOLAND_SEARCH_MONTHS` (default 18) under the Pages 1 GB limit.

## 4. Analysis and content (needs a person with the expertise)

- [ ] **Lexicon review.** A first pass read 25 random matches of each framing (27 September 2026, made by an AI
      assistant): 537 of 600 fit the definitions after the fixes it led to — see `docs/lexicon-audit.md`, with
      every excerpt and verdict in `docs/lexicon-audit-sample.csv`. It needs a specialist's second reading, and
      its "still to do" list: the remaining wordings of the foreign-agent label ("enemies within", 16 of 25),
      Trump's "fake news" and scams ("Western fakes", 17 of 25), the R-280 "Novorossiya" highway, the US P-8
      Poseidon, and whether the "genocide of the Soviet people" memory campaign belongs under "'Genocide' of
      Russians". After changing a framing, read a fresh sample and update its `checked` entry. Matching stays
      lexical: consider marking quotations.
- [ ] **Rising words** now group Russian words by lemma (pymorphy3) and group words that share their headlines
      into events. The English list stays thin (TASS English and RT give ~200 headlines a day): consider a
      longer baseline or a higher threshold for English.
- [ ] **Translation glossary** (`config/glossary.yaml`, 24 entries): run `python -m woland mtcheck` now and then
      and add the names it shows still mistranslated.
- [ ] **Finnish and Swedish** need a native speaker's check: `site/assets/js/i18n.js` and the FI/SV halves of
      `site/method.html` — including the paragraphs added on 25–26 September (sites that refuse automated
      readers, the Internet Archive, *headline only* records, where leads come from), the strings
      `article.listed` / `article.listed.title`, and everything added on 27 September: the Method sections on
      matching, measures, machine translation, searching and citing; the strings for article details, citations,
      completed days, coverage, rising words, archive filters and the collection log; the outlet notes
      (`note` in `config/outlets.yaml`) and the context labels in `config/lexicon.yaml`.
- [ ] **Legal**: most of these outlets fall under the EU broadcasting ban. Woland shows headlines, leads
      (≤ 240 characters) and snippets (≤ ~170) for analysis; the README flags this, but it is not legal
      advice.

## 5. Site

- [ ] **Coverage status of backfilled days.** A backfill that starts on the first day has no earlier days to
      compare with, so `run_collection` marked Zvezda's empty 22–23 September "complete". The site now shows
      such days as not collected (`woland/build.py: coverage_codes`); `collect.py` should compare with the days
      around, not only those before.
- [ ] Load time was not measured. (Phone width was checked on 27 September at 375px: every page fits.)
