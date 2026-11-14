# ==========================================
# 1. IMPORTS
# ==========================================

# Import logging to record load results
import logging

# Import Pandas to inspect column types and reuse the change detector
import pandas as pd

# Import the reusable change detection and hashing functions
from tracking.change_detector import detect_record_changes
from tracking.record_hasher import add_record_hash

# Import the reusable checks and quarantine used for bad key rows
from validation.data_validator import validate_required_values, validate_unique_values
from validation.quarantine import quarantine_records
from validation.schema_validator import validate_required_columns


# Use the same named logger as the rest of the pipeline
logger = logging.getLogger("restaurant_pipeline")


# ==========================================
# 2. TABLE CATALOG
# ==========================================

# Every data sheet and its primary key columns.
# START_HERE and Dashboard sheets are notes and summaries, not records, so they are skipped.
# To load a new sheet later, add one line here.
TABLES = {
    # Menu workbook (kRpfYv.xlsx)
    "Menu_Items": ("menu", ["Menu_ID"]),
    "Categories": ("menu", ["Category_ID"]),
    "Variants": ("menu", ["Variant_ID"]),
    "Addons": ("menu", ["Addon_ID"]),
    "Item_Addons": ("menu", ["Mapping_ID"]),
    "Branch_Menu": ("menu", ["Branch_Menu_ID"]),
    "Inventory_Links": ("menu", ["Menu_ID", "Branch_ID"]),
    "Item_Aliases": ("menu", ["Alias_ID"]),
    "Deals": ("menu", ["Deal_ID"]),
    "Deal_Items": ("menu", ["Deal_ID", "Menu_ID"]),
    "Allergen_Guide": ("menu", ["Allergen_Code"]),
    "Service_Rules": ("menu", ["Rule_ID"]),
    # Inventory workbook (mMcHmK.xlsx)
    "Branches": ("inventory", ["Branch_ID"]),
    "Ingredients": ("inventory", ["Ingredient_ID"]),
    "Branch_Stock": ("inventory", ["Branch_ID", "Ingredient_ID"]),
    "Recipes": ("inventory", ["Menu_ID", "Ingredient_ID"]),
    "Menu_Availability": ("inventory", ["Menu_ID"]),
    "Stock_Movements": ("inventory", ["Movement_ID"]),
    "Suppliers": ("inventory", ["Supplier_ID"]),
}


# ==========================================
# 3. TABLE PREPARATION
# ==========================================

def column_type(series):
    """
    Map a Pandas column to a PostgreSQL type.

    NUMERIC holds both whole and decimal numbers, so a column that
    switches from 18 to 18.5 in a later workbook still loads.
    """

    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_numeric_dtype(series):
        return "NUMERIC"
    return "TEXT"


def prepare_rows(df, key_columns):
    """
    Add the row_key and record_hash columns used for incremental loads.

    row_key joins the primary key values, so composite keys such as
    (Menu_ID, Ingredient_ID) work with the single-ID change detector.
    """

    missing = [column for column in key_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Key columns missing from sheet: {', '.join(missing)}")

    if df[key_columns].isna().any(axis=None):
        raise ValueError(f"Rows with an empty key ({', '.join(key_columns)}) cannot be loaded.")

    data_columns = list(df.columns)
    prepared = add_record_hash(df, data_columns)
    prepared["row_key"] = prepared[key_columns].astype(str).agg("|".join, axis=1)

    # Name the duplicated keys, so the Excel sheet can be fixed directly
    duplicated = sorted(prepared.loc[prepared["row_key"].duplicated(), "row_key"].unique())
    if duplicated:
        raise ValueError(
            f"Duplicate {', '.join(key_columns)} values: {', '.join(duplicated[:10])}"
            + (f" and {len(duplicated) - 10} more" if len(duplicated) > 10 else "")
        )

    return prepared, data_columns


def to_db_value(value):
    """
    Convert one cell to a value psycopg can store: NaN becomes NULL,
    numbers stay numbers, everything else (dates included) becomes text.
    """

    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if hasattr(value, "item"):
        # numpy scalars to plain Python numbers
        return value.item()
    return str(value)


# ==========================================
# 4. LOAD ONE TABLE
# ==========================================

def sync_table(conn, sheet_name, df, key_columns):
    """
    Make the PostgreSQL table for one sheet match df in one transaction:
    insert new rows, rewrite changed rows, delete removed rows.
    Unchanged rows keep their loaded_at time.

    The table is created on first load, and columns added to the sheet
    later are added to the table automatically.

    Returns the new/changed/unchanged/removed row keys.
    """

    # An empty sheet would delete everything; treat it as an error instead
    if df.empty:
        raise ValueError(f"Sheet {sheet_name} has no rows; refusing to empty its table.")

    table = sheet_name.lower()
    prepared, data_columns = prepare_rows(df, key_columns)
    db_columns = [column.lower() for column in data_columns]

    with conn.transaction():
        conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{table}" ('
            "row_key TEXT PRIMARY KEY, record_hash TEXT NOT NULL, "
            "loaded_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        for column, db_column in zip(data_columns, db_columns):
            conn.execute(
                f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS '
                f'"{db_column}" {column_type(df[column])}'
            )

        stored_df = pd.DataFrame(
            conn.execute(f'SELECT row_key, record_hash FROM "{table}"').fetchall(),
            columns=["row_key", "record_hash"],
        )

        # Reuse the snapshot change detector (it also rejects duplicate keys)
        changes = detect_record_changes(stored_df, prepared[["row_key", "record_hash"]], "row_key")

        write_columns = ["row_key", "record_hash", *db_columns]
        quoted = ", ".join(f'"{column}"' for column in write_columns)
        upsert_sql = (
            f'INSERT INTO "{table}" ({quoted}) '
            f'VALUES ({", ".join(["%s"] * len(write_columns))}) '
            "ON CONFLICT (row_key) DO UPDATE SET "
            + ", ".join(f'"{column}" = EXCLUDED."{column}"' for column in write_columns[1:])
            + ", loaded_at = now()"
        )

        to_write = prepared[prepared["row_key"].isin(changes["new"] | changes["changed"])]
        with conn.cursor() as cursor:
            cursor.executemany(upsert_sql, [
                tuple(to_db_value(value) for value in row)
                for row in to_write[["row_key", "record_hash", *data_columns]].itertuples(index=False)
            ])

        if changes["removed"]:
            conn.execute(
                f'DELETE FROM "{table}" WHERE row_key = ANY(%s)',
                [list(changes["removed"])],
            )

    logger.info(
        "Table %s loaded: %s new, %s changed, %s unchanged, %s removed.",
        table,
        *(len(changes[kind]) for kind in ("new", "changed", "unchanged", "removed")),
    )
    return changes


# ==========================================
# 5. BAD KEY QUARANTINE
# ==========================================

def quarantine_bad_keys(df, sheet_name, key_columns, rejected_dir):
    """
    Move rows with an empty or repeated key to data/rejected/, so one bad
    row does not stop the rest of the sheet from loading.
    Every copy of a repeated key is rejected, because there is no way to
    tell which copy is right. Returns only the good rows.
    """

    name = sheet_name.lower()

    # A missing key column is a problem with the whole sheet, not one row
    validate_required_columns(df, key_columns, sheet_name)

    before = len(df)
    df = quarantine_records(
        df, validate_required_values(df, key_columns), f"{name}_missing_keys", rejected_dir
    )
    df = quarantine_records(
        df, validate_unique_values(df, key_columns), f"{name}_duplicate_keys", rejected_dir
    )

    if len(df) < before:
        logger.warning("Table %s: %s row(s) with a bad key moved to %s.", name, before - len(df), rejected_dir)
    return df


# ==========================================
# 6. LOAD ALL TABLES
# ==========================================

def load_all_tables(conn, menu_excel, inventory_excel, overrides, rejected_dir="data/rejected"):
    """
    Load every sheet in TABLES into its own table.

    overrides maps a sheet name to an already validated and cleaned
    DataFrame (such as Menu_Items and Recipes), which is loaded instead
    of the raw sheet.

    Use an autocommit connection, so each table commits on its own.

    In a raw sheet, rows with an empty or repeated key are saved to
    rejected_dir and the good rows still load. A sheet that fails
    (missing sheet or key column, no good rows, database error) is
    rolled back and keeps its previous data; the other sheets still
    load. Returns (results, failures): failures maps each failed sheet
    name to its error message.
    """

    workbooks = {"menu": menu_excel, "inventory": inventory_excel}
    results = {}
    failures = {}

    for sheet_name, (workbook, key_columns) in TABLES.items():
        try:
            df = overrides.get(sheet_name)
            if df is None:
                df = pd.read_excel(workbooks[workbook], sheet_name=sheet_name)
                df = quarantine_bad_keys(df, sheet_name, key_columns, rejected_dir)
            results[sheet_name] = sync_table(conn, sheet_name, df, key_columns)
        except Exception as error:
            failures[sheet_name] = f"{type(error).__name__}: {error}"
            logger.error("Table %s not loaded; it keeps its previous data. %s", sheet_name.lower(), failures[sheet_name])

    return results, failures
