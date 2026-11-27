"""The phrase-cloning research aid (woland/phrases.py): common wording is left out, a rare phrase several
outlets take up within hours is listed, with who used it first and how long the others took."""
from collections import Counter

from woland import phrases

BOILER = "Президент России Владимир Путин заявил"


def rec(o, hhmm, t, day="2026-11-19", d=""):
    return {"o": o, "p": f"{day}T{hhmm}:00+03:00", "u": f"https://{o}.ru/{day}/{hhmm}", "id": f"{o}:{hhmm}", "t": t, "d": d}


def background_with_boilerplate(days=30):
    sets = [phrases.common([rec(o, "10:00", f"{BOILER} о {topic}", day=f"2026-10-{k + 1:02d}")
                            for o, topic in (("a", "погоде"), ("b", "ценах"), ("c", "спорте"), ("d", "мире"))])
            for k in range(days)]
    return phrases.background(sets)


def test_common_wording_is_left_out_and_a_rare_phrase_taken_up_within_hours_is_listed():
    bg = background_with_boilerplate()
    assert bg[tuple(w for w, _, _ in phrases.words(BOILER))[:3]] == 30
    rare = "ползучая денацификация сознания"
    day = [
        rec("a", "09:00", f"{BOILER} о бюджете"), rec("b", "09:05", f"{BOILER} о погоде"),
        rec("c", "09:10", f"{BOILER} о спорте"), rec("d", "09:20", f"{BOILER} о мире"), rec("e", "09:30", f"{BOILER} о ценах"),
        rec("tsar", "10:00", f"Эксперт: Европе грозит {rare} элит"),
        rec("kp", "10:40", f"Учителя заметили {rare} у школьников"),
        rec("ria", "11:15", f"Депутат назвал {rare} угрозой"),
        rec("rg", "11:55", f"В Прибалтике идет {rare} молодежи"),
    ]
    story_of = {r["u"]: i for i, r in enumerate(day)}  # every article a story of its own
    (c,) = phrases.clusters(day, bg, story_of)
    assert c["phrase"] == rare and c["outlets"] == 4 and c["stories"] == 4
    assert c["first"]["o"] == "tsar" and [(a["o"], a["lag"]) for a in c["adopters"]] == [("kp", 40), ("ria", 75), ("rg", 115)]


def test_a_phrase_from_one_story_from_one_agency_or_spread_over_more_hours_is_not_listed():
    bg = Counter()
    rare = "ползучая денацификация сознания"
    four = [rec(o, hhmm, f"Эксперт: {rare} нарастает") for o, hhmm in (("a", "10:00"), ("b", "10:30"), ("c", "11:00"), ("d", "11:30"))]
    assert phrases.clusters(four, bg, {r["u"]: 0 for r in four}) == []                     # one story
    assert phrases.clusters([{**r, "d": "Об этом сообщает ТАСС."} for r in four], bg,
                            {r["u"]: i for i, r in enumerate(four)}) == []                  # one agency's report
    late = four[:3] + [rec("d", "17:30", f"Эксперт: {rare} нарастает")]
    assert phrases.clusters(late, bg, {r["u"]: i for i, r in enumerate(late)}) == []      # 7½ hours apart
