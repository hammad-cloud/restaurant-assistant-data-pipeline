# ==========================================
# 1. RECIPE ID STANDARDIZATION
# ==========================================

def standardize_recipe_ids(df):
    """
    Standardize recipe identifiers the same way as menu identifiers,
    so recipes still match their menu items.

    The original DataFrame remains unchanged.
    """

    # Create a separate copy to protect the original data
    transformed_df = df.copy()

    # Trim and uppercase identifier text; leave other values unchanged
    for column in ["Menu_ID", "Ingredient_ID"]:
        transformed_df[column] = transformed_df[column].apply(
            lambda value: value.strip().upper()
            if isinstance(value, str)
            else value
        )

    # Return the standardized dataset
    return transformed_df
