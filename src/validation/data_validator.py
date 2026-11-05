
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
    Identify records where a numeric column contains
    zero or negative values.
    """

    # Identify records with zero or negative values
    invalid_records = df[
        df[column_name] <= 0
    ]

    # Return the invalid records for further investigation
    return invalid_records
