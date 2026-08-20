// Inventory Diagnostic v2 - all app logic in one file.
// Flow: pick a file -> Step 1 (data quality review, always shown) -> Step 2 (dashboard).

// ---------- DOM references ----------
const uploadView = document.querySelector('#upload');
const step1View = document.querySelector('#step1');
const step2View = document.querySelector('#step2');
const fileInput = document.querySelector('#file-input');
const status = document.querySelector('#status');
const euro = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });

// Holds the parsed result while the user is on Step 1, so "Continue" can render Step 2.
let pending = null;

// ---------- Column aliases (accepted header spellings) ----------
const aliases = {
  sku: ['sku', 'item', 'item number', 'material', 'material number', 'product', 'product code'],
  inventory: ['inventory €', 'inventory eur', 'inventory', 'inventory value', 'stock value', 'on hand value', 'on hand inventory'],
  demand: ['annual demand €', 'annual demand eur', 'annual demand', 'demand', 'annual sales', 'yearly demand', 'annual consumption'],
  leadTime: ['lead time days', 'lead time', 'leadtime', 'lead time day', 'procurement lead time'],
  safetyStock: ['safety stock €', 'safety stock eur', 'safety stock', 'safety stock value', 'buffer stock']
};

// ---------- Data quality: which fields each KPI needs ----------
// Single source of truth for the "X is missing, so Y can't be computed" messaging on Step 1.
const KPI_DEFS = [
  { id: 'total-inventory', label: 'Total inventory', fields: ['inventory'] },
  { id: 'inventory-turns', label: 'Inventory turns', fields: ['inventory', 'demand'] },
  { id: 'days-inventory', label: 'Days inventory', fields: ['inventory', 'demand'] },
  { id: 'inventory-ratio', label: 'Inventory / demand ratio', fields: ['inventory', 'demand'] },
  { id: 'potential-excess', label: 'Potential excess inventory', fields: ['inventory', 'demand', 'leadTime', 'safetyStock'] }
];
const FIELD_LABELS = { sku: 'SKU', inventory: 'inventory value', demand: 'annual demand', leadTime: 'lead time', safetyStock: 'safety stock' };

// Builds the Step 1 report: which KPIs are blocked (a required column is missing
// entirely), which are degraded (column exists but some rows are blank), and
// which values look suspicious (outliers - informational only, never blocking).
function buildQualityReport(records, missingColumns = []) {
  if (!records.length) {
    const reason = missingColumns.includes('sku')
      ? 'No SKU / item identifier column was found, so no rows could be matched to a SKU.'
      : 'No usable SKU rows were found in this file.';
    return { blockedKpis: KPI_DEFS.map(k => ({ id: k.id, label: k.label, reason })), degradedKpis: [], outliers: [] };
  }

  const blockedKpis = KPI_DEFS.filter(k => k.fields.some(f => missingColumns.includes(f))).map(k => {
    const missingFields = k.fields.filter(f => missingColumns.includes(f)).map(f => FIELD_LABELS[f]);
    return { id: k.id, label: k.label, reason: `${missingFields.join(' and ')} column was not found, so ${k.label.toLowerCase()} cannot be computed.` };
  });
  const blockedIds = new Set(blockedKpis.map(k => k.id));

  const degradedKpis = KPI_DEFS.filter(k => !blockedIds.has(k.id)).map(k => {
    const usable = records.filter(r => k.fields.every(f => r[f] != null)).length;
    if (usable === records.length) return null;
    const missingFieldLabels = k.fields.filter(f => records.some(r => r[f] == null)).map(f => FIELD_LABELS[f]);
    const gap = records.length - usable;
    return { id: k.id, label: k.label, reason: `${missingFieldLabels.join(' / ')} is missing for ${gap} of ${records.length} SKU${records.length === 1 ? '' : 's'}; ${k.label.toLowerCase()} is computed from the remaining ${usable}.` };
  }).filter(Boolean);

  return { blockedKpis, degradedKpis, outliers: findOutliers(records) };
}

// Plausibility checks: values that parse fine but look suspicious. Informational only.
function findOutliers(records) {
  const complete = records.filter(r => r.inventory != null && r.demand != null && r.leadTime != null);
  const positives = complete.map(r => r.inventory).filter(v => v > 0).sort((a, b) => a - b);
  const mid = Math.floor(positives.length / 2);
  const median = positives.length ? (positives.length % 2 ? positives[mid] : (positives[mid - 1] + positives[mid]) / 2) : 0;
  const messages = [];
  complete.forEach(r => {
    if (r.leadTime === 0) messages.push(`SKU "${r.sku}": lead time is 0 days; please verify.`);
    if (r.demand === 0 && r.inventory > 0) messages.push(`SKU "${r.sku}": demand is 0 while inventory is on hand; please verify.`);
    if (median && r.inventory > median * 10) messages.push(`SKU "${r.sku}": inventory value is far above the typical SKU (more than 10x the median); please verify.`);
  });
  return messages;
}

// ---------- Parsing helpers ----------
function normalise(v) { return String(v ?? '').trim().toLowerCase().replace(/€/g, ' eur ').replace(/[^a-z0-9]+/g, ' ').trim(); }
function headerMatches(v, names) { return names.map(normalise).includes(normalise(v)); }
// Parses a numeric cell that may use different regional formats (currency symbols, EU/US decimals).
function number(v) {
  let text = String(v ?? '').trim().replace(/[€$£\s]/g, '');
  if (!text) return 0;
  const comma = text.lastIndexOf(','), dot = text.lastIndexOf('.');
  if (comma > -1 && dot > -1) text = comma > dot ? text.replace(/\./g, '').replace(',', '.') : text.replace(/,/g, '');
  else if (comma > -1) text = /,\d{3}(,|$)/.test(text) ? text.replace(/,/g, '') : text.replace(',', '.');
  else if (dot > -1 && /\.\d{3}(\.|$)/.test(text)) text = text.replace(/\./g, '');
  return Number(text.replace(/[^0-9.-]/g, '')) || 0;
}
// Like number(), but null for a blank cell instead of 0 - keeps "missing" distinguishable from "zero".
function numberOrNull(v) { return String(v ?? '').trim() ? number(v) : null; }
// Scans the first 100 rows for the one that looks most like a header row.
function findHeaderRow(values) {
  let best = { index: 0, score: -1 };
  values.slice(0, 100).forEach((row, index) => {
    const score = row.filter(cell => Object.values(aliases).some(names => headerMatches(cell, names))).length;
    if (score > best.score) best = { index, score };
  });
  return best;
}

function cellAt(sheet, column, row) { return sheet[`${column}${row}`]?.v; }
function lastRow(sheet) { return XLSX.utils.decode_range(sheet['!ref'] || 'A1:A1').e.r + 1; }

// Special-case parser for a specific multi-sheet "SAP inventory network" export
// (fixed sheet names, fixed cell layout). Returns null if it doesn't match.
function parseSapNetworkWorkbook(workbook) {
  const requiredSheets = ['Master Data', 'Stock'];
  const usageSheets = workbook.SheetNames.filter(name => /^Usage_/.test(name));
  if (!requiredSheets.every(name => workbook.Sheets[name]) || !usageSheets.length) return null;

  const master = new Map();
  const masterSheet = workbook.Sheets['Master Data'];
  for (let row = 3; row <= lastRow(masterSheet); row += 1) {
    const sku = String(cellAt(masterSheet, 'A', row) ?? '').trim();
    if (!sku) continue;
    const siteReorderLevel = ['K', 'M', 'O', 'Q', 'S'].reduce((sum, col) => sum + number(cellAt(masterSheet, col, row)), 0);
    master.set(sku, { unitValue: number(cellAt(masterSheet, 'F', row)), leadTime: number(cellAt(masterSheet, 'I', row)), bufferQty: siteReorderLevel || number(cellAt(masterSheet, 'J', row)) });
  }

  const stock = new Map();
  const stockSheet = workbook.Sheets.Stock;
  for (let row = 29; row <= lastRow(stockSheet); row += 1) {
    const sku = String(cellAt(stockSheet, 'A', row) ?? '').trim();
    if (!sku || sku === 'Gesamtergebnis') continue;
    const quantity = ['B', 'C', 'D', 'E', 'F'].reduce((sum, col) => sum + number(cellAt(stockSheet, col, row)), 0);
    if (quantity) stock.set(sku, quantity);
  }

  const usage = new Map();
  usageSheets.forEach(name => {
    const sheet = workbook.Sheets[name];
    for (let row = 29; row <= lastRow(sheet); row += 1) {
      const sku = String(cellAt(sheet, 'A', row) ?? '').trim();
      if (!sku || sku === 'Gesamtergebnis') continue;
      usage.set(sku, (usage.get(sku) || 0) + number(cellAt(sheet, 'B', row)));
    }
  });

  const issues = []; let missingMaster = 0; let missingValue = 0;
  const records = [...stock.entries()].map(([sku, stockQty]) => {
    const details = master.get(sku);
    if (!details) { missingMaster += 1; return null; }
    if (!details.unitValue) missingValue += 1;
    const annualUsageQty = (usage.get(sku) || 0) / 3; // 36 monthly periods (Jan 2008-Dec 2010) in the source model
    const inventory = stockQty * details.unitValue;
    const demand = annualUsageQty * details.unitValue;
    const safetyStock = details.bufferQty * details.unitValue;
    return { sku, inventory, demand, leadTime: details.leadTime, safetyStock, excess: Math.max(0, inventory - safetyStock - (demand / 365) * details.leadTime) };
  }).filter(Boolean);

  if (missingMaster) issues.push(`${missingMaster} stocked SKU${missingMaster === 1 ? '' : 's'} had no matching master-data record and were excluded.`);
  if (missingValue) issues.push(`${missingValue} SKU${missingValue === 1 ? '' : 's'} have a zero or missing unit value; their € impact may be understated.`);
  issues.push('Demand is annualised from 36 months of historic usage (January 2008-December 2010).');
  issues.push('Reorder levels are used as a buffer-stock proxy; this is an initial diagnostic assumption.');
  if (!records.length) throw new Error('I recognised the SAP network format but could not create any stocked SKU records.');
  return { records, issues, source: 'SAP inventory network model' };
}

// Generic parser for a simple flat table. Never throws for missing/blank data -
// records what's missing so Step 1 can explain it instead.
function validateAndPrepare(rows) {
  const headers = rows[0] || [];
  const positions = Object.fromEntries(Object.entries(aliases).map(([field, names]) => [field, headers.findIndex(cell => headerMatches(cell, names))]));
  const required = ['sku', 'inventory', 'demand', 'leadTime', 'safetyStock'];
  const missingColumns = required.filter(field => positions[field] === -1);

  const issues = []; const seen = new Set();
  const records = rows.slice(1).map(row => {
    // A field is null when its column is missing entirely or the cell is blank -
    // both are "unknown", as opposed to a real parsed number (including 0).
    const field = name => positions[name] === -1 ? null : numberOrNull(row[positions[name]]);
    const record = { sku: positions.sku === -1 ? '' : String(row[positions.sku] ?? '').trim(), inventory: field('inventory'), demand: field('demand'), leadTime: field('leadTime'), safetyStock: field('safetyStock') };
    if (!record.sku) { issues.push('Ignored a row without an SKU.'); return null; }
    if (seen.has(record.sku)) issues.push(`Duplicate SKU "${record.sku}" is included more than once.`);
    seen.add(record.sku);
    if ((record.inventory ?? 0) < 0 || (record.demand ?? 0) < 0 || (record.leadTime ?? 0) < 0 || (record.safetyStock ?? 0) < 0) issues.push(`SKU "${record.sku}" has a negative value; please review it.`);
    // Excess = inventory beyond safety stock plus expected lead-time demand; only computable when all four inputs are known.
    const complete = record.inventory != null && record.demand != null && record.leadTime != null && record.safetyStock != null;
    return { ...record, excess: complete ? Math.max(0, record.inventory - record.safetyStock - (record.demand / 365) * record.leadTime) : null };
  }).filter(Boolean);

  return { records, issues: [...new Set(issues)], missingColumns };
}

function escapeHtml(v) { const el = document.createElement('div'); el.textContent = v; return el.innerHTML; }

// ---------- Screen switching ----------
function showView(view) {
  [uploadView, step1View, step2View].forEach(v => v.classList.toggle('hidden', v !== view));
  document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === view.id));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function resetToUpload() {
  fileInput.value = ''; pending = null;
  status.textContent = 'Choose another file to run the diagnostic.';
  showView(uploadView);
}

// ---------- Step 1: data quality review ----------
function renderStep1() {
  const { records, issues, quality } = pending;
  const otherIssues = [...issues, ...quality.outliers];
  const section = (title, items, renderItem) => items.length ? `<div class="gate-section"><h3>${title}</h3><ul>${items.map(renderItem).join('')}</ul></div>` : '';

  document.querySelector('#step1-summary').innerHTML = quality.blockedKpis.length || quality.degradedKpis.length || otherIssues.length
    ? '<p class="intro">Before showing the dashboard, here is what we found and how it affects the results.</p>'
    : `<p class="intro">Data quality looks good - ${records.length} SKU${records.length === 1 ? '' : 's'} ready to analyze.</p>`;

  document.querySelector('#step1-details').innerHTML =
    section('Cannot be computed', quality.blockedKpis, k => `<li><strong>${escapeHtml(k.label)}</strong> — ${escapeHtml(k.reason)}</li>`) +
    section('Computed from partial data', quality.degradedKpis, k => `<li><strong>${escapeHtml(k.label)}</strong> — ${escapeHtml(k.reason)}</li>`) +
    section('Other things to check', otherIssues, issue => `<li>${escapeHtml(issue)}</li>`);

  document.querySelector('#step1-continue').classList.toggle('hidden', records.length === 0);
  showView(step1View);
}

// ---------- Step 2: dashboard ----------
function renderStep2() {
  const { records, quality } = pending;
  const blockedById = new Map(quality.blockedKpis.map(k => [k.id, k]));
  const degradedById = new Map(quality.degradedKpis.map(k => [k.id, k]));
  const sum = (list, field) => list.reduce((s, r) => s + r[field], 0);

  // Writes one KPI card: "—" + reason if blocked, otherwise computes from the
  // records that have every field this KPI needs (with a note if that's a subset).
  const setKpi = (id, fields, formatFn) => {
    const strong = document.querySelector(`#${id}`);
    const article = strong.closest('.kpi');
    const note = document.querySelector(`#${id}-note`);
    article.classList.remove('blocked', 'degraded');
    if (blockedById.has(id)) { strong.textContent = '—'; note.textContent = blockedById.get(id).reason; article.classList.add('blocked'); return; }
    const usable = records.filter(r => fields.every(f => r[f] != null));
    strong.textContent = formatFn(usable);
    if (degradedById.has(id)) { note.textContent = degradedById.get(id).reason; article.classList.add('degraded'); }
    else note.textContent = '';
  };

  setKpi('total-inventory', ['inventory'], list => euro.format(sum(list, 'inventory')));
  setKpi('inventory-turns', ['inventory', 'demand'], list => { const inv = sum(list, 'inventory'), dem = sum(list, 'demand'); return `${(inv ? dem / inv : 0).toFixed(1)}×`; });
  setKpi('days-inventory', ['inventory', 'demand'], list => { const inv = sum(list, 'inventory'), dem = sum(list, 'demand'); const turns = inv ? dem / inv : 0; return `${Math.round(turns ? 365 / turns : 0)} days`; });
  setKpi('inventory-ratio', ['inventory', 'demand'], list => { const inv = sum(list, 'inventory'), dem = sum(list, 'demand'); return `${(dem ? (inv / dem) * 100 : 0).toFixed(1)}%`; });
  setKpi('potential-excess', ['inventory', 'demand', 'leadTime', 'safetyStock'], list => euro.format(sum(list, 'excess')));

  const chartable = records.filter(r => r.inventory != null);
  const chartEl = document.querySelector('#inventory-chart');
  if (!chartable.length) {
    chartEl.innerHTML = '<p class="hint">Inventory value could not be computed for this file.</p>';
  } else {
    const top = [...chartable].sort((a, b) => b.inventory - a.inventory).slice(0, 8);
    const largest = Math.max(...top.map(r => r.inventory), 1);
    chartEl.innerHTML = top.map(r => `<div class="bar-row"><span>${escapeHtml(r.sku)}</span><div class="bar"><span style="width:${(r.inventory / largest) * 100}%"></span></div><span class="bar-value">${euro.format(r.inventory)}</span></div>`).join('');
  }

  const rankable = records.filter(r => r.excess != null);
  document.querySelector('#opportunities-table').innerHTML = rankable.length
    ? [...rankable].sort((a, b) => b.excess - a.excess).slice(0, 5).map(r => `<tr><td>${escapeHtml(r.sku)}</td><td>${euro.format(r.inventory)}</td><td>${euro.format(r.excess)}</td></tr>`).join('')
    : '<tr><td colspan="3">Potential excess could not be computed for this file.</td></tr>';

  showView(step2View);
}

// ---------- Wiring ----------
fileInput.addEventListener('change', event => {
  const [file] = event.target.files;
  if (!file) return;
  if (!window.XLSX) { status.textContent = 'The Excel reader did not load. Please check your internet connection and refresh the page.'; return; }
  status.textContent = `Reading ${file.name}… Large multi-sheet workbooks can take up to a minute.`;
  const reader = new FileReader();
  reader.onload = loadEvent => {
    window.setTimeout(() => { try {
      const workbook = XLSX.read(loadEvent.target.result, { type: 'array' });
      const sap = parseSapNetworkWorkbook(workbook);
      if (sap) {
        pending = { records: sap.records, issues: sap.issues, quality: buildQualityReport(sap.records) };
      } else {
        const selectedSheet = workbook.SheetNames.map(name => {
          const values = XLSX.utils.sheet_to_json(workbook.Sheets[name], { header: 1, defval: '' });
          return { name, values, header: findHeaderRow(values) };
        }).sort((a, b) => b.header.score - a.header.score)[0];
        if (selectedSheet.header.score < 2) throw new Error('I could not recognize enough column headings. Use the sample template, or rename your headings to match it.');
        const result = validateAndPrepare(selectedSheet.values.slice(selectedSheet.header.index));
        pending = { records: result.records, issues: result.issues, quality: buildQualityReport(result.records, result.missingColumns) };
      }
      status.textContent = `${pending.records.length} SKU${pending.records.length === 1 ? '' : 's'} analysed from ${file.name}.`;
      renderStep1();
    } catch (error) { status.textContent = error.message || 'I could not read that file.'; } }, 30);
  };
  reader.readAsArrayBuffer(file);
});

document.querySelector('#step1-continue').addEventListener('click', () => { if (pending) renderStep2(); });
document.querySelectorAll('.upload-different').forEach(button => button.addEventListener('click', resetToUpload));
