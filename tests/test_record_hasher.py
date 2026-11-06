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

# ==========================================
# 4. NUMERIC HASH STABILITY TESTS
# ==========================================

def test_integer_and_whole_decimal_produce_same_hash():

    # Create the same price stored as an integer and as a decimal
    int_df = pd.DataFrame({"Menu_ID": ["MENU001"], "Price": [450]})
    float_df = pd.DataFrame({"Menu_ID": ["MENU001"], "Price": [450.0]})

    # Generate hashes for both datasets
    int_hash = add_record_hash(int_df, ["Menu_ID", "Price"])["record_hash"].iloc[0]
    float_hash = add_record_hash(float_df, ["Menu_ID", "Price"])["record_hash"].iloc[0]

    # Confirm that the same value produces the same hash
    assert int_hash == float_hash


def test_column_upcast_by_missing_value_keeps_hash():

    # Create an integer price column
    clean_df = pd.DataFrame({"Menu_ID": ["MENU001", "MENU002"], "Price": [450, 650]})

    # Create the same data where a missing value turns the column into decimals
    upcast_df = pd.DataFrame({"Menu_ID": ["MENU001", "MENU002"], "Price": [450, None]})

    # Generate hashes for both datasets
    clean_hash = add_record_hash(clean_df, ["Menu_ID", "Price"])["record_hash"].iloc[0]
    upcast_hash = add_record_hash(upcast_df, ["Menu_ID", "Price"])["record_hash"].iloc[0]

    # Confirm that the unchanged first record keeps its hash
    assert clean_hash == upcast_hash


def test_numpy_and_python_booleans_produce_same_hash():

    # Import NumPy to create a NumPy boolean value
    import numpy as np

    # Confirm that NumPy and Python booleans normalize to the same value
    from tracking.record_hasher import normalize_value
    assert normalize_value(np.bool_(True)) is True


def test_float_noise_does_not_change_hash():

    # Create the same stock value with and without float noise
    noisy_df = pd.DataFrame({"Menu_ID": ["MENU001"], "Stock": [18.790000000000003]})
    clean_df = pd.DataFrame({"Menu_ID": ["MENU001"], "Stock": [18.79]})

    # Generate hashes for both datasets
    noisy_hash = add_record_hash(noisy_df, ["Menu_ID", "Stock"])["record_hash"].iloc[0]
    clean_hash = add_record_hash(clean_df, ["Menu_ID", "Stock"])["record_hash"].iloc[0]

    # Confirm that float noise is ignored
    assert noisy_hash == clean_hash


def test_real_value_change_produces_different_hash():

    # Create two prices that differ only in decimals
    old_df = pd.DataFrame({"Menu_ID": ["MENU001"], "Price": [450.0]})
    new_df = pd.DataFrame({"Menu_ID": ["MENU001"], "Price": [450.5]})

    # Generate hashes for both datasets
    old_hash = add_record_hash(old_df, ["Menu_ID", "Price"])["record_hash"].iloc[0]
    new_hash = add_record_hash(new_df, ["Menu_ID", "Price"])["record_hash"].iloc[0]

    # Confirm that a real change is still detected
    assert old_hash != new_hash
