# ==========================================
# 1. IMPORTS
# ==========================================

# Import Pandas to create sample datasets
import pandas as pd

# Import the knowledge builder functions
from knowledge.knowledge_builder import (
    NO_SALES_DATA_ANSWER,
    build_knowledge_entries,
    make_entry,
    rule_status,
)


# ==========================================
# 2. SAMPLE DATA HELPERS
# ==========================================

def sample_data():

    # Small versions of the workbook sheets used by the builder
    menu_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU050"],
        "Item_Name": ["Chicken Biryani", "Draft Pasta"],
        "Category": ["Pakistani", "Continental"],
        "Description": ["Traditional preparation", "Not ready"],
        "Base_Price_PKR": [420, 900],
        "Currency": ["PKR", "PKR"],
        "Service_Window": ["All day", "All day"],
        "Catalog_Status": ["Active", "Draft - Recipe Needed"],
    })
    aliases_df = pd.DataFrame({
        "Menu_ID": ["MENU001", "MENU001"],
        "Customer_Phrase": ["chicken biryani", "chikkan biryani"],
    })
    branches_df = pd.DataFrame({
        "Branch_ID": ["UTG-KHI-001", "UTG-KHI-009"],
        "Branch_Name": ["PECHS", "Closed Branch"],
        "Address_Demo": ["Shahrah-e-Faisal", "Nowhere"],
        "Tables": [18, 1],
        "Seats": [72, 4],
        "Hours": ["24/7", "Closed"],
        "Status": ["Active", "Inactive"],
    })
    rules_df = pd.DataFrame({
        "Rule_ID": ["RULE001", "RULE006"],
        "Rule_Name": ["Operating hours", "Minimum delivery order"],
        "Value": ["24/7", "Not configured"],
        "Applies_To": ["Both branches", "Delivery"],
        "Verification_Status": ["Confirmed in synthetic profile", "Pending"],
        "Comment": ["Item windows may differ", "Configure zones"],
    })
    return menu_df, aliases_df, branches_df, rules_df


def entries_by_id():

    return {entry["entry_id"]: entry for entry in build_knowledge_entries(*sample_data())}


# ==========================================
# 3. CONTENT TESTS
# ==========================================

def test_branch_entries_carry_branch_metadata():

    entries = entries_by_id()
    hours = entries["branch:UTG-KHI-001:hours"]

    assert hours["topic"] == "opening_hours"
    assert hours["branch_id"] == "UTG-KHI-001"
    assert "24/7" in hours["answer"]

    # Inactive branches are not offered to customers
    assert not any("UTG-KHI-009" in entry_id for entry_id in entries)


def test_rules_are_grouped_and_pending_rules_are_not_approved():

    entries = entries_by_id()

    assert entries["rule:RULE001"]["topic"] == "opening_hours"
    assert entries["rule:RULE001"]["status"] == "approved"
    assert entries["rule:RULE006"]["topic"] == "delivery_policy"
    assert entries["rule:RULE006"]["status"] == "pending"


def test_rule_status_never_approves_partly_pending_rules():

    assert rule_status("Scope confirmed; eligibility pending") == "pending"
    assert rule_status("Demo assumption") == "pending"
    assert rule_status("Scope confirmed") == "approved"


def test_menu_entries_include_aliases_and_skip_draft_items():

    entries = entries_by_id()
    biryani = entries["menu:MENU001"]

    assert "chikkan biryani" in biryani["keywords"]
    assert "420 PKR" in biryani["answer"]
    assert "menu:MENU050" not in entries


def test_top_10_reports_missing_sales_data_instead_of_using_menu():

    top_10 = entries_by_id()["sales:top_10"]

    assert top_10["status"] == "unavailable"
    assert top_10["answer"] == NO_SALES_DATA_ANSWER

    # No menu item is presented as a best seller
    assert "Biryani" not in top_10["answer"]


# ==========================================
# 4. CHANGE DETECTION TESTS
# ==========================================

def test_entry_ids_are_unique_and_rebuilds_are_stable():

    first = build_knowledge_entries(*sample_data())
    second = build_knowledge_entries(*sample_data())

    assert len({entry["entry_id"] for entry in first}) == len(first)
    assert first == second


def test_content_hash_changes_only_when_content_changes():

    entry = make_entry("x", "faq", "Q?", "A.", "src", "approved")
    same = make_entry("x", "faq", "Q?", "A.", "src", "approved")
    changed = make_entry("x", "faq", "Q?", "A changed.", "src", "approved")

    assert entry["content_hash"] == same["content_hash"]
    assert entry["content_hash"] != changed["content_hash"]
