# ==========================================
# 1. IMPORTS
# ==========================================

# Import Path to write the simulated partial file
from pathlib import Path

# Import Pandas to create sample datasets
import pandas as pd

# Import pytest to check raised errors
import pytest

# Import the record hashing function
from tracking.record_hasher import add_record_hash

# Import the snapshot functions
from tracking.snapshot_manager import save_snapshot, update_snapshot


# ==========================================
# 2. SAMPLE DATA HELPER
# ==========================================

def make_menu(ids, prices):

    # Create a hashed sample menu dataset
    menu_df = pd.DataFrame({"Menu_ID": ids, "Price": prices})
    return add_record_hash(menu_df, ["Menu_ID", "Price"])


# ==========================================
# 3. FIRST RUN (BASELINE) TEST
# ==========================================

def test_first_run_saves_baseline(tmp_path):

    # Use a snapshot path inside a folder that does not exist yet
    snapshot_file = tmp_path / "processed" / "menu_items.csv"
    current_df = make_menu(["MENU001", "MENU002"], [450, 650])

    # Run the snapshot update with no previous snapshot
    changes = update_snapshot(current_df, snapshot_file)

    # Confirm that no comparison was made
    assert changes is None

    # Confirm that the folder and snapshot were created with stored hashes
    saved_df = pd.read_csv(snapshot_file)
    assert len(saved_df) == 2
    assert saved_df["record_hash"].tolist() == current_df["record_hash"].tolist()


# ==========================================
# 4. SUBSEQUENT RUN COMPARISON TEST
# ==========================================

def test_subsequent_run_reports_changes(tmp_path):

    # Save the first snapshot
    snapshot_file = tmp_path / "menu_items.csv"
    update_snapshot(make_menu(["MENU001", "MENU002", "MENU003"], [450, 650, 300]), snapshot_file)

    # Create a second run: same, price change, removed, and new item
    current_df = make_menu(["MENU001", "MENU002", "MENU004"], [450.0, 700, 900])

    # Compare against the stored snapshot
    changes = update_snapshot(current_df, snapshot_file)

    # Verify every change category
    assert changes["unchanged"] == {"MENU001"}
    assert changes["changed"] == {"MENU002"}
    assert changes["new"] == {"MENU004"}
    assert changes["removed"] == {"MENU003"}

    # Confirm that the snapshot now holds the current run
    assert pd.read_csv(snapshot_file)["Menu_ID"].tolist() == ["MENU001", "MENU002", "MENU004"]


# ==========================================
# 5. SAFE SNAPSHOT REPLACEMENT TEST
# ==========================================

def test_failed_write_keeps_old_snapshot(tmp_path, monkeypatch):

    # Save a valid first snapshot
    snapshot_file = tmp_path / "menu_items.csv"
    save_snapshot(make_menu(["MENU001"], [450]), snapshot_file)
    original_content = snapshot_file.read_text()

    # Make the next write fail halfway through
    def broken_to_csv(self, path, **kwargs):
        Path(path).write_text("partial")
        raise OSError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_csv", broken_to_csv)

    # Confirm that the error is raised
    with pytest.raises(OSError):
        save_snapshot(make_menu(["MENU002"], [650]), snapshot_file)

    # Confirm that the old snapshot is untouched and no temp file remains
    assert snapshot_file.read_text() == original_content
    assert list(tmp_path.iterdir()) == [snapshot_file]


def test_successful_write_leaves_no_temp_file(tmp_path):

    # Save a snapshot
    snapshot_file = tmp_path / "menu_items.csv"
    save_snapshot(make_menu(["MENU001"], [450]), snapshot_file)

    # Confirm that only the final snapshot remains
    assert list(tmp_path.iterdir()) == [snapshot_file]


# ==========================================
# 6. COMBINED ID SNAPSHOT TEST
# ==========================================

def test_snapshot_with_combined_ids(tmp_path):

    # Create a hashed recipe dataset
    recipe_df = add_record_hash(
        pd.DataFrame({
            "Menu_ID": ["MENU001", "MENU001"],
            "Ingredient_ID": ["ING001", "ING002"],
            "Qty": [0.25, 0.5]
        }),
        ["Menu_ID", "Ingredient_ID", "Qty"]
    )
    snapshot_file = tmp_path / "recipes.csv"
    id_columns = ["Menu_ID", "Ingredient_ID"]

    # Save the baseline, then compare an identical run
    assert update_snapshot(recipe_df, snapshot_file, id_columns) is None
    changes = update_snapshot(recipe_df, snapshot_file, id_columns)

    # Confirm that both ingredients are unchanged
    assert changes["unchanged"] == {("MENU001", "ING001"), ("MENU001", "ING002")}
