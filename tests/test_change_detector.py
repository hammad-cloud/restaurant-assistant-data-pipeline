
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
