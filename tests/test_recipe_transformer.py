# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas to create sample datasets
import pandas as pd

# Import the recipe ID standardization function
from transformation.recipe_transformer import standardize_recipe_ids


# ==========================================
# 2. RECIPE ID STANDARDIZATION TEST
# ==========================================

def test_recipe_ids_are_trimmed_and_uppercased():

    # Create recipe records with messy identifiers
    recipe_df = pd.DataFrame({
        "Menu_ID": [" menu001 ", None],
        "Ingredient_ID": ["ing002", "ING003"],
        "Qty_Per_Portion": [0.25, 0.5]
    })

    # Standardize the recipe identifiers
    result = standardize_recipe_ids(recipe_df)

    # Confirm that identifiers match the menu ID format
    assert result["Menu_ID"].iloc[0] == "MENU001"
    assert result["Ingredient_ID"].tolist() == ["ING002", "ING003"]

    # Confirm that missing values and other columns are kept
    assert pd.isna(result["Menu_ID"].iloc[1])
    assert result["Qty_Per_Portion"].tolist() == [0.25, 0.5]

    # Confirm that the original dataset remains unchanged
    assert recipe_df["Menu_ID"].iloc[0] == " menu001 "
