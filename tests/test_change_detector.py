
# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas to create sample datasets
import pandas as pd

# Import the change detection function
from tracking.change_detector import detect_record_changes


# ==========================================
# 2. CHANGE DETECTION TEST
# ==========================================

def test_detect_new_changed_unchanged_and_removed_records():

    # Create the previous pipeline dataset
    previous_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU002", "MENU003"],
        "record_hash": ["hash_A", "hash_B", "hash_C"]
    })

    # Create the current pipeline dataset
    current_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU002", "MENU004"],
        "record_hash": ["hash_A", "hash_D", "hash_E"]
    })

    # Compare both datasets
    changes = detect_record_changes(
        previous_df,
        current_df
    )

    # Verify unchanged records
    assert changes["unchanged"] == {"MENU001"}

    # Verify changed records
    assert changes["changed"] == {"MENU002"}

    # Verify new records
    assert changes["new"] == {"MENU004"}

    # Verify removed records
    assert changes["removed"] == {"MENU003"}


# ==========================================
# 3. DUPLICATE ID SAFETY TEST
# ==========================================

def test_duplicate_ids_raise_error():

    # Import pytest to check raised errors
    import pytest

    # Create a current dataset where MENU001 appears twice
    previous_df = pd.DataFrame({"Menu_ID": ["MENU001"], "record_hash": ["hash_A"]})
    current_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU001"],
        "record_hash": ["hash_A", "hash_B"]
    })

    # Confirm that duplicates stop the comparison instead of being merged
    with pytest.raises(ValueError, match="Duplicate Menu_ID"):
        detect_record_changes(previous_df, current_df)


# ==========================================
# 4. COMBINED ID CHANGE DETECTION TEST
# ==========================================

def test_detect_changes_with_combined_ids():

    # Create recipe datasets identified by Menu_ID + Ingredient_ID
    previous_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU001"],
        "Ingredient_ID": ["ING001", "ING002"],
        "record_hash": ["hash_A", "hash_B"]
    })
    current_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU001"],
        "Ingredient_ID": ["ING001", "ING002"],
        "record_hash": ["hash_A", "hash_C"]
    })

    # Compare both datasets using both ID columns
    changes = detect_record_changes(previous_df, current_df, ["Menu_ID", "Ingredient_ID"])

    # Verify that ingredients of the same dish are tracked separately
    assert changes["unchanged"] == {("MENU001", "ING001")}
    assert changes["changed"] == {("MENU001", "ING002")}
    assert changes["new"] == set()
    assert changes["removed"] == set()
