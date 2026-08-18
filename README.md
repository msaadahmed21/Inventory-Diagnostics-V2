# Inventory Diagnostic (v2)

A static, client-side inventory diagnostic tool. Upload a CSV/Excel export and
see 5 headline KPIs: total inventory, inventory turns, days inventory,
inventory/demand ratio, and potential excess inventory.

No build step, no backend - just open `index.html` (or serve the folder
statically) and it runs entirely in the browser using
[SheetJS](https://sheetjs.com/) to parse the uploaded file.

## Flow

1. **Upload** - pick a CSV/Excel file, or try the included `sample-inventory.csv`.
2. **Step 1: data quality review** - always shown before the dashboard. Explains
   what's missing from the file (a whole column, or just some rows) and exactly
   which KPIs that blocks or degrades, plus any other things worth checking
   (duplicate SKUs, suspicious values). If the file is clean, this just says so.
3. **Step 2: dashboard** - the 5 KPIs, a bar chart of inventory by SKU, and a
   table of the top opportunities by estimated excess inventory. Any KPI that
   couldn't be fully computed is shown as `—` with a short reason instead of a
   silently wrong number.

## Files

- `index.html` - page structure (upload screen, Step 1, Step 2)
- `app.js` - all logic: file parsing, the data-quality checks, and rendering
- `style.css` - styling
- `sample-inventory.csv` - example file matching the expected columns

## What's new in v2

- The upload → data-quality-review → dashboard flow is now always two explicit
  steps, instead of conditionally skipping straight to the dashboard.
- `app.js` and the former `data-quality.js` are combined into one file.
