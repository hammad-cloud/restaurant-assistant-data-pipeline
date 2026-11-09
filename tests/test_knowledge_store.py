# ==========================================
# 1. IMPORTS
# ==========================================

# Import SimpleNamespace for a minimal fake query result
from types import SimpleNamespace

# Import pytest for fixtures, skips, and exception checks
import pytest

# Import psycopg to check database constraint errors
import psycopg

# Import the test database connection
from database.connection import DatabaseConfigurationError, connect_to_test_database

# Import the entry helper used to build sample knowledge
from knowledge.knowledge_builder import make_entry

# Import the knowledge store functions
from knowledge.knowledge_store import (
    MIN_SCORE,
    NOT_FOUND_ANSWER,
    answer_question,
    create_knowledge_table,
    keyword_search,
    prefer_opening_hours,
    refresh_embeddings,
    refresh_knowledge,
    retrieve_answer,
    search_knowledge,
)


# ==========================================
# 2. FIXTURES AND HELPERS
# ==========================================

def open_test_database():

    # These are integration tests: skip when no test database is configured
    try:
        connection = connect_to_test_database()
    except DatabaseConfigurationError:
        pytest.skip("Test database settings (PG* variables) are not set.")

    # Each conn.transaction() block then commits on its own
    connection.autocommit = True
    return connection


@pytest.fixture
def conn():

    # Start every test from an empty knowledge table in the TEST database
    connection = open_test_database()
    with connection.transaction():
        connection.execute("DROP TABLE IF EXISTS knowledge_entries")
    create_knowledge_table(connection)

    yield connection
    connection.close()


def sample_entries(hours="24/7"):

    return [
        make_entry("branch:UTG-KHI-002:hours", "opening_hours",
                   "What are the opening hours of the Gulshan-e-Iqbal branch?",
                   f"The Gulshan-e-Iqbal branch is open {hours}.",
                   "test", "approved", branch_id="UTG-KHI-002"),
        make_entry("menu:MENU001", "menu_item", "What is Chicken Biryani?",
                   "Chicken Biryani (Pakistani). Price 420 PKR.",
                   "test", "approved", keywords="chicken biryani chikkan biryani"),
        make_entry("sales:top_10", "popular_items",
                   "What are your 10 most-selling menu items?",
                   "Sales history is not available yet.", "none", "unavailable"),
    ]


def stored(conn):

    # Read the committed table as {entry_id: (answer, updated_at)}
    rows = conn.execute("SELECT entry_id, answer, updated_at FROM knowledge_entries").fetchall()
    return {entry_id: (answer, updated_at) for entry_id, answer, updated_at in rows}


# ==========================================
# 3. REFRESH TESTS
# ==========================================

def test_first_refresh_stores_all_entries_and_commits(conn):

    changes = refresh_knowledge(conn, sample_entries())

    assert len(changes["new"]) == 3

    # A separate connection sees the rows, so they were committed
    with open_test_database() as other:
        row = other.execute(
            "SELECT branch_id, status FROM knowledge_entries WHERE entry_id = %s",
            ["branch:UTG-KHI-002:hours"],
        ).fetchone()
    assert row == ("UTG-KHI-002", "approved")


def test_rerun_without_changes_keeps_updated_at(conn):

    refresh_knowledge(conn, sample_entries())
    before = stored(conn)

    changes = refresh_knowledge(conn, sample_entries())

    assert len(changes["unchanged"]) == 3
    assert stored(conn) == before


def test_changed_entry_is_rewritten_and_removed_entry_deleted(conn):

    refresh_knowledge(conn, sample_entries())
    before = stored(conn)

    # Hours change at Gulshan and the top-10 entry disappears from the source
    changes = refresh_knowledge(conn, sample_entries(hours="10:00-23:00")[:2])
    after = stored(conn)

    assert changes["changed"] == {"branch:UTG-KHI-002:hours"}
    assert changes["removed"] == {"sales:top_10"}
    assert after["branch:UTG-KHI-002:hours"][0].endswith("10:00-23:00.")
    assert after["branch:UTG-KHI-002:hours"][1] > before["branch:UTG-KHI-002:hours"][1]
    assert after["menu:MENU001"] == before["menu:MENU001"]
    assert "sales:top_10" not in after


def test_empty_refresh_is_refused(conn):

    refresh_knowledge(conn, sample_entries())

    with pytest.raises(ValueError):
        refresh_knowledge(conn, [])

    assert len(stored(conn)) == 3


def test_failed_refresh_rolls_back_completely(conn):

    refresh_knowledge(conn, sample_entries())
    before = stored(conn)

    # One valid change plus one entry the table rejects
    entries = sample_entries(hours="Closed") + [
        make_entry("faq:bad", "faq", "Q?", "A.", "test", "not-a-status"),
    ]
    with pytest.raises(psycopg.errors.CheckViolation):
        refresh_knowledge(conn, entries)

    # The valid change was not applied either
    assert stored(conn) == before


# ==========================================
# 4. SEARCH INDEX TEST
# ==========================================

def test_search_vector_covers_customer_phrases(conn):

    refresh_knowledge(conn, sample_entries())

    # A Roman Urdu phrase that appears only in keywords still finds the item
    rows = conn.execute(
        "SELECT entry_id FROM knowledge_entries "
        "WHERE search_vector @@ plainto_tsquery('simple', %s)",
        ["chikkan"],
    ).fetchall()

    assert rows == [("menu:MENU001",)]


# ==========================================
# 4. EMBEDDING TESTS
# ==========================================

def fake_embed(texts):

    # Deterministic 3-number "embeddings": hours, biryani, sales
    return [
        [float("hours" in text or "open" in text), float("biryani" in text.lower()), float("sales" in text.lower())]
        for text in texts
    ]


def test_embeddings_created_once_and_redone_only_for_changed_entries(conn):

    refresh_knowledge(conn, sample_entries())
    assert refresh_embeddings(conn, fake_embed, "fake") == 3

    # Nothing changed: nothing embedded again
    assert refresh_embeddings(conn, fake_embed, "fake") == 0

    # One changed entry: only it is embedded again
    refresh_knowledge(conn, sample_entries(hours="from 9 am to 11 pm"))
    assert refresh_embeddings(conn, fake_embed, "fake") == 1

    # A different model re-embeds everything
    assert refresh_embeddings(conn, fake_embed, "fake-v2") == 3


def test_search_returns_closest_entry_first(conn):

    refresh_knowledge(conn, sample_entries())
    refresh_embeddings(conn, fake_embed, "fake")

    results = search_knowledge(conn, "biryani price", fake_embed, limit=2)
    assert results[0][0] == "menu:MENU001"
    assert len(results) == 2

    # Branch filter keeps that branch plus entries for all branches
    ids = {row[0] for row in search_knowledge(conn, "open", fake_embed, branch_id="UTG-KHI-001")}
    assert "branch:UTG-KHI-002:hours" not in ids


# ==========================================
# OPENING-STATUS INTENT (no database)
# ==========================================

def match(entry_id, score):

    return (entry_id, "question", "answer", "approved", score)


# Ranked as the real model ranked "Can I visit Gulshan-e-Iqbal now?"
GULSHAN_LOCATION_FIRST = [
    match("branch:UTG-KHI-002:location", 0.670),
    match("branch:UTG-KHI-002:hours", 0.607),
    match("branch:UTG-KHI-001:location", 0.410),
]


@pytest.mark.parametrize("question", [
    "Can I visit Gulshan-e-Iqbal now?",
    "Is it open now?",
    "Can I go there now?",
    "Are you open tonight?",
    "Is the branch operating today?",
    "Gulshan opening hours",
])
def test_opening_status_question_prefers_same_branch_hours(question):

    assert prefer_opening_hours(question, GULSHAN_LOCATION_FIRST)[0] == "branch:UTG-KHI-002:hours"


@pytest.mark.parametrize("question", [
    "Can I visit Gulshan?",          # "visit" alone is not an opening-status question
    "How do I go to Gulshan?",
    "Where is Gulshan?",
    "What is the Gulshan address?",
    "How many seats does Gulshan have?",
])
def test_location_question_keeps_best_match(question):

    assert prefer_opening_hours(question, GULSHAN_LOCATION_FIRST)[0] == "branch:UTG-KHI-002:location"


def test_hours_entry_must_be_trusted_and_for_the_same_branch():

    weak_hours = [match("branch:UTG-KHI-002:location", 0.60), match("branch:UTG-KHI-002:hours", MIN_SCORE - 0.01)]
    other_branch = [match("branch:UTG-KHI-002:location", 0.60), match("branch:UTG-KHI-001:hours", 0.59)]
    not_location = [match("menu:MENU001", 0.70), match("branch:UTG-KHI-002:hours", 0.65)]

    assert prefer_opening_hours("open now?", weak_hours)[0] == "branch:UTG-KHI-002:location"
    assert prefer_opening_hours("open now?", other_branch)[0] == "branch:UTG-KHI-002:location"
    # Only a location answer is ever swapped
    assert prefer_opening_hours("biryani now?", not_location)[0] == "menu:MENU001"


# ==========================================
# KEYWORD FALLBACK IGNORES COMMON WORDS (no database)
# ==========================================

class QueryRecorder:
    """Records the tsquery text keyword_search sends; returns no rows."""

    def __init__(self):
        self.queries = []

    def execute(self, sql, params):
        self.queries.append(params[0])
        return SimpleNamespace(fetchall=lambda: [])


@pytest.mark.parametrize("question, tsquery", [
    ("Can I come to Gulshan tonight?", "come | gulshan | tonight"),   # "can" matched "soft drink can"
    ("Gulshan ki timing kya hai?", "gulshan | timing"),               # "ki" matched "pani ki bottle"
    ("Is all food halal?", "food | halal"),                          # "all" matched "All items"
    ("Gulshan-e-Iqbal address", "gulshan | iqbal | address"),        # single letters dropped
    ("chikkan biryani milega?", "chikkan | biryani | milega"),       # customer phrases kept
    ("soft drink can", "soft | drink"),
    ("bbq tea ice", "bbq | tea | ice"),                              # short food words kept
    ("chow mein milega?", "chow | milega"),                          # "chow" still finds Chicken Chow Mein
])
def test_keyword_search_drops_common_words(question, tsquery):

    recorder = QueryRecorder()
    keyword_search(recorder, question)

    assert recorder.queries == [tsquery]


def test_keyword_search_with_only_common_words_does_not_query():

    recorder = QueryRecorder()

    assert keyword_search(recorder, "Can I? Is it? kya hai") == []
    assert recorder.queries == []


def test_keyword_search_common_words_do_not_match_in_database(conn):

    refresh_knowledge(conn, [
        make_entry("menu:MENU031", "menu_item", "What is Mineral Water?", "Mineral Water. Price 100 PKR.",
                   "test", "approved", keywords="mineral water pani ki bottle"),
        make_entry("menu:MENU032", "menu_item", "What is Soft Drink Can?", "Soft Drink Can. Price 150 PKR.",
                   "test", "approved", keywords="soft drink can"),
    ])

    assert keyword_search(conn, "Can I come to Gulshan tonight?") == []
    assert keyword_search(conn, "Gulshan ki timing kya hai?") == []
    assert [row[0] for row in keyword_search(conn, "pani ki bottle")] == ["menu:MENU031"]
    assert [row[0] for row in keyword_search(conn, "soft drink chahiye")] == ["menu:MENU032"]


# ==========================================
# KEYWORD FALLBACK BRANCH INTENT
# ==========================================

def keyword_hit(entry_id):

    # Both entries of one branch get the same ts_rank: their keywords both hold the branch name
    return (entry_id, "question", "answer", "approved", 0.06)


GULSHAN_TIE = [keyword_hit("branch:UTG-KHI-002:hours"), keyword_hit("branch:UTG-KHI-002:location")]


@pytest.mark.parametrize("matches", [GULSHAN_TIE, GULSHAN_TIE[::-1]], ids=["hours-first", "location-first"])
@pytest.mark.parametrize("question, expected", [
    ("Can I come to Gulshan tonight?", "branch:UTG-KHI-002:hours"),
    ("Gulshan ki timing kya hai?", "branch:UTG-KHI-002:hours"),
    ("How many seats does Gulshan have?", "branch:UTG-KHI-002:location"),
    ("Gulshan seating capacity", "branch:UTG-KHI-002:location"),
])
def test_keyword_tie_resolved_by_question_intent(matches, question, expected):

    assert prefer_opening_hours(question, matches, min_score=0)[0] == expected


def test_keyword_intent_never_crosses_branches_or_swaps_menu_items():

    other_branch = [keyword_hit("branch:UTG-KHI-002:location"), keyword_hit("branch:UTG-KHI-001:hours")]
    menu_first = [keyword_hit("menu:MENU001"), keyword_hit("branch:UTG-KHI-002:hours")]

    assert prefer_opening_hours("open tonight?", other_branch, min_score=0)[0] == "branch:UTG-KHI-002:location"
    assert prefer_opening_hours("biryani tonight?", menu_first, min_score=0)[0] == "menu:MENU001"


def test_seating_question_prefers_location_over_hours_in_meaning_search():

    hours_first = [match("branch:UTG-KHI-001:hours", 0.55), match("branch:UTG-KHI-001:location", 0.50)]

    assert prefer_opening_hours("PECHS seats?", hours_first)[0] == "branch:UTG-KHI-001:location"
    # An untrusted location match is not used
    assert prefer_opening_hours("PECHS seats?", hours_first[:1] + [match("branch:UTG-KHI-001:location", 0.30)])[0] \
        == "branch:UTG-KHI-001:hours"


def test_keyword_search_breaks_rank_ties_by_entry_id():

    sql = []
    conn = SimpleNamespace(execute=lambda s, p: sql.append(s) or SimpleNamespace(fetchall=lambda: []))

    keyword_search(conn, "Gulshan")

    assert "ORDER BY rank DESC, entry_id" in sql[0]


def test_keyword_fallback_branch_intent_in_database(conn):

    refresh_knowledge(conn, [
        make_entry("branch:UTG-KHI-002:location", "branch", "Where is the Gulshan-e-Iqbal branch?",
                   "Gulshan-e-Iqbal: Main University Road. 24 tables, 112 seats.", "test", "approved",
                   branch_id="UTG-KHI-002", keywords="Gulshan-e-Iqbal address location"),
        make_entry("branch:UTG-KHI-002:hours", "opening_hours", "When is the Gulshan-e-Iqbal branch open?",
                   "The Gulshan-e-Iqbal branch is open 24/7.", "test", "approved",
                   branch_id="UTG-KHI-002", keywords="Gulshan-e-Iqbal timings open close"),
        make_entry("menu:MENU001", "menu_item", "What is Chicken Biryani?", "Chicken Biryani. Price 420 PKR.",
                   "test", "approved", keywords="chicken biryani chikkan biryani"),
    ])
    # No embeddings stored, so every question reaches keyword search
    no_embed = lambda texts: [[0.0] for _ in texts]

    # The two Gulshan entries tie on rank in PostgreSQL itself
    ranks = {row[0]: row[4] for row in keyword_search(conn, "How many seats does Gulshan have?")}
    assert ranks["branch:UTG-KHI-002:hours"] == ranks["branch:UTG-KHI-002:location"]

    for question, expected in [
        ("Can I come to Gulshan tonight?", "branch:UTG-KHI-002:hours"),
        ("Gulshan ki timing kya hai?", "branch:UTG-KHI-002:hours"),
        ("How many seats does Gulshan have?", "branch:UTG-KHI-002:location"),
        ("chikkan biryani milega?", "menu:MENU001"),
    ]:
        assert answer_question(conn, question, no_embed)[1:] == (expected, "keyword"), question


# ==========================================
# CACHE CONFIDENCE POLICY (no database)
# ==========================================

class ScoredConn:
    """
    Meaning search gets entries scored exactly as given (query embedding [1, 0]);
    keyword search gets the given hits; keyword lookups get the given phrases.
    """

    def __init__(self, scores=(), keyword_hits=(), phrases=None, status="approved"):
        self.rows = [(entry_id, "q", f"answer {entry_id}", status, [score, 0.0]) for entry_id, score in scores]
        self.keyword_hits = list(keyword_hits)
        self.phrases = phrases or {}

    def execute(self, sql, params=None):
        if sql.startswith("SELECT keywords"):
            rows = [(self.phrases[params[0]],)] if params[0] in self.phrases else []
        elif "to_tsquery" in sql:
            rows = self.keyword_hits
        else:
            rows = self.rows
        return SimpleNamespace(fetchall=lambda: rows)


def query_embed(texts):

    return [[1.0, 0.0] for _ in texts]


@pytest.mark.parametrize("scores, cacheable", [
    ([("menu:MENU001", 0.80), ("menu:MENU002", 0.40)], True),     # confident and clear
    ([("menu:MENU001", 0.61), ("menu:MENU002", 0.55)], True),     # just above both limits
    ([("menu:MENU001", 0.55), ("menu:MENU002", 0.20)], False),    # answered (>= MIN_SCORE) but low confidence
    ([("menu:MENU001", 0.70), ("menu:MENU002", 0.68)], False),    # ambiguous: two entries nearly tie
    ([("menu:MENU001", 0.65)], True),                             # only one entry exists
])
def test_meaning_answer_cacheable_by_score_and_margin(scores, cacheable):

    answer, entry_id, method, is_cacheable = retrieve_answer(ScoredConn(scores), "biryani", query_embed)

    assert (entry_id, method, is_cacheable) == ("menu:MENU001", "meaning", cacheable)
    assert answer == "answer menu:MENU001"  # the answer itself never changes


def test_intent_swapped_meaning_answer_is_not_cached():

    conn = ScoredConn([("branch:UTG-KHI-002:location", 0.75), ("branch:UTG-KHI-002:hours", 0.70)])

    assert retrieve_answer(conn, "Is Gulshan open now?", query_embed)[1:] == ("branch:UTG-KHI-002:hours", "meaning", False)


PANI = {"menu:MENU031": "mineral water pani ki bottle"}


@pytest.mark.parametrize("question, hits, phrases, cacheable", [
    # One entry, every searched word among its phrases: cached whatever its ts_rank
    ("pani ki bottle", [keyword_hit("menu:MENU031")], PANI, True),
    ("PANI bottle?", [keyword_hit("menu:MENU031")], PANI, True),
    # One entry, but "thandi" matched nothing: a partial match
    ("thandi pani", [keyword_hit("menu:MENU031")], PANI, False),
    # Two entries matched: ambiguous even though intent picks one
    ("Gulshan tonight", GULSHAN_TIE, {"branch:UTG-KHI-002:hours": "gulshan e iqbal tonight"}, False),
])
def test_keyword_answer_cacheable_only_when_unambiguous(question, hits, phrases, cacheable):

    conn = ScoredConn(keyword_hits=hits, phrases=phrases)

    assert retrieve_answer(conn, question, query_embed)[2:] == ("keyword", cacheable)


def test_keyword_cacheability_ignores_rank_scale():

    tiny_rank = [("menu:MENU031", "q", "a", "approved", 0.0001)]

    assert retrieve_answer(ScoredConn(keyword_hits=tiny_rank, phrases=PANI), "pani", query_embed)[3] is True


@pytest.mark.parametrize("status, cacheable", [("approved", True), ("pending", False), ("unavailable", False)])
def test_high_confidence_meaning_answer_cacheable_only_when_approved(status, cacheable):

    conn = ScoredConn([("menu:MENU001", 0.90), ("menu:MENU002", 0.20)], status=status)

    assert retrieve_answer(conn, "biryani", query_embed)[1:] == ("menu:MENU001", "meaning", cacheable)


@pytest.mark.parametrize("status, cacheable", [("approved", True), ("pending", False), ("unavailable", False)])
def test_unambiguous_keyword_answer_cacheable_only_when_approved(status, cacheable):

    hit = [("menu:MENU031", "q", "a", status, 0.06)]

    assert retrieve_answer(ScoredConn(keyword_hits=hit, phrases=PANI), "pani ki bottle", query_embed)[2:] == ("keyword", cacheable)


def test_not_found_is_never_cacheable():

    assert retrieve_answer(ScoredConn(), "do you sell cars", query_embed) == (NOT_FOUND_ANSWER, None, "none", False)
