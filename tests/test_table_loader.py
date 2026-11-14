# ==========================================
# 1. IMPORTS
# ==========================================

import math

import pandas as pd
import pytest

from database.connection import DatabaseConfigurationError, connect_to_test_database
from loading.table_loader import column_type, prepare_rows, quarantine_bad_keys, sync_table, to_db_value


# ==========================================
# 2. UNIT TESTS (no database)
# ==========================================

def test_column_types():

    assert column_type(pd.Series([1, 2])) == "NUMERIC"
    assert column_type(pd.Series([1.5, None])) == "NUMERIC"
    assert column_type(pd.Series(["a", "b"])) == "TEXT"


def test_prepare_rows_builds_composite_key():

    df = pd.DataFrame({"Menu_ID": ["M1", "M1"], "Ingredient_ID": ["I1", "I2"], "Qty": [0.2, 0.3]})
    prepared, columns = prepare_rows(df, ["Menu_ID", "Ingredient_ID"])

    assert prepared["row_key"].tolist() == ["M1|I1", "M1|I2"]
    assert columns == ["Menu_ID", "Ingredient_ID", "Qty"]
    assert prepared["record_hash"].nunique() == 2


def test_prepare_rows_rejects_missing_or_empty_keys():

    with pytest.raises(ValueError, match="missing"):
        prepare_rows(pd.DataFrame({"A": [1]}), ["Menu_ID"])
    with pytest.raises(ValueError, match="empty key"):
        prepare_rows(pd.DataFrame({"Menu_ID": ["M1", None]}), ["Menu_ID"])


def test_bad_key_rows_are_quarantined_and_good_rows_kept(tmp_path):

    df = pd.DataFrame({
        "Deal_ID": ["D1", "D2", "D2", None, " ", "D3"],
        "Price": [100, 200, 250, 300, 400, 500],
    })

    good = quarantine_bad_keys(df, "Deals", ["Deal_ID"], tmp_path)

    # Every copy of the repeated D2 is rejected, plus the empty and blank keys
    assert good["Deal_ID"].tolist() == ["D1", "D3"]
    assert len(pd.read_csv(tmp_path / "rejected_deals_missing_keys.csv")) == 2
    assert len(pd.read_csv(tmp_path / "rejected_deals_duplicate_keys.csv")) == 2

    # The good rows now pass the loader's own key checks
    prepare_rows(good, ["Deal_ID"])


def test_missing_key_column_still_fails_the_sheet(tmp_path):

    with pytest.raises(ValueError, match="missing required columns"):
        quarantine_bad_keys(pd.DataFrame({"Price": [1]}), "Deals", ["Deal_ID"], tmp_path)


def test_to_db_value():

    assert to_db_value(math.nan) is None
    assert to_db_value(pd.NaT) is None
    assert to_db_value(pd.Series([3]).iloc[0]) == 3
    assert to_db_value(pd.Timestamp("2026-10-31")) == "2026-10-31 00:00:00"
    assert to_db_value("PKR") == "PKR"


# ==========================================
# 3. DATABASE TESTS (test database only)
# ==========================================

@pytest.fixture
def conn():

    try:
        connection = connect_to_test_database()
    except DatabaseConfigurationError:
        pytest.skip("Test database settings (PG* variables) are not set.")

    connection.autocommit = True
    connection.execute('DROP TABLE IF EXISTS "test_sheet"')
    yield connection
    connection.execute('DROP TABLE IF EXISTS "test_sheet"')
    connection.close()


def rows(conn):

    return dict(conn.execute('SELECT row_key, price FROM "test_sheet"').fetchall())


def test_sync_inserts_updates_and_deletes(conn):

    first = pd.DataFrame({"ID": ["A", "B"], "Price": [100, 200]})
    changes = sync_table(conn, "Test_Sheet", first, ["ID"])
    assert changes["new"] == {"A", "B"}
    assert rows(conn) == {"A": 100, "B": 200}

    # Same data again: nothing rewritten
    changes = sync_table(conn, "Test_Sheet", first, ["ID"])
    assert changes["unchanged"] == {"A", "B"}

    # A changes, B is removed, C is new, and a new column appears
    second = pd.DataFrame({"ID": ["A", "C"], "Price": [150.5, 300], "Note": ["x", None]})
    changes = sync_table(conn, "Test_Sheet", second, ["ID"])
    assert (changes["changed"], changes["removed"], changes["new"]) == ({"A"}, {"B"}, {"C"})
    assert rows(conn) == {"A": pytest.approx(150.5), "C": 300}
    assert conn.execute('SELECT note FROM "test_sheet" WHERE row_key = \'C\'').fetchone() == (None,)


def test_sync_refuses_empty_sheet_and_duplicate_keys(conn):

    with pytest.raises(ValueError, match="no rows"):
        sync_table(conn, "Test_Sheet", pd.DataFrame({"ID": []}), ["ID"])
    with pytest.raises(ValueError):
        sync_table(conn, "Test_Sheet", pd.DataFrame({"ID": ["A", "A"]}), ["ID"])


def test_failing_sheet_is_skipped_and_other_sheets_still_load(conn, monkeypatch):

    import loading.table_loader as table_loader

    monkeypatch.setattr(table_loader, "TABLES", {
        "Test_Sheet": ("menu", ["ID"]),
        "Test_Broken": ("menu", ["ID"]),
        "Test_Missing": ("menu", ["ID"]),
    })
    conn.execute('DROP TABLE IF EXISTS "test_broken"')

    # Load good data first, so the broken sheet's old data can be checked
    table_loader.load_all_tables(conn, None, None, overrides={
        "Test_Sheet": pd.DataFrame({"ID": ["A"], "Price": [100]}),
        "Test_Broken": pd.DataFrame({"ID": ["X"], "Price": [1]}),
        "Test_Missing": pd.DataFrame({"ID": ["M"], "Price": [1]}),
    })

    # Test_Broken now has duplicate keys; Test_Missing is not in the workbook at all
    results, failures = table_loader.load_all_tables(conn, {"broken": "workbook"}, None, overrides={
        "Test_Sheet": pd.DataFrame({"ID": ["A"], "Price": [150]}),
        "Test_Broken": pd.DataFrame({"ID": ["X", "X"], "Price": [2, 3]}),
    })

    assert set(failures) == {"Test_Broken", "Test_Missing"}
    assert results["Test_Sheet"]["changed"] == {"A"}
    assert rows(conn) == {"A": 150}
    # The failed sheet was rolled back and keeps its previous data
    assert dict(conn.execute('SELECT row_key, price FROM "test_broken"').fetchall()) == {"X": 1}

    conn.execute('DROP TABLE IF EXISTS "test_broken"')
    conn.execute('DROP TABLE IF EXISTS "test_missing"')


def test_prepare_rows_names_duplicate_keys():

    with pytest.raises(ValueError, match="Duplicate Deal_ID values: DEAL001"):
        prepare_rows(pd.DataFrame({"Deal_ID": ["DEAL001", "DEAL001", "DEAL003"]}), ["Deal_ID"])
