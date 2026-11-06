# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas to create test DataFrames
import pandas as pd

# Import the quarantine function
from validation.quarantine import split_valid_and_invalid_records


# ==========================================
# 2. TEST VALID AND INVALID RECORD SEPARATION
# ==========================================

def test_split_valid_and_invalid_records():

    # Create sample recipe records
    test_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU001", "MENU002"],
        "Ingredient_ID": ["ING001", "ING002", "ING003"],
        "Qty_Per_Portion": [0.5, -3, 0.25]
    })

    # Create a rejected record with its rejection reason
    invalid_records = test_df.loc[[1]].copy()

    invalid_records["rejection_reason"] = (
        "Qty_Per_Portion cannot be negative."
    )

    # Separate valid and rejected records
    valid_records, rejected_records = split_valid_and_invalid_records(
        test_df,
        invalid_records
    )

    # Confirm that two records remain valid
    assert len(valid_records) == 2

    # Confirm that one record was rejected
    assert len(rejected_records) == 1

    # Confirm that the rejected record is MENU001 / ING002
    assert rejected_records.iloc[0]["Ingredient_ID"] == "ING002"

    # Confirm that its rejection reason is preserved
    assert rejected_records.iloc[0]["rejection_reason"] == (
        "Qty_Per_Portion cannot be negative."
    )

    # Confirm that the original DataFrame remains unchanged
    assert len(test_df) == 3

# ==========================================
# 3. TEST SAVING REJECTED RECORDS TO CSV
# ==========================================

def test_save_rejected_records(tmp_path):

    # Import the CSV saving function
    from validation.quarantine import save_rejected_records

    # Create sample rejected recipe records
    rejected_records = pd.DataFrame({
        "Menu_ID": ["MENU001"],
        "Ingredient_ID": ["ING002"],
        "Qty_Per_Portion": [-3],
        "rejection_reason": [
            "Qty_Per_Portion cannot be negative."
        ]
    })

    # Save rejected records into a temporary folder
    saved_file = save_rejected_records(
        rejected_records,
        "recipes",
        output_dir=tmp_path
    )

    # Confirm that the CSV file was created
    assert saved_file is not None, "Expected a CSV file path, but received None."
    assert saved_file.exists()

    # Read the saved CSV file
    saved_records = pd.read_csv(saved_file)

    # Confirm that the saved record is correct
    assert len(saved_records) == 1
    assert saved_records.iloc[0]["Menu_ID"] == "MENU001"

    # Confirm that the rejection reason was preserved
    assert saved_records.iloc[0]["rejection_reason"] == (
        "Qty_Per_Portion cannot be negative."
    )

    # Confirm that the CSV does not contain an extra index column
    assert "Unnamed: 0" not in saved_records.columns


# ==========================================
# 4. TEST EMPTY REJECTED RECORDS
# ==========================================

def test_save_empty_rejected_records(tmp_path):

    # Import the CSV saving function
    from validation.quarantine import save_rejected_records

    # Create an empty DataFrame with the expected columns
    rejected_records = pd.DataFrame(
        columns=[
            "Menu_ID",
            "Ingredient_ID",
            "Qty_Per_Portion",
            "rejection_reason"
        ]
    )

    # Attempt to save the empty rejected dataset
    saved_file = save_rejected_records(
        rejected_records,
        "recipes",
        output_dir=tmp_path
    )

    # Confirm that the function returns None
    assert saved_file is None

    # Confirm that no CSV file was created
    assert list(tmp_path.iterdir()) == []