"""Live checks against the real outlets (network). Off by default:

    WOLAND_LIVE=1 python -m pytest -m live -q          # add WOLAND_DOH=1 behind an EU DNS block

For each enabled outlet: yesterday's articles can be discovered through its everyday sources, and a
couple of them can be read and parsed. `python -m woland check` prints the same as a table.
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest

from woland.check import check_outlet
from woland.config import load_lexicon, load_outlets
from woland.lexicon import Lexicon
from woland.util import today_msk

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(os.environ.get("WOLAND_LIVE") != "1", reason="set WOLAND_LIVE=1 to read the outlets")]

LEX = Lexicon(load_lexicon())


@pytest.mark.parametrize("outlet", load_outlets(), ids=lambda o: o.id)
def test_outlet_can_be_read(outlet):
    h = check_outlet(outlet, today_msk() - timedelta(days=1), LEX)
    assert h.found > 0, h.problems
    if h.tried:
        assert h.read > 0, h.problems
    assert h.sample.strip()
