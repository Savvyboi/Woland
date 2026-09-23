# Woland's archive

Filled in automatically by the nightly and hourly GitHub Actions workflows.

* `articles/YYYY/MM/DD/<outlet>.jsonl` — one article per line; the fields are described in the main README.
* `state/coverage.json` — for every outlet and Moscow day: articles stored, articles announced by the outlet's
  own listings, and whether the day is complete, partial, or feed-only.
* `state/runs.json` — summaries of the latest collection runs.
* `state/seen.json` — URLs recently rejected (outside the date range, gone), so they are not fetched again.
