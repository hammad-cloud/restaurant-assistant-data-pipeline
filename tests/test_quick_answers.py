# ==========================================
# 1. IMPORTS
# ==========================================

from types import SimpleNamespace

import pytest

from database.connection import DatabaseConfigurationError, connect_to_test_database
from knowledge.knowledge_builder import make_entry
from knowledge.knowledge_store import (
    NOT_FOUND_ANSWER,
    answer_question,
    create_knowledge_table,
    refresh_embeddings,
    refresh_knowledge,
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
# 2b. MENU QUESTION VARIATIONS (fake connection, no database)
# ==========================================

BIRYANI_ANSWER = "Chicken Biryani (Pakistani). Price 420 PKR."


class FakeConn:
    """Serves knowledge_entries rows to warm() and records every SQL statement."""

    def __init__(self, frequent=()):
        self.sql = []
        self.frequent = [(q,) for q in frequent]
        self.rows = [
            ("menu:MENU001", "menu_item", "What is Chicken Biryani?", BIRYANI_ANSWER, None, "approved"),
            ("branch:UTG-KHI-002:hours", "opening_hours",
             "What are the opening hours of the Gulshan-e-Iqbal branch?",
             "The Gulshan-e-Iqbal branch is open 24/7.", "UTG-KHI-002", "approved"),
            ("menu:MENU002", "menu_item", "What is Mutton Karahi?", "Mutton Karahi. Price 900 PKR.", None, "pending"),
        ]

    def execute(self, sql, params=None):
        self.sql.append(sql)
        if "FROM knowledge_entries" in sql:
            # Mirrors the status filter warm() puts in its SQL
            assert "WHERE status = 'approved'" in sql
            rows = [r[:5] for r in self.rows if r[5] == "approved"]
        else:
            rows = self.frequent if "FROM question_log" in sql else []
        return SimpleNamespace(fetchall=lambda: rows)


def warmed(answer_fn, frequent=()):

    conn = FakeConn(frequent)
    quick = QuickAnswers(conn, lambda texts: [[0.0]] * len(texts), answer_fn=answer_fn)
    quick.warm()
    return quick, conn


@pytest.mark.parametrize("question", [
    "What is Chicken Biryani?",
    "What is the price of Chicken Biryani?",
    "How much does Chicken Biryani cost?",
    "tell me about chicken biryani",
])
def test_menu_variations_are_cache_hits_for_the_canonical_entry(question):

    def fail(*args, **kwargs):
        raise AssertionError("knowledge base searched for a known menu variation")

    quick, _ = warmed(fail)

    for _ in range(2):  # first ask and repeat are both served from cache
        assert quick.ask(question) == (BIRYANI_ANSWER, "menu:MENU001", "exact", True)


def test_variations_add_cache_keys_but_no_knowledge_entries():

    answer_fn, _ = counting_answer_fn()
    quick, conn = warmed(answer_fn)

    menu_keys = [key for key, hit in quick.cache.items() if hit[1] == "menu:MENU001"]
    assert len(menu_keys) == 4
    assert not any("INSERT" in sql or "UPDATE" in sql for sql in conn.sql)


@pytest.mark.parametrize("question", ["What is Mutton Karahi?", "How much does Mutton Karahi cost?"])
def test_pending_canonical_entries_and_variations_are_not_preloaded(question):

    answer_fn, calls = counting_answer_fn()
    quick, _ = warmed(answer_fn)

    assert all(hit[1] != "menu:MENU002" for hit in quick.cache.values())
    assert quick.ask(question)[3] is False  # searched, not served from the warm cache
    assert calls == [question]


def test_unknown_questions_still_use_semantic_retrieval():

    answer_fn, calls = counting_answer_fn()
    quick, _ = warmed(answer_fn)

    # Variation templates are applied to menu entries only
    assert quick.ask("Tell me about the Gulshan-e-Iqbal branch")[2:] == ("meaning", False)
    assert quick.ask("Is chicken biryani spicy?")[2:] == ("meaning", False)
    assert len(calls) == 2


def test_variation_cache_stays_isolated_per_branch():

    answer_fn, calls = counting_answer_fn()
    quick, _ = warmed(answer_fn)

    # A branch-specific ask is searched for that branch, then cached for it only
    assert quick.ask("How much does Chicken Biryani cost?", branch_id="UTG-KHI-001")[3] is False
    assert quick.ask("How much does Chicken Biryani cost?", branch_id="UTG-KHI-001")[3] is True
    assert quick.ask("How much does Chicken Biryani cost?", branch_id="UTG-KHI-002")[3] is False
    assert calls == ["How much does Chicken Biryani cost?"] * 2

    # A branch entry is warmed for its own branch, never another one
    hours = "What are the opening hours of the Gulshan-e-Iqbal branch?"
    assert quick.ask(hours, branch_id="UTG-KHI-002")[3] is True
    assert quick.ask(hours, branch_id="UTG-KHI-001")[3] is False


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


def test_warm_preloads_only_confident_frequent_questions():

    answer_fn, calls = counting_answer_fn()
    quick, _ = warmed(answer_fn, frequent=["Biryani price?", "unsure thing", "unknown thing"])

    assert calls == ["Biryani price?", "unsure thing", "unknown thing"]
    assert quick.ask("biryani price")[3] is True
    assert quick.ask("unsure thing")[3] is False
    assert quick.ask("unknown thing")[3] is False
    # Canonical questions are still warmed without a search
    assert quick.ask("What is Chicken Biryani?")[3] is True


# ==========================================
# 3. DATABASE TESTS (test database only)
# ==========================================

def fake_embed(texts):

    # Deterministic 3-number "embeddings": hours, biryani, sales
    return [
        [float("hours" in t or "open" in t), float("biryani" in t.lower()), float("sales" in t.lower())]
        for t in texts
    ]


@pytest.fixture
def conn():

    try:
        connection = connect_to_test_database()
    except DatabaseConfigurationError:
        pytest.skip("Test database settings (PG* variables) are not set.")

    connection.autocommit = True
    connection.execute("DROP TABLE IF EXISTS knowledge_entries")
    connection.execute("DROP TABLE IF EXISTS question_log")
    create_knowledge_table(connection)
    refresh_knowledge(connection, [
        make_entry("branch:UTG-KHI-002:hours", "opening_hours",
                   "What are the opening hours of the Gulshan-e-Iqbal branch?",
                   "The Gulshan-e-Iqbal branch is open 24/7.", "test", "approved",
                   branch_id="UTG-KHI-002"),
        make_entry("menu:MENU001", "menu_item", "What is Chicken Biryani?",
                   "Chicken Biryani (Pakistani). Price 420 PKR.", "test", "approved",
                   keywords="chicken biryani chikkan biryani"),
        make_entry("menu:MENU002", "menu_item", "What is Mutton Karahi?",
                   "Mutton Karahi. Price 900 PKR.", "test", "pending",
                   keywords="mutton karahi"),
    ])
    refresh_embeddings(connection, fake_embed, "fake")

    yield connection
    connection.execute("DROP TABLE IF EXISTS question_log")
    connection.close()


def test_answer_by_meaning_keyword_and_not_found(conn):

    assert answer_question(conn, "when are you open", fake_embed)[1:] == ("branch:UTG-KHI-002:hours", "meaning")

    # No meaning match, but the Roman Urdu phrase is in the keywords
    answer, entry_id, method = answer_question(conn, "chikkan milega?", fake_embed)
    assert (entry_id, method) == ("menu:MENU001", "keyword")
    assert "not confirmed" not in answer

    answer, entry_id, method = answer_question(conn, "karahi milega?", fake_embed)
    assert (entry_id, method) == ("menu:MENU002", "keyword")
    assert "not confirmed" in answer  # pending entries carry a note

    assert answer_question(conn, "do you sell cars", fake_embed) == (NOT_FOUND_ANSWER, None, "none")


def test_warm_caches_knowledge_questions_without_searching(conn):

    def fail(*args, **kwargs):
        raise AssertionError("knowledge base searched for a warmed question")

    quick = QuickAnswers(conn, fake_embed, answer_fn=fail)
    quick.warm()

    answer, entry_id, method, from_cache = quick.ask("what is chicken biryani")
    assert (entry_id, method, from_cache) == ("menu:MENU001", "exact", True)
    assert quick.ask("What are the opening hours of the Gulshan-e-Iqbal branch?",
                     branch_id="UTG-KHI-002")[3] is True
    assert all(hit[1] != "menu:MENU002" for hit in quick.cache.values())  # pending entry not preloaded


def test_counts_are_saved_and_frequent_questions_warm_next_session(conn):

    with QuickAnswers(conn, fake_embed) as quick:
        for _ in range(3):
            quick.ask("Biryani price?")
        quick.ask("when are you open")

    with QuickAnswers(conn, fake_embed) as quick:
        quick.ask("biryani price")
        assert quick.top_questions()[0] == ("Biryani price?", 4)

    # A new session preloads the frequent question, so it is cached on first ask
    quick = QuickAnswers(conn, fake_embed)
    quick.warm()
    assert quick.ask("biryani price")[3] is True


def test_keyword_answers_cached_only_when_unambiguous_in_database(conn):

    quick = QuickAnswers(conn, fake_embed)

    # Every searched word is in the one matching entry's customer phrases
    # (fake_embed scores "chikkan" 0 everywhere, so it reaches keyword search)
    assert quick.ask("Chikkan?")[1:] == ("menu:MENU001", "keyword", False)
    assert quick.ask("chikkan")[3] is True

    # "milega" is not in its phrases: answered by keyword each time, never cached
    for _ in range(2):
        assert quick.ask("chikkan milega?")[1:] == ("menu:MENU001", "keyword", False)


def test_pending_keyword_answer_is_never_cached_in_database(conn):

    quick = QuickAnswers(conn, fake_embed)

    # "karahi" is among the pending entry's phrases, so only its status blocks caching
    for _ in range(2):
        answer, entry_id, method, from_cache = quick.ask("karahi")
        assert (entry_id, method, from_cache) == ("menu:MENU002", "keyword", False)
        assert "not confirmed" in answer
