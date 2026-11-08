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
from knowledge.knowledge_store import create_knowledge_table, refresh_knowledge


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
