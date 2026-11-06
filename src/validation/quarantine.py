# ==========================================
# 1. IMPORTS
# ==========================================

# Import Path to manage folders and file paths
from pathlib import Path

# Import datetime to generate unique batch timestamps
from datetime import datetime


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
    Save rejected records into a timestamped CSV file.
    """

    # Skip file creation when there are no rejected records
    if rejected_records.empty:
        print("No rejected records to save.")
        return None

    # Create the output directory if it does not exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate a timestamp for the rejection batch
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create a unique filename for this dataset and batch
    file_path = output_path / f"rejected_{dataset_name}_{timestamp}.csv"

    # Save rejected records without the DataFrame index
    rejected_records.to_csv(file_path, index=False)

    # Return the location of the saved file
    return file_path
