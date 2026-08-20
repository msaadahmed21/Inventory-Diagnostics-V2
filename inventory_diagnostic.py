"""
Inventory Diagnostic (Python edition)
======================================

This is a command-line (text-based) program. That means it runs in a
terminal window instead of a web browser, and you interact with it by
typing answers to questions instead of clicking buttons.

What it does (same idea as the original web app):
  1. You give it a CSV inventory file (SKU, inventory value, demand, etc).
  2. STEP 1: it checks the data quality - is anything missing? anything
     that looks wrong? - and tells you plainly.
  3. STEP 2: it shows you 5 headline KPIs (Key Performance Indicators),
     a simple text "bar chart" of inventory by SKU, and a table of the
     SKUs with the most potential excess inventory.

How to run it:
    python inventory_diagnostic.py
    (or)  python inventory_diagnostic.py sample-inventory.csv
"""

# ---------------------------------------------------------------------------
# IMPORTS
# An "import" brings in extra tools that already exist in Python, so we
# don't have to write everything from scratch ourselves.
#   - csv     : reads/writes CSV (comma-separated values) files.
#   - sys     : lets us read command-line arguments (sys.argv) and exit.
#   - re      : "regular expressions" - a mini language for matching text
#               patterns, used here to spot things like "1,234" formatting.
#   - statistics.median : calculates the middle value of a list of numbers.
# ---------------------------------------------------------------------------
import csv
import sys
import re
from statistics import median


# ---------------------------------------------------------------------------
# THIS IS A DICTIONARY (a set of "key: value" pairs, a bit like a phone book
# where you look up a name (key) to find a number (value)).
# Here, each key is a field we care about (e.g. "sku"), and the value is a
# LIST of alternative column headings we'll accept for that field. This
# means the user doesn't have to name their spreadsheet columns exactly
# right - "Item Number" and "SKU" can both be understood as the SKU column.
# ---------------------------------------------------------------------------
ALIASES = {
    "sku": ["sku", "item", "item number", "material", "material number", "product", "product code"],
    "inventory": ["inventory €", "inventory eur", "inventory", "inventory value", "stock value", "on hand value", "on hand inventory"],
    "demand": ["annual demand €", "annual demand eur", "annual demand", "demand", "annual sales", "yearly demand", "annual consumption"],
    "lead_time": ["lead time days", "lead time", "leadtime", "lead time day", "procurement lead time"],
    "safety_stock": ["safety stock €", "safety stock eur", "safety stock", "safety stock value", "buffer stock"],
}

# Another dictionary: a friendly, human-readable name for each field.
# We use these when printing messages, e.g. "inventory value column was not found".
FIELD_LABELS = {
    "sku": "SKU",
    "inventory": "inventory value",
    "demand": "annual demand",
    "lead_time": "lead time",
    "safety_stock": "safety stock",
}

# THIS IS A LIST OF DICTIONARIES. Each dictionary describes one KPI: its
# short id, the label we display, and which fields it needs to be
# calculated. Keeping this in one place means the rest of the program can
# ask "what does this KPI need?" instead of that logic being scattered
# everywhere.
KPI_DEFS = [
    {"id": "total_inventory", "label": "Total inventory", "fields": ["inventory"]},
    {"id": "inventory_turns", "label": "Inventory turns", "fields": ["inventory", "demand"]},
    {"id": "days_inventory", "label": "Days inventory", "fields": ["inventory", "demand"]},
    {"id": "inventory_ratio", "label": "Inventory / demand ratio", "fields": ["inventory", "demand"]},
    {"id": "potential_excess", "label": "Potential excess inventory", "fields": ["inventory", "demand", "lead_time", "safety_stock"]},
]


# ---------------------------------------------------------------------------
# THIS IS A FUNCTION. A function is a named, reusable block of code - you
# define it once, then "call" it (use it) as many times as you like instead
# of retyping the same steps. This particular function cleans up a piece of
# text so two different spellings of the same heading compare as equal,
# e.g. "Inventory €" and "inventory eur" should both become "inventory eur".
# ---------------------------------------------------------------------------
def normalise(text):
    text = str(text).strip().lower().replace("€", " eur ")
    # A "list comprehension": for every character in the text, keep it if
    # it's a letter/number, otherwise replace it with a space.
    only_letters_and_numbers = [ch if ch.isalnum() else " " for ch in text]
    # Join the characters back into one string, then split()/join() again
    # to collapse any repeated spaces down to single spaces.
    return " ".join("".join(only_letters_and_numbers).split())


# Another small function: checks whether a header cell matches any of the
# accepted spellings for a field, using normalise() so spelling/case/symbols
# don't matter.
def header_matches(cell_text, accepted_names):
    return normalise(cell_text) in [normalise(name) for name in accepted_names]


# ---------------------------------------------------------------------------
# THIS IS A FUNCTION that turns messy spreadsheet text into a real Python
# number (a "float", i.e. a number that can have decimals). Spreadsheet
# cells can look like "€12,345", "12.345,00" (European style) or just
# "12345" - this function handles all of those. We use it every time we
# need to read a numeric column from the file.
# ---------------------------------------------------------------------------
def parse_number(value):
    text = str(value).strip()
    # Strip out currency symbols and spaces - they're not part of the number.
    for symbol in ["€", "$", "£", " "]:
        text = text.replace(symbol, "")
    if not text:
        return 0.0

    comma_pos = text.rfind(",")   # rfind = position of the LAST comma (-1 if none)
    dot_pos = text.rfind(".")     # position of the LAST dot (-1 if none)

    if comma_pos > -1 and dot_pos > -1:
        # Both a comma and a dot appear - whichever comes LAST is the real
        # decimal separator, and the other one is a thousands separator.
        if comma_pos > dot_pos:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif comma_pos > -1:
        # Only a comma. If it looks like "1,234" (three digits after it,
        # a thousands separator), remove it. Otherwise treat it as a
        # decimal point, e.g. "12,5" -> "12.5".
        if re.search(r",\d{3}(,|$)", text):
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif dot_pos > -1 and re.search(r"\.\d{3}(\.|$)", text):
        # Only a dot, used as a thousands separator, e.g. "12.345" -> "12345".
        text = text.replace(".", "")

    # Keep only digits, a dot and a minus sign, then convert to a float.
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch in ".-")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# This function is almost the same as parse_number(), but it returns None
# ("nothing here") for a blank cell instead of 0. We keep these separate
# because "the value IS 0" and "we DON'T KNOW the value" are different
# situations for our diagnostics - mixing them up would hide missing data.
def parse_number_or_none(value):
    if str(value).strip() == "":
        return None
    return parse_number(value)


# ---------------------------------------------------------------------------
# THIS IS A FUNCTION that reads a CSV file from disk and returns its rows
# as a list of lists (one inner list per row, one string per cell). We use
# Python's built-in csv module so we don't have to split lines by commas
# ourselves (which breaks on quoted text containing commas).
# ---------------------------------------------------------------------------
def read_inventory_file(path):
    with open(path, newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        # Skip any completely blank rows.
        rows = [row for row in reader if any(cell.strip() for cell in row)]
    return rows


# This function looks at the header row (the first row of the file) and
# works out which column number holds each field, using the ALIASES
# dictionary from up top. It returns a dictionary like:
#   {"sku": 0, "inventory": 2, "demand": 3, "lead_time": -1, "safety_stock": 4}
# where -1 means "this column was not found at all".
def map_columns(header_row):
    positions = {}
    for field, accepted_names in ALIASES.items():
        positions[field] = -1
        # enumerate() gives us both the index and the value while looping.
        for index, cell in enumerate(header_row):
            if header_matches(cell, accepted_names):
                positions[field] = index
                break
    return positions


# ---------------------------------------------------------------------------
# THIS IS A FUNCTION that turns the raw data rows into a clean list of
# dictionaries - one dictionary per SKU - plus a list of "issues" worth
# flagging (duplicate SKUs, negative numbers, rows with no SKU at all).
# This never crashes on missing/blank data; it just records what's missing
# so we can explain it to the user in Step 1 instead of guessing.
# ---------------------------------------------------------------------------
def build_records(data_rows, positions):
    required_fields = ["sku", "inventory", "demand", "lead_time", "safety_stock"]
    missing_columns = [field for field in required_fields if positions[field] == -1]

    records = []
    issues = []
    seen_skus = set()  # a "set" stores unique values - great for spotting duplicates

    for row in data_rows:

        # A small "helper function" defined INSIDE another function - this is
        # allowed in Python, and handy when the helper is only needed here.
        def get_field(field_name):
            column = positions[field_name]
            if column == -1 or column >= len(row):
                return None
            return parse_number_or_none(row[column])

        sku_column = positions["sku"]
        sku = str(row[sku_column]).strip() if sku_column != -1 and sku_column < len(row) else ""

        if not sku:
            issues.append("Ignored a row without an SKU.")
            continue  # "continue" skips the rest of this loop turn and moves to the next row

        if sku in seen_skus:
            issues.append(f'Duplicate SKU "{sku}" is included more than once.')
        seen_skus.add(sku)

        record = {
            "sku": sku,
            "inventory": get_field("inventory"),
            "demand": get_field("demand"),
            "lead_time": get_field("lead_time"),
            "safety_stock": get_field("safety_stock"),
        }

        # Check for negative values - a negative inventory or demand usually
        # means a data entry mistake, so we flag it (but still keep the row).
        for field in ["inventory", "demand", "lead_time", "safety_stock"]:
            if record[field] is not None and record[field] < 0:
                issues.append(f'SKU "{sku}" has a negative value; please review it.')
                break

        # "Potential excess" = inventory sitting beyond what's needed to
        # cover safety stock plus expected demand during the lead time.
        # We can only compute it once ALL four numbers are known.
        all_four_known = None not in (record["inventory"], record["demand"], record["lead_time"], record["safety_stock"])
        if all_four_known:
            expected_lead_time_demand = (record["demand"] / 365) * record["lead_time"]
            record["excess"] = max(0.0, record["inventory"] - record["safety_stock"] - expected_lead_time_demand)
        else:
            record["excess"] = None

        records.append(record)

    # dict.fromkeys(issues) drops duplicate messages while keeping the
    # original order; wrapping it in list(...) turns it back into a list.
    unique_issues = list(dict.fromkeys(issues))
    return records, unique_issues, missing_columns


# ---------------------------------------------------------------------------
# THIS IS A FUNCTION that builds the Step 1 "data quality" report: which
# KPIs are BLOCKED (a whole column is missing, so it can't be computed at
# all), which are DEGRADED (the column exists, but some rows are blank), and
# a list of OUTLIERS (values that parsed fine but look suspicious).
# ---------------------------------------------------------------------------
def build_quality_report(records, missing_columns):
    if not records:
        if "sku" in missing_columns:
            reason = "No SKU / item identifier column was found, so no rows could be matched to a SKU."
        else:
            reason = "No usable SKU rows were found in this file."
        blocked = [{"id": kpi["id"], "label": kpi["label"], "reason": reason} for kpi in KPI_DEFS]
        return {"blocked": blocked, "degraded": [], "outliers": []}

    blocked = []
    blocked_ids = set()
    for kpi in KPI_DEFS:
        missing_fields = [f for f in kpi["fields"] if f in missing_columns]
        if missing_fields:
            labels = " and ".join(FIELD_LABELS[f] for f in missing_fields)
            reason = f"{labels} column was not found, so {kpi['label'].lower()} cannot be computed."
            blocked.append({"id": kpi["id"], "label": kpi["label"], "reason": reason})
            blocked_ids.add(kpi["id"])

    degraded = []
    total = len(records)
    for kpi in KPI_DEFS:
        if kpi["id"] in blocked_ids:
            continue  # already blocked, no point also calling it "degraded"
        usable = [r for r in records if all(r[f] is not None for f in kpi["fields"])]
        if len(usable) == total:
            continue  # nothing missing for this KPI - all good
        missing_field_labels = [FIELD_LABELS[f] for f in kpi["fields"] if any(r[f] is None for r in records)]
        gap = total - len(usable)
        plural = "" if total == 1 else "s"
        reason = (f"{' / '.join(missing_field_labels)} is missing for {gap} of {total} SKU{plural}; "
                  f"{kpi['label'].lower()} is computed from the remaining {len(usable)}.")
        degraded.append({"id": kpi["id"], "label": kpi["label"], "reason": reason})

    return {"blocked": blocked, "degraded": degraded, "outliers": find_outliers(records)}


# THIS IS A FUNCTION for "plausibility checks" - values that are technically
# valid numbers but look suspicious, e.g. a lead time of 0 days. These are
# informational only; they never block a KPI from being shown.
def find_outliers(records):
    complete = [r for r in records if r["inventory"] is not None and r["demand"] is not None and r["lead_time"] is not None]
    positive_values = sorted(r["inventory"] for r in complete if r["inventory"] > 0)
    middle_value = median(positive_values) if positive_values else 0

    messages = []
    for r in complete:
        if r["lead_time"] == 0:
            messages.append(f'SKU "{r["sku"]}": lead time is 0 days; please verify.')
        if r["demand"] == 0 and r["inventory"] > 0:
            messages.append(f'SKU "{r["sku"]}": demand is 0 while inventory is on hand; please verify.')
        if middle_value and r["inventory"] > middle_value * 10:
            messages.append(f'SKU "{r["sku"]}": inventory value is far above the typical SKU (more than 10x the median); please verify.')
    return messages


# A tiny helper function to format a number as euros, e.g. 12345 -> "€12,345".
# The ":,.0f" part is Python's "format spec": comma for thousands, 0 decimals.
def format_euro(value):
    return f"€{value:,.0f}"


# Adds up one field (e.g. "inventory") across a list of records. This is
# the Python equivalent of the JavaScript ".reduce()" pattern.
def sum_field(records, field):
    return sum(record[field] for record in records)


# ---------------------------------------------------------------------------
# THIS IS A FUNCTION that prints the Step 1 screen: a summary of what's
# missing or worth checking, grouped into three sections. It takes the
# records, the free-text issues list, and the quality report we already
# built, and just formats them for the terminal.
# ---------------------------------------------------------------------------
def print_step1_report(records, issues, quality):
    print()
    print("=" * 60)
    print("STEP 1 OF 2 - DATA QUALITY REVIEW")
    print("=" * 60)

    other_issues = issues + quality["outliers"]
    if quality["blocked"] or quality["degraded"] or other_issues:
        print("Before showing the dashboard, here is what we found:\n")
    else:
        plural = "" if len(records) == 1 else "s"
        print(f"Data quality looks good - {len(records)} SKU{plural} ready to analyze.\n")

    # A small helper function, local to this one: prints a titled section
    # of bullet points, but only if there's actually something to show.
    def print_section(title, items, line_for):
        if not items:
            return
        print(f"-- {title} --")
        for item in items:
            print(line_for(item))
        print()

    print_section("Cannot be computed", quality["blocked"], lambda k: f'  * {k["label"]}: {k["reason"]}')
    print_section("Computed from partial data", quality["degraded"], lambda k: f'  * {k["label"]}: {k["reason"]}')
    print_section("Other things to check", other_issues, lambda message: f"  * {message}")


# ---------------------------------------------------------------------------
# THIS IS A FUNCTION that prints ONE KPI card to the terminal: its label,
# its value (or "-" plus a reason if it's blocked), and a note if it's only
# computed from partial data. Reusing this one function for all 5 KPIs
# keeps the "blocked / degraded / fine" logic in a single place.
# ---------------------------------------------------------------------------
def print_kpi(label, records, fields, blocked_by_id, degraded_by_id, kpi_id, compute_value):
    print(f"{label}:")
    if kpi_id in blocked_by_id:
        print("  -")
        print(f"  ({blocked_by_id[kpi_id]['reason']})")
        print()
        return

    # "usable" = only the records that have every field this KPI needs.
    usable = [r for r in records if all(r[f] is not None for f in fields)]
    print(f"  {compute_value(usable)}")
    if kpi_id in degraded_by_id:
        print(f"  ({degraded_by_id[kpi_id]['reason']})")
    print()


# THIS IS A FUNCTION that prints a simple text-based bar chart of the top 8
# SKUs by inventory value, using repeated "#" characters as the bar.
def print_inventory_chart(records):
    chartable = [r for r in records if r["inventory"] is not None]
    print("-- Inventory by SKU (top 8) --")
    if not chartable:
        print("  Inventory value could not be computed for this file.\n")
        return

    # sorted(..., reverse=True) sorts biggest-first; [:8] keeps only the first 8.
    top = sorted(chartable, key=lambda r: r["inventory"], reverse=True)[:8]
    largest = max(r["inventory"] for r in top) or 1  # avoid dividing by zero
    for r in top:
        bar_length = round((r["inventory"] / largest) * 30)  # scale to max 30 characters
        bar = "#" * bar_length
        print(f"  {r['sku']:<20} {bar:<30} {format_euro(r['inventory'])}")
    print()


# THIS IS A FUNCTION that prints a table of the 5 SKUs with the highest
# potential excess inventory - the items most worth investigating first.
def print_opportunities_table(records):
    rankable = [r for r in records if r["excess"] is not None]
    print("-- Top 5 opportunities (highest potential excess inventory) --")
    if not rankable:
        print("  Potential excess could not be computed for this file.\n")
        return

    top = sorted(rankable, key=lambda r: r["excess"], reverse=True)[:5]
    print(f"  {'SKU':<20}{'Inventory':>15}{'Potential excess':>20}")
    for r in top:
        print(f"  {r['sku']:<20}{format_euro(r['inventory']):>15}{format_euro(r['excess']):>20}")
    print()


# ---------------------------------------------------------------------------
# THIS IS A FUNCTION that prints the whole Step 2 dashboard: the 5 KPI
# cards, the bar chart, and the opportunities table, in that order.
# ---------------------------------------------------------------------------
def print_step2_dashboard(records, quality):
    print()
    print("=" * 60)
    print("STEP 2 OF 2 - INVENTORY HEALTH AT A GLANCE")
    print("=" * 60)
    print()

    # Turning the blocked/degraded lists into dictionaries keyed by KPI id
    # makes "is this KPI blocked?" a fast, simple lookup instead of a loop.
    blocked_by_id = {k["id"]: k for k in quality["blocked"]}
    degraded_by_id = {k["id"]: k for k in quality["degraded"]}

    print_kpi(
        "Total inventory", records, ["inventory"], blocked_by_id, degraded_by_id, "total_inventory",
        lambda usable: format_euro(sum_field(usable, "inventory")),
    )

    def turns_value(usable):
        inv = sum_field(usable, "inventory")
        dem = sum_field(usable, "demand")
        turns = dem / inv if inv else 0
        return f"{turns:.1f}x"
    print_kpi("Inventory turns", records, ["inventory", "demand"], blocked_by_id, degraded_by_id, "inventory_turns", turns_value)

    def days_value(usable):
        inv = sum_field(usable, "inventory")
        dem = sum_field(usable, "demand")
        turns = dem / inv if inv else 0
        days = 365 / turns if turns else 0
        return f"{round(days)} days"
    print_kpi("Days inventory", records, ["inventory", "demand"], blocked_by_id, degraded_by_id, "days_inventory", days_value)

    def ratio_value(usable):
        inv = sum_field(usable, "inventory")
        dem = sum_field(usable, "demand")
        ratio = (inv / dem) * 100 if dem else 0
        return f"{ratio:.1f}%"
    print_kpi("Inventory / demand ratio", records, ["inventory", "demand"], blocked_by_id, degraded_by_id, "inventory_ratio", ratio_value)

    print_kpi(
        "Potential excess inventory", records, ["inventory", "demand", "lead_time", "safety_stock"],
        blocked_by_id, degraded_by_id, "potential_excess",
        lambda usable: format_euro(sum_field(usable, "excess")),
    )

    print_inventory_chart(records)
    print_opportunities_table(records)


# ---------------------------------------------------------------------------
# THIS IS A FUNCTION called main(). It is the "entry point" of the program -
# the function that runs first and controls the overall flow (ask for a
# file, show Step 1, maybe show Step 2, ask to go again), the same job the
# button click-handlers did at the bottom of the original JavaScript file.
# ---------------------------------------------------------------------------
def main():
    print("INVENTORY DIAGNOSTIC (Python edition)")
    print("Give it a CSV inventory file to see the first five diagnostic KPIs.\n")

    # sys.argv is a list of the words typed on the command line.
    # sys.argv[0] is always the script's own name; sys.argv[1] (if present)
    # is the first extra argument, e.g. a file path.
    file_path_from_command_line = sys.argv[1] if len(sys.argv) > 1 else None

    # A "while True" loop repeats forever until we explicitly "break" out of
    # it - here, that lets the user analyse more than one file in a row.
    while True:
        if file_path_from_command_line:
            path = file_path_from_command_line
            file_path_from_command_line = None  # only use the command-line one once
        else:
            path = input("Path to your CSV file (press Enter to use sample-inventory.csv): ").strip()
            if not path:
                path = "sample-inventory.csv"

        # "try/except" lets us attempt something risky (opening a file that
        # might not exist) without crashing the whole program if it fails.
        try:
            rows = read_inventory_file(path)
        except OSError as error:
            print(f"Could not read that file: {error}\n")
            continue  # go back to the top of the loop and ask again

        if not rows:
            print("That file looks empty.\n")
            continue

        header_row, data_rows = rows[0], rows[1:]
        positions = map_columns(header_row)
        records, issues, missing_columns = build_records(data_rows, positions)
        quality = build_quality_report(records, missing_columns)

        print_step1_report(records, issues, quality)

        if not records:
            print("No SKUs could be analysed from this file.\n")
        else:
            answer = input("Continue to dashboard? (y/n): ").strip().lower()
            if answer.startswith("y"):
                print_step2_dashboard(records, quality)

        again = input("Analyse another file? (y/n): ").strip().lower()
        if not again.startswith("y"):
            print("Goodbye!")
            break  # exits the while loop, ending the program


# ---------------------------------------------------------------------------
# This "if" check is a common Python pattern. __name__ is a special variable
# Python sets automatically; it only equals "__main__" when this file is run
# directly (e.g. `python inventory_diagnostic.py`), not when it's imported
# by another file. So this line means: "only start the program here."
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
