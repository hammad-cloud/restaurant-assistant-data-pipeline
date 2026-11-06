
# ==========================================
# 1. CHANGE DETECTION FUNCTION
# ==========================================

def detect_record_changes(previous_df, current_df, id_column="Menu_ID"):
    """
    Compare previous and current datasets to identify
    new, changed, unchanged, and removed records.

    id_column can be one column name, or a list of column names
    for records identified by a combination (IDs are then tuples).
    """

    # Stop on repeated IDs, because the lookup below would keep only one copy
    for dataset_name, df in [("previous", previous_df), ("current", current_df)]:
        if df[id_column].duplicated().any():
            raise ValueError(f"Duplicate {id_column} values in {dataset_name} dataset.")

    # Create dictionaries for quick record lookup
    previous_records = previous_df.set_index(id_column)["record_hash"].to_dict()
    current_records = current_df.set_index(id_column)["record_hash"].to_dict()

    # Identify records that exist only in the current dataset
    new_ids = set(current_records) - set(previous_records)

    # Identify records that exist in both datasets but have different hashes
    changed_ids = {
        record_id
        for record_id in current_records.keys() & previous_records.keys()
        if current_records[record_id] != previous_records[record_id]
    }

    # Identify records that exist in both datasets with identical hashes
    unchanged_ids = {
        record_id
        for record_id in current_records.keys() & previous_records.keys()
        if current_records[record_id] == previous_records[record_id]
    }

    # Identify records that no longer exist in the current dataset
    removed_ids = set(previous_records) - set(current_records)

    # Return the four categories of record identifiers
    return {
        "new": new_ids,
        "changed": changed_ids,
        "unchanged": unchanged_ids,
        "removed": removed_ids
    }
