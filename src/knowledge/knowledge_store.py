# ==========================================
# 1. IMPORTS
# ==========================================

# Import logging to record knowledge refresh results
import logging

# Import re to split questions into search words
import re

# Import NumPy for similarity search over stored embeddings
import numpy as np

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
-- Added after the first release, so existing tables gain them too.
-- shortcut: REAL[] + NumPy search instead of pgvector (not installed on this Windows PostgreSQL);
-- switch to a vector(384) column with an HNSW index if entries grow past ~100k.
ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS embedding REAL[];
ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS embedding_model TEXT;
"""

UPSERT_SQL = f"""
INSERT INTO knowledge_entries ({", ".join(ENTRY_COLUMNS)})
VALUES ({", ".join(["%s"] * len(ENTRY_COLUMNS))})
ON CONFLICT (entry_id) DO UPDATE SET
    {", ".join(f"{column} = EXCLUDED.{column}" for column in ENTRY_COLUMNS[1:])},
    updated_at = now(),
    -- Changed content needs a new embedding
    embedding = NULL,
    embedding_model = NULL
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


# ==========================================
# 4. DOCUMENT EMBEDDINGS
# ==========================================

def document_text(question, answer, keywords):
    """
    The text embedded for one entry: question, answer and customer phrases.
    """

    return "\n".join(part for part in (question, answer, keywords) if part)


def refresh_embeddings(conn, embed, model_name):
    """
    Embed every entry that has no embedding yet, or one made by another model.
    New and changed entries lose their embedding in refresh_knowledge,
    so only they are embedded again.

    embed takes a list of texts and returns one list of floats per text.
    Returns the number of entries embedded.
    """

    with conn.transaction():
        rows = conn.execute(
            "SELECT entry_id, question, answer, keywords FROM knowledge_entries "
            "WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM %s",
            [model_name],
        ).fetchall()

        if rows:
            vectors = embed([document_text(*row[1:]) for row in rows])
            with conn.cursor() as cursor:
                cursor.executemany(
                    "UPDATE knowledge_entries SET embedding = %s, embedding_model = %s "
                    "WHERE entry_id = %s",
                    [(list(map(float, vector)), model_name, row[0]) for row, vector in zip(rows, vectors)],
                )

    logger.info("Embeddings refreshed: %s entries embedded with %s.", len(rows), model_name)
    return len(rows)


def search_knowledge(conn, query, embed, limit=5, branch_id=None):
    """
    Return the entries most similar in meaning to query, best first,
    as (entry_id, question, answer, status, score) tuples.

    Embeddings are normalized, so the dot product is the cosine similarity.
    branch_id keeps entries for that branch plus entries for all branches.
    """

    sql = "SELECT entry_id, question, answer, status, embedding FROM knowledge_entries WHERE embedding IS NOT NULL"
    params = []
    if branch_id is not None:
        sql += " AND (branch_id = %s OR branch_id IS NULL)"
        params.append(branch_id)

    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return []

    scores = np.array([row[4] for row in rows]) @ np.array(embed([query])[0])
    best = np.argsort(-scores)[:limit]
    return [(*rows[i][:4], float(scores[i])) for i in best]


# ==========================================
# 5. QUICK ANSWERS
# ==========================================

# Cosine similarity a meaning match needs before it is trusted as the answer
MIN_SCORE = 0.45

# Added to answers whose source data is not confirmed yet
STATUS_NOTES = {
    "pending": " (Please note: this is not confirmed yet; staff can confirm it.)",
    "unavailable": "",
}

NOT_FOUND_ANSWER = "Sorry, I don't have an answer to that yet. A staff member can help."


# Question words that carry no meaning on their own, in English and Roman Urdu.
# The 'simple' text search config has no stopword list, so they are removed here.
# shortcut: fixed list; check new customer phrases against it when aliases are added
KEYWORD_STOPWORDS = {
    # English
    "a", "about", "all", "am", "an", "and", "any", "are", "at", "be", "can", "could",
    "did", "do", "does", "for", "from", "get", "have", "has", "how", "i", "in", "is",
    "it", "many", "me", "much", "my", "of", "on", "or", "please", "some", "tell",
    "the", "there", "this", "to", "we", "what", "when", "where", "which", "will",
    "with", "would", "you", "your",
    # Roman Urdu
    "aap", "aur", "bhi", "hai", "hain", "ka", "kab", "kahan", "ke", "ki", "kitna",
    "kitne", "ko", "kya", "main", "mein", "se",
}


def keyword_words(query):
    """
    The words of query that keyword search looks for.
    Letters and digits only, so the text is a safe tsquery; common words are
    dropped so "can" in "Can I come?" does not match "soft drink can".
    """

    return [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1 and w not in KEYWORD_STOPWORDS]


def keyword_search(conn, query, limit=5, branch_id=None):
    """
    Find entries whose customer phrases (keywords) contain any word of
    query, best ranked first, as (entry_id, question, answer, status, rank).
    Catches Roman Urdu phrases such as "chikkan biryani" that the English
    embedding model scores weakly. Question and answer text is left out,
    so a common word like "sell" in "do you sell cars" does not match.
    branch_id keeps entries for that branch plus entries for all branches.
    """

    words = keyword_words(query)
    if not words:
        return []

    # shortcut: keywords tsvector computed per query (no index); fine for a few thousand entries
    sql = (
        "SELECT entry_id, question, answer, status, "
        "ts_rank(to_tsvector('simple', keywords), q) AS rank "
        "FROM knowledge_entries, to_tsquery('simple', %s) AS q "
        "WHERE to_tsvector('simple', keywords) @@ q"
    )
    params = [" | ".join(words)]
    if branch_id is not None:
        sql += " AND (branch_id = %s OR branch_id IS NULL)"
        params.append(branch_id)

    # entry_id breaks rank ties, so equal matches never come back in arbitrary order
    return conn.execute(sql + " ORDER BY rank DESC, entry_id LIMIT %s", [*params, limit]).fetchall()


# Words that ask whether a branch is open, not where it is ("visit" and "go" alone are not enough)
OPEN_STATUS_WORDS = {
    "now", "tonight", "open", "opening", "operating",
    "close", "closed", "closing", "hours", "timing", "timings",
}

# Words that ask about branch seating; the location entry holds the table and seat counts
SEATING_WORDS = {"seat", "seats", "seating", "capacity"}

# How many matches are checked for the same branch's other entry
OPEN_STATUS_CANDIDATES = 3


def prefer_opening_hours(question, matches, min_score=MIN_SCORE):
    """
    Pick the best match, given matches best first.

    The embedding model reads "Can I visit Gulshan now?" as a location
    question, and keyword search ranks a branch's location and hours entries
    equally because both hold the branch name. So when the best match is a
    branch entry, the question's intent picks between that branch's two
    entries: opening-status words choose hours, seating words choose location.
    The other entry is used only if it is among the matches and scores at
    least min_score (pass 0 for keyword ranks).
    """

    best = matches[0]
    branch, _, kind = best[0].rpartition(":")
    if not branch.startswith("branch:") or kind not in ("hours", "location"):
        return best

    words = set(re.findall(r"\w+", question.lower()))
    if OPEN_STATUS_WORDS & words:
        wanted = "hours"
    elif SEATING_WORDS & words:
        wanted = "location"
    else:
        return best

    wanted_id = f"{branch}:{wanted}"
    return next((m for m in matches if m[0] == wanted_id and m[4] >= min_score), best)


# ------------------------------------------
# Cache confidence
# ------------------------------------------
# A cached answer is replayed for every repeat of the question until it
# expires, so caching needs more confidence than answering once.
#
# Meaning matches: all-MiniLM-L6-v2 scores on the branch and menu entries
# (measured 2026-11-09) put clear questions at 0.60-0.93 ("PECHS timings" 0.62,
# "Where is the Gulshan branch?" 0.62, "Biryani price" 0.71), while answerable
# but weak ones sit at 0.45-0.57 ("Gulshan address" 0.54, "when are you open"
# 0.56). The runner-up score shows ambiguity: "when are you open" scores
# PECHS hours 0.564 and Gulshan hours 0.519 (gap 0.045), a guess between
# branches; clear questions lead by 0.06 or more.
CACHE_MIN_SCORE = 0.60
CACHE_MIN_MARGIN = 0.05

# Keyword matches: ts_rank depends on word counts and weights, not meaning, so it
# is not compared with these thresholds. A keyword answer is cached only when it
# is the only entry matched and its customer phrases hold every searched word.


def answer_is_cacheable(conn, question, matches, chosen, method):
    """
    Whether the answer chosen from matches is confident enough to cache.
    Only approved entries qualify: a pending or unavailable answer is
    searched again on every ask, however high it scores.
    """

    if chosen[3] != "approved":
        return False

    if method == "meaning":
        runner_up = max((m[4] for m in matches if m[0] != chosen[0]), default=0.0)
        # An intent swap picks a lower-scored entry, so its gap is negative and it is not cached
        return chosen[4] >= CACHE_MIN_SCORE and chosen[4] - runner_up >= CACHE_MIN_MARGIN

    if method == "keyword" and len(matches) == 1:
        rows = conn.execute("SELECT keywords FROM knowledge_entries WHERE entry_id = %s", [chosen[0]]).fetchall()
        phrases = set(re.findall(r"\w+", rows[0][0].lower())) if rows else set()
        return set(keyword_words(question)) <= phrases

    return False


def retrieve_answer(conn, question, embed, branch_id=None):
    """
    Answer a customer question from the knowledge base.

    Returns (answer, entry_id, method, cacheable): method is "meaning",
    "keyword" or "none"; cacheable says the answer is confident enough to
    reuse for the same question (see Cache confidence). Unconfirmed answers
    carry a note saying so.
    """

    matches = search_knowledge(conn, question, embed, limit=OPEN_STATUS_CANDIDATES, branch_id=branch_id)
    if matches and matches[0][4] >= MIN_SCORE:
        chosen = prefer_opening_hours(question, matches)
        method = "meaning"
    else:
        matches = keyword_search(conn, question, limit=OPEN_STATUS_CANDIDATES, branch_id=branch_id)
        if not matches:
            return NOT_FOUND_ANSWER, None, "none", False
        chosen = prefer_opening_hours(question, matches, min_score=0)
        method = "keyword"

    entry_id, _, answer, status, _ = chosen
    cacheable = answer_is_cacheable(conn, question, matches, chosen, method)
    return answer + STATUS_NOTES.get(status, ""), entry_id, method, cacheable


def answer_question(conn, question, embed, branch_id=None):
    """
    Answer a customer question: (answer, entry_id, method) from retrieve_answer.
    """

    return retrieve_answer(conn, question, embed, branch_id=branch_id)[:3]
