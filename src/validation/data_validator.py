
# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas for DataFrame operations
import pandas as pd


# ==========================================
# 2. POSITIVE VALUE VALIDATION
# ==========================================

def validate_positive_values(df, column_name):
    """
    Identify records with missing, zero, or negative values
    and attach a specific rejection reason to each record.
    """

    # Identify records with missing, zero, or negative values
    invalid_records = df[
        df[column_name].isna() | (df[column_name] <= 0)
    ].copy()

    # Generate a rejection reason for each invalid record
    invalid_records["rejection_reason"] = invalid_records[column_name].apply(
        lambda value:
            f"{column_name} is missing."
            if pd.isna(value)
            else f"{column_name} cannot be zero."
            if value == 0
            else f"{column_name} cannot be negative."
    )

    # Return invalid records with their rejection reasons
    return invalid_records
