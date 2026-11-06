
# ==========================================
# 1. CHANGE DETECTION FUNCTION
# ==========================================

def detect_record_changes(previous_df, current_df, id_column="Menu_ID"):
    """
    Compare previous and current datasets to identify
    new, changed, unchanged, and removed records.
    """

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
