# ==========================================
# 1. IMPORTS
# ==========================================

# Import hashlib to generate SHA-256 fingerprints
import hashlib

# Import json to serialize record values consistently
import json

# Import numbers to recognise Python and NumPy numeric values
import numbers

# Import NumPy to recognise NumPy boolean values
import numpy as np

# Import Pandas for DataFrame and missing-value handling
import pandas as pd


# ==========================================
# 1b. VALUE NORMALIZATION FUNCTION
# ==========================================

def normalize_value(value):
    """
    Convert a value into a consistent form before hashing,
    so 450 and 450.0 produce the same hash.
    """

    # Standardize missing values as None
    if pd.isna(value):
        return None

    # Keep True/False as plain booleans (they also count as numbers)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)

    # Convert NumPy and Python integers to plain Python integers
    if isinstance(value, numbers.Integral):
        return int(value)

    # Round away float noise (18.790000000000003 -> 18.79), then
    # convert whole-number decimals such as 450.0 into 450
    if isinstance(value, numbers.Real):
        value = round(float(value), 9)
        return int(value) if value.is_integer() else value

    # Leave text and other values unchanged
    return value


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

        # Standardize missing and numeric values
        values = [
            normalize_value(value)
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
