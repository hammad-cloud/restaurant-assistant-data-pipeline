# ==========================================
# 1. IMPORTS
# ==========================================

from contextlib import contextmanager
from types import SimpleNamespace

import pandas as pd
import pytest

from knowledge.knowledge_builder import build_branch_entries, make_entry
from knowledge.knowledge_store import (
    MIN_SCORE,
    answer_question,
    document_text,
    retrieve_answer,
    refresh_knowledge,
    search_knowledge,
)


# ==========================================
# 2. SAMPLE BRANCHES (as in the Branches sheet)
# ==========================================

BRANCHES = {"UTG-KHI-001": "PECHS", "UTG-KHI-002": "Gulshan-e-Iqbal"}
OLD_HOURS_QUESTION = "What are the opening hours of the {} branch?"


def branch_entries():

    return build_branch_entries(pd.DataFrame({
        "Branch_ID": list(BRANCHES),
        "Branch_Name": list(BRANCHES.values()),
        "Address_Demo": ["Main Shahrah-e-Faisal, PECHS, Karachi (demo address)",
                         "Main University Road, Gulshan-e-Iqbal, Karachi (demo address)"],
        "Tables": [18, 24],
        "Seats": [72, 112],
        "Hours": ["24/7", "24/7"],
        "Status": ["Active", "Active"],
    }))


class FakeConn:
    """Stands in for PostgreSQL: execute() returns fixed rows, writes are recorded."""

    def __init__(self, rows):
        self.rows = rows
        self.sql = []
        self.written = []

    @contextmanager
    def transaction(self):
        yield

    @contextmanager
    def cursor(self):
        yield SimpleNamespace(executemany=lambda sql, rows: self.written.extend(rows))

    def execute(self, sql, params=None):
        self.sql.append(sql)
        return SimpleNamespace(fetchall=lambda: self.rows)


# ==========================================
# 3. RENAMED QUESTION UPDATES, NOT DUPLICATES
# ==========================================

def test_renamed_hours_question_updates_existing_entries():

    current = branch_entries()

    # What the knowledge table held before the rename
    stored = [
        make_entry(e["entry_id"], e["topic"], OLD_HOURS_QUESTION.format(BRANCHES[e["branch_id"]]),
                   e["answer"], e["source"], e["status"], e["branch_id"], e["keywords"])
        if e["entry_id"].endswith(":hours") else e
        for e in current
    ]
    conn = FakeConn([(e["entry_id"], e["content_hash"]) for e in stored])

    changes = refresh_knowledge(conn, current)

    hours_ids = {f"branch:{b}:hours" for b in BRANCHES}
    assert changes["changed"] == hours_ids
    assert changes["new"] == set() and changes["removed"] == set()
    # Upserted under the same entry IDs; nothing deleted
    assert {row[0] for row in conn.written} == hours_ids
    assert not any("DELETE" in sql for sql in conn.sql)


# ==========================================
# 4. REAL-MODEL RANKING REGRESSION
# ==========================================

@pytest.fixture(scope="module")
def ranked_conn():

    pytest.importorskip("sentence_transformers")
    from knowledge.embedder import embed_texts

    entries = branch_entries()
    vectors = embed_texts([document_text(e["question"], e["answer"], e["keywords"]) for e in entries])
    rows = [(e["entry_id"], e["question"], e["answer"], e["status"], v) for e, v in zip(entries, vectors)]
    return FakeConn(rows), embed_texts


HOURS_QUESTIONS = [
    "When is the {} branch open?",
    OLD_HOURS_QUESTION,
    "When does the {} branch open?",
    "Is {} branch open now?",
    "What time does {} close?",
    "{} timings",
]
LOCATION_QUESTIONS = [
    "Where is the {} branch?",
    "{} address",
    "How do I get to {}?",
    "Where is {} located?",
]


@pytest.mark.parametrize("branch_id", BRANCHES)
@pytest.mark.parametrize("kind, template", [("hours", q) for q in HOURS_QUESTIONS]
                         + [("location", q) for q in LOCATION_QUESTIONS])
def test_meaning_search_ranks_the_right_branch_entry_first(ranked_conn, branch_id, kind, template):

    conn, embed = ranked_conn
    question = template.format(BRANCHES[branch_id])

    best = search_knowledge(conn, question, embed, limit=1)[0]

    assert best[0] == f"branch:{branch_id}:{kind}", question
    # Above the threshold, so answer_question uses this match instead of the keyword fallback
    assert best[4] >= MIN_SCORE, question


# ==========================================
# 5. OPENING-STATUS INTENT WITH THE REAL MODEL
# ==========================================

@pytest.mark.parametrize("question, expected", [
    # Ranked location first by the model; the intent rule picks hours
    ("Can I visit Gulshan now?", "branch:UTG-KHI-002:hours"),
    ("Can I visit Gulshan-e-Iqbal now?", "branch:UTG-KHI-002:hours"),
    ("Can I go to PECHS now?", "branch:UTG-KHI-001:hours"),
    ("Can I visit PECHS now?", "branch:UTG-KHI-001:hours"),
    ("Is Gulshan-e-Iqbal branch open now?", "branch:UTG-KHI-002:hours"),
    ("Is PECHS branch open now?", "branch:UTG-KHI-001:hours"),
    # Location questions are unchanged
    ("Where is Gulshan?", "branch:UTG-KHI-002:location"),
    ("Where is PECHS?", "branch:UTG-KHI-001:location"),
    ("What is the Gulshan address?", "branch:UTG-KHI-002:location"),
    # "How many seats does Gulshan have?" scores 0.418 < MIN_SCORE; see the keyword fallback tests below
    ("How many seats does Gulshan-e-Iqbal have?", "branch:UTG-KHI-002:location"),
    ("How many seats does PECHS have?", "branch:UTG-KHI-001:location"),
    ("Can I visit Gulshan?", "branch:UTG-KHI-002:location"),
])
def test_answer_question_uses_opening_status_intent(ranked_conn, question, expected):

    conn, embed = ranked_conn

    _, entry_id, method = answer_question(conn, question, embed)

    assert (entry_id, method) == (expected, "meaning"), question


# ==========================================
# 6. KEYWORD FALLBACK WITH THE REAL MODEL
# ==========================================

class FallbackConn(FakeConn):
    """
    Meaning search gets embedding rows; keyword search gets every entry whose
    keywords hold a query word, all with the same rank (as ts_rank gives the
    two entries of one branch), in the order given, so no answer can depend
    on which tied row PostgreSQL happens to return first.
    """

    def __init__(self, rows, entries, reverse):
        super().__init__(rows)
        self.entries = sorted(entries, key=lambda e: e["entry_id"], reverse=reverse)

    def execute(self, sql, params=None):
        if sql.startswith("SELECT keywords"):
            rows = [(e["keywords"],) for e in self.entries if e["entry_id"] == params[0]]
            return SimpleNamespace(fetchall=lambda: rows)
        if "to_tsquery" not in sql:
            return super().execute(sql, params)
        words = set(params[0].split(" | "))
        hits = [(e["entry_id"], e["question"], e["answer"], e["status"], 0.1)
                for e in self.entries if words & set(e["keywords"].lower().replace("-", " ").split())]
        return SimpleNamespace(fetchall=lambda: hits[:params[-1]])


MENU_ENTRY = make_entry("menu:MENU001", "menu_item", "What is Chicken Biryani?",
                        "Chicken Biryani (Pakistani). Price 420 PKR.", "test", "approved",
                        keywords="chicken biryani chikkan biryani")


@pytest.fixture(scope="module")
def fallback_entries(ranked_conn):

    conn, embed = ranked_conn
    vector = embed([document_text(MENU_ENTRY["question"], MENU_ENTRY["answer"], MENU_ENTRY["keywords"])])[0]
    rows = conn.rows + [(MENU_ENTRY["entry_id"], MENU_ENTRY["question"], MENU_ENTRY["answer"],
                         MENU_ENTRY["status"], vector)]
    return rows, branch_entries() + [MENU_ENTRY], embed


@pytest.mark.parametrize("reverse", [False, True], ids=["hours-row-first", "location-row-first"])
@pytest.mark.parametrize("question, expected, expected_method", [
    # Meaning scores 0.443, 0.389 and 0.418 (< MIN_SCORE), so these reach keyword search
    ("Can I come to Gulshan tonight?", "branch:UTG-KHI-002:hours", "keyword"),
    ("Gulshan ki timing kya hai?", "branch:UTG-KHI-002:hours", "keyword"),
    ("How many seats does Gulshan have?", "branch:UTG-KHI-002:location", "keyword"),
    # Menu questions are unaffected: one by meaning, one only the Roman Urdu phrase finds
    ("chikkan biryani milega?", "menu:MENU001", "meaning"),
    ("chikkan milega?", "menu:MENU001", "keyword"),
])
def test_keyword_fallback_uses_branch_intent(fallback_entries, reverse, question, expected, expected_method):

    rows, entries, embed = fallback_entries
    conn = FallbackConn(rows, entries, reverse)

    answer, entry_id, method = answer_question(conn, question, embed)

    assert (entry_id, method) == (expected, expected_method), question
    if expected.endswith(":location"):
        assert "24 tables, 112 seats" in answer


@pytest.mark.parametrize("question", ["Is PECHS branch open now?", "What time does PECHS close?", "PECHS timings"])
def test_pechs_hours_questions_still_answered_by_meaning(fallback_entries, question):

    rows, entries, embed = fallback_entries

    _, entry_id, method = answer_question(FallbackConn(rows, entries, reverse=True), question, embed)

    assert (entry_id, method) == ("branch:UTG-KHI-001:hours", "meaning")


# ==========================================
# 7. CACHE CONFIDENCE WITH THE REAL MODEL
# ==========================================

@pytest.mark.parametrize("question, expected, cacheable", [
    # Clear questions: score >= 0.60 and well ahead of the runner-up
    ("When is the Gulshan-e-Iqbal branch open?", "branch:UTG-KHI-002:hours", True),
    ("PECHS timings", "branch:UTG-KHI-001:hours", True),
    ("Where is the Gulshan branch?", "branch:UTG-KHI-002:location", True),
    ("What is the price of Chicken Biryani?", "menu:MENU001", True),
    # Answered, but not confident enough to replay from the cache
    ("Gulshan address", "branch:UTG-KHI-002:location", False),          # 0.54 < 0.60
    ("when are you open", "branch:UTG-KHI-001:hours", False),           # PECHS 0.564 vs Gulshan 0.519
    ("Can I go to PECHS now?", "branch:UTG-KHI-001:hours", False),      # intent swap over a higher location score
    ("chikkan biryani milega?", "menu:MENU001", False),                 # meaning 0.48
    # Keyword fallback: one entry matched, but "milega" is not one of its phrases
    ("chikkan milega?", "menu:MENU001", False),
    # Keyword fallback: both Gulshan entries match, intent picks one
    ("Can I come to Gulshan tonight?", "branch:UTG-KHI-002:hours", False),
])
def test_cacheable_only_for_confident_answers(fallback_entries, question, expected, cacheable):

    rows, entries, embed = fallback_entries

    _, entry_id, _, is_cacheable = retrieve_answer(FallbackConn(rows, entries, reverse=False), question, embed)

    assert (entry_id, is_cacheable) == (expected, cacheable), question
