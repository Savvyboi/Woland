#!/usr/bin/env bash
# Commit what a run added under data/ and push it: bash .github/commit-data.sh "<commit message>"
#
# If someone pushed meanwhile, the commit is replayed on top of theirs, and git merges the data files that
# both changed record by record (woland/merge.py, routed there by .gitattributes). Commits go under
# Savvyboi's no-reply address, so that the repository keeps a single contributor.
set -uo pipefail

git config user.name "woland-bot"
git config user.email "123981133+Savvyboi@users.noreply.github.com"
git config merge.woland.name "Woland data files"
git config merge.woland.driver "PYTHONPATH='$PWD' python -m woland merge %O %A %B %P"

git add data
if git diff --cached --quiet; then
  echo "Nothing new."
  exit 0
fi
git diff --cached --shortstat
git commit -q -m "$1" || exit 1
for attempt in 1 2 3 4 5; do
  if git pull -q --rebase && git push -q; then
    exit 0
  fi
  git status --short | grep -v '^??' | head -20
  git rebase --abort 2>/dev/null
  sleep $((attempt * 15))
done
echo "::error::Could not push the new data (see the conflicts listed above)."
exit 1
