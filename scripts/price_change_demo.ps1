# ==========================================
# Price-change demo: shows that only changed data is reloaded
# ==========================================
# Run from the project folder, with the PG* variables (including PGPASSWORD) set:
#   powershell -ExecutionPolicy Bypass -File scripts/price_change_demo.ps1
#
# Step 1 loads data/demo/kRpfYv_price_demo.xlsx (Chicken Biryani 420 -> 450 PKR).
# Step 2 loads the owner's original workbook again, putting the price back.
# The original Excel file and its backups are never modified.

# The pipeline logs to stderr; failures are caught by the exit-code checks below
$ErrorActionPreference = "Continue"
$pattern = "^(Changed|Unchanged) (menu|knowledge)|^menu_items |^item_aliases |^Document embeddings|completed successfully|ERROR \||CRITICAL"

Write-Host "`n=== STEP 1: owner sends a new menu file (Chicken Biryani 420 -> 450 PKR) ===" -ForegroundColor Cyan
$env:RESTAURANT_MENU_FILE = "data/demo/kRpfYv_price_demo.xlsx"
# Keep demo backups out of the real backup folder
$env:RESTAURANT_BACKUP_DIR = "data/demo/backups"
python src/inspect_workbooks.py 2>&1 | Select-String -CaseSensitive -Pattern $pattern
if ($LASTEXITCODE -ne 0) { throw "Demo run failed." }

python -c "import psycopg; c = psycopg.connect(); print('Chicken Biryani price in menu_items:', c.execute('select base_price_pkr from menu_items where row_key = %s', ['MENU001']).fetchone()[0], 'PKR')"

Write-Host "`n=== STEP 2: back to the original menu file (450 -> 420 PKR) ===" -ForegroundColor Cyan
Remove-Item Env:RESTAURANT_MENU_FILE, Env:RESTAURANT_BACKUP_DIR
python src/inspect_workbooks.py 2>&1 | Select-String -CaseSensitive -Pattern $pattern
if ($LASTEXITCODE -ne 0) { throw "Restore run failed." }

python -c "import psycopg; c = psycopg.connect(); print('Chicken Biryani price in menu_items:', c.execute('select base_price_pkr from menu_items where row_key = %s', ['MENU001']).fetchone()[0], 'PKR')"
