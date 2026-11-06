# ==========================================
# 1. IMPORTS
# ==========================================

# Import Path to manage folders and file paths
from pathlib import Path

# Import Pandas to read and write snapshot files
import pandas as pd

# Import the reusable change detection function
from tracking.change_detector import detect_record_changes


# ==========================================
# 2. LOAD SNAPSHOT
# ==========================================

def load_snapshot(snapshot_path, id_column="Menu_ID"):
    """
    Load the previous snapshot, or return None if it does not exist.
    """

    # Report a missing snapshot as None (first run)
    path = Path(snapshot_path)
    if not path.exists():
        return None

    # Accept one ID column or a list of ID columns
    id_columns = [id_column] if isinstance(id_column, str) else list(id_column)

    # Read IDs and stored hashes as text so they are compared exactly
    text_columns = {column: str for column in id_columns + ["record_hash"]}
    return pd.read_csv(path, dtype=text_columns)


# ==========================================
# 3. SAVE SNAPSHOT
# ==========================================

def save_snapshot(df, snapshot_path):
    """
    Save a snapshot through a temporary file, so the old snapshot
    is replaced only after the new one is fully written.
    """

    # Create the output directory if it does not exist
    path = Path(snapshot_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write next to the real file so the final swap stays on one drive
    temp_path = path.with_name(path.name + ".tmp")

    try:
        # Write the complete snapshot into the temporary file
        df.to_csv(temp_path, index=False)

        # Replace the old snapshot only after the write succeeded
        temp_path.replace(path)

    except Exception:
        # Remove the partial file and keep the old snapshot untouched
        temp_path.unlink(missing_ok=True)
        raise

    # Return the location of the saved snapshot
    return path


# ==========================================
# 4. COMPARE AND UPDATE SNAPSHOT
# ==========================================

def update_snapshot(current_df, snapshot_path, id_column="Menu_ID"):
    """
    Compare the current hashed dataset with the previous snapshot,
    then save the current dataset as the new snapshot.

    Returns None on the first run (baseline), otherwise the
    new/changed/unchanged/removed record IDs.
    """

    # Load the previous snapshot before it is overwritten
    previous_df = load_snapshot(snapshot_path, id_column)

    # Compare stored hashes only when a previous snapshot exists
    changes = None
    if previous_df is not None:
        changes = detect_record_changes(previous_df, current_df, id_column)

    # Save the current dataset as the new snapshot
    save_snapshot(current_df, snapshot_path)

    # Return the comparison result (None means baseline)
    return changes
