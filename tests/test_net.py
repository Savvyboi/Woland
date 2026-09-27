"""Politeness: the per-host pause widens after "too many requests" and narrows again with success."""
from __future__ import annotations

from woland import net
from woland.net import Fetcher, Response, _HostThrottle


def test_throttle_widens_on_429_and_relaxes_with_success():
    t = _HostThrottle()
    assert t.penalise("x.ru") == 10.0 and t.gap("x.ru") == 2.0          # pause 5× the new gap
    assert t.penalise("x.ru", "7") == 7.0 and t.gap("x.ru") == 4.0      # Retry-After wins
    for _ in range(10):
        t.penalise("x.ru")
    assert t.gap("x.ru") == 30.0                                          # capped
    for _ in range(200):
        t.relax("x.ru")
    assert t.gap("x.ru") == 0.0 and t.gap("other.ru") == 0.0


def test_a_ddos_shield_challenge_is_a_request_to_slow_down_not_a_puzzle_to_solve(monkeypatch):
    captcha = b"<html><script src='/__qrator/qauth.js'></script>Enter the text from the image</html>"
    answers = [Response(401, "u", captcha), Response(200, "u", b"<html>article</html>")]
    slept = []
    monkeypatch.setattr(net, "THROTTLE", _HostThrottle())
    monkeypatch.setattr(net.time, "sleep", slept.append)
    f = Fetcher()
    monkeypatch.setattr(f, "_get", lambda url, gap, timeout=None: answers.pop(0))
    assert f.get("https://rg.ru/a.html", check_robots=False).ok and slept == [10.0]
    # a plain 401 (a login wall, say) is an answer, not a request to slow down
    assert not Response(401, "u", b"<html>Please sign in</html>").slow_down()


def test_fetcher_pauses_and_retries_after_429(monkeypatch):
    answers = [Response(429, "u", b"", {"retry-after": "3"}), Response(429, "u"), Response(200, "u", b"ok")]
    slept = []
    monkeypatch.setattr(net, "THROTTLE", _HostThrottle())
    monkeypatch.setattr(net.time, "sleep", slept.append)
    f = Fetcher()
    monkeypatch.setattr(f, "_get", lambda url, gap, timeout=None: answers.pop(0))
    r = f.get("https://www.mk.ru/a.html", check_robots=False)
    assert r.ok and r.content == b"ok"
    assert slept == [3.0, 20.0]                   # Retry-After, then 5× the doubled gap
    assert 0 < net.THROTTLE.gap("www.mk.ru") < 4.0


class _Clock:
    """Stands in for the time module in woland.net: a clock that only moves when told to."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_a_host_that_does_not_answer_is_left_alone_for_a_while(monkeypatch):
    import requests
    clock = _Clock()
    monkeypatch.setattr(net, "time", clock)
    monkeypatch.setattr(net, "THROTTLE", _HostThrottle())
    monkeypatch.setattr(net, "HEALTH", net._HostHealth(limit=3, pause=900))
    tried = []

    def silent(url, **kw):
        tried.append(url)
        raise requests.ConnectTimeout("connection timed out")

    f = Fetcher()
    monkeypatch.setattr(f.session, "get", silent)
    answers = [f.get("https://www.mk.ru/news/2026/9/%d/" % d) for d in range(1, 8)]
    assert not any(r.ok for r in answers)
    # robots.txt, the first listing, robots.txt again (not remembered while unanswered): three connection
    # attempts that went unanswered, then nothing more
    assert len(tried) == 3 and f.requests == 1 and answers[-1].error.startswith("NoConnection")
    clock.now += 901                        # a quarter of an hour later, one more try
    f.get("https://www.mk.ru/news/2026/9/8/")
    assert len(tried) == 4 and net.HEALTH.down("www.mk.ru")
    # a host that answers is not held back, and an answer ends the pause
    monkeypatch.setattr(f.session, "get", lambda url, **kw: (_ for _ in ()).throw(requests.ReadTimeout("slow")))
    for _ in range(5):
        f.get("https://ria.ru/a.html", check_robots=False)
    assert not net.HEALTH.down("ria.ru")    # a slow answer is not a missing one
    net.HEALTH.answered("www.mk.ru")
    assert not net.HEALTH.down("www.mk.ru")
