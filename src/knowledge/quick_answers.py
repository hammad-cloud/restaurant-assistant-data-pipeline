# ==========================================
# 1. IMPORTS
# ==========================================

# Import logging to record cache warm-up and saved counts
import logging

# Import re to normalize question text
import re

# Import time for cache expiry
import time

# Import OrderedDict to drop the least recently asked questions first
from collections import OrderedDict

# Import the knowledge base answer function
from knowledge.knowledge_store import retrieve_answer

# Import the other phrasings customers use for a menu question
from knowledge.knowledge_builder import menu_question_variations


logger = logging.getLogger("restaurant_pipeline")


# ==========================================
# 2. QUESTION LOG TABLE
# ==========================================

CREATE_QUESTION_LOG_SQL = """
CREATE TABLE IF NOT EXISTS question_log (
    question_key  TEXT PRIMARY KEY,
    question      TEXT NOT NULL,
    times_asked   INTEGER NOT NULL DEFAULT 0,
    last_asked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

SAVE_COUNT_SQL = """
INSERT INTO question_log (question_key, question, times_asked)
VALUES (%s, %s, %s)
ON CONFLICT (question_key) DO UPDATE SET
    times_asked = question_log.times_asked + EXCLUDED.times_asked,
    last_asked_at = now()
"""


def normalize_question(question):
    """
    Turn a question into its cache key: lowercase, punctuation removed,
    spaces collapsed, so "Where is the Gulshan branch??" and
    "where is the gulshan branch" share one cached answer.
    """

    return " ".join(re.findall(r"\w+", question.lower()))


# ==========================================
# 3. QUICK ANSWER CACHE
# ==========================================

class QuickAnswers:
    """
    Answer customer questions, serving repeated and frequent questions
    from memory without searching the knowledge base again.

    Cached answers expire after ttl_seconds, so knowledge updated by the
    pipeline appears without restarting. The cache keeps at most max_size
    questions and drops the least recently asked first.

    Only confident answers are cached (see retrieve_answer); uncertain ones
    are searched again on every ask.

    Use as a context manager: question counts are saved to question_log on close.
    """

    def __init__(self, conn, embed, ttl_seconds=300, max_size=1000,
                 answer_fn=retrieve_answer, clock=time.monotonic):
        self.conn = conn
        self.embed = embed
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.answer_fn = answer_fn
        self.clock = clock
        # (question_key, branch_id) -> (answer, entry_id, method, expires_at)
        self.cache = OrderedDict()
        # question_key -> [question text as first asked, unsaved count]
        self.counts = {}

    # ------------------------------------------
    # Cache helpers
    # ------------------------------------------

    def _store(self, key, answer, entry_id, method):
        self.cache[key] = (answer, entry_id, method, self.clock() + self.ttl_seconds)
        self.cache.move_to_end(key)
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def _cached(self, key):
        hit = self.cache.get(key)
        if hit is None or hit[3] <= self.clock():
            self.cache.pop(key, None)
            return None
        self.cache.move_to_end(key)
        return hit[:3]

    # ------------------------------------------
    # Public methods
    # ------------------------------------------

    def ask(self, question, branch_id=None):
        """
        Return (answer, entry_id, method, from_cache) for one question.
        """

        question_key = normalize_question(question)
        if not question_key:
            raise ValueError("Question is empty.")

        record = self.counts.setdefault(question_key, [question.strip(), 0])
        record[1] += 1

        key = (question_key, branch_id)
        hit = self._cached(key)
        if hit is not None:
            return (*hit, True)

        answer, entry_id, method, cacheable = self.answer_fn(self.conn, question, self.embed, branch_id=branch_id)
        # Not-found and uncertain answers are not cached, so the next ask searches again
        if cacheable:
            self._store(key, answer, entry_id, method)
        else:
            logger.debug("Not cached (uncertain %s answer): %r", method, question)
        return answer, entry_id, method, False

    def warm(self, top_n=50):
        """
        Preload the cache before the first customer asks:
        every approved knowledge base question with its own answer (one quick query),
        then the top_n most frequently asked questions from question_log
        whose answers are confident enough to cache.

        Returns the number of cached questions.
        """

        self.conn.execute(CREATE_QUESTION_LOG_SQL)

        # Load the embedding model now, so the first uncached question is not slow
        self.embed(["warm up"])

        rows = self.conn.execute(
            "SELECT entry_id, topic, question, answer, branch_id FROM knowledge_entries "
            "WHERE status = 'approved'"
        ).fetchall()
        for entry_id, topic, question, answer, branch_id in rows:
            # Menu phrasings ("How much does X cost?") are extra cache keys for the same entry, not extra entries
            questions = [question] + (menu_question_variations(question) if topic == "menu_item" else [])
            # A branch question is cached for that branch and for "any branch"
            for text in questions:
                for key_branch in {None, branch_id}:
                    self._store((normalize_question(text), key_branch), answer, entry_id, "exact")

        frequent = self.conn.execute(
            "SELECT question FROM question_log ORDER BY times_asked DESC, last_asked_at DESC LIMIT %s",
            [top_n],
        ).fetchall()
        for (question,) in frequent:
            key = (normalize_question(question), None)
            if self._cached(key) is None:
                answer, entry_id, method, cacheable = self.answer_fn(self.conn, question, self.embed)
                if cacheable:
                    self._store(key, answer, entry_id, method)

        logger.info("Quick answer cache warmed: %s questions.", len(self.cache))
        return len(self.cache)

    def save_counts(self):
        """
        Add the question counts since the last save to question_log.
        """

        pending = [(key, text, count) for key, (text, count) in self.counts.items() if count]
        if not pending:
            return 0

        with self.conn.transaction():
            self.conn.execute(CREATE_QUESTION_LOG_SQL)
            with self.conn.cursor() as cursor:
                cursor.executemany(SAVE_COUNT_SQL, pending)

        for record in self.counts.values():
            record[1] = 0
        logger.info("Saved counts for %s questions to question_log.", len(pending))
        return len(pending)

    def top_questions(self, limit=10):
        """
        The most frequently asked questions, as (question, times_asked).
        """

        self.save_counts()
        return self.conn.execute(
            "SELECT question, times_asked FROM question_log ORDER BY times_asked DESC LIMIT %s",
            [limit],
        ).fetchall()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        # shortcut: counts are saved on close only, so a crash loses that session's counts; save every N asks if that matters
        self.save_counts()
