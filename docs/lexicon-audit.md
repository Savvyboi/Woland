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
* **Two rounds**: a first sample was read; the patterns that produced clear errors were changed; for the 11
  framings that changed, a **fresh** sample (another seed) was read, so that the published figure does not come
  from the sample the changes were tuned on. For the 13 framings left unchanged, the first sample is the result.
* **Who**: this first pass was made by an AI assistant (Claude, working on this repository) reading every
  excerpt in Russian and English. It has not yet been reviewed by a person with expertise in Russian state media;
  every excerpt and verdict is in [`lexicon-audit-sample.csv`](lexicon-audit-sample.csv) for that review.

A sample of 25 gives a rough figure: 20 of 25 (80%) is compatible with anything from about 60% to 93%. Read the
figures as a check for gross errors and a ranking of the framings by reliability, not as precise rates.

## Results (the lexicon as of 2026-09-27)

Across the framings, **537 of 600** sampled matches fit the definition.

| Framing | Articles before | after | Fit (of 25) | Round | Notes |
|---|---:|---:|---:|---:|---|
| 'Special military operation' | 7,496 | 7,496 | 25 | 1 | Every match is the euphemism itself. |
| Nazis & 'denazification' | 2,186 | 1,751 | 22 | 1 | Now needs Ukraine, the war or the West nearby, and skips the stock phrases of Second World War memory. Misses remain: Italian and Polish politics, a quoted slur. |
| 'The Kyiv regime' | 5,270 | 5,270 | 25 | 1 | The phrase is the framing. |
| Zelensky 'illegitimate' | 381 | 218 | 25 | 2 | First read: 'President' in the context list let in Russia's president, Maduro and the Duma; now Ukraine's president or government must be named. 'Former president of Ukraine' was dropped (it found Kuchma, Yanukovych and Poroshenko). |
| 'Collective West' & 'Anglo-Saxons' | 541 | 537 | 25 | 1 | Clean. |
| Russophobia | 1,045 | 1,045 | 25 | 1 | Clean. |
| 'Provocations' & staged events | 2,453 | 2,190 | 22 | 2 | The adjective 'провокационный' (pop videos, WeChat titles) now needs Ukraine, the war or the West; staged robberies and stage adaptations ('инсценировка') likewise. Celebrities' denials and fraud still count. |
| 'Western fakes' & information war | 2,272 | 1,759 | 17 | 2 | The weakest framing. Trump's 'fake news', scams, debunked domestic rumours and Western accusations of Russian disinformation still count. Fake accounts, letters and websites, ballot stuffing and hockey face-offs ('вброс') and Ukraine's Centre for Countering Disinformation no longer do. |
| Ukraine as 'terrorist state' | 2,341 | 1,545 | 23 | 1 | 'Теракт' and 'terrorist attack' now need Ukraine, its army, drones or the war nearby (Dagestan, Pakistan and 11 September no longer count). Polish cases still slip through via 'drone'. |
| 'Foreign mercenaries' | 810 | 806 | 21 | 1 | Mostly the Defence Ministry's stock phrase 'foreign mercenaries'. Opposite claims (North Korean 'mercenaries') and insults count too. |
| US 'biolabs' | 104 | 36 | 24 | 2 | 'Biological weapons' matched North Korea and insurance policies and was removed; laboratories need Ukraine or the West (an AI company's lab still slips through). |
| Nuclear threats & 'superweapons' | 1,266 | 336 | 18 | 2 | First read 13 of 25: general nuclear news (Iran, arms control, France's deterrent) is now the topic 'Nuclear weapons'; strikes and war need Russia, Europe, NATO or Ukraine; Sarmat, Burevestnik and Poseidon need missile words. Still counted: opposite claims, explainers, a US patrol aircraft. |
| 'Genocide' of Russians | 30 | 30 | 24 | 1 | Almost all matches are the state's 'genocide of the Soviet people' memory campaign about 1941–45, which the definition includes: read this framing as memory politics rather than a claim about the current war. |
| 'Traditional values' | 335 | 332 | 24 | 2 | Clean; 'traditional family' matched a family get-together and now needs 'values'. |
| 'Satanism' & 'LGBT propaganda' | 290 | 152 | 20 | 2 | The legally required note 'the LGBT movement is recognised as extremist' was attached to unrelated stories; its commonest wordings no longer count. Gossip and neutral news remain. |
| 'Russian world' & 'historical lands' | 1,193 | 463 | 21 | 2 | 'Новороссийск', the port city, made up most of the old matches; now only 'Новороссия'. The R-280 'Novorossiya' highway still counts. |
| Multipolarity vs. 'hegemony' | 1,033 | 1,033 | 23 | 1 | 'Global South' is sometimes merely descriptive. |
| Decline of the West | 181 | 181 | 21 | 1 | De-dollarisation is in the definition; Peskov's denials that Russia seeks it count too. |
| Enemies within: 'foreign agents' | 1,497 | 720 | 16 | 2 | First read 6 of 25: most matches were the label Russian law requires after every name on the foreign-agent register, under stories about something else. The commonest wordings of that label no longer count (as with the 'extremist organisation' note on Meta); others remain (see below). 'Traitor' now needs 'motherland' or 'Russia' (it found a film title and South Korea's president). |
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
and lead, or within 50 characters in the text), or **not** inside given phrases. `woland/lexicon.py` and
`site/assets/js/lexicon.js` implement the same rules; `tests/test_woland.py` checks that they agree. The patterns
and their conditions are listed with each framing on the site and in `config/lexicon.yaml`, with a comment
explaining every condition.

## Still to do

* Enemies within: exclude further wordings of the foreign-agent and 'undesirable organisation' labels ('включена Минюстом в список иноагентов', 'в список лиц, выполняющих функции иноагента', 'признан(а) нежелательной организацией', 'признан Минюстом России иностранным агентом', 'включён в России в реестр'), then re-check a fresh sample.
* Western fakes: decide whether Trump's 'fake news' ('фейк-ньюс', 'fake news') and debunked domestic rumours belong to the framing; exclude scams ('фейковой биржи', 'фейковые видео').
* Russian world: exclude the R-280 'Novorossiya' highway ('трасса «Новороссия»').
* Nuclear threats: exclude 'anti-submarine' as missile context for Poseidon; decide on opposite claims (calls to strike Russia).
* Genocide claims: decide whether the 'genocide of the Soviet people' memory campaign should be its own framing.
* Every framing: a second reader, and a larger sample for framings whose count drives conclusions.

Re-check a framing on a fresh sample after changing its patterns, and update its `checked` entry in
`config/lexicon.yaml` (the site shows it with the framing).
