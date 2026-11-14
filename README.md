# Restaurant Assistant BOT (Data Engineering Pipeline) - PHASE 01

An end-to-end data engineering pipeline for restaurant data.

## Project Goals

- Extract restaurant master data from Excel.
- Validate and clean incoming data.
- Transform data into structured records.
- Load validated records into PostgreSQL.
- Generate documents for semantic retrieval.
- Create and store vector embeddings.

## Technology Stack

- Python
- Pandas
- PostgreSQL
- psycopg 3
- NumPy
- sentence-transformers (`all-MiniLM-L6-v2`, runs locally on CPU)

## Pipeline Stages

```
Excel workbooks (data/raw)
   │  1. Ingest      back up each file (hash + manifest), work on a copy
   ▼
pandas DataFrames
   │  2. Validate    required columns, empty/duplicate IDs, positive prices
   │                 and quantities, recipe → menu foreign keys;
   │                 bad rows go to data/rejected/ instead of stopping the run
   │  3. Transform   standardise menu text and recipe IDs
   │  4. Track       SHA-256 hash per row; compare with the last snapshot
   ▼
PostgreSQL
   │  5. Load        one table per data sheet (19 tables), see below
   │  6. Documents   question/answer knowledge entries → knowledge_entries
   │  7. Embed       384-number sentence embedding per document
   ▼
Semantic search (search_knowledge)
```

### Structured tables

Each data sheet listed in `src/loading/table_loader.py` (`TABLES`) is loaded into a table
with the same name in lowercase (`menu_items`, `recipes`, `branch_stock`, ...).
Every table has:

- `row_key`: the primary key. Composite keys are joined with `|`, for example
  `MENU001|ING002` in `recipes`.
- `record_hash`: a fingerprint of the row, used to spot changes.
- `loaded_at`: the time the row was last written.
- one column per sheet column, lowercase. Number columns are `NUMERIC`, everything else is `TEXT`.

`menu_items` and `recipes` are loaded from the validated data, so rejected rows never reach
the database. The other sheets are loaded as they are, after their keys are checked.

### Future data loads and updates

Replace a workbook in `data/raw/` and run the pipeline again. Each run:

- inserts new rows, rewrites only changed rows, and deletes rows removed from the sheet;
- leaves unchanged rows (and their `loaded_at`) alone;
- adds new sheet columns to the table automatically;
- commits each table on its own, and rolls back that table if anything fails;
- refuses to empty a table when a sheet comes back empty, and rejects empty or duplicate keys;
- re-embeds only the documents whose text changed (or every document if the model changes).

To load a new sheet, add one line to `TABLES` with its workbook and key columns.

### When something fails

The pipeline works like a building. Each table and each pipeline step is its own floor. If one
floor has a problem, only that floor is closed for repair: it keeps its previous data, the other
floors stay open, and nothing has to be reset or rebuilt from scratch. Fix that floor and run again;
only the fixed part is reloaded.

One problem stops only the part it affects:

| Problem | What happens |
|---|---|
| Bad row (negative price, missing ID, duplicate, orphan recipe) | Saved to `data/rejected/`; the good rows load |
| Bad sheet (duplicate or empty keys, sheet missing, no rows) | That table is rolled back and keeps its previous data; the other tables still load |
| Knowledge base step fails | Previous knowledge entries are kept; embeddings still run |
| Embedding step fails | Tables and knowledge are saved; embeddings are retried on the next run |
| Database unreachable, or Menu_Items / Recipes missing required columns | The run stops: later steps cannot work without them |

A run with any failed step ends with a list of what failed and why, for example
`table deals: ValueError: Duplicate Deal_ID values: DEAL001`, logs it as `ERROR`, and exits with
status 1. Fix the sheet and run again; only the fixed part is loaded.

### Price-change demo

> **Warning:** this script runs the full pipeline twice against the **production** database
> (`PGDATABASE`) and changes production data (tables, knowledge entries and embeddings).
> Do not run it as part of a submission or review check.

Shows that a new workbook only rewrites what changed. With the PG* variables set:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/price_change_demo.ps1
```

Step 1 loads `data/demo/kRpfYv_price_demo.xlsx`, a copy of the menu workbook with Chicken Biryani
changed from 420 to 450 PKR. It is designed to show that only the changed menu row, its knowledge
entry and that entry's embedding are rewritten. Step 2 loads the original workbook again and puts the price back. The original Excel file
and its backups are not modified.

To run the pipeline on any other menu workbook, set `RESTAURANT_MENU_FILE` to its path.

### Document embeddings

Each knowledge entry (question, answer and customer phrases) is embedded with
`sentence-transformers/all-MiniLM-L6-v2`. The first run downloads the model (~90 MB) and caches it.
Embeddings are stored in `knowledge_entries.embedding` (`REAL[]`), with the model name in
`embedding_model`. Search them by meaning:

```python
from database.connection import connect_to_production_database
from knowledge.embedder import embed_texts
from knowledge.knowledge_store import search_knowledge

with connect_to_production_database() as conn:
    for entry_id, question, answer, status, score in search_knowledge(conn, "kya biryani milegi?", embed_texts):
        print(round(score, 2), question)
```

pgvector is not installed on this PostgreSQL, so similarity is computed with NumPy.
That is fast for a few thousand documents. For much larger data, install pgvector and switch the
column to `vector(384)` with an HNSW index.

## Project Folder Structure

```text
restaurant-assistant/
├── .gitignore
├── .env.example
├── README.md
├── pyproject.toml
├── requirements.txt
├── scripts/
│   ├── price_change_demo.ps1
│   └── setup_database.sql
├── src/
│   ├── ask.py
│   ├── inspect_workbooks.py
│   ├── logging_config.py
│   ├── database/
│   │   └── connection.py
│   ├── ingestion/
│   │   └── source_backup.py
│   ├── knowledge/
│   │   ├── embedder.py
│   │   ├── knowledge_builder.py
│   │   ├── knowledge_store.py
│   │   └── quick_answers.py
│   ├── loading/
│   │   └── table_loader.py
│   ├── tracking/
│   │   ├── change_detector.py
│   │   ├── record_hasher.py
│   │   └── snapshot_manager.py
│   ├── transformation/
│   │   ├── menu_transformer.py
│   │   └── recipe_transformer.py
│   └── validation/
│       ├── data_validator.py
│       ├── menu_schema.py
│       ├── quarantine.py
│       └── schema_validator.py
└── tests/
    ├── test_branch_hours_retrieval.py
    ├── test_change_detector.py
    ├── test_database_connection.py
    ├── test_data_validator.py
    ├── test_knowledge_builder.py
    ├── test_knowledge_store.py
    ├── test_logging_config.py
    ├── test_menu_transformer.py
    ├── test_quarantine.py
    ├── test_quick_answers.py
    ├── test_recipe_transformer.py
    ├── test_record_hasher.py
    ├── test_schema_validator.py
    ├── test_snapshot_manager.py
    ├── test_source_backup.py
    └── test_table_loader.py
```

The `data/` folder (raw workbooks, backups, processed files, rejected rows and logs) is not shown
because it is kept out of Git; the pipeline reads from and writes to it at run time.

### Root files

| File | Purpose |
|---|---|
| `.env.example` | Lists the PostgreSQL environment variables (`PGHOST`, `PGDATABASE`, ...). Reference only; nothing loads a `.env` file. |
| `.gitignore` | Keeps data files, virtual environments and secrets out of Git. |
| `pyproject.toml` | pytest configuration: adds `src/` to the import path and points pytest at `tests/`. |
| `requirements.txt` | Python dependencies installed with `pip install -r requirements.txt`. |

### Folders

| Folder | Responsibility |
|---|---|
| `scripts/` | Helper scripts run outside the Python pipeline. `setup_database.sql` is the one-time PostgreSQL setup (app user and databases). `price_change_demo.ps1` is the price-change demo, which writes to the **production** database (see the warning above). |
| `src/` | All pipeline source code. Each subfolder groups the code for one part of the pipeline. |
| `src/ingestion/` | **Extract / ingest:** safely backs up the source Excel workbooks before any processing. |
| `src/validation/` | **Data quality:** checks columns and values, and moves bad rows to quarantine. |
| `src/transformation/` | **Transform:** standardises text and IDs so records match across sheets. |
| `src/tracking/` | **Change data capture:** fingerprints rows and compares each run with the previous one. |
| `src/database/` | **Connectivity:** opens PostgreSQL connections from environment variables. |
| `src/loading/` | **Load:** writes the validated sheets into PostgreSQL tables. |
| `src/knowledge/` | **Knowledge base and retrieval:** builds question/answer entries, embeds them and finds the best stored answer for a question. |
| `tests/` | Automated pytest tests (see below). |

### Important files

| File | Role |
|---|---|
| `src/inspect_workbooks.py` | The pipeline entry point (orchestrator). Runs every stage in order (ingest, validate, transform, track, load, build knowledge, embed), runs each step on its own so one failure does not stop the others, and reports what failed at the end. |
| `src/ask.py` | Command-line tool for asking customer questions. It returns stored answers from the knowledge base; it does not generate text. Writes question counts to the **production** database (see the warning under Quick Answers). |
| `src/logging_config.py` | Central logging setup: terminal output plus a rotating log file in `data/logs/`, and logging of unexpected crashes as `CRITICAL`. |
| `src/database/connection.py` | Builds PostgreSQL connections for the production (`PGDATABASE`) and test (`PGDATABASE_TEST`) databases, with clear errors when settings are missing or the server cannot be reached. Passwords are never logged. |
| `src/ingestion/source_backup.py` | Copies each source workbook to a backup folder, records its SHA-256 checksum in a manifest, verifies the copy, and gives the pipeline a working copy so the original file is never modified. |
| `src/loading/table_loader.py` | Lists the sheets to load (`TABLES`) and syncs each one into its own PostgreSQL table: inserts new rows, updates changed rows, deletes removed rows, and rolls back a table if its load fails. |
| `src/knowledge/knowledge_builder.py` | Turns menu items, aliases, branches and service rules into question/answer knowledge entries, each with a status (for example approved or pending). |
| `src/knowledge/knowledge_store.py` | Stores knowledge entries and their embeddings in the `knowledge_entries` table, and searches them by meaning (cosine similarity with NumPy) or by keywords. |
| `src/knowledge/embedder.py` | Converts text into 384-number vectors with the local `all-MiniLM-L6-v2` sentence-transformers model (CPU, no API key). |
| `src/knowledge/quick_answers.py` | The retrieval engine behind `ask.py`: answer cache, meaning search, keyword search and the "no answer" reply, plus question counts in `question_log`. |

The remaining modules support these stages: `record_hasher.py` (row fingerprints),
`change_detector.py` (new / changed / unchanged / removed rows), `snapshot_manager.py` (saved
baseline for comparison), `menu_transformer.py` and `recipe_transformer.py` (standardisation),
`menu_schema.py` (required menu columns), `schema_validator.py` (required-column checks),
`data_validator.py` (positive, unique, required and foreign-key value checks) and `quarantine.py`
(splits off and saves rejected rows).

### Tests

The `tests/` directory contains pytest tests, mostly one file per module, named
`test_<module>.py` (for example `test_table_loader.py` tests `src/loading/table_loader.py`).
Most are unit tests that check one module on its own. `test_branch_hours_retrieval.py` checks
that opening-hours questions retrieve the correct branch-hours answer. The PostgreSQL integration
tests connect only to the test database; see **Run the tests** under Usage for what they change there.

## Setup

1. Create and activate a virtual environment (Windows):

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Install the dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Place the source Excel workbooks in `data/raw/`
   (`kRpfYv.xlsx` and `mMcHmK.xlsx`). They are not stored in Git.

## Database Configuration

One-time setup (creates the app user and both databases; asks for passwords, stores none):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -f scripts/setup_database.sql
```

The PostgreSQL connection module (`src/database/connection.py`) reads its settings
from environment variables. `.env.example` lists them; nothing loads a `.env` file.
Set them in your PowerShell session (the password prompt keeps it off screen and out of history):

```powershell
$env:PGHOST = "localhost"
$env:PGPORT = "5432"
$env:PGUSER = "restaurant_assistant_app"
$env:PGDATABASE = "restaurant_assistant"
$env:PGDATABASE_TEST = "restaurant_assistant_test"
$env:PGPASSWORD = [Net.NetworkCredential]::new("", (Read-Host "PostgreSQL password" -AsSecureString)).Password
```

## Usage

Run the pipeline:

> **Warning:** this command executes the ingestion pipeline and writes to the PostgreSQL database
> configured through `PGDATABASE`. Do not run it against production during submission review.
> Use a controlled test environment for database testing.

```powershell
python src/inspect_workbooks.py
```

The run ends by syncing the knowledge base into the `knowledge_entries` table of the
`PGDATABASE` database (created on first run), so the PostgreSQL variables above must be set.
It stops with an error if they are missing or the database cannot be reached.

Rejected records are saved as CSV files in `data/rejected/`, one file per check
(for example `rejected_menu_prices.csv`). Each run replaces these files, and a file
is removed when its check finds nothing.

The validated menu is saved with a `record_hash` column to `data/processed/menu_items.csv`.
The first run saves a baseline; later runs report new, changed, unchanged and removed menu records.

Each run appends its progress to `data/logs/restaurant_pipeline.log` and prints it to the terminal.
The log starts a new file at 1 MB and keeps the 5 most recent old files (`.log.1` to `.log.5`).
If the pipeline fails unexpectedly, the full traceback is logged as `CRITICAL`, the run exits with a
non-zero status, and no success message is written. Stopping a run with Ctrl+C is not logged as a failure.

Run the tests:

```powershell
python -m pytest -v
```

The PostgreSQL integration tests (in `test_knowledge_store.py`, `test_quick_answers.py` and
`test_table_loader.py`) connect only to the test database (`PGDATABASE_TEST`,
`restaurant_assistant_test`) and are skipped when its settings are not set. Their fixtures
**drop and recreate test tables** (`knowledge_entries`, `question_log`, `test_sheet`) and store
**fake test embeddings** (3 numbers, model name `fake`), replacing any real embeddings in the test
database. Refresh the test database embeddings after running them if you need real ones there.

## Quick Answers

Answers are **retrieved, not generated**: the system returns answer text stored in
`knowledge_entries` (with a note when it is not confirmed). No LLM is used to generate responses.

> **Warning:** `src/ask.py` connects to the **production** database (`PGDATABASE`) and writes to it:
> it creates the `question_log` table if missing and saves question counts when the session ends.
> It is not a safe test command.

`src/ask.py` answers customer questions from the knowledge base:

```powershell
python src/ask.py                          # ask questions one after another
python src/ask.py "where is gulshan branch"
python src/ask.py --branch UTG-KHI-002     # answers for one branch
python src/ask.py --top                    # most frequently asked questions
```

How an answer is found (`src/knowledge/quick_answers.py`):

1. **Cache.** Questions are matched ignoring case, spaces and punctuation. A cached question is
   answered from memory in under 1 ms, with no database lookup and no embedding model.
2. **Meaning.** Otherwise the question is embedded and compared with every stored document.
   A match scoring at least 0.45 is used.
3. **Keywords.** Otherwise the customer phrases (Roman Urdu aliases such as "chikkan biryani")
   are searched.
4. **No match.** The bot says it has no answer and that staff can help. This is not cached.

Answers that are not confirmed yet carry a note saying so.

At startup the cache is filled with the questions of **approved** knowledge entries only (plus the
other phrasings of each approved menu question), and with those of the 50 most frequently asked
questions whose answers are eligible for caching: approved, and a confident, unambiguous match.
Pending and unavailable answers are never cached; they are searched again on every ask.

Each question asked is counted in the `question_log` table when the session ends, so frequent questions are ready instantly next time. Cached answers expire after 5 minutes,
so a pipeline update shows up without a restart.

## Project Status

The seven stages above are implemented and called in order from `python src/inspect_workbooks.py`.

Not included in Phase 01:

- LLM-generated responses (answers are retrieved stored text).
- Best-selling items: no sales data exists, so the bot says this is unavailable.
- Clarifying questions: a question that could match either branch is answered with the best match.
