# Restaurant Assistant Data Pipeline

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
- SQLAlchemy
- Pydantic
- pgvector

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

## Usage

Run the pipeline:

```powershell
python src/inspect_workbooks.py
```

Rejected records are saved as CSV files in `data/rejected/`, one file per check
(for example `rejected_menu_prices.csv`). Each run replaces these files, and a file
is removed when its check finds nothing.

The validated menu and recipes are saved with a `record_hash` column to
`data/processed/menu_items.csv` and `data/processed/recipes.csv`.
The first run saves a baseline; later runs report new, changed, unchanged and removed records.

Run the tests:

```powershell
python -m pytest -v
```

## Project Status

Under development.
