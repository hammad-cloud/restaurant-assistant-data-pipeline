# ==========================================
# 1. IMPORTS
# ==========================================

import pytest

from knowledge.knowledge_store import (
    NOT_FOUND_ANSWER,
)
from knowledge.quick_answers import QuickAnswers, normalize_question


# ==========================================
# 2. CACHE UNIT TESTS (no database)
# ==========================================

class FakeClock:

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def counting_answer_fn():

    calls = []

    def answer_fn(conn, question, embed, branch_id=None):
        calls.append(question)
        if "unknown" in question:
            return NOT_FOUND_ANSWER, None, "none", False
        if "unsure" in question:
            return f"guess for {question}", "entry:2", "meaning", False
        return f"answer to {question}", "entry:1", "meaning", True

    return answer_fn, calls


def test_normalize_question_ignores_case_spaces_and_punctuation():

    assert normalize_question("  Where is the GULSHAN branch?? ") == "where is the gulshan branch"


def test_repeated_question_is_served_from_cache():

    answer_fn, calls = counting_answer_fn()
    quick = QuickAnswers(None, None, answer_fn=answer_fn)

    first = quick.ask("Where is Gulshan?")
    second = quick.ask("where is gulshan")

    assert first[3] is False and second[3] is True
    assert second[0] == first[0]
    assert len(calls) == 1


def test_cache_expires_after_ttl():

    answer_fn, calls = counting_answer_fn()
    clock = FakeClock()
    quick = QuickAnswers(None, None, ttl_seconds=60, answer_fn=answer_fn, clock=clock)

    quick.ask("hours?")
    clock.now = 59
    assert quick.ask("hours?")[3] is True
    clock.now = 61
    assert quick.ask("hours?")[3] is False
    assert len(calls) == 2


def test_cache_drops_least_recently_asked_when_full():

    answer_fn, calls = counting_answer_fn()
    quick = QuickAnswers(None, None, max_size=2, answer_fn=answer_fn)

    quick.ask("a")
    quick.ask("b")
    quick.ask("a")  # a is now the most recent
    quick.ask("c")  # drops b

    assert quick.ask("a")[3] is True
    assert quick.ask("b")[3] is False


def test_branch_answers_are_cached_separately_and_not_found_is_not_cached():

    answer_fn, calls = counting_answer_fn()
    quick = QuickAnswers(None, None, answer_fn=answer_fn)

    quick.ask("hours", branch_id="UTG-KHI-001")
    assert quick.ask("hours", branch_id="UTG-KHI-002")[3] is False

    quick.ask("unknown thing")
    assert quick.ask("unknown thing")[3] is False


def test_empty_question_is_refused():

    with pytest.raises(ValueError):
        QuickAnswers(None, None).ask(" ?! ")


# ==========================================
# 2c. CONFIDENCE-AWARE CACHING (no database)
# ==========================================

def test_confident_answer_is_cached_and_uncertain_answer_is_searched_again():

    answer_fn, calls = counting_answer_fn()
    quick = QuickAnswers(None, None, answer_fn=answer_fn)

    assert quick.ask("Biryani price?")[3] is False
    assert quick.ask("biryani price")[3] is True

    # The uncertain answer is still given every time, but never from the cache
    for _ in range(3):
        assert quick.ask("unsure thing") == ("guess for unsure thing", "entry:2", "meaning", False)
    assert calls == ["Biryani price?"] + ["unsure thing"] * 3
    assert all(hit[1] != "entry:2" for hit in quick.cache.values())


def test_uncertain_answer_does_not_evict_confident_ones():

    answer_fn, _ = counting_answer_fn()
    quick = QuickAnswers(None, None, max_size=1, answer_fn=answer_fn)

    quick.ask("a")
    quick.ask("unsure b")  # not stored, so "a" keeps the only slot
    assert quick.ask("a")[3] is True
