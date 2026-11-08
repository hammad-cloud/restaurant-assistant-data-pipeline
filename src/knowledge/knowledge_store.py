# ==========================================
# 1. IMPORTS
# ==========================================

# Import logging to record knowledge refresh results
import logging

# Import Pandas to reuse the existing change detector
import pandas as pd

# Import the reusable change detection function
from tracking.change_detector import detect_record_changes


# Use the same named logger as the rest of the pipeline
logger = logging.getLogger("restaurant_pipeline")

# Entry fields stored in the table, in insert order
ENTRY_COLUMNS = (
    "entry_id", "topic", "question", "answer", "keywords",
    "branch_id", "status", "source", "content_hash",
)


# ==========================================
# 2. TABLE DEFINITION
# ==========================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_entries (
    entry_id      TEXT PRIMARY KEY,
    topic         TEXT NOT NULL,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    keywords      TEXT NOT NULL DEFAULT '',
    branch_id     TEXT,
    status        TEXT NOT NULL CHECK (status IN ('approved', 'pending', 'unavailable')),
    source        TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Question and customer phrases rank above answer text; 'simple' keeps Roman Urdu words unstemmed
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', question), 'A')
        || setweight(to_tsvector('simple', keywords), 'A')
        || setweight(to_tsvector('english', answer), 'B')
    ) STORED
);
CREATE INDEX IF NOT EXISTS knowledge_entries_search_idx
    ON knowledge_entries USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS knowledge_entries_topic_branch_idx
    ON knowledge_entries (topic, branch_id);
"""

UPSERT_SQL = f"""
INSERT INTO knowledge_entries ({", ".join(ENTRY_COLUMNS)})
VALUES ({", ".join(["%s"] * len(ENTRY_COLUMNS))})
ON CONFLICT (entry_id) DO UPDATE SET
    {", ".join(f"{column} = EXCLUDED.{column}" for column in ENTRY_COLUMNS[1:])},
    updated_at = now()
"""


def create_knowledge_table(conn):
    """
    Create the knowledge table and its indexes if they do not exist.
    """

    with conn.transaction():
        conn.execute(CREATE_TABLE_SQL)


# ==========================================
# 3. REFRESH KNOWLEDGE
# ==========================================

def refresh_knowledge(conn, entries):
    """
    Make the stored knowledge match entries in one transaction:
    insert new entries, rewrite changed ones, delete removed ones.
    Unchanged entries keep their updated_at date.

    Returns the new/changed/unchanged/removed entry IDs.

    Use an autocommit connection: inside an already-open transaction
    this block becomes a savepoint and is only committed by the caller.
    """

    # An empty build would delete everything; treat it as an error instead
    if not entries:
        raise ValueError("No knowledge entries to store; refusing to empty the knowledge base.")

    current_df = pd.DataFrame(
        [(entry["entry_id"], entry["content_hash"]) for entry in entries],
        columns=["entry_id", "record_hash"],
    )

    with conn.transaction():
        stored_df = pd.DataFrame(
            conn.execute("SELECT entry_id, content_hash FROM knowledge_entries").fetchall(),
            columns=["entry_id", "record_hash"],
        )

        # Reuse the snapshot change detector (it also rejects duplicate IDs)
        changes = detect_record_changes(stored_df, current_df, "entry_id")

        to_write = changes["new"] | changes["changed"]
        with conn.cursor() as cursor:
            cursor.executemany(UPSERT_SQL, [
                tuple(entry[column] for column in ENTRY_COLUMNS)
                for entry in entries if entry["entry_id"] in to_write
            ])

        if changes["removed"]:
            conn.execute(
                "DELETE FROM knowledge_entries WHERE entry_id = ANY(%s)",
                [list(changes["removed"])],
            )

    logger.info(
        "Knowledge refreshed: %s new, %s changed, %s unchanged, %s removed.",
        *(len(changes[kind]) for kind in ("new", "changed", "unchanged", "removed")),
    )
    return changes
