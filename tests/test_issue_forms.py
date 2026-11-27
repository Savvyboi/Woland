"""The issue forms (.github/ISSUE_TEMPLATE): well-formed as GitHub reads them, and with the field ids that the
site may use to fill them in (…/issues/new?template=<file>&<id>=…). They were also checked against the
published schema (check-jsonschema --builtin-schema vendor.github-issue-forms)."""
from __future__ import annotations

import re

import pytest
import yaml

from woland.config import ROOT

FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"
TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}
# ids that links from the site rely on: renaming one breaks them silently
STABLE = {"lexicon-false-positive.yml": {"kind", "url", "outlet", "framing", "excerpt", "reason", "suggestion"},
          "glossary-override.yml": {"russian", "machine", "suggested", "url", "context"}}


@pytest.mark.parametrize("name", sorted(STABLE))
def test_an_issue_form_is_well_formed(name):
    form = yaml.safe_load((FORMS / name).read_text(encoding="utf-8"))
    assert form["name"] and form["description"] and isinstance(form["body"], list)
    ids, labels = [], []
    for item in form["body"]:
        assert item["type"] in TYPES
        if item["type"] == "markdown":
            assert item["attributes"]["value"].strip()
            continue
        assert re.fullmatch(r"[A-Za-z0-9_-]+", item["id"])
        ids.append(item["id"])
        labels.append(item["attributes"]["label"])
        if item["type"] == "dropdown":
            options = item["attributes"]["options"]
            assert options and len(set(options)) == len(options)
    assert len(set(ids)) == len(ids) and len(set(labels)) == len(labels)
    assert set(ids) == STABLE[name]
    assert any(i["type"] != "markdown" and i.get("validations", {}).get("required") for i in form["body"])


def test_the_chooser_links_to_the_audit_and_the_site():
    config = yaml.safe_load((FORMS / "config.yml").read_text(encoding="utf-8"))
    urls = [link["url"] for link in config["contact_links"]]
    assert all(link["name"] and link["about"] and link["url"].startswith("https://") for link in config["contact_links"])
    assert any(u.endswith("docs/lexicon-audit.md") for u in urls) and "https://savvyboi.github.io/Woland/" in urls
    assert (ROOT / "docs" / "lexicon-audit.md").exists()
