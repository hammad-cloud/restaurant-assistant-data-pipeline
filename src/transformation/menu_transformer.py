# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas for DataFrame operations
import pandas as pd


# ==========================================
# 2. MENU TEXT STANDARDIZATION
# ==========================================

def standardize_menu_text(df):
    """
    Standardize selected text columns in the menu dataset.

    The original DataFrame remains unchanged.
    """

    # Create a separate copy to protect the original data
    transformed_df = df.copy()

    # Define text columns that require whitespace cleanup
    text_columns = [
        "Menu_ID",
        "Item_Name",
        "Category_ID",
        "Category",
        "Description",
        "Currency",
        "Item_Type",
        "Catalog_Status",
        "Recipe_Linked",
        "Dietary_Hint",
        "Allergen_Hint",
        "Allergen_Verified",
        "Service_Window",
        "Upsell_Eligible",
        "Slug",
        "Data_Provenance"
    ]

    # Remove leading and trailing whitespace from text values
    for column in text_columns:
        transformed_df[column] = transformed_df[column].apply(
            lambda value: value.strip()
            if isinstance(value, str)
            else value
        )

    # Standardize menu identifiers
    transformed_df["Menu_ID"] = transformed_df["Menu_ID"].str.upper()

    # Standardize category identifiers
    transformed_df["Category_ID"] = transformed_df["Category_ID"].str.upper()

    # Standardize currency codes
    transformed_df["Currency"] = transformed_df["Currency"].str.upper()

    # Standardize URL-friendly slugs
    transformed_df["Slug"] = transformed_df["Slug"].str.lower()

    # Return the standardized dataset
    return transformed_df