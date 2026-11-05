
# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas for Excel reading and data analysis
import pandas as pd


# Import the reusable schema validation function
from validation.schema_validator import validate_required_columns

# Import the reusable positive value validation function
from validation.data_validator import validate_positive_values


# ==========================================
# 2. WORKBOOK FILE PATHS
# ==========================================

# Define the file paths for both restaurant workbooks
menu_file = "data/raw/kRpfYv.xlsx"
inventory_file = "data/raw/mMcHmK.xlsx"


# ==========================================
# 3. WORKBOOK INSPECTION
# ==========================================

# Open both Excel workbooks to inspect their worksheet names
menu_excel = pd.ExcelFile(menu_file)
inventory_excel = pd.ExcelFile(inventory_file)

# Display all available worksheet names
print("Menu worksheets:", menu_excel.sheet_names)
print("Inventory worksheets:", inventory_excel.sheet_names)


# ==========================================
# 4. MENU DATA INGESTION
# ==========================================

# Read the Menu_Items worksheet into a Pandas DataFrame
menu_df = pd.read_excel(menu_file, sheet_name="Menu_Items")


# ==========================================
# 5. MENU DATA PREVIEW
# ==========================================

# Display the first five menu records
print("\nMenu Items DataFrame:")
print(menu_df.head())

# Display the number of rows and columns
print("\nDataFrame shape:")
print(menu_df.shape)

# Display all column names
print("\nColumn names:")
print(menu_df.columns.tolist())


# ==========================================
# 6. INVENTORY DATA INGESTION
# ==========================================

# Read the Recipes worksheet from the inventory workbook
inventory_df = pd.read_excel(
    inventory_file,
    sheet_name="Recipes"
)


# ==========================================
# 7. INVENTORY DATA PREVIEW
# ==========================================

# Display the first five recipe records
print("\nInventory Recipes DataFrame:")
print(inventory_df.head())

# Display the number of rows and columns
print("\nRecipes DataFrame shape:")
print(inventory_df.shape)

# Display all recipe column names
print("\nRecipes columns:")
print(inventory_df.columns.tolist())


# ==========================================
# 8. MENU DATA PROFILING
# ==========================================

# Count missing values in each menu column
print("\nMissing values in Menu_Items:")
print(menu_df.isnull().sum())


# ==========================================
# 9. INVENTORY DATA PROFILING
# ==========================================

# Count missing values in each recipe column
print("\nMissing values in Recipes:")
print(inventory_df.isnull().sum())


# ==========================================
# 10. DUPLICATE MENU ID CHECK
# ==========================================

# Count duplicate Menu_ID values in the menu catalog
menu_duplicates = menu_df["Menu_ID"].duplicated().sum()

print("\nDuplicate Menu IDs in Menu_Items:", menu_duplicates)

# ==========================================
# 11. DUPLICATE RECIPE INGREDIENT CHECK
# ==========================================

# Check for repeated ingredient IDs within the same menu item
recipe_duplicates = inventory_df.duplicated(
    subset=["Menu_ID", "Ingredient_ID"]
).sum()

print("\nDuplicate Menu-ID and Ingredient-ID combinations:", recipe_duplicates)

# ==========================================
# 12. DATA TYPE INSPECTION
# ==========================================

# Display the data types of all menu columns
print("\nMenu_Items Data Types:")
print(menu_df.dtypes)

# Display the data types of all recipe columns
print("\nRecipes Data Types:")
print(inventory_df.dtypes)

# ==========================================
# 13. FOREIGN KEY VALIDATION
# ==========================================

# Identify recipe Menu_ID values that do not exist in Menu_Items
invalid_recipe_ids = inventory_df[
    ~inventory_df["Menu_ID"].isin(menu_df["Menu_ID"])
]

# Display the number of invalid Menu_ID values
print("\nInvalid recipe ID count:", len(invalid_recipe_ids))

# Display any invalid recipe records
print(invalid_recipe_ids)

# Display the number of invalid Menu_ID values
print("Invalid recipe ID count:", len(invalid_recipe_ids))

# ==========================================
# 14. MENU ITEMS WITHOUT RECIPES
# ==========================================

# Identify menu items that do not have a recipe record
menu_without_recipes = menu_df[
    ~menu_df["Menu_ID"].isin(inventory_df["Menu_ID"])
]

# Display the number of menu items without recipes
print("\nMenu items without recipes:", len(menu_without_recipes))

# Display the menu items without recipes
print("\nMenu items without recipe records:")
print(menu_without_recipes[["Menu_ID", "Item_Name", "Catalog_Status"]])

# ==========================================
# 15. NUMERIC DATA VALIDATION
# ==========================================

# Identify menu items with negative prices
negative_prices = menu_df[
    menu_df["Base_Price_PKR"] < 0
]

# Identify recipes with zero or negative ingredient quantities
invalid_quantities = inventory_df[
    inventory_df["Qty_Per_Portion"] <= 0
]

# Display the number of menu items with negative prices
print("\nMenu items with negative prices:", len(negative_prices))

# Display the number of recipes with invalid quantities
print("\nRecipes with invalid quantities:", len(invalid_quantities))

# ==========================================
# 16. INVENTORY AVAILABILITY VALIDATION
# ==========================================

# Identify ingredients with negative PECHS availability
negative_pechs_stock = inventory_df[
    inventory_df["PECHS_Available"] < 0
]

# Identify ingredients with negative Gulshan availability
negative_gulshan_stock = inventory_df[
    inventory_df["Gulshan_Available"] < 0
]

# Display the number of negative PECHS stock records
print("\nNegative PECHS stock records:", len(negative_pechs_stock))

# Display the number of negative Gulshan stock records
print("\nNegative Gulshan stock records:", len(negative_gulshan_stock))


# ==========================================
# 17. REUSABLE SCHEMA VALIDATION
# ==========================================

# Define the columns required from the menu catalog
required_menu_columns = [
    "Menu_ID",
    "Item_Name",
    "Base_Price_PKR",
    "Catalog_Status"
]

# Define the columns required from the recipe data
required_recipe_columns = [
    "Menu_ID",
    "Ingredient_ID",
    "Qty_Per_Portion"
]

# Validate the structure of the Menu_Items dataset
menu_schema_valid = validate_required_columns(
    menu_df,
    required_menu_columns,
    "Menu_Items"
)

# Validate the structure of the Recipes dataset
recipe_schema_valid = validate_required_columns(
    inventory_df,
    required_recipe_columns,
    "Recipes"
)

# Display the validation results
print("\nSchema Validation Results:")
print("Menu_Items:", menu_schema_valid)
print("Recipes:", recipe_schema_valid)


# ==========================================
# 18. SCHEMA VALIDATION FAILURE TEST
# ==========================================

# Create a temporary copy of the Recipes DataFrame
test_recipes_df = inventory_df.copy()

# Remove a required column from the temporary copy
test_recipes_df = test_recipes_df.drop(
    columns=["Qty_Per_Portion"]
)

# Test whether the validator detects the missing column
try:
    validate_required_columns(
        test_recipes_df,
        required_recipe_columns,
        "Test Recipes"
    )

except ValueError as error:
    print("\nExpected Validation Error:")
    print(error)


# ==========================================
# 19. POSITIVE VALUE VALIDATION TEST
# ==========================================

# Create a temporary copy of the Recipes DataFrame
test_inventory_df = inventory_df.copy()

# Insert an invalid ingredient quantity for testing
test_inventory_df.loc[0, "Qty_Per_Portion"] = -3

# Run the reusable quantity validator
test_invalid_quantities = validate_positive_values(
    test_inventory_df,
    "Qty_Per_Portion"
)

# Display the test result
print("\nInvalid quantity test:")
print(test_invalid_quantities[["Menu_ID", "Ingredient_ID", "Qty_Per_Portion"]])
