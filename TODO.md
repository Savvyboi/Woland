# Woland — to do

Open work for future sessions, most urgent first. State of the archive when this list was last updated
(10 October 2026, night): 262,268 articles from 23 outlets, 1 September – 9 October 2026.

| Outlet | Articles | Note |
|---|---:|---|
| RIA, RT (both), Izvestia, Vesti, Lenta, Life, Gazeta.ru, AiF, Parlamentskaya Gazeta, TASS English, Tsargrad, Ukraina.ru, InoSMI, Rossiyskaya Gazeta, the Kremlin (both) | | complete from their own sitemaps and listings |
| MK | 21,269 | did not answer GitHub 27–29 September and on 2, 3, 6 and 9 October: read from the Internet Archive's copies those nights (4,608 records); answers on the other nights; no headline-only records left |
| KP | 11,013 | early September: only what the Internet Archive captured (~60% of online news) |
| Zvezda | 3,367 | early September and 21–23 September from the Internet Archive (~70% of early September) |
| TASS (Russian) | 13,483 | feeds only, from 24 September; hours lost are listed on the Outlets page; its fullest feed refuses GitHub more often than not since 8 October (§1) |
| Sputnik | 791 | answers neither Finland nor GitHub: some 15–30 a day from the Internet Archive's copies |
| Regnum | 2,387 | feed only since 29 September, ~210 a day; its pages answered GitHub in the check of 5 October (§2) |

## 1. Collection on GitHub (watch the next runs)

- [ ] **TASS's feed for news aggregators refuses GitHub more often than not** (since 8 October). It failed
      unreported on 7–8 October (readings found ~170 items in TASS's feeds instead of ~800, because a source
      only reported an error when *all* its feeds failed; fixed on 9 October, `SourcePartial` in `discover.py`).
      Reported since: `rss/yandex.xml` answered 403 in 3 of the 5 readings of 9 October (the nightly run, 16:31
      and 21:12 UTC) while the main and sport feeds answered, and ~7 hours were lost (12:32–17:57 and
      20:08–21:40 Moscow time: 818 articles that day against ~1,200; from 12:30 to 18:00 only 46, 35 of them
      sport, against 447 on 7 October). On 10 October every TASS feed answered 403 to Finland. From 10 October
      six section feeds are read as well (world, politics, society, economy, incidents, culture: 87% of what
      was lost on 9 October), which reach back further than the main feed's three hours. Watch the next runs:
      do the section feeds answer GitHub, and how far back do they reach? Their items come without the full
      text unless the aggregator feed answers within about twelve hours (framings in headline and lead only).
      The army, space and regional sections have no feed of their own that Woland knows of (an unknown
      `sections=` id gives the main feed).
- [ ] **Hourly feeds run every three to seven hours** (4–6 polls a day, 30 September – 9 October). Decided on 28
      September: no outside trigger; reconsider now that TASS's fullest feed refuses (above): with only the main
      feed's three hours, TASS loses hours at every longer interval. The decision is the user's.
- [ ] The nightly run (01:17 UTC) starts at 06:30–07:35 UTC and takes 70–100 minutes when MK answers (its
      90-minute cap dominates; 18 minutes on 9 October, when MK did not answer), the site build ~10 more: late
      runs cost nothing but a later site. Translating leads as well (from 9 October) made each outlet's reading
      ~40–70% longer (the runner's four processors are shared with the translation: Gazeta.ru 16 minutes
      instead of 10, RIA 18 instead of 15), which only matters on a night MK does not fill.

Done on 30 September – 9 October:
- **The changes of 29 September worked**: every nightly run and poll since has succeeded, the site was rebuilt
  after each nightly run, and `tests/test_data.py` passed each time.
- **MK answers GitHub** on most nights (not on 29 September, 2, 3 or 6 October, when its pages were read from the
  Internet Archive's copies): its note (en/fi/sv), the README and the Method page say so now. Its 5,253
  headline-only records were all completed by 8 October.
- AiF's feed, sitemap and news listing all answered 404 one night (30 September; nothing new from AiF that
  night) and its sitemap once answered 502 (5 October); the next nights caught up.

## 2. Data gaps

- [ ] **Regnum's pages answered GitHub** in the check of 5 October (article page, `robots.txt` and sitemap: 200;
      on 29 September all 403; from Finland still 403). If the next checks (Mondays) confirm it, decide whether
      to read its pages from GitHub as for the other outlets (`fetch: true`, `article`, a sitemap source): full
      texts, so framings in the body too, and a backfill of its sitemaps for September. Not decided: a site that
      answers is not refusing, but Finland is still refused.
- [ ] Regnum's feed holds ~250 items (about a day) and its leads end with "..." where the feed cuts them: they
      read well enough. A few items of 24 and 28 September came with the first reading; the Outlets page now
      says "since" the first of three days in a row with articles, and "a day" as the median of complete days.

## 3. Engineering

- [ ] **Repository size.** 1 September – 8 October is ~214 MB of JSONL on disk, ~50 MB packed in git; the lead
      translations of 9 October add about a fifth. At ~2 GB of JSONL a year, plan to move older years into
      release assets and keep `WOLAND_SEARCH_MONTHS` (default 18) under the Pages 1 GB limit.
- [ ] **Two runs writing at once** can merge (`woland/merge.py`), but all data-writing workflows share the
      `woland-data` concurrency group, so GitHub's own runs never do. If the polls are ever moved to a group of
      their own, one rare case is not handled: the same new article filed under two different days by the two
      runs (feed time and page time on either side of midnight) would be stored twice, and
      `tests/test_data.py` would say so after the nightly commit.

Done on 9 October: **leads and snippets are translated too** (`de`, `kbe`; the user's request): sentence by
sentence (whole leads lost a sentence in 36 of 180 two-sentence leads), with the little words left dangling
where a lead was cut off dropped and an ellipsis instead (the model otherwise finished such sentences itself:
"рассказал президент…" → "said the President of Russia"); in batches side by side (2.5 times faster). The
archive's 245,530 leads and 34,890 snippets were translated locally the same night; new records are
translated as they are collected, and `woland translate` (the nightly step) fills in what is missing.

## 4. Analysis and content (needs a person with the expertise)

- [ ] **Lexicon review.** Three rounds of reading 25 random matches per framing (27–28 September 2026, by an AI
      assistant): 545 of 600 fit — see `docs/lexicon-audit.md`, every excerpt and verdict in
      `docs/lexicon-audit-sample.csv`. It needs a specialist's second reading, and decisions on its "still to
      do" list: Trump's "fake news" and debunked domestic rumours under "Western fakes" (14 of 25), removals
      from the foreign-agent register, opposite and mirror claims under "Nuclear threats", whether the
      "genocide of the Soviet people" campaign is its own framing. `python -m woland sample <framing> --seed N`
      draws a fresh sample; after changing a framing, read one and update its `checked` entry. TASS's texts are
      matched since 30 September: its body matches were not part of the audited samples.
- [ ] **Translation glossary** (`config/glossary.yaml`, 26 entries): it now corrects leads and snippets too, and
      `python -m woland mtcheck` counts them. Run it now and then; names missing from the glossary have to be
      spotted in the translations. Added on 9 October: СФ, the Federation Council ("SF" in 28 of 40 headlines,
      once "FSB" in a snippet); and the model's "Previous article", which it writes now and then in place of a
      sentence's first words (113 headlines, 32 leads: "Сальдо: Киеву…" → "Previous articleKiev…"), is left out
      at build time — the words it replaced stay lost. Not added: "SC" for СК (it can be a sports complex,
      "СК «ЦСКА Арена»"); "В СФ России" rendered "In the Russian Federation" (2 headlines).
- [ ] **Finnish and Swedish** need a native speaker's check: `site/assets/js/i18n.js` and the FI/SV halves of
      `site/method.html` — including the paragraphs added on 25–26 September (sites that refuse automated
      readers, the Internet Archive, *headline only* records, where leads come from), the strings
      `article.listed` / `article.listed.title`, everything added on 27 September (the Method sections on
      matching, measures, machine translation, searching and citing; the strings for article details,
      citations, completed days, coverage, rising words, archive filters and the collection log; the outlet
      notes (`note` in `config/outlets.yaml`) and the context labels in `config/lexicon.yaml`), on 28
      September: `narratives.patterns.note` (the `~`), the Method page's sentence on the chance test for rising
      words, and the MK, Sputnik and TASS notes; on 29 September: TASS's new note, the Method page's TASS
      paragraph and coverage item, and the strings `today.cov.gaps`, `outlets.gaps`, `outlets.gaps.hint`,
      `outlets.gaps.day`; `article.video` and `article.video.title`; the notes of Izvestia, Tsargrad, KP and
      Regnum (and Regnum's shorter `about`); the Method page's sentence on Regnum; and on 9 October: MK's note,
      the sentence in TASS's note on its failing feed, the Method page's sentences on MK, on what is stored, machine translation and searching, the strings
      `archive.syntax`, `archive.scope.words`, `today.lede.rising.one`, `outlets.perday.hint`, `problem.*`,
      `title.*`, `nav.contents`, `nav.days`; "narratiiveja" and "narrativ" for "kehystyksiä" and "inramningar"
      in TASS's note and Method paragraph (the words the rest of the site uses).
- [ ] **Legal**: most of these outlets fall under the EU broadcasting ban. Woland shows headlines, leads
      (≤ 240 characters) and snippets (≤ ~170) for analysis, and now their machine translations; the README
      flags this, but it is not legal advice.

## 5. Site

- [ ] **Load time** (measured 28 September from Finland on the live site; sizes compressed): Today ~104 KB and
      loaded in ~1.2 s, Narratives ~145 KB, Outlets ~70 KB. (Narratives read two or three whole day digests,
      ~57 KB each, for its dozen examples; since 10 October one file per framing, ~10 KB: ~60 KB in all. Today's
      digest was ~57 KB, three quarters of it the examples behind its rows: since 10 October they are a file of
      their own, read when a row first opens, and the digest ~12 KB.) Fonts come on top on a first visit: the site asks
      Google Fonts for 10 styles (20 files in Cyrillic and Latin, 585 KB), a page uses about seven (~430 KB) —
      four times the page itself, though `display=swap` shows the text at once. Fewer faces per page would mean
      design changes (translations not in italic, no bold sans in tiles and badges, the epigraphs' Russian lines
      in another face): the user's decision.
      An archive search for "Finland" over September and October downloaded ~785 KB after the lead translations
      (one index shard and one month file per month, and a block of 100 documents, ~30 KB, for nearly every
      result shown); since 10 October, with blocks of 25 documents and 256 shards, 336 KB (blocks 157 KB, month
      files 136 KB, shards 43 KB). The month files (one outlet code per document, ~100 KB a month) are now the
      biggest part, and every month searched adds one: ordering a day's documents by outlet would shrink them
      to almost nothing, but results are shown in the documents' (time) order. The site is 111 MB, 11,000 files.
- [ ] **Rising words** sometimes list one event twice ("Устуу Хурээ · буддийский" and "монастырский" on 7
      October): a word joins an event only if 60% of its headlines share the event's *first* word (9 of 16
      there). Comparing with every word of the event would join them, at some risk of chaining unrelated events.

Done on 9 October: page titles and the labels of the page's landmarks in Finnish and Swedish; the run log says
in words what went wrong (with the messages as a tooltip) instead of Python's exceptions; an outlet's "a day" is
the median of its complete days and its "since" ignores stray early items (Regnum showed "166 a day since 24
September"); ratios and the chart axis in the reader's number format; the Today summary in the singular when
one framing rose; on a phone the list of framings and topics is a short box above the charts, not four screens.
