# ==========================================
# QUICK ANSWERS FROM THE KNOWLEDGE BASE
# ==========================================
# Usage:
#   python src/ask.py                         ask questions one after another
#   python src/ask.py "where is gulshan branch"
#   python src/ask.py --branch UTG-KHI-002    answers for one branch
#   python src/ask.py --top                   most frequently asked questions

import argparse
import time

from database.connection import connect_to_production_database
from knowledge.embedder import embed_texts
from knowledge.quick_answers import QuickAnswers


def show(quick, question, branch_id):

    started = time.perf_counter()
    answer, entry_id, method, from_cache = quick.ask(question, branch_id=branch_id)
    elapsed_ms = (time.perf_counter() - started) * 1000
    source = "cache" if from_cache else f"knowledge base ({method})"
    print(f"{answer}\n  [{source}, {entry_id or 'no match'}, {elapsed_ms:.1f} ms]")


def main():

    parser = argparse.ArgumentParser(description="Answer customer questions from the knowledge base.")
    parser.add_argument("question", nargs="*", help="the question; leave out to ask several")
    parser.add_argument("--branch", help="branch ID, for example UTG-KHI-001")
    parser.add_argument("--top", action="store_true", help="show the most frequently asked questions")
    args = parser.parse_args()

    with connect_to_production_database() as conn:
        conn.autocommit = True

        with QuickAnswers(conn, embed_texts) as quick:
            if args.top:
                for question, times_asked in quick.top_questions():
                    print(f"{times_asked:>5}  {question}")
                return

            print("Loading answers...")
            print(f"{quick.warm()} questions ready.\n")

            if args.question:
                show(quick, " ".join(args.question), args.branch)
                return

            print("Ask a question (empty line to quit).")
            while question := input("> ").strip():
                show(quick, question, args.branch)


if __name__ == "__main__":
    main()
