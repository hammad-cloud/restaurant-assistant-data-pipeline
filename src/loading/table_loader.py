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
