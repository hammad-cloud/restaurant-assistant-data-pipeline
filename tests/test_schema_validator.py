# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas to create test datasets
import pandas as pd

# Import the schema validation function
from validation.schema_validator import validate_required_columns


# ==========================================
# 2. TEST VALID SCHEMA
# ==========================================

def test_valid_schema_is_accepted():

    # Create a sample Recipes dataset with all required columns
    test_df = pd.DataFrame({
        "Menu_ID": ["MENU001"],
        "Ingredient_ID": ["ING001"],
        "Qty_Per_Portion": [0.25]
    })

    # Define the columns required by the Recipes dataset
    required_columns = [
        "Menu_ID",
        "Ingredient_ID",
        "Qty_Per_Portion"
    ]

    # Validate the dataset structure
    result = validate_required_columns(
        test_df,
        required_columns,
        "Recipes"
    )

    # Confirm that the schema is valid
    assert result is True


# ==========================================
# 3. TEST MISSING REQUIRED COLUMNS
# ==========================================

def test_missing_required_columns_raise_error():

    # Create a Recipes dataset missing Ingredient_ID
    test_df = pd.DataFrame({
        "Menu_ID": ["MENU001"],
        "Qty_Per_Portion": [0.25]
    })

    # Define all columns required by the Recipes dataset
    required_columns = [
        "Menu_ID",
        "Ingredient_ID",
        "Qty_Per_Portion"
    ]

    # Confirm that validation raises a ValueError
    try:
        validate_required_columns(
            test_df,
            required_columns,
            "Recipes"
        )

    except ValueError as error:

        # Confirm that the missing column is identified
        assert "Ingredient_ID" in str(error)

    else:

        # Fail if the validator accepts an incomplete schema
        raise AssertionError(
            "Expected ValueError for missing required columns."
        )
