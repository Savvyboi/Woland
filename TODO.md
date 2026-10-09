# Woland — to do

Open work for future sessions, most urgent first. State of the archive when this list was last updated
(9 October 2026, early morning): 254,750 articles from 23 outlets, 1 September – 8 October 2026.

| Outlet | Articles | Note |
|---|---:|---|
| RIA, RT (both), Izvestia, Vesti, Lenta, Life, Gazeta.ru, AiF, Parlamentskaya Gazeta, TASS English, Tsargrad, Ukraina.ru, InoSMI, Rossiyskaya Gazeta, the Kremlin (both) | | complete from their own sitemaps and listings |
| MK | 21,267 | did not answer GitHub 27–29 September and on 2, 3 and 6 October: read from the Internet Archive's copies those nights (4,608 records); answers on the other nights; no headline-only records left |
| KP | 10,602 | early September: only what the Internet Archive captured (~60% of online news) |
| Zvezda | 3,247 | early September and 21–23 September from the Internet Archive (~70% of early September) |
| TASS (Russian) | 12,690 | feeds only, from 24 September; hours lost are listed on the Outlets page (§1) |
| Sputnik | 778 | answers neither Finland nor GitHub: some 15–30 a day from the Internet Archive's copies |
| Regnum | 2,159 | feed only since 29 September, ~210 a day; its pages answered GitHub in the check of 5 October (§2) |

## 1. Collection on GitHub (watch the next runs)

- [ ] **TASS's feed for news aggregators fails now and then, and did so unreported.** On 7–8 October several
      readings found only ~170 items in TASS's three feeds (13:49 UTC on the 7th; 03:01, 07:25 and 10:25 UTC on
      the 8th) instead of ~800: `rss/yandex.xml`, which holds ~650 of them and reaches back about twelve hours,
      had failed while the main and sport feeds answered, and a source only reported an error when *all* its
      feeds failed. The hours 05:54–07:07 and 07:10–07:31 Moscow time on 8 October were lost (the Outlets page
      lists them). Fixed on 9 October: a feed that fails beside others, answers with nothing in it, or with a
      bot check is now reported (`SourcePartial` in `discover.py`), and the run log says "error 403", "a feed
      was empty" or "refused the pages". Watch the next runs: how often it fails, and with what. If it is often,
      read the feeds more often while they fail, or ask why.
- [ ] **Hourly feeds run every three to seven hours** (4–6 polls a day, 30 September – 8 October). Since TASS is
      read from its twelve-hour feed (30 September) that lost nothing until the feed itself failed (above).
      Decided on 28 September: no outside trigger; reconsider if hours are lost again.
- [ ] The nightly run (01:17 UTC) starts at 06:30–07:35 UTC and takes 70–100 minutes (MK's 90-minute cap
      dominates), the site build ~10 more: late runs cost nothing but a later site.

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
      once "FSB" in a snippet). Not added: "SC" for СК (it can be a sports complex, "СК «ЦСКА Арена»").
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
      loaded in ~1.2 s, Narratives ~145 KB, Outlets ~70 KB. Fonts come on top on a first visit: the site asks
      Google Fonts for 10 styles (20 files in Cyrillic and Latin, 585 KB), a page uses about seven (~430 KB) —
      four times the page itself, though `display=swap` shows the text at once. An archive search downloads
      ~600 KB (22 files; "Finland": the month's index file and 20 blocks of ~23 KB, one per result shown); the
      lead translations make each block bigger (measure). Possible gains: smaller search blocks (more files).
      Fewer faces per page would mean design changes (translations not in italic, no bold sans in tiles and
      badges, the epigraphs' Russian lines in another face): the user's decision.
- [ ] **Rising words** sometimes list one event twice ("Устуу Хурээ · буддийский" and "монастырский" on 7
      October): a word joins an event only if 60% of its headlines share the event's *first* word (9 of 16
      there). Comparing with every word of the event would join them, at some risk of chaining unrelated events.

Done on 9 October: page titles and the labels of the page's landmarks in Finnish and Swedish; the run log says
in words what went wrong (with the messages as a tooltip) instead of Python's exceptions; an outlet's "a day" is
the median of its complete days and its "since" ignores stray early items (Regnum showed "166 a day since 24
September"); ratios and the chart axis in the reader's number format; the Today summary in the singular when
one framing rose; on a phone the list of framings and topics is a short box above the charts, not four screens.
