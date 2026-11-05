# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas to create artificial test data
import pandas as pd

# Import the function we want to test
from src.validation.data_validator import validate_positive_values

# ==========================================
# 2. TEST NEGATIVE QUANTITY
# ==========================================

def test_negative_quantity_is_rejected():

    # Create artificial recipe records
    test_df = pd.DataFrame({
        "Qty_Per_Portion": [-3, 0.25]
    })

    # Run the actual validation function
    rejected_records = validate_positive_values(
        test_df,
        "Qty_Per_Portion"
    )

    # Confirm that exactly one record was rejected
    assert len(rejected_records) == 1

    # Confirm that the rejected quantity is -3
    assert rejected_records.iloc[0]["Qty_Per_Portion"] == -3

    # Confirm that the rejection reason is correct
    assert rejected_records.iloc[0]["rejection_reason"] == (
        "Qty_Per_Portion cannot be negative."
    )


    # ==========================================
# 3. TEST ZERO QUANTITY
# ==========================================

def test_zero_quantity_is_rejected():

    # Create an artificial recipe record with zero quantity
    test_df = pd.DataFrame({
        "Qty_Per_Portion": [0]
    })

    # Run the actual validation function
    rejected_records = validate_positive_values(
        test_df,
        "Qty_Per_Portion"
    )

    # Confirm that exactly one record was rejected
    assert len(rejected_records) == 1

    # Confirm that the rejected quantity is zero
    assert rejected_records.iloc[0]["Qty_Per_Portion"] == 0

    # Confirm that the rejection reason is correct
    assert rejected_records.iloc[0]["rejection_reason"] == (
        "Qty_Per_Portion cannot be zero."
    )

    # ==========================================
# 4. TEST MISSING QUANTITY
# ==========================================

def test_missing_quantity_is_rejected():

    # Create an artificial recipe record with a missing quantity
    test_df = pd.DataFrame({
        "Qty_Per_Portion": [None]
    })

    # Run the actual validation function
    rejected_records = validate_positive_values(
        test_df,
        "Qty_Per_Portion"
    )

    # Confirm that exactly one record was rejected
    assert len(rejected_records) == 1

    # Confirm that the quantity is missing
    assert pd.isna(rejected_records.iloc[0]["Qty_Per_Portion"])

    # Confirm that the rejection reason is correct
    assert rejected_records.iloc[0]["rejection_reason"] == (
        "Qty_Per_Portion is missing."
    )

    # ==========================================
# 5. TEST POSITIVE QUANTITY
# ==========================================

def test_positive_quantity_is_accepted():

    # Create an artificial recipe record with a valid quantity
    test_df = pd.DataFrame({
        "Qty_Per_Portion": [0.25]
    })

    # Run the actual validation function
    rejected_records = validate_positive_values(
        test_df,
        "Qty_Per_Portion"
    )

    # Confirm that no records were rejected
    assert len(rejected_records) == 0