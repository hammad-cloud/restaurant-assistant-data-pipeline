
# ==========================================
# 1. SCHEMA VALIDATION FUNCTION
# ==========================================

def validate_required_columns(df, required_columns, dataset_name):
    """
    Check whether a DataFrame contains all required columns.
    """

    # Identify required columns that are missing
    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    # Stop processing if required columns are missing
    if missing_columns:
        raise ValueError(
            f"{dataset_name} is missing required columns: {missing_columns}"
        )

    # Confirm that the dataset structure is valid
    return True
