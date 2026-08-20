# Inventory Diagnostic (Python edition)

A simple command-line (terminal-based) inventory diagnostic tool. Give it a
CSV inventory export and see 5 headline KPIs: total inventory, inventory
turns, days inventory, inventory/demand ratio, and potential excess
inventory.

No installation needed beyond Python itself - it only uses Python's
built-in standard library (`csv`, `sys`, `re`, `statistics`).

## How to run it

```
python inventory_diagnostic.py
```

or point it straight at a file:

```
python inventory_diagnostic.py sample-inventory.csv
```

If you don't pass a file, it will ask for a path and default to
`sample-inventory.csv` if you just press Enter.

## Flow

1. **Choose a file** - a CSV export, or the included `sample-inventory.csv`.
2. **Step 1: data quality review** - always shown before the dashboard.
   Explains what's missing from the file (a whole column, or just some
   rows) and exactly which KPIs that blocks or degrades, plus any other
   things worth checking (duplicate SKUs, suspicious values). If the file
   is clean, this just says so.
3. **Step 2: dashboard** - the 5 KPIs, a text-based bar chart of inventory
   by SKU, and a table of the top opportunities by estimated excess
   inventory. Any KPI that couldn't be fully computed shows `-` with a
   short reason instead of a silently wrong number.

## Files

- `inventory_diagnostic.py` - the whole program: file parsing, the
  data-quality checks, the KPI maths, and printing the report to the
  terminal. It's written with plenty of comments, aimed at someone
  revising core Python concepts (functions, dictionaries, lists,
  loops, `try`/`except`).
- `sample-inventory.csv` - example file matching the expected columns.

## Expected columns

The program looks for these columns (a few alternate spellings are
accepted for each - see `ALIASES` near the top of the script):

| SKU | Inventory € | Annual Demand € | Lead Time days | Safety Stock € |
|-----|-------------|------------------|-----------------|-----------------|
| A001 | 120000 | 600000 | 30 | 40000 |
| A002 | 80000 | 320000 | 45 | 30000 |
| A003 | 250000 | 500000 | 60 | 120000 |

## What's new in this edition

- Rewritten from a browser-based JavaScript/HTML/CSS app into a single
  Python script that runs in the terminal.
- The very specific "SAP inventory network" multi-sheet Excel importer
  from the old version was dropped to keep the code simple and readable;
  this edition reads a single flat CSV file, which covers the same
  column layout as `sample-inventory.csv`.
