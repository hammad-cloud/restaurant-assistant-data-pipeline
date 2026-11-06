# ==========================================
# 1. IMPORTS
# ==========================================

# Import hashlib to generate SHA-256 fingerprints
import hashlib

# Import json to serialize record values consistently
import json

# Import Pandas for DataFrame and missing-value handling
import pandas as pd


# ==========================================
# 2. SINGLE RECORD HASHING FUNCTION
# ==========================================

def generate_record_hash(record):
    """
    Generate a consistent SHA-256 hash for one record.
    """

    # Convert the record into a consistent JSON string
    record_string = json.dumps(
        record,
        sort_keys=True,
        default=str,
        ensure_ascii=False
    )

    # Generate the SHA-256 fingerprint
    record_hash = hashlib.sha256(
        record_string.encode("utf-8")
    ).hexdigest()

    # Return the generated fingerprint
    return record_hash


# ==========================================
# 3. DATAFRAME RECORD HASHING FUNCTION
# ==========================================

def add_record_hash(df, columns, hash_column="record_hash"):
    """
    Add SHA-256 hashes for selected DataFrame columns.

    The original DataFrame remains unchanged.
    """

    # Create a separate copy to protect the original data
    hashed_df = df.copy()

    # Define a function to generate a hash for each row
    def hash_row(row):

        # Standardize missing values as None
        values = [
            None if pd.isna(value) else value
            for value in row
        ]

        # Convert row values into a consistent JSON string
        payload = json.dumps(
            values,
            default=str,
            ensure_ascii=False
        )

        # Generate and return the row fingerprint
        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    # Generate hashes using only the selected columns
    hashed_df[hash_column] = hashed_df[columns].apply(
        hash_row,
        axis=1
    )

    # Return the DataFrame with record hashes
    return hashed_df
