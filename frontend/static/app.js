const API = '/api';
let customers = [];
let processRates = {};
let materialPrices = {};
let lineItemCount = 0;

// --- Navigation ---
function showSection(name) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`section-${name}`).classList.add('active');
    const btn = [...document.querySelectorAll('.nav-btn')].find(b => b.getAttribute('onclick')?.includes(`'${name}'`));
    if (btn) btn.classList.add('active');
    if (name === 'quotes') loadQuotes();
    if (name === 'customers') loadCustomers();
    if (name === 'new-quote') initNewQuote();
}

// --- Load reference data ---
async function loadRates() {
    const [ratesRes, matsRes] = await Promise.all([
        fetch(`${API}/process-rates/`),
        fetch(`${API}/materials/`)
    ]);
    const ratesArr = await ratesRes.json();
    const matsArr = await matsRes.json();
    processRates = {};
    ratesArr.forEach(r => { processRates[r.process_type] = r.rate_per_hour; });
    materialPrices = {};
    matsArr.forEach(m => { materialPrices[m.material_type] = m.price_per_lb; });
}

// --- Quotes ---
async function loadQuotes() {
    const res = await fetch(`${API}/quotes/`);
    const quotes = await res.json();
    const el = document.getElementById('quotes-list');
    if (!quotes.length) {
        el.innerHTML = '<div class="empty-state">No quotes yet. Hit <strong>+ New Quote</strong> to start.</div>';
        return;
    }
    el.innerHTML = quotes.map(q => `
        <div class="card" onclick="showQuoteDetail(${q.id})">
            <div class="card-header">
                <div>
                    <div class="card-title">${q.customer?.name || 'Unknown'}</div>
                    <div class="card-sub">${q.quote_number} &middot; ${q.customer?.company || ''}</div>
                    <div class="card-sub">${(q.project_description || '').slice(0, 60)}</div>
                    <div class="card-sub" style="margin-top:4px">
                        <span class="badge badge-type">${(q.job_type||'custom').replace('_',' ')}</span>
                        ${q.contingency_pct > 0 ? `<span class="badge badge-warn">+${q.contingency_pct}% contingency</span>` : ''}
                    </div>
                </div>
                <div style="text-align:right">
                    <div class="card-total">$${(q.total||0).toLocaleString('en-US', {minimumFractionDigits:2})}</div>
                    <div style="color:var(--text-dim);font-size:11px">cost: $${(q.subtotal||0).toLocaleString('en-US', {minimumFractionDigits:2})}</div>
                    <span class="badge badge-${q.status}">${q.status}</span>
                </div>
            </div>
            <div class="card-sub">${new Date(q.created_at).toLocaleDateString()}</div>
        </div>
    `).join('');
}

async function showQuoteDetail(id) {
    const [qRes, bkRes] = await Promise.all([
        fetch(`${API}/quotes/${id}`),
        fetch(`${API}/quotes/${id}/breakdown`)
    ]);
    const q = await qRes.json();
    const bk = await bkRes.json();
    showSection('quote-detail');
    document.getElementById('quote-detail-content').innerHTML = `
        <div class="quote-detail-header">
            <div>
                <div class="quote-number">${q.quote_number}</div>
                <div style="color:var(--text-dim);margin-top:4px">${q.customer?.name}${q.customer?.company ? ' · ' + q.customer.company : ''}</div>
                <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
                    <select class="status-select" onchange="updateStatus(${q.id}, this.value)">
                        ${['draft','sent','accepted','declined'].map(s =>
                            `<option value="${s}" ${q.status===s?'selected':''}>${s.charAt(0).toUpperCase()+s.slice(1)}</option>`
                        ).join('')}
                    </select>
                    <span class="badge badge-type">${(q.job_type||'custom').replace(/_/g,' ')}</span>
                </div>
            </div>
            <div style="text-align:right">
                <div class="quote-total-big">$${(q.total||0).toLocaleString('en-US', {minimumFractionDigits:2})}</div>
                <div style="color:var(--text-dim);font-size:12px">Valid ${q.valid_days} days &middot; Expires ${new Date(Date.now()+q.valid_days*86400000).toLocaleDateString()}</div>
            </div>
        </div>

        <!-- Cost Breakdown (internal) -->
        <div class="breakdown-card">
            <div class="breakdown-title">📊 Cost Breakdown (Internal)</div>
            <div class="breakdown-grid">
                <div class="brow"><span>Materials (with waste)</span><span>$${bk.material_cost.toFixed(2)}</span></div>
                <div class="brow"><span>Labor</span><span>$${bk.labor_cost.toFixed(2)}</span></div>
                ${bk.outsourced_cost > 0 ? `<div class="brow"><span>Outsourced (powder coat, etc.)</span><span>$${bk.outsourced_cost.toFixed(2)}</span></div>` : ''}
                <div class="brow"><span>Subtotal</span><span>$${bk.subtotal_raw.toFixed(2)}</span></div>
                ${bk.contingency_pct > 0 ? `<div class="brow warn"><span>Contingency (+${bk.contingency_pct}%)</span><span>+$${bk.contingency_amt.toFixed(2)}</span></div>` : ''}
                <div class="brow"><span>Cost to deliver</span><span>$${bk.subtotal_with_contingency.toFixed(2)}</span></div>
                <div class="brow profit"><span>Profit margin (+${bk.profit_margin_pct}%)</span><span>+$${bk.profit_amt.toFixed(2)}</span></div>
                <div class="brow total-final"><span>QUOTE TOTAL</span><span>$${bk.total.toFixed(2)}</span></div>
            </div>
        </div>

        ${q.project_description ? `<p style="color:var(--text-dim);margin:1rem 0">${q.project_description}</p>` : ''}

        <table class="detail-table">
            <thead>
                <tr>
                    <th>Description</th>
                    <th>Material</th>
                    <th>Process</th>
                    <th>Qty</th>
                    <th>Wt (lbs)</th>
                    <th>Mat Cost</th>
                    <th>Labor</th>
                    <th>Line Total</th>
                </tr>
            </thead>
            <tbody>
                ${q.line_items.map(item => `
                    <tr ${item.outsourced ? 'class="outsourced-row"' : ''}>
                        <td>${item.description}${item.outsourced ? ' <span class="badge badge-out">outsourced</span>' : ''}</td>
                        <td>${item.material_type?.replace(/_/g,' ') || '—'}</td>
                        <td>
                            ${item.outsourced ? (item.outsource_service||'outsourced') : (item.process_type?.replace(/_/g,' ')||'—')}
                            ${!item.outsourced && item.process_type ? `<div style="color:var(--text-dim);font-size:11px">$${(item.process_rate_override || processRates[item.process_type] || 0).toFixed(0)}/hr</div>` : ''}
                        </td>
                        <td>${item.quantity} ${item.unit}</td>
                        <td>${item.weight_lbs ? item.weight_lbs.toFixed(1)+' lb' : (item.sq_ft ? item.sq_ft.toFixed(1)+' sqft' : '—')}</td>
                        <td>$${(item.material_cost||0).toFixed(2)}</td>
                        <td>${item.outsourced ? `$${((item.outsource_rate_per_sqft||0)*(item.sq_ft||0)).toFixed(2)} (${item.outsource_rate_per_sqft||0}/sqft)` : `${item.labor_hours}h @ $${(item.process_rate_override || processRates[item.process_type] || 0).toFixed(0)}/hr`}</td>
                        <td><strong>$${(item.line_total||0).toFixed(2)}</strong></td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        ${q.notes ? `<div style="margin-top:1rem;color:var(--text-dim);font-size:13px"><strong>Notes / Terms:</strong> ${q.notes}</div>` : ''}
    `;
}

async function updateStatus(id, status) {
    await fetch(`${API}/quotes/${id}`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ status })
    });
}

// --- Customers ---
async function loadCustomers() {
    const res = await fetch(`${API}/customers/`);
    customers = await res.json();
    const el = document.getElementById('customers-list');
    if (!customers.length) {
        el.innerHTML = '<div class="empty-state">No customers yet.</div>';
        return;
    }
    el.innerHTML = customers.map(c => `
        <div class="card">
            <div class="card-title">${c.name}</div>
            ${c.company ? `<div class="card-sub">${c.company}</div>` : ''}
            ${c.email ? `<div class="card-sub">${c.email}</div>` : ''}
            ${c.phone ? `<div class="card-sub">${c.phone}</div>` : ''}
        </div>
    `).join('');
}

document.getElementById('customer-form').addEventListener('submit', async e => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    await fetch(`${API}/customers/`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    e.target.reset();
    showSection('customers');
});

// --- New Quote ---
async function initNewQuote() {
    await loadRates();
    const res = await fetch(`${API}/customers/`);
    customers = await res.json();
    const sel = document.querySelector('[name="customer_id"]');
    sel.innerHTML = '<option value="">Select customer...</option>' +
        customers.map(c => `<option value="${c.id}">${c.name}${c.company ? ' — ' + c.company : ''}</option>`).join('');
    document.getElementById('line-items').innerHTML = '';
    lineItemCount = 0;
    updateLiveTotal();
    addLineItem();
}

// --- Line Items ---
const MATERIALS = [
    ['mild_steel','Mild Steel (A36)'],
    ['stainless_304','Stainless 304'],
    ['stainless_316','Stainless 316'],
    ['aluminum_6061','Aluminum 6061'],
    ['aluminum_5052','Aluminum 5052'],
    ['dom_tubing','DOM Round Tube'],
    ['square_tubing','Square Tubing (HSS)'],
    ['angle_iron','Angle Iron (A36)'],
    ['flat_bar','Flat Bar (A36)'],
    ['plate','Plate (A36)'],
    ['channel','Channel (A36)'],
];

const PROCESSES = [
    ['layout','Layout / Marking — $75/hr'],
    ['cutting','Cold Saw Cutting — $85/hr'],
    ['cnc_plasma','CNC Plasma — $125/hr'],
    ['cnc_router','CNC Router — $125/hr'],
    ['welding','MIG Welding — $125/hr'],
    ['tig_welding','TIG Welding — $150/hr'],
    ['grinding','Grinding / Finishing — $75/hr'],
    ['drilling','Drilling / Punching — $85/hr'],
    ['bending','Bending / Forming — $95/hr'],
    ['assembly','Assembly / Fit-up — $100/hr'],
    ['design','Design / CAD — $150/hr'],
    ['field_install','Field Install — $185/hr'],
    ['project_management','Project Mgmt — $125/hr'],
];

function addLineItem() {
    const id = lineItemCount++;
    const div = document.createElement('div');
    div.className = 'line-item-row';
    div.id = `li-${id}`;
    div.innerHTML = `
        <div class="li-main">
            <div class="li-row-1">
                <label class="li-desc">Description
                    <input type="text" name="li_desc_${id}" placeholder="e.g. 2x2 11ga tube frame, 8ft run" oninput="calcLineItem(${id})">
                </label>
                <label>Qty
                    <input type="number" name="li_qty_${id}" value="1" min="0.01" step="0.01" style="width:70px" oninput="calcLineItem(${id})">
                </label>
                <label>Unit
                    <input type="text" name="li_unit_${id}" value="ea" style="width:60px">
                </label>
                <button type="button" class="btn-remove" onclick="removeLineItem(${id})" title="Remove">×</button>
            </div>

            <div class="li-row-2">
                <label>Material
                    <select name="li_mat_${id}" onchange="onMaterialChange(${id})">
                        <option value="">—</option>
                        ${MATERIALS.map(([v,l]) => `<option value="${v}">${l}</option>`).join('')}
                    </select>
                </label>
                <label>Process
                    <select name="li_proc_${id}" onchange="onProcessChange(${id})">
                        <option value="">—</option>
                        ${PROCESSES.map(([v,l]) => `<option value="${v}">${l}</option>`).join('')}
                    </select>
                </label>
                <label id="li_rate_label_${id}" style="color:var(--accent);font-weight:700;font-size:13px;justify-content:flex-end;padding-top:18px">
                    —
                </label>
            </div>

            <div class="li-row-3" id="li-dims-${id}">
                <label>L (in)<input type="number" name="li_len_${id}" min="0" step="0.001" placeholder="length" oninput="onDimChange(${id})"></label>
                <label>W (in)<input type="number" name="li_wid_${id}" min="0" step="0.001" placeholder="width" oninput="onDimChange(${id})"></label>
                <label>T (in)<input type="number" name="li_thk_${id}" min="0" step="0.001" placeholder="thickness" oninput="onDimChange(${id})"></label>
                <label>Wt (lbs)<input type="number" name="li_wgt_${id}" min="0" step="0.01" placeholder="auto" oninput="calcLineItem(${id})"></label>
                <label>Mat $/lb<input type="number" name="li_priceplb_${id}" min="0" step="0.001" placeholder="auto" oninput="calcLineItem(${id})"></label>
            </div>

            <div class="li-row-4">
                <label>Mat $ (total)
                    <input type="number" name="li_matcost_${id}" value="0" min="0" step="0.01" oninput="calcLineItem(${id})">
                </label>
                <label>Labor Hrs
                    <input type="number" name="li_hrs_${id}" value="0" min="0" step="0.25" oninput="calcLineItem(${id})">
                </label>
                <label>Rate Override ($/hr)
                    <input type="number" name="li_rate_${id}" min="0" step="1" placeholder="auto" oninput="calcLineItem(${id})">
                </label>
                <div class="li-total-display" id="li_total_${id}">$0.00</div>
            </div>

            <div class="li-outsource-toggle">
                <label class="checkbox-label">
                    <input type="checkbox" name="li_outsource_${id}" onchange="toggleOutsource(${id})"> Outsourced (powder coat, laser, etc.)
                </label>
            </div>

            <div class="li-outsource-row" id="li-out-${id}" style="display:none">
                <label>Service
                    <select name="li_svc_${id}">
                        <option value="powder_coat">Powder Coat</option>
                        <option value="laser_cut">Laser Cutting</option>
                        <option value="sandblast">Sandblasting</option>
                        <option value="galvanize">Galvanizing</option>
                        <option value="other">Other</option>
                    </select>
                </label>
                <label>Sq Ft
                    <input type="number" name="li_sqft_${id}" min="0" step="0.01" value="0" oninput="calcLineItem(${id})">
                </label>
                <label>$/Sq Ft
                    <input type="number" name="li_sqftrate_${id}" min="0" step="0.01" value="2.50" oninput="calcLineItem(${id})">
                </label>
                <div class="li-total-display" id="li_out_total_${id}">$0.00</div>
            </div>
        </div>
    `;
    document.getElementById('line-items').appendChild(div);
    calcLineItem(id);
}

function removeLineItem(id) {
    const el = document.getElementById(`li-${id}`);
    if (el) el.remove();
    updateLiveTotal();
}

function onMaterialChange(id) {
    const mat = document.querySelector(`[name="li_mat_${id}"]`)?.value;
    // Auto-fill price per lb from material prices table
    const pricePlb = materialPrices[mat] || 0;
    if (pricePlb > 0) {
        const priceInput = document.querySelector(`[name="li_priceplb_${id}"]`);
        if (priceInput && !priceInput.value) priceInput.value = pricePlb;
    }
    calcLineItem(id);
}

function onProcessChange(id) {
    const proc = document.querySelector(`[name="li_proc_${id}"]`)?.value;
    const rate = processRates[proc] || 0;
    const label = document.getElementById(`li_rate_label_${id}`);
    if (label) label.textContent = proc ? `$${rate}/hr` : '—';
    calcLineItem(id);
}

function onDimChange(id) {
    // Auto-calc weight from dimensions + material density
    const mat = document.querySelector(`[name="li_mat_${id}"]`)?.value;
    const L = parseFloat(document.querySelector(`[name="li_len_${id}"]`)?.value || 0);
    const W = parseFloat(document.querySelector(`[name="li_wid_${id}"]`)?.value || 0);
    const T = parseFloat(document.querySelector(`[name="li_thk_${id}"]`)?.value || 0);

    const DENSITIES = {
        mild_steel: 0.2833, stainless_304: 0.2890, stainless_316: 0.2890,
        aluminum_6061: 0.0975, aluminum_5052: 0.0970,
        dom_tubing: 0.2833, square_tubing: 0.2833, angle_iron: 0.2833,
        flat_bar: 0.2833, plate: 0.2833, channel: 0.2833,
    };

    if (L > 0 && W > 0 && T > 0) {
        const density = DENSITIES[mat] || 0.2833;
        const wgt = L * W * T * density;
        const wgtInput = document.querySelector(`[name="li_wgt_${id}"]`);
        if (wgtInput) wgtInput.value = wgt.toFixed(2);

        // Auto-calc sq ft for powder coat reference
        const sqft = (L * W) / 144;
        const sqftInput = document.querySelector(`[name="li_sqft_${id}"]`);
        if (sqftInput && parseFloat(sqftInput.value) === 0) sqftInput.value = sqft.toFixed(2);
    }

    // Auto-calc material cost from weight + price/lb
    calcLineItem(id);
}

function toggleOutsource(id) {
    const checked = document.querySelector(`[name="li_outsource_${id}"]`)?.checked;
    const outRow = document.getElementById(`li-out-${id}`);
    const laborRow = document.querySelector(`[name="li_hrs_${id}"]`)?.closest('label');
    if (outRow) outRow.style.display = checked ? 'flex' : 'none';
    calcLineItem(id);
}

function calcLineItem(id) {
    const outsourced = document.querySelector(`[name="li_outsource_${id}"]`)?.checked;
    const qty = parseFloat(document.querySelector(`[name="li_qty_${id}"]`)?.value || 1);

    let lineTotal = 0;

    if (outsourced) {
        const sqft = parseFloat(document.querySelector(`[name="li_sqft_${id}"]`)?.value || 0);
        const sqftRate = parseFloat(document.querySelector(`[name="li_sqftrate_${id}"]`)?.value || 2.50);
        lineTotal = sqft * sqftRate * qty;
        const el = document.getElementById(`li_out_total_${id}`);
        if (el) el.textContent = '$' + lineTotal.toFixed(2);
    } else {
        const wgt = parseFloat(document.querySelector(`[name="li_wgt_${id}"]`)?.value || 0);
        const pricePlb = parseFloat(document.querySelector(`[name="li_priceplb_${id}"]`)?.value || 0);

        // If weight and price/lb both known, auto-set material cost
        let matCost = parseFloat(document.querySelector(`[name="li_matcost_${id}"]`)?.value || 0);
        if (wgt > 0 && pricePlb > 0) {
            const quoteLevelWaste = parseFloat(document.querySelector('[name="waste_factor"]')?.value || 0.05);
            matCost = wgt * pricePlb * (1 + quoteLevelWaste);
            const matInput = document.querySelector(`[name="li_matcost_${id}"]`);
            if (matInput) matInput.value = matCost.toFixed(2);
        }

        const hrs = parseFloat(document.querySelector(`[name="li_hrs_${id}"]`)?.value || 0);
        const proc = document.querySelector(`[name="li_proc_${id}"]`)?.value;
        const rateOverride = parseFloat(document.querySelector(`[name="li_rate_${id}"]`)?.value || 0);
        const rate = rateOverride > 0 ? rateOverride : (processRates[proc] || parseFloat(document.querySelector('[name="labor_rate"]')?.value || 125));

        const laborCost = hrs * rate;
        lineTotal = (matCost + laborCost) * qty;
    }

    const el = document.getElementById(`li_total_${id}`);
    if (el) el.textContent = '$' + lineTotal.toFixed(2);

    updateLiveTotal();
}

function updateLiveTotal() {
    const contingency = parseFloat(document.querySelector('[name="contingency_pct"]')?.value || 0);
    const profit = parseFloat(document.querySelector('[name="profit_margin_pct"]')?.value || 20);

    let subtotal = 0;
    document.querySelectorAll('[id^="li-"]').forEach(row => {
        const id = row.id.replace('li-', '');
        if (isNaN(parseInt(id))) return;
        const totalEl = document.getElementById(`li_total_${id}`) || document.getElementById(`li_out_total_${id}`);
        if (totalEl) {
            const val = parseFloat(totalEl.textContent.replace('$','')) || 0;
            subtotal += val;
        }
    });

    const withCont = subtotal * (1 + contingency / 100);
    const total = withCont * (1 + profit / 100);

    const preview = document.getElementById('totals-preview');
    if (preview) preview.style.display = subtotal > 0 ? 'flex' : 'none';

    const elSub = document.getElementById('preview-subtotal');
    const elCont = document.getElementById('preview-contingency');
    const elTotal = document.getElementById('preview-total');
    const elMargin = document.getElementById('preview-margin');

    if (elSub) elSub.textContent = '$' + subtotal.toFixed(2);
    if (elCont && contingency > 0) {
        document.getElementById('preview-cont-row').style.display = '';
        elCont.textContent = `+$${(withCont - subtotal).toFixed(2)} (${contingency}%)`;
    } else if (document.getElementById('preview-cont-row')) {
        document.getElementById('preview-cont-row').style.display = 'none';
    }
    if (elMargin) elMargin.textContent = `+$${(total - withCont).toFixed(2)} (${profit}%)`;
    if (elTotal) elTotal.textContent = '$' + total.toFixed(2);
}

// Quote form
document.getElementById('quote-form').addEventListener('submit', async e => {
    e.preventDefault();
    const form = new FormData(e.target);
    const lineItems = [];

    document.querySelectorAll('[id^="li-"]').forEach(row => {
        const id = row.id.replace('li-', '');
        if (isNaN(parseInt(id))) return;
        const desc = document.querySelector(`[name="li_desc_${id}"]`)?.value;
        if (!desc?.trim()) return;

        const outsourced = document.querySelector(`[name="li_outsource_${id}"]`)?.checked || false;

        lineItems.push({
            description: desc,
            material_type: document.querySelector(`[name="li_mat_${id}"]`)?.value || null,
            process_type: outsourced ? null : (document.querySelector(`[name="li_proc_${id}"]`)?.value || null),
            quantity: parseFloat(document.querySelector(`[name="li_qty_${id}"]`)?.value || 1),
            unit: document.querySelector(`[name="li_unit_${id}"]`)?.value || 'ea',
            dim_length: parseFloat(document.querySelector(`[name="li_len_${id}"]`)?.value) || null,
            dim_width: parseFloat(document.querySelector(`[name="li_wid_${id}"]`)?.value) || null,
            dim_thickness: parseFloat(document.querySelector(`[name="li_thk_${id}"]`)?.value) || null,
            weight_lbs: parseFloat(document.querySelector(`[name="li_wgt_${id}"]`)?.value) || null,
            material_cost: parseFloat(document.querySelector(`[name="li_matcost_${id}"]`)?.value || 0),
            labor_hours: outsourced ? 0 : parseFloat(document.querySelector(`[name="li_hrs_${id}"]`)?.value || 0),
            process_rate_override: parseFloat(document.querySelector(`[name="li_rate_${id}"]`)?.value) || null,
            outsourced,
            outsource_service: outsourced ? document.querySelector(`[name="li_svc_${id}"]`)?.value : null,
            outsource_rate_per_sqft: outsourced ? parseFloat(document.querySelector(`[name="li_sqftrate_${id}"]`)?.value || 0) : null,
            sq_ft: outsourced ? parseFloat(document.querySelector(`[name="li_sqft_${id}"]`)?.value || 0) : null,
        });
    });

    const payload = {
        customer_id: parseInt(form.get('customer_id')),
        job_type: form.get('job_type'),
        project_description: form.get('project_description'),
        notes: form.get('notes'),
        labor_rate: parseFloat(form.get('labor_rate') || 125),
        waste_factor: parseFloat(form.get('waste_factor') || 0.05),
        contingency_pct: parseFloat(form.get('contingency_pct') || 0),
        profit_margin_pct: parseFloat(form.get('profit_margin_pct') || 20),
        line_items: lineItems,
    };

    const res = await fetch(`${API}/quotes/`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    });
    const quote = await res.json();
    showSection('quotes');
    showQuoteDetail(quote.id);
});

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadQuotes();
});
