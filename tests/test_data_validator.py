# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas to create artificial test data
import pandas as pd

# Import the function we want to test
from validation.data_validator import validate_positive_values

# ==========================================
# 2. TEST NEGATIVE QUANTITY
# ==========================================

def test_negative_quantity_is_rejected():

    # Create artificial recipe records
    test_df = pd.DataFrame({
        "Qty_Per_Portion": [-3, 0.25]
    })

    # Run the actual validation function
    rejected_records = validate_positive_values(
        test_df,
        "Qty_Per_Portion"
    )

    # Confirm that exactly one record was rejected
    assert len(rejected_records) == 1

    # Confirm that the rejected quantity is -3
    assert rejected_records.iloc[0]["Qty_Per_Portion"] == -3

    # Confirm that the rejection reason is correct
    assert rejected_records.iloc[0]["rejection_reason"] == (
        "Qty_Per_Portion cannot be negative."
    )


# ==========================================
# 3. TEST ZERO QUANTITY
# ==========================================

def test_zero_quantity_is_rejected():

    # Create an artificial recipe record with zero quantity
    test_df = pd.DataFrame({
        "Qty_Per_Portion": [0]
    })

    # Run the actual validation function
    rejected_records = validate_positive_values(
        test_df,
        "Qty_Per_Portion"
    )

    # Confirm that exactly one record was rejected
    assert len(rejected_records) == 1

    # Confirm that the rejected quantity is zero
    assert rejected_records.iloc[0]["Qty_Per_Portion"] == 0

    # Confirm that the rejection reason is correct
    assert rejected_records.iloc[0]["rejection_reason"] == (
        "Qty_Per_Portion cannot be zero."
    )


# ==========================================
# 4. TEST MISSING QUANTITY
# ==========================================

def test_missing_quantity_is_rejected():

    # Create an artificial recipe record with a missing quantity
    test_df = pd.DataFrame({
        "Qty_Per_Portion": [None]
    })

    # Run the actual validation function
    rejected_records = validate_positive_values(
        test_df,
        "Qty_Per_Portion"
    )

    # Confirm that exactly one record was rejected
    assert len(rejected_records) == 1

    # Confirm that the quantity is missing
    assert pd.isna(rejected_records.iloc[0]["Qty_Per_Portion"])

    # Confirm that the rejection reason is correct
    assert rejected_records.iloc[0]["rejection_reason"] == (
        "Qty_Per_Portion is missing."
    )


# ==========================================
# 5. TEST POSITIVE QUANTITY
# ==========================================

def test_positive_quantity_is_accepted():

    # Create an artificial recipe record with a valid quantity
    test_df = pd.DataFrame({
        "Qty_Per_Portion": [0.25]
    })

    # Run the actual validation function
    rejected_records = validate_positive_values(
        test_df,
        "Qty_Per_Portion"
    )

    # Confirm that no records were rejected
    assert len(rejected_records) == 0

# ==========================================
# 6. MENU PRICE VALIDATION TEST
# ==========================================

def test_invalid_menu_prices_are_rejected():

    # Create sample menu records
    menu_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU002", "MENU003", "MENU004"],
        "Item_Name": [
            "Chicken Biryani",
            "Beef Biryani",
            "Chicken Karahi",
            "Mutton Karahi"
        ],
        "Base_Price_PKR": [450, 0, -200, None]
    })

    # Validate menu prices
    invalid_records = validate_positive_values(
        menu_df,
        "Base_Price_PKR"
    )

    # Verify that three invalid records are rejected
    assert len(invalid_records) == 3

    # Verify that every rejected record has a reason
    assert "rejection_reason" in invalid_records.columns

    # Verify the exact rejected menu records
    assert invalid_records["Menu_ID"].tolist() == [
        "MENU002",
        "MENU003",
        "MENU004"
    ]

    # Verify the rejection reasons
    assert invalid_records["rejection_reason"].tolist() == [
        "Base_Price_PKR cannot be zero.",
        "Base_Price_PKR cannot be negative.",
        "Base_Price_PKR is missing."
    ]


# ==========================================
# 7. DUPLICATE MENU ID VALIDATION TEST
# ==========================================

def test_duplicate_menu_ids_are_rejected():

    # Import the function under test
    from validation.data_validator import validate_unique_values

    # Create menu records where MENU001 appears twice
    menu_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU002", "MENU001"],
        "Base_Price_PKR": [450, 650, 500]
    })

    # Validate menu identifiers
    invalid_records = validate_unique_values(menu_df, "Menu_ID")

    # Verify that both copies of MENU001 are rejected
    assert invalid_records.index.tolist() == [0, 2]

    # Verify the rejection reason
    assert invalid_records["rejection_reason"].tolist() == [
        "Menu_ID is duplicated.",
        "Menu_ID is duplicated."
    ]


def test_unique_menu_ids_are_accepted():

    # Import the function under test
    from validation.data_validator import validate_unique_values

    # Create menu records with unique identifiers
    menu_df = pd.DataFrame({"Menu_ID": ["MENU001", "MENU002"]})

    # Confirm that no records were rejected
    assert len(validate_unique_values(menu_df, "Menu_ID")) == 0


# ==========================================
# 8. NON-NUMERIC VALUE VALIDATION TEST
# ==========================================

def test_text_prices_are_rejected_without_crashing():

    # Create menu prices that include text values
    menu_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU002", "MENU003"],
        "Base_Price_PKR": [450, "N/A", "650"]
    })

    # Validate menu prices
    invalid_records = validate_positive_values(menu_df, "Base_Price_PKR")

    # Verify that only the text value is rejected (numeric text "650" is accepted)
    assert invalid_records["Menu_ID"].tolist() == ["MENU002"]
    assert invalid_records["rejection_reason"].tolist() == [
        "Base_Price_PKR is not a number."
    ]


# ==========================================
# 9. REQUIRED VALUE VALIDATION TESTS
# ==========================================

def test_missing_and_blank_ids_are_rejected():

    # Import the function under test
    from validation.data_validator import validate_required_values

    # Create records with one missing and one blank Menu_ID
    menu_df = pd.DataFrame({"Menu_ID": ["MENU001", None, "  "]})

    # Validate menu identifiers
    invalid_records = validate_required_values(menu_df, "Menu_ID")

    # Verify that both missing identifiers are rejected
    assert invalid_records.index.tolist() == [1, 2]
    assert invalid_records["rejection_reason"].tolist() == [
        "Menu_ID is missing.",
        "Menu_ID is missing."
    ]


def test_missing_values_in_any_id_column_are_rejected():

    # Import the function under test
    from validation.data_validator import validate_required_values

    # Create recipe records with a missing Ingredient_ID
    recipe_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU001"],
        "Ingredient_ID": ["ING001", None]
    })

    # Validate both identifier columns
    invalid_records = validate_required_values(recipe_df, ["Menu_ID", "Ingredient_ID"])

    # Verify that the record and the missing column are reported
    assert invalid_records["rejection_reason"].tolist() == ["Ingredient_ID is missing."]


# ==========================================
# 10. COMBINED KEY AND FOREIGN KEY TESTS
# ==========================================

def test_duplicate_recipe_key_combinations_are_rejected():

    # Import the function under test
    from validation.data_validator import validate_unique_values

    # Create recipes where MENU001 + ING001 appears twice
    recipe_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU001", "MENU001"],
        "Ingredient_ID": ["ING001", "ING002", "ING001"]
    })

    # Validate the identifier combination
    invalid_records = validate_unique_values(recipe_df, ["Menu_ID", "Ingredient_ID"])

    # Verify that both copies are rejected with a readable reason
    assert invalid_records.index.tolist() == [0, 2]
    assert invalid_records["rejection_reason"].iloc[0] == (
        "Menu_ID + Ingredient_ID is duplicated."
    )


def test_recipes_without_menu_item_are_rejected():

    # Import the function under test
    from validation.data_validator import validate_foreign_keys

    # Create recipes where MENU009 is not on the menu
    recipe_df = pd.DataFrame({"Menu_ID": ["MENU001", "MENU009"]})
    menu_ids = pd.Series(["MENU001", "MENU002"])

    # Validate the menu link
    invalid_records = validate_foreign_keys(recipe_df, "Menu_ID", menu_ids, "validated menu")

    # Verify that only the orphan recipe is rejected
    assert invalid_records["Menu_ID"].tolist() == ["MENU009"]
    assert invalid_records["rejection_reason"].iloc[0] == (
        "Menu_ID not found in validated menu."
    )
