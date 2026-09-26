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

- [ ] **Lexicon.** The 24 framings and 21 topics in `config/lexicon.yaml` are a first draft. Matching is
      lexical: articles that quote or rebut a claim count too. Review patterns and add examples; consider
      marking quotations.
- [ ] **Rising words** group word forms by Snowball stem, so unrelated words can merge (Медведев and медведь,
      "bear", share the stem *медвед*). Consider lemmatisation (pymorphy3) for this feature.
- [ ] **Finnish and Swedish** need a native speaker's check: `site/assets/js/i18n.js` and the FI/SV halves of
      `site/method.html` — including the paragraphs added on 25–26 September (sites that refuse
      automated readers, the Internet Archive, *headline only* records, where leads come from) and the
      strings `article.listed` / `article.listed.title`.
- [ ] **Legal**: most of these outlets fall under the EU broadcasting ban. Woland shows headlines, leads
      (≤ 240 characters) and snippets (≤ ~170) for analysis; the README flags this, but it is not legal
      advice.

## 5. Site

- [ ] Outlets page: show how many of each outlet's records are headline only, and a short completeness
      note per outlet (e.g. "TASS Russian: from 24 September, feed only").
- [ ] Outlets page: the coverage legend sits beside the drop-capped lede instead of below it.
