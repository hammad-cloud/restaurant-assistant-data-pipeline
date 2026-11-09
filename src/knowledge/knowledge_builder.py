# ==========================================
# 1. IMPORTS
# ==========================================

# Import the reusable record hashing function for change detection
from tracking.record_hasher import generate_record_hash


# Answer stored until real sales or order history is provided
NO_SALES_DATA_ANSWER = (
    "Sales history is not available yet, so the best-selling items "
    "cannot be reported."
)


# ==========================================
# 2. ENTRY HELPER
# ==========================================

def make_entry(entry_id, topic, question, answer, source, status,
               branch_id=None, keywords=""):
    """
    Build one knowledge entry with a fingerprint of its content.

    status is "approved", "pending" or "unavailable", so the chatbot
    can tell confirmed answers from ones that need a caveat.
    """

    entry = {
        "entry_id": entry_id,
        "topic": topic,
        "question": question,
        "answer": answer,
        "keywords": keywords,
        "branch_id": branch_id,
        "status": status,
        "source": source,
    }

    # The hash changes only when the content changes
    entry["content_hash"] = generate_record_hash(entry)
    return entry


# ==========================================
# 3. BRANCHES AND OPENING HOURS
# ==========================================

def build_branch_entries(branches_df, source="mMcHmK.xlsx:Branches"):
    """
    Create a location entry and an opening-hours entry for each active branch.
    """

    entries = []

    for branch in branches_df[branches_df["Status"] == "Active"].itertuples():
        entries.append(make_entry(
            f"branch:{branch.Branch_ID}:location",
            "branch",
            f"Where is the {branch.Branch_Name} branch?",
            f"{branch.Branch_Name}: {branch.Address_Demo}. "
            f"{branch.Tables} tables, {branch.Seats} seats.",
            source, "approved", branch_id=branch.Branch_ID,
            keywords=f"{branch.Branch_Name} address location",
        ))
        entries.append(make_entry(
            f"branch:{branch.Branch_ID}:hours",
            "opening_hours",
            # Worded this way so "Is X branch open now?" ranks hours above "Where is the X branch?"
            f"When is the {branch.Branch_Name} branch open?",
            f"The {branch.Branch_Name} branch is open {branch.Hours}.",
            source, "approved", branch_id=branch.Branch_ID,
            keywords=f"{branch.Branch_Name} timings open close",
        ))

    return entries


# ==========================================
# 4. SERVICE AND DELIVERY RULES
# ==========================================

def rule_status(verification_status):
    """
    Map a workbook verification note to an entry status.
    Anything still pending is never treated as approved.
    """

    text = str(verification_status).lower()
    return "approved" if "confirmed" in text and "pending" not in text else "pending"


def build_service_rule_entries(rules_df, source="kRpfYv.xlsx:Service_Rules"):
    """
    Create one entry per service rule, grouped into delivery,
    opening-hours, or general service topics.
    """

    entries = []

    for rule in rules_df.itertuples():
        if "delivery" in str(rule.Applies_To).lower():
            topic = "delivery_policy"
        elif "hours" in str(rule.Rule_Name).lower():
            topic = "opening_hours"
        else:
            topic = "service_rule"

        entries.append(make_entry(
            f"rule:{rule.Rule_ID}",
            topic,
            f"What is the {rule.Rule_Name.lower()} policy?",
            f"{rule.Rule_Name}: {rule.Value} (applies to {rule.Applies_To}). {rule.Comment}.",
            source, rule_status(rule.Verification_Status),
            keywords=str(rule.Applies_To),
        ))

    return entries


# ==========================================
# 5. MENU DESCRIPTIONS
# ==========================================

# How customers ask about one menu item; the first is the stored canonical question
MENU_QUESTION_TEMPLATES = (
    "What is {}?",
    "What is the price of {}?",
    "How much does {} cost?",
    "Tell me about {}.",
)


def menu_question_variations(question):
    """
    The other phrasings of a canonical menu question, answered by the same entry.
    Returns [] for a question not built from the canonical template.
    """

    prefix, suffix = MENU_QUESTION_TEMPLATES[0].split("{}")
    if not (question.startswith(prefix) and question.endswith(suffix)):
        return []
    name = question.removeprefix(prefix).removesuffix(suffix)
    return [template.format(name) for template in MENU_QUESTION_TEMPLATES[1:]]


def build_menu_entries(menu_df, aliases_df, source="kRpfYv.xlsx:Menu_Items"):
    """
    Create one entry per active menu item, with customer phrases
    (including Roman Urdu aliases) as search keywords.
    """

    # Collect every customer phrase per Menu_ID
    phrases = aliases_df.groupby("Menu_ID")["Customer_Phrase"].apply(" ".join)

    entries = []

    for item in menu_df[menu_df["Catalog_Status"] == "Active"].itertuples():
        entries.append(make_entry(
            f"menu:{item.Menu_ID}",
            "menu_item",
            MENU_QUESTION_TEMPLATES[0].format(item.Item_Name),
            f"{item.Item_Name} ({item.Category}): {item.Description}. "
            f"Price {item.Base_Price_PKR} {item.Currency}, served {item.Service_Window}. "
            f"Allergen information is not verified.",
            source, "approved",
            keywords=phrases.get(item.Menu_ID, ""),
        ))

    return entries


# ==========================================
# 6. POPULAR ITEMS
# ==========================================

def build_popular_items_entry():
    """
    Store the top-10 limitation honestly: best sellers must come from
    real sales history, never from the menu catalogue.
    """

    # shortcut: no sales/order data exists yet; add the top-10 calculation when its schema is known
    return make_entry(
        "sales:top_10",
        "popular_items",
        "What are your 10 most-selling menu items?",
        NO_SALES_DATA_ANSWER,
        "none: sales history not provided",
        "unavailable",
        keywords="best selling popular top bestseller favourite",
    )


# ==========================================
# 7. ALL ENTRIES
# ==========================================

def build_knowledge_entries(menu_df, aliases_df, branches_df, rules_df):
    """
    Build every knowledge entry from the validated restaurant data.
    """

    return (
        build_branch_entries(branches_df)
        + build_service_rule_entries(rules_df)
        + build_menu_entries(menu_df, aliases_df)
        + [build_popular_items_entry()]
    )
