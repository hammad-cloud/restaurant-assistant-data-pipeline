# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas for creating test DataFrames
import pandas as pd

# Import the menu text standardization function
from transformation.menu_transformer import standardize_menu_text


# ==========================================
# 2. WHITESPACE STANDARDIZATION TEST
# ==========================================

def test_menu_text_whitespace_is_removed():

    # Create a sample menu record with inconsistent whitespace
    test_df = pd.DataFrame({
        "Menu_ID": [" MENU001 "],
        "Item_Name": [" Chicken Biryani "],
        "Category_ID": [" CAT-PK "],
        "Category": [" Pakistani "],
        "Description": [" Delicious biryani "],
        "Currency": [" PKR "],
        "Item_Type": [" Food "],
        "Catalog_Status": [" Active "],
        "Recipe_Linked": [" Yes "],
        "Dietary_Hint": [" None "],
        "Allergen_Hint": [" None "],
        "Allergen_Verified": [" No "],
        "Service_Window": [" All day "],
        "Upsell_Eligible": [" Yes "],
        "Slug": [" utg-item-001 "],
        "Data_Provenance": [" Synthetic demo pricing "]
    })

    # Apply text standardization
    transformed_df = standardize_menu_text(test_df)

    # Verify that leading and trailing whitespace is removed
    assert transformed_df["Item_Name"].iloc[0] == "Chicken Biryani"
    assert transformed_df["Category"].iloc[0] == "Pakistani"
    assert transformed_df["Description"].iloc[0] == "Delicious biryani"


# ==========================================
# 3. IDENTIFIER AND CURRENCY STANDARDIZATION TEST
# ==========================================

def test_menu_identifiers_and_currency_are_standardized():

    # Create a sample menu record
    test_df = pd.DataFrame({
        "Menu_ID": [" menu001 "],
        "Item_Name": ["Chicken Biryani"],
        "Category_ID": [" cat-pk "],
        "Category": ["Pakistani"],
        "Description": ["Biryani"],
        "Currency": [" pkr "],
        "Item_Type": ["Food"],
        "Catalog_Status": ["Active"],
        "Recipe_Linked": ["Yes"],
        "Dietary_Hint": ["None"],
        "Allergen_Hint": ["None"],
        "Allergen_Verified": ["No"],
        "Service_Window": ["All day"],
        "Upsell_Eligible": ["Yes"],
        "Slug": ["utg-item-001"],
        "Data_Provenance": ["Synthetic demo pricing"]
    })

    # Apply text standardization
    transformed_df = standardize_menu_text(test_df)

    # Verify standardized identifiers and currency
    assert transformed_df["Menu_ID"].iloc[0] == "MENU001"
    assert transformed_df["Category_ID"].iloc[0] == "CAT-PK"
    assert transformed_df["Currency"].iloc[0] == "PKR"


# ==========================================
# 4. SLUG STANDARDIZATION TEST
# ==========================================

def test_menu_slug_is_standardized():

    # Create a sample menu record
    test_df = pd.DataFrame({
        "Menu_ID": ["MENU001"],
        "Item_Name": ["Chicken Biryani"],
        "Category_ID": ["CAT-PK"],
        "Category": ["Pakistani"],
        "Description": ["Biryani"],
        "Currency": ["PKR"],
        "Item_Type": ["Food"],
        "Catalog_Status": ["Active"],
        "Recipe_Linked": ["Yes"],
        "Dietary_Hint": ["None"],
        "Allergen_Hint": ["None"],
        "Allergen_Verified": ["No"],
        "Service_Window": ["All day"],
        "Upsell_Eligible": ["Yes"],
        "Slug": [" UTG-ITEM-001 "],
        "Data_Provenance": ["Synthetic demo pricing"]
    })

    # Apply text standardization
    transformed_df = standardize_menu_text(test_df)

    # Verify that the slug is lowercase and whitespace-free
    assert transformed_df["Slug"].iloc[0] == "utg-item-001"


# ==========================================
# 5. ORIGINAL DATA PRESERVATION TEST
# ==========================================

def test_original_menu_data_remains_unchanged():

    # Create a sample menu record with inconsistent formatting
    test_df = pd.DataFrame({
        "Menu_ID": [" menu001 "],
        "Item_Name": [" Chicken Biryani "],
        "Category_ID": [" cat-pk "],
        "Category": [" Pakistani "],
        "Description": [" Biryani "],
        "Currency": [" pkr "],
        "Item_Type": [" Food "],
        "Catalog_Status": [" Active "],
        "Recipe_Linked": [" Yes "],
        "Dietary_Hint": [" None "],
        "Allergen_Hint": [" None "],
        "Allergen_Verified": [" No "],
        "Service_Window": [" All day "],
        "Upsell_Eligible": [" Yes "],
        "Slug": [" UTG-ITEM-001 "],
        "Data_Provenance": [" Synthetic demo pricing "]
    })

    # Create a copy of the original dataset for comparison
    original_df = test_df.copy(deep=True)

    # Apply text standardization
    transformed_df = standardize_menu_text(test_df)

    # Verify that the original dataset remains unchanged
    pd.testing.assert_frame_equal(test_df, original_df)

    # Verify that transformation returns a separate DataFrame
    assert transformed_df is not test_df