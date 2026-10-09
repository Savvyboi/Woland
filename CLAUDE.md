# Woland — notes for AI coding sessions

A daily, searchable chronicle of the Russian state and pro-Kremlin press since 1 September 2026, for
researchers, journalists and activists. GitHub Actions collects, the repository stores (`data/`), GitHub
Pages publishes. Read `README.md` for how it works and **`TODO.md` for the open work**.

## Layout

- `woland/` — collector and site builder (`python -m woland collect | poll | backfill | translate | build | probe | check | mtcheck | reindex | sample`)
- `config/outlets.yaml` — the outlets and how each is read (all options documented at the top);
  `config/lexicon.yaml` — framings and topics, with contexts and exclusions; `config/glossary.yaml` —
  corrections to the machine translation, applied at build time
- `docs/lexicon-audit.md` — how many of a random sample of each framing's matches fit its definition
- `site/` — the website (plain HTML/CSS/JS modules, no build tool); UI strings in `site/assets/js/i18n.js`
- `data/articles/YYYY/MM/DD/<outlet>.jsonl` — the archive; `data/state/` — coverage, runs, rejected URLs, and `urls/` (every URL stored, so none is stored twice)
- `.github/workflows/` — nightly collection, hourly feeds, build and publish, tests, outlet check

## Commands

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt pytest   # (bin/ on Linux)
.venv/Scripts/python -m pytest -q                      # offline; needs Node.js for the site tests
WOLAND_LIVE=1 .venv/Scripts/python -m pytest -m live   # reads the real outlets
.venv/Scripts/python -m woland check                   # health table for every outlet
.venv/Scripts/python -m woland build --out _site       # then: python -m http.server -d _site
# once per clone, so that pulling data merges record by record (woland/merge.py) instead of conflicting:
git config merge.woland.driver "PYTHONPATH='$PWD' '$PWD/.venv/Scripts/python.exe' -m woland merge %O %A %B %P"
```

Working from Finland (or elsewhere in the EU): ISPs block most of these domains in DNS; set
`WOLAND_DOH=1` to resolve through DNS-over-HTTPS. sputnikglobe.com is blocked by IP. From GitHub's runners
neither Sputnik nor MK answered on 27 September 2026 (MK does from Finland): see `TODO.md`.

## Ground rules

- **Never get around bot checks or CAPTCHAs.** Woland identifies itself honestly (`WolandMonitor`), obeys
  robots.txt, keeps a per-site pause and slows down when a site says so (429, Qrator's challenge). Sites that
  refuse automated readers stay feed-only (TASS Russian, Regnum — whose feed answers GitHub, not Finland). Gazeta.ru's cookie is fine: it
  only declines an optional sign-in, as every anonymous visitor does (see `outlets.yaml`).
- **Keep English, Finnish and Swedish in step**: every UI string exists in all three (`tests/test_site.py`
  checks), and the Method page has a section per language. Finnish and Swedish need a native speaker's review.
- **Framing counts are pattern matches**, and the site says so. `woland/lexicon.py` and
  `site/assets/js/lexicon.js` must match the same words (`tests/test_woland.py` compares them). After changing a
  framing's patterns, read a fresh random sample of its matches and update its `checked` entry
  (`docs/lexicon-audit.md` says how).
- **Days still being collected** (after `complete_through` in `meta.json`) stay out of comparisons and averages
  unless the reader asks for them, and are marked wherever they are shown.
- **Data**: one record per URL, filed under the Moscow day it was published; only headlines, leads (≤ 240
  characters) and snippets (≤ ~170), with their English machine translations (`te`, `de`, `kbe`), are stored —
  never full texts. A translation goes with the text it translates (`store.lends`). `tests/test_data.py`
  validates every record; run it after any change to data or collection code.
- **The workflows commit to `main` every hour**: pull before committing locally, and don't run a local
  collection for outlets GitHub is collecting at the same time. Workflows commit data only through
  `.github/commit-data.sh` (merge driver, retries) and check out the branch tip (`ref: ${{ github.ref_name }}`):
  a scheduled run otherwise gets the commit current when it was *queued*, and after waiting behind another
  run its push conflicts. GitHub's run list and job steps are public (`api.github.com/repos/Savvyboi/Woland/
  actions/runs`); logs and step summaries need a token, so results worth reading later go into the repository
  (`data/state/check.json`, `runs.json`).
- **Savvyboi is the only contributor**: commit messages carry no `Co-Authored-By` line, and the workflows
  commit under Savvyboi's no-reply address. GitHub lists every address it can tie to an account (a bot's, a
  co-author's, someone else's `name@users.noreply.github.com`), and taking one off means rewriting history.
