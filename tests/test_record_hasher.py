# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas to create sample datasets
import pandas as pd

# Import the record hashing functions
from tracking.record_hasher import (
    generate_record_hash,
    add_record_hash
)


# ==========================================
# 2. SINGLE RECORD HASHING TEST
# ==========================================

def test_generate_record_hash():

    # Create two records with the same information
    record_one = {"Menu_ID": "MENU001", "Price": 500}
    record_two = {"Price": 500, "Menu_ID": "MENU001"}

    # Generate hashes for both records
    hash_one = generate_record_hash(record_one)
    hash_two = generate_record_hash(record_two)

    # Confirm that identical records produce identical hashes
    assert hash_one == hash_two


# ==========================================
# 3. DATAFRAME RECORD HASHING TEST
# ==========================================

def test_add_record_hash():

    # Create a sample menu dataset
    menu_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU002"],
        "Item_Name": ["Chicken Biryani", "Beef Burger"],
        "Price": [500, 650]
    })

    # Add hashes using selected columns
    hashed_df = add_record_hash(
        menu_df,
        ["Menu_ID", "Item_Name", "Price"]
    )

    # Confirm that the hash column was created
    assert "record_hash" in hashed_df.columns

    # Confirm that every record received a hash
    assert hashed_df["record_hash"].notna().all()

    # Confirm that the original dataset remains unchanged
    assert "record_hash" not in menu_df.columns