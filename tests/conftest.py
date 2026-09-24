"""Shared test helpers: a fake network, and an isolated data directory."""
from __future__ import annotations

import json
import re

import pytest

from woland import build as buildmod
from woland import store
from woland.net import Response


def pytest_configure(config):
    config.addinivalue_line("markers", "live: reads the real outlets over the network (WOLAND_LIVE=1)")


class FakeFetcher:
    """Answers get() from a table of URL → body (str/bytes), status code, or a function of the URL.
    Keys may be exact URLs or compiled regular expressions. Unknown URLs are 404s."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []
        self.requests = 0

    def get(self, url, **kw):
        self.calls.append(url)
        self.requests += 1
        body = self.routes.get(url)
        if body is None:
            for key, value in self.routes.items():
                if isinstance(key, re.Pattern) and key.search(url):
                    body = value(url) if callable(value) else value
                    break
        elif callable(body):
            body = body(url)
        if body is None:
            return Response(404, url, b"not found")
        if isinstance(body, int):
            return Response(body, url, b"")
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body)
        data = body.encode("utf-8") if isinstance(body, str) else body
        return Response(200, url, data, {"content-type": "text/html; charset=utf-8"})


@pytest.fixture
def fake():
    return FakeFetcher


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """An empty data directory and build cache for the duration of a test."""
    monkeypatch.setattr(store, "ART_DIR", tmp_path / "data" / "articles")
    monkeypatch.setattr(store, "STATE_DIR", tmp_path / "data" / "state")
    monkeypatch.setattr(buildmod, "CACHE", tmp_path / "cache")
    return tmp_path
