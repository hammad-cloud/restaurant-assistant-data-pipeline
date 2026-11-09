# ==========================================
# 1. IMPORTS
# ==========================================

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
    create_knowledge_table,
    prefer_opening_hours,
    refresh_embeddings,
    refresh_knowledge,
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
