
# ==========================================
# 1. IMPORTS
# ==========================================

# Import Path to build file paths from the project folder
from pathlib import Path

# Import Pandas for Excel reading and data analysis
import pandas as pd


# Import the reusable schema validation function
from validation.schema_validator import validate_required_columns

# Import the reusable positive value validation function
from validation.data_validator import validate_positive_values

# Import the reusable unique value validation function
from validation.data_validator import validate_unique_values

# Import the reusable required value validation function
from validation.data_validator import validate_required_values

# Import the reusable foreign key validation function
from validation.data_validator import validate_foreign_keys


# Import the reusable quarantine function
from validation.quarantine import split_valid_and_invalid_records

# Import the rejected-record storage function
from validation.quarantine import save_rejected_records

# Import the combined split, save, and report function
from validation.quarantine import quarantine_records

# Import the reusable menu text standardization function
from transformation.menu_transformer import standardize_menu_text

# Import the reusable recipe ID standardization function
from transformation.recipe_transformer import standardize_recipe_ids

# Import the reusable menu schema definition
from validation.menu_schema import required_menu_columns

# Import the reusable record hashing function
from tracking.record_hasher import add_record_hash

# Import the snapshot comparison and storage function
from tracking.snapshot_manager import update_snapshot


# ==========================================
# 2. WORKBOOK FILE PATHS
# ==========================================

# Locate the project folder (one level above src/), so the script
# works no matter which folder it is run from
project_root = Path(__file__).resolve().parent.parent

# Define the file paths for both restaurant workbooks
menu_file = project_root / "data" / "raw" / "kRpfYv.xlsx"
inventory_file = project_root / "data" / "raw" / "mMcHmK.xlsx"

# Define the folder for rejected records
rejected_dir = project_root / "data" / "rejected"

# Define the file for the latest processed menu snapshot
menu_snapshot_file = project_root / "data" / "processed" / "menu_items.csv"


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
# 8. REUSABLE SCHEMA VALIDATION
# ==========================================

# Define the columns required from the recipe data
# (all columns, so a change in any of them is tracked)
required_recipe_columns = [
    "Menu_ID",
    "Menu_Item",
    "Category",
    "Ingredient_ID",
    "Ingredient_Name",
    "Qty_Per_Portion",
    "PECHS_Available",
    "PECHS_Max_Portions",
    "Gulshan_Available",
    "Gulshan_Max_Portions"
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
# 9. MENU DATA PROFILING
# ==========================================

# Count missing values in each menu column
print("\nMissing values in Menu_Items:")
print(menu_df.isnull().sum())


# ==========================================
# 10. INVENTORY DATA PROFILING
# ==========================================

# Count missing values in each recipe column
print("\nMissing values in Recipes:")
print(inventory_df.isnull().sum())


# ==========================================
# 11. DUPLICATE MENU ID CHECK
# ==========================================

# Count duplicate Menu_ID values in the menu catalog
menu_duplicates = menu_df["Menu_ID"].duplicated().sum()

print("\nDuplicate Menu IDs in Menu_Items:", menu_duplicates)

# ==========================================
# 12. DUPLICATE RECIPE INGREDIENT CHECK
# ==========================================

# Check for repeated ingredient IDs within the same menu item
recipe_duplicates = inventory_df.duplicated(
    subset=["Menu_ID", "Ingredient_ID"]
).sum()

print("\nDuplicate Menu-ID and Ingredient-ID combinations:", recipe_duplicates)

# ==========================================
# 13. DATA TYPE INSPECTION
# ==========================================

# Display the data types of all menu columns
print("\nMenu_Items Data Types:")
print(menu_df.dtypes)

# Display the data types of all recipe columns
print("\nRecipes Data Types:")
print(inventory_df.dtypes)

# ==========================================
# 14. FOREIGN KEY VALIDATION
# ==========================================

# Identify recipe Menu_ID values that do not exist in Menu_Items
invalid_recipe_ids = inventory_df[
    ~inventory_df["Menu_ID"].isin(menu_df["Menu_ID"])
]

# Display the number of invalid Menu_ID values
print("\nInvalid recipe ID count:", len(invalid_recipe_ids))

# Display any invalid recipe records
print(invalid_recipe_ids)

# ==========================================
# 15. MENU ITEMS WITHOUT RECIPES
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
# 16. NUMERIC DATA VALIDATION
# ==========================================

# Identify menu items with negative prices
negative_prices = menu_df[
    pd.to_numeric(menu_df["Base_Price_PKR"], errors="coerce") < 0
]

# Identify recipes with zero or negative ingredient quantities
invalid_quantities = inventory_df[
    pd.to_numeric(inventory_df["Qty_Per_Portion"], errors="coerce") <= 0
]

# Display the number of menu items with negative prices
print("\nMenu items with negative prices:", len(negative_prices))

# Display the number of recipes with invalid quantities
print("\nRecipes with invalid quantities:", len(invalid_quantities))

# ==========================================
# 17. INVENTORY AVAILABILITY VALIDATION
# ==========================================

# Identify ingredients with negative PECHS availability
negative_pechs_stock = inventory_df[
    pd.to_numeric(inventory_df["PECHS_Available"], errors="coerce") < 0
]

# Identify ingredients with negative Gulshan availability
negative_gulshan_stock = inventory_df[
    pd.to_numeric(inventory_df["Gulshan_Available"], errors="coerce") < 0
]

# Display the number of negative PECHS stock records
print("\nNegative PECHS stock records:", len(negative_pechs_stock))

# Display the number of negative Gulshan stock records
print("\nNegative Gulshan stock records:", len(negative_gulshan_stock))


# ==========================================
# 18. MENU DATA STANDARDIZATION
# ==========================================

# Preserve the original menu dataset
original_menu_df = menu_df.copy(deep=True)

# Apply menu text standardization
transformed_menu_df = standardize_menu_text(menu_df)

# ==========================================
# 19. MENU TRANSFORMATION VERIFICATION
# ==========================================

# Display original and transformed menu identifiers
print("\nOriginal Menu ID:", original_menu_df["Menu_ID"].iloc[0])
print("Transformed Menu ID:", transformed_menu_df["Menu_ID"].iloc[0])

# Verify that the original dataset remains unchanged
print(
    "Original data preserved:",
    original_menu_df.equals(menu_df)
)

# Verify that the transformed dataset is a separate copy
print(
    "Separate DataFrame:",
    transformed_menu_df is not menu_df
)


# Use the standardized menu dataset for subsequent processing
menu_df = transformed_menu_df


# ==========================================
# 19b. RECIPE ID STANDARDIZATION
# ==========================================

# Trim and uppercase recipe IDs so they match the standardized menu IDs
inventory_df = standardize_recipe_ids(inventory_df)

# ==========================================
# 20. SCHEMA VALIDATION FAILURE TEST
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
# 21. MENU PRICE VALIDATION
# ==========================================

# Identify menu records with invalid prices
invalid_menu_prices = validate_positive_values(
    menu_df,
    "Base_Price_PKR"
)

# Separate valid and rejected menu records
valid_menu_records, rejected_menu_prices = split_valid_and_invalid_records(
    menu_df,
    invalid_menu_prices
)

# Display the validation results
print("\nMenu Price Validation:")
print("Valid menu records:", len(valid_menu_records))
print("Rejected menu records:", len(rejected_menu_prices))

# Display rejected menu records with their reasons
if not rejected_menu_prices.empty:
    print("\nRejected Menu Prices:")
    print(
        rejected_menu_prices[
            ["Menu_ID", "Item_Name", "Base_Price_PKR", "rejection_reason"]
        ]
    )

# Save rejected menu records
menu_price_rejection_file = save_rejected_records(
    rejected_menu_prices,
    "menu_prices",
    output_dir=str(rejected_dir)
)

# Display the saved file location
if menu_price_rejection_file:
    print("\nRejected menu prices saved to:", menu_price_rejection_file)

# Continue processing only menu records with valid prices
menu_df = valid_menu_records

# Store prices as numbers (text such as "450" was accepted above)
menu_df["Base_Price_PKR"] = pd.to_numeric(menu_df["Base_Price_PKR"])


# ==========================================
# 21b. MENU ID QUARANTINE
# ==========================================

# Reject menu records with a missing or blank Menu_ID
menu_df = quarantine_records(
    menu_df,
    validate_required_values(menu_df, "Menu_ID"),
    "menu_missing_ids",
    output_dir=str(rejected_dir)
)

# Reject every copy of a repeated Menu_ID (after IDs were standardized)
menu_df = quarantine_records(
    menu_df,
    validate_unique_values(menu_df, "Menu_ID"),
    "menu_duplicates",
    output_dir=str(rejected_dir)
)


# ==========================================
# 22. RECIPE QUANTITY VALIDATION
# ==========================================

# Identify recipe records with missing, zero, or negative quantities
invalid_recipe_quantities = validate_positive_values(
    inventory_df,
    "Qty_Per_Portion"
)


# ==========================================
# 23. VALID AND INVALID RECORD SEPARATION
# ==========================================

# Separate valid and rejected recipe records
valid_records, rejected_records = split_valid_and_invalid_records(
    inventory_df,
    invalid_recipe_quantities
)

# Display the number of valid records
print("\nValid recipe records:", len(valid_records))

# Display the number of rejected records
print("Rejected recipe records:", len(rejected_records))

# Display rejected records with their rejection reasons
if not rejected_records.empty:
    print("\nQuarantined Records:")
    print(
        rejected_records[
            ["Menu_ID", "Ingredient_ID", "Qty_Per_Portion", "rejection_reason"]
        ]
    )

# ==========================================
# 24. SAVE REJECTED RECORDS
# ==========================================

# Save rejected recipe records into a CSV file
rejected_file = save_rejected_records(
    rejected_records,
    "recipes",
    output_dir=str(rejected_dir)
)

# Display the saved file location
if rejected_file:
    print("\nRejected records saved to:", rejected_file)

# Continue processing only recipe records with valid quantities
inventory_df = valid_records

# Store quantities as numbers (text such as "0.25" was accepted above)
inventory_df["Qty_Per_Portion"] = pd.to_numeric(inventory_df["Qty_Per_Portion"])


# ==========================================
# 24b. RECIPE ID AND MENU LINK QUARANTINE
# ==========================================

# Reject recipe records with a missing or blank Menu_ID or Ingredient_ID
inventory_df = quarantine_records(
    inventory_df,
    validate_required_values(inventory_df, ["Menu_ID", "Ingredient_ID"]),
    "recipe_missing_ids",
    output_dir=str(rejected_dir)
)

# Reject every copy of a repeated Menu_ID + Ingredient_ID combination
inventory_df = quarantine_records(
    inventory_df,
    validate_unique_values(inventory_df, ["Menu_ID", "Ingredient_ID"]),
    "recipe_duplicates",
    output_dir=str(rejected_dir)
)

# Reject recipes whose menu item is not in the final validated menu
# (this runs after all menu checks, so recipes of rejected items are caught)
inventory_df = quarantine_records(
    inventory_df,
    validate_foreign_keys(inventory_df, "Menu_ID", menu_df["Menu_ID"], "validated menu"),
    "recipe_orphans",
    output_dir=str(rejected_dir)
)

# ==========================================
# 25. MENU DATA TRANSFORMATION INSPECTION
# ==========================================

# Display sample values from important menu columns
columns_to_inspect = [
    "Menu_ID",
    "Item_Name",
    "Category",
    "Currency",
    "Item_Type",
    "Catalog_Status"
]

for column in columns_to_inspect:
    print(f"\n{column}:")
    print(menu_df[column].head(10).tolist())


# ==========================================
# 26. SNAPSHOT AND CHANGE DETECTION
# ==========================================

# Define each dataset to track: name, data, hashed columns, ID, snapshot file
tracked_datasets = [
    ("menu", menu_df, required_menu_columns, "Menu_ID", menu_snapshot_file),
]

for name, df, hash_columns, id_column, snapshot_file in tracked_datasets:

    # Add a fingerprint to every validated record
    hashed_df = add_record_hash(df, hash_columns)

    # Compare with the previous snapshot, then save the new snapshot
    changes = update_snapshot(hashed_df, snapshot_file, id_column)

    # Report the baseline on the first run
    if changes is None:
        print(f"\nNo previous {name} snapshot found.")
        print(f"Baseline {name} snapshot saved to:", snapshot_file)

    # Report record changes on later runs
    else:
        print(f"\n{name.capitalize()} Change Detection:")
        for change_type in ["new", "changed", "unchanged", "removed"]:
            print(f"{change_type.capitalize()} {name} records:", len(changes[change_type]))
        print(f"{name.capitalize()} snapshot updated:", snapshot_file)
