# ==========================================
# 1. IMPORTS
# ==========================================

import math

import pandas as pd
import pytest

from loading.table_loader import column_type, prepare_rows, to_db_value


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


def test_to_db_value():

    assert to_db_value(math.nan) is None
    assert to_db_value(pd.NaT) is None
    assert to_db_value(pd.Series([3]).iloc[0]) == 3
    assert to_db_value(pd.Timestamp("2026-10-31")) == "2026-10-31 00:00:00"
    assert to_db_value("PKR") == "PKR"


def test_prepare_rows_names_duplicate_keys():

    with pytest.raises(ValueError, match="Duplicate Deal_ID values: DEAL001"):
        prepare_rows(pd.DataFrame({"Deal_ID": ["DEAL001", "DEAL001", "DEAL003"]}), ["Deal_ID"])
