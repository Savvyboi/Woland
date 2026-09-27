# Lexicon audit, September 2026

Woland counts an article under a framing when its headline, lead or (where Woland read the page) text contains
one of the framing's word patterns (`config/lexicon.yaml`). This audit asked how often such a match is what the
framing's definition describes. It answers a review of the site (27 September 2026) that asked for the matches
of every framing to be checked by hand, broad patterns such as "disinformation" and "terrorist attack" first.

## How it was done

* **Sample**: for each of the 24 framings, 25 articles drawn at random (fixed seeds) from everything the site
  counts under it in the archive of 1–26 September 2026 (160,551 articles): the headline, the lead or the stored
  text snippet in which the pattern matched, exactly as the site counts it.
* **Reading**: each match was judged against the framing's definition. *Fits* means the text uses or relays the
  framing (an official's statement reported without distance counts); *does not fit* means the words are used in
  another sense, about something the definition does not cover, or for the opposite claim.
* **Three rounds**: a first sample was read; the patterns that produced clear errors were changed; for the 11
  framings that changed, a **fresh** sample (another seed) was read, so that the published figure does not come
  from the sample the changes were tuned on. For the 13 framings left unchanged, the first sample is the result.
  A third round (28 September 2026, archive of 1–27 September) worked through this report's own list of what was
  still to do for four framings, then read a fresh sample of each (seed 3), with the same rules for judging.
* **Tool**: `python -m woland sample <framing> --seed <n> --csv <file>` draws such a sample from the archive as the
  site counts it, with the matched words marked `[[like this]]` and the columns of the CSV below. The same seed
  over the same archive draws the same articles; a new seed draws a fresh sample.
* **Who**: all three rounds were read by an AI assistant (Claude, working on this repository), every excerpt in
  Russian and English. It has not yet been reviewed by a person with expertise in Russian state media;
  every excerpt and verdict is in [`lexicon-audit-sample.csv`](lexicon-audit-sample.csv) for that review.

A sample of 25 gives a rough figure: 20 of 25 (80%) is compatible with anything from about 60% to 93%. Read the
figures as a check for gross errors and a ranking of the framings by reliability, not as precise rates.

## Results (the lexicon as of 2026-09-28)

Across the framings, **545 of 600** sampled matches fit the definition (537 before the third round).

| Framing | Articles before | after | Fit (of 25) | Round | Notes |
|---|---:|---:|---:|---:|---|
| 'Special military operation' | 7,496 | 7,496 | 25 | 1 | Every match is the euphemism itself. |
| Nazis & 'denazification' | 2,186 | 1,751 | 22 | 1 | Now needs Ukraine, the war or the West nearby, and skips the stock phrases of Second World War memory. Misses remain: Italian and Polish politics, a quoted slur. |
| 'The Kyiv regime' | 5,270 | 5,270 | 25 | 1 | The phrase is the framing. |
| Zelensky 'illegitimate' | 381 | 218 | 25 | 2 | First read: 'President' in the context list let in Russia's president, Maduro and the Duma; now Ukraine's president or government must be named. 'Former president of Ukraine' was dropped (it found Kuchma, Yanukovych and Poroshenko). |
| 'Collective West' & 'Anglo-Saxons' | 541 | 537 | 25 | 1 | Clean. |
| Russophobia | 1,045 | 1,045 | 25 | 1 | Clean. |
| 'Provocations' & staged events | 2,453 | 2,190 | 22 | 2 | The adjective 'провокационный' (pop videos, WeChat titles) now needs Ukraine, the war or the West; staged robberies and stage adaptations ('инсценировка') likewise. Celebrities' denials and fraud still count. |
| 'Western fakes' & information war | 2,272 | 1,759 | 14 | 3 | The weakest framing. Fake accounts, letters, websites, crypto exchanges, notices and giveaways, ballot stuffing and hockey face-offs ('вброс') and Ukraine's Centre for Countering Disinformation no longer count (third round: 1,794 → 1,771 articles in 1–27 September). Still counted: Trump's 'fake news' (2 of 25), debunked domestic rumours (2), gossip, humour and the word itself, Kyiv's own accusations, a museum's 'information war' of the 1850s. The second round read 17 of 25. |
| Ukraine as 'terrorist state' | 2,341 | 1,545 | 23 | 1 | 'Теракт' and 'terrorist attack' now need Ukraine, its army, drones or the war nearby (Dagestan, Pakistan and 11 September no longer count). Polish cases still slip through via 'drone'. |
| 'Foreign mercenaries' | 810 | 806 | 21 | 1 | Mostly the Defence Ministry's stock phrase 'foreign mercenaries'. Opposite claims (North Korean 'mercenaries') and insults count too. |
| US 'biolabs' | 104 | 36 | 24 | 2 | 'Biological weapons' matched North Korea and insurance policies and was removed; laboratories need Ukraine or the West (an AI company's lab still slips through). |
| Nuclear threats & 'superweapons' | 1,266 | 336 | 22 | 3 | First read 13 of 25: general nuclear news (Iran, arms control, France's deterrent) is now the topic 'Nuclear weapons'; strikes and war need Russia, Europe, NATO or Ukraine; Sarmat, Burevestnik and Poseidon need missile words, and the US Boeing P-8 Poseidon no longer counts (third round). Still counted: Western fears retold as absurd (the opposite claim), bridges built to withstand a nuclear strike, China denying Finland's claim. The second round read 18 of 25. |
| 'Genocide' of Russians | 30 | 30 | 24 | 1 | Almost all matches are the state's 'genocide of the Soviet people' memory campaign about 1941–45, which the definition includes: read this framing as memory politics rather than a claim about the current war. |
| 'Traditional values' | 335 | 332 | 24 | 2 | Clean; 'traditional family' matched a family get-together and now needs 'values'. |
| 'Satanism' & 'LGBT propaganda' | 290 | 152 | 20 | 2 | The legally required note 'the LGBT movement is recognised as extremist' was attached to unrelated stories; its commonest wordings no longer count. Gossip and neutral news remain. |
| 'Russian world' & 'historical lands' | 1,193 | 463 | 25 | 3 | 'Новороссийск', the port city, made up most of the old matches; now only 'Новороссия'. Third round: not the R-280 'Novorossiya' highway, and 'исконно русский' only of land, cities and regions (it is also said of words, dishes and patronymics): 490 → 464 articles in 1–27 September. The closest call left: the Russkiy Mir Foundation as a sponsor. The second round read 21 of 25. |
| Multipolarity vs. 'hegemony' | 1,033 | 1,033 | 23 | 1 | 'Global South' is sometimes merely descriptive. |
| Decline of the West | 181 | 181 | 21 | 1 | De-dollarisation is in the definition; Peskov's denials that Russia seeks it count too. |
| Enemies within: 'foreign agents' | 1,497 | 720 | 19 | 3 | First read 6 of 25: most matches were the label Russian law requires after every name on the foreign-agent register, under stories about something else. The label no longer counts (as with the 'extremist organisation' note on Meta): it is in the passive voice with a varying number of words in between, which patterns can now say with `~` ('внесен* ~ в реестр ~ иноагент*'); third round: 733 → 583 articles in 1–27 September, the second round having read 16 of 25. Still counted: the nominal label '(СМИ-иноагент и нежелательная организация)', removals from the register, a country that 'betrayed Russia', neutral uses of 'релоканты'. 'Traitor' needs 'motherland' or 'Russia' (it found a film title and South Korea's president). |
| Blaming Kyiv & the West for no peace | 645 | 577 | 24 | 2 | 'Парти* войн*' matched 'partisan war'; the party of war is now spelled out. Root causes now need Ukraine or talks (global warming, fuel prices). |
| Stolen aid & black-market arms | 398 | 127 | 19 | 2 | Resale, 'распил' (sawing) and 'corruption in Ukraine' were broad: resale now needs arms or aid, 'распил' a budget or money, corruption aid or money. Black markets in other goods and opposite claims remain. |
| Ukraine's 'forced mobilisation' | 650 | 650 | 25 | 1 | Clean: stories about Ukraine's recruitment centres (ТЦК). |
| 'Liberation' & 'new regions' | 1,286 | 1,034 | 23 | 1 | 'New regions' matched 'a new regional format' (now excluded) and, twice, generic uses. 'Reunification' of families and of Ireland no longer counts. |
| Dehumanising labels | 1,782 | 1,746 | 25 | 1 | Mostly 'Ukrainian militants' ('украинские боевики'), which the definition includes. The surname Хохлов and Khokhloma painting no longer count. |

*Articles before/after*: articles counted under the framing in 1–26 September 2026 with the old and the revised
lexicon. Also split off: general news about nuclear weapons (Iran, arms control, deterrence) is the new topic
*Nuclear weapons*.

## What changed in the lexicon

The lexicon can now say that a word counts only **with** a context (a word from a named list in the same headline
and lead, or within 50 characters in the text), or **not** inside given phrases; since the third round a phrase
may leave room for up to three words of any kind with `~` (and for a quotation mark before the next word:
'трасс* ~ новороссия' finds "трассе Р-280 «Новороссия»"). `woland/lexicon.py` and
`site/assets/js/lexicon.js` implement the same rules; `tests/test_woland.py` checks that they agree. The patterns
and their conditions are listed with each framing on the site and in `config/lexicon.yaml`, with a comment
explaining every condition.

## Still to do

Done in the third round: the passive wordings of the foreign-agent and 'undesirable organisation' labels, crypto
and other scams under 'Western fakes', the R-280 highway and the non-territorial 'исконно русский', the Boeing
P-8 Poseidon. Left for a person with the expertise:

* Enemies within: the nominal label '(СМИ-иноагент и нежелательная организация в РФ)'; whether removals from the
  register belong to the framing; 'предал Россию' said of a country; footnotes in the active voice ('* Минюст России
  внес … в реестр СМИ-иноагентов') cannot be told from news by their words.
* Western fakes: decide whether Trump's 'fake news' ('фейк-ньюс', 'fake news') and debunked domestic rumours belong
  to the framing (together 4 of the 11 misses in the third round); 'фейк' as a word of slang or gossip, and Kyiv's
  own accusations of disinformation, are the rest. 'Фейковые видео' was left in: most are the framing ("ВСУ
  снимают фейковые видео"), the scam videos few.
* Nuclear threats: decide on opposite and mirror claims (Western fears retold as absurd, calls to strike Russia,
  a 'sudden' NATO strike); engineering that 'withstands a nuclear strike'.
* Genocide claims: decide whether the 'genocide of the Soviet people' memory campaign should be its own framing.
* Every framing: a second reader, and a larger sample for framings whose count drives conclusions.

Re-check a framing on a fresh sample after changing its patterns, and update its `checked` entry in
`config/lexicon.yaml` (the site shows it with the framing).
