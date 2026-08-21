# Inventory Diagnostic

This repo now ships **two versions** of the same tool, for two different
purposes:

1. **The live web app** (`index.html`, `app.js`, `style.css`) - a
   static, client-side app you open in a browser. This is what's
   published at the project's GitHub Pages link. No build step, no
   backend - it runs entirely in the browser using
   [SheetJS](https://sheetjs.com/) to parse the uploaded file.
2. **A Python command-line version** (`inventory_diagnostic.py`) - the
   same logic and flow, rewritten as a heavily-commented terminal
   program, aimed at someone revising core Python concepts (functions,
   dictionaries, lists, loops, `try`/`except`). It runs in a terminal,
   not a browser, and isn't part of the hosted web app (GitHub Pages
   can only serve static HTML/CSS/JS, not run Python).

Both give you the same 5 headline KPIs from an inventory file: total
inventory, inventory turns, days inventory, inventory/demand ratio, and
potential excess inventory.

## Web app: flow

1. **Step 1: Data Foundation** - where data comes in. Six tabs: Overview,
   Sources & Ingestion, Data Quality Cockpit, Unstructured Capture, Golden
   Record Workbench, and Governance & Lineage - previewing the roadmap for
   pulling data from every source a team actually works with (ERP, Excel,
   email, PPT decks, meeting transcripts). **Only the "Sources & Ingestion"
   tab is live today** - it's where you pick a CSV/Excel file, or try the
   included `sample-inventory.csv`. The other five tabs show illustrative,
   synthetic data as a preview of what this becomes once connected to real
   auto-extraction sources - clearly marked with a wireframe banner, not
   live functionality yet.
2. **Step 2: data quality review** - always shown before the dashboard. Explains
   what's missing from the file (a whole column, or just some rows) and exactly
   which KPIs that blocks or degrades, plus any other things worth checking
   (duplicate SKUs, suspicious values). If the file is clean, this just says so.
3. **Step 3: dashboard** - the 5 KPIs, a bar chart of inventory by SKU, and a
   table of the top opportunities by estimated excess inventory. Any KPI that
   couldn't be fully computed is shown as `—` with a short reason instead of a
   silently wrong number.

### Web app files

- `index.html` - page structure (Data Foundation / Step 1, Step 2, Step 3)
- `app.js` - all logic: file parsing, the data-quality checks, rendering, and
  the Data Foundation tab-switching
- `style.css` - styling

## Python version: how to run it

No installation needed beyond Python itself - it only uses Python's
built-in standard library (`csv`, `sys`, `re`, `statistics`).

```
python inventory_diagnostic.py
```

or point it straight at a file:

```
python inventory_diagnostic.py sample-inventory.csv
```

If you don't pass a file, it will ask for a path and default to
`sample-inventory.csv` if you just press Enter. It follows the same
Step 1 (data quality) → Step 2 (dashboard) flow as the web app, printed
to the terminal instead of rendered as a web page.

Note: the Python version's file parser is intentionally simpler than
the web app's - it reads a single flat CSV file (like
`sample-inventory.csv`), and doesn't include the web app's very
specific "SAP inventory network" multi-sheet Excel importer.

## Shared files

- `sample-inventory.csv` - example file matching the expected columns,
  usable by both versions.

## Expected columns

Both versions look for these columns (a few alternate spellings are
accepted for each):

| SKU | Inventory € | Annual Demand € | Lead Time days | Safety Stock € |
|-----|-------------|------------------|-----------------|-----------------|
| A001 | 120000 | 600000 | 30 | 40000 |
| A002 | 80000 | 320000 | 45 | 30000 |
| A003 | 250000 | 500000 | 60 | 120000 |
