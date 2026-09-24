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
