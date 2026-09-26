# Woland — notes for AI coding sessions

A daily, searchable chronicle of the Russian state and pro-Kremlin press since 1 September 2026, for
researchers, journalists and activists. GitHub Actions collects, the repository stores (`data/`), GitHub
Pages publishes. Read `README.md` for how it works and **`TODO.md` for the open work**.

## Layout

- `woland/` — collector and site builder (`python -m woland collect | poll | backfill | translate | build | probe | check`)
- `config/outlets.yaml` — the outlets and how each is read (all options documented at the top);
  `config/lexicon.yaml` — framings and topics
- `site/` — the website (plain HTML/CSS/JS modules, no build tool); UI strings in `site/assets/js/i18n.js`
- `data/articles/YYYY/MM/DD/<outlet>.jsonl` — the archive; `data/state/` — coverage, runs, rejected URLs
- `.github/workflows/` — nightly collection, hourly feeds, build and publish, tests, outlet check

## Commands

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt pytest   # (bin/ on Linux)
.venv/Scripts/python -m pytest -q                      # offline; needs Node.js for the site tests
WOLAND_LIVE=1 .venv/Scripts/python -m pytest -m live   # reads the real outlets
.venv/Scripts/python -m woland check                   # health table for every outlet
.venv/Scripts/python -m woland build --out _site       # then: python -m http.server -d _site
```

Working from Finland (or elsewhere in the EU): ISPs block most of these domains in DNS; set
`WOLAND_DOH=1` to resolve through DNS-over-HTTPS. sputnikglobe.com is blocked by IP and can only be read
from GitHub's runners.

## Ground rules

- **Never get around bot checks or CAPTCHAs.** Woland identifies itself honestly (`WolandMonitor`), obeys
  robots.txt, keeps a per-site pause and slows down when a site says so (429, Qrator's challenge). Sites that
  refuse automated readers stay feed-only (TASS Russian) or disabled (Regnum). Gazeta.ru's cookie is fine: it
  only declines an optional sign-in, as every anonymous visitor does (see `outlets.yaml`).
- **Keep English, Finnish and Swedish in step**: every UI string exists in all three (`tests/test_site.py`
  checks), and the Method page has a section per language. Finnish and Swedish need a native speaker's review.
- **Data**: one record per URL, filed under the Moscow day it was published; only headlines, leads (≤ 240
  characters) and snippets (≤ ~170) are stored — never full texts. `tests/test_data.py` validates every record;
  run it after any change to data or collection code.
- **The workflows commit to `main` every hour**: pull before committing locally, and don't run a local
  collection for outlets GitHub is collecting at the same time.
- **Savvyboi is the only contributor**: commit messages carry no `Co-Authored-By` line, and the workflows
  commit under Savvyboi's no-reply address. GitHub lists every address it can tie to an account (a bot's, a
  co-author's, someone else's `name@users.noreply.github.com`), and taking one off means rewriting history.
