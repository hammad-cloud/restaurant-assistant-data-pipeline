
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
    Identify records with missing, non-numeric, zero, or negative values
    and attach a specific rejection reason to each record.
    """

    # Convert values to numbers; text such as "N/A" becomes missing
    numeric_values = pd.to_numeric(df[column_name], errors="coerce")

    # Identify records with missing, non-numeric, zero, or negative values
    invalid_mask = numeric_values.isna() | (numeric_values <= 0)
    invalid_records = df[invalid_mask].copy()

    # Generate a rejection reason for each invalid record
    invalid_records["rejection_reason"] = [
        f"{column_name} is missing."
        if pd.isna(value)
        else f"{column_name} is not a number."
        if pd.isna(number)
        else f"{column_name} cannot be zero."
        if number == 0
        else f"{column_name} cannot be negative."
        for value, number in zip(invalid_records[column_name], numeric_values[invalid_mask])
    ]

    # Return invalid records with their rejection reasons
    return invalid_records


# ==========================================
# 3. UNIQUE VALUE VALIDATION
# ==========================================

def validate_unique_values(df, column_name):
    """
    Identify every record whose value in the column (or combination
    of columns, when a list is given) is repeated, and attach a
    rejection reason to each copy.
    """

    # Keep all copies, because the correct one cannot be chosen automatically
    invalid_records = df[
        df[column_name].duplicated(keep=False)
    ].copy()

    # Name the column, or the column combination, in the reason
    label = column_name if isinstance(column_name, str) else " + ".join(column_name)

    # Attach the same rejection reason to every duplicate copy
    invalid_records["rejection_reason"] = f"{label} is duplicated."

    # Return invalid records with their rejection reasons
    return invalid_records


# ==========================================
# 4. REQUIRED VALUE VALIDATION
# ==========================================

def validate_required_values(df, column_names):
    """
    Identify records where any of the given columns is missing
    or blank, and attach a rejection reason to each record.
    """

    # Accept one column name or a list of column names
    if isinstance(column_names, str):
        column_names = [column_names]

    # Treat missing values and blank text as missing
    missing = df[column_names].isna() | (
        df[column_names].astype(str).apply(lambda column: column.str.strip()) == ""
    )

    # Keep records where at least one required value is missing
    invalid_records = df[missing.any(axis=1)].copy()

    # Name the missing columns for each rejected record
    invalid_records["rejection_reason"] = [
        " + ".join(missing.columns[row]) + " is missing."
        for row in missing.loc[invalid_records.index].to_numpy()
    ]

    # Return invalid records with their rejection reasons
    return invalid_records


# ==========================================
# 5. FOREIGN KEY VALIDATION
# ==========================================

def validate_foreign_keys(df, column_name, valid_values, reference_name):
    """
    Identify records whose value does not exist in the reference
    dataset, and attach a rejection reason to each record.
    """

    # Keep records whose value has no match in the reference values
    invalid_records = df[
        ~df[column_name].isin(valid_values)
    ].copy()

    # Attach the rejection reason
    invalid_records["rejection_reason"] = (
        f"{column_name} not found in {reference_name}."
    )

    # Return invalid records with their rejection reasons
    return invalid_records
