# ==========================================
# 1. IMPORTS
# ==========================================

# Import Path to manage folders and file paths
from pathlib import Path


# ==========================================
# 2. RECORD QUARANTINE FUNCTION
# ==========================================

def split_valid_and_invalid_records(df, invalid_records):
    """
    Separate valid records from invalid records
    while preserving their individual rejection reasons.
    """

    # Get the original row indexes of invalid records
    invalid_indexes = invalid_records.index

    # Keep records that passed validation
    valid_records = df.drop(
        index=invalid_indexes
    ).copy()

    # Preserve rejected records and their rejection reasons
    rejected_records = invalid_records.copy()

    # Return both datasets
    return valid_records, rejected_records

# ==========================================
# 3. SAVE REJECTED RECORDS
# ==========================================

def save_rejected_records(rejected_records, dataset_name, output_dir="data/rejected"):
    """
    Save rejected records into one CSV file per dataset.

    The file always holds the rejects of the latest run, so
    repeated runs do not pile up duplicate files.
    """

    # Use one fixed file per dataset
    output_path = Path(output_dir)
    file_path = output_path / f"rejected_{dataset_name}.csv"

    # Skip file creation when there are no rejected records
    if rejected_records.empty:

        # Remove the previous run's file, so it is not mistaken for current rejects
        file_path.unlink(missing_ok=True)
        print("No rejected records to save.")
        return None

    # Create the output directory if it does not exist
    output_path.mkdir(parents=True, exist_ok=True)

    # Save rejected records without the DataFrame index
    rejected_records.to_csv(file_path, index=False)

    # Return the location of the saved file
    return file_path


# ==========================================
# 4. QUARANTINE AND REPORT
# ==========================================

def quarantine_records(df, invalid_records, dataset_name, output_dir="data/rejected"):
    """
    Separate invalid records, save them, report the counts,
    and return only the valid records.
    """

    # Separate valid and rejected records
    valid_records, rejected_records = split_valid_and_invalid_records(
        df,
        invalid_records
    )

    # Display the validation results
    print(f"\n{dataset_name}: {len(valid_records)} kept, {len(rejected_records)} rejected")

    # Save rejected records and display the file location
    saved_file = save_rejected_records(rejected_records, dataset_name, output_dir)
    if saved_file:
        print("Rejected records saved to:", saved_file)

    # Return only the records that passed validation
    return valid_records
