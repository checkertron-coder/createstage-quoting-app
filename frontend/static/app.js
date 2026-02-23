const API = '/api';
let customers = [];
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
    if (name === 'new-quote') loadCustomerSelect();
}

// --- Quotes ---
async function loadQuotes() {
    const res = await fetch(`${API}/quotes/`);
    const quotes = await res.json();
    const el = document.getElementById('quotes-list');
    if (!quotes.length) {
        el.innerHTML = '<div class="empty-state">No quotes yet.<br>Click <strong>+ New Quote</strong> to create one.</div>';
        return;
    }
    el.innerHTML = quotes.map(q => `
        <div class="card" onclick="showQuoteDetail(${q.id})">
            <div class="card-header">
                <div>
                    <div class="card-title">${q.customer?.name || 'Unknown'}</div>
                    <div class="card-sub">${q.quote_number} &middot; ${q.customer?.company || ''}</div>
                    <div class="card-sub">${q.project_description?.slice(0, 60) || ''}</div>
                </div>
                <div>
                    <div class="card-total">$${q.total.toLocaleString('en-US', {minimumFractionDigits:2})}</div>
                    <span class="badge badge-${q.status}">${q.status}</span>
                </div>
            </div>
            <div class="card-sub">${new Date(q.created_at).toLocaleDateString()}</div>
        </div>
    `).join('');
}

async function showQuoteDetail(id) {
    const res = await fetch(`${API}/quotes/${id}`);
    const q = await res.json();
    showSection('quote-detail');
    document.getElementById('quote-detail-content').innerHTML = `
        <div class="quote-detail-header">
            <div>
                <div class="quote-number">${q.quote_number}</div>
                <div style="color:var(--text-dim);margin-top:0.25rem">${q.customer?.name} ${q.customer?.company ? '· ' + q.customer.company : ''}</div>
                <div style="margin-top:0.5rem">
                    <select class="status-select" onchange="updateStatus(${q.id}, this.value)">
                        ${['draft','sent','accepted','declined'].map(s =>
                            `<option value="${s}" ${q.status===s?'selected':''}>${s.charAt(0).toUpperCase()+s.slice(1)}</option>`
                        ).join('')}
                    </select>
                </div>
            </div>
            <div style="text-align:right">
                <div class="quote-total-big">$${q.total.toLocaleString('en-US', {minimumFractionDigits:2})}</div>
                <div style="color:var(--text-dim);font-size:12px">Subtotal: $${q.subtotal.toLocaleString('en-US', {minimumFractionDigits:2})} × ${q.markup}x markup</div>
                <div style="color:var(--text-dim);font-size:12px">Valid ${q.valid_days} days · Labor @ $${q.labor_rate}/hr</div>
            </div>
        </div>
        ${q.project_description ? `<p style="color:var(--text-dim);margin-bottom:1rem">${q.project_description}</p>` : ''}
        <table class="detail-table">
            <thead>
                <tr>
                    <th>Description</th>
                    <th>Material</th>
                    <th>Process</th>
                    <th>Qty</th>
                    <th>Mat. Cost</th>
                    <th>Labor Hrs</th>
                    <th>Labor Cost</th>
                    <th>Line Total</th>
                </tr>
            </thead>
            <tbody>
                ${q.line_items.map(item => `
                    <tr>
                        <td>${item.description}</td>
                        <td>${item.material_type?.replace(/_/g,' ') || '—'}</td>
                        <td>${item.process_type?.replace(/_/g,' ') || '—'}</td>
                        <td>${item.quantity} ${item.unit}</td>
                        <td>$${item.material_cost.toFixed(2)}</td>
                        <td>${item.labor_hours}h</td>
                        <td>$${item.labor_cost.toFixed(2)}</td>
                        <td><strong>$${item.line_total.toFixed(2)}</strong></td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        ${q.notes ? `<div style="margin-top:1rem;color:var(--text-dim);font-size:13px"><strong>Notes:</strong> ${q.notes}</div>` : ''}
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

async function loadCustomerSelect() {
    const res = await fetch(`${API}/customers/`);
    customers = await res.json();
    const sel = document.querySelector('[name="customer_id"]');
    sel.innerHTML = '<option value="">Select customer...</option>' +
        customers.map(c => `<option value="${c.id}">${c.name}${c.company ? ' — ' + c.company : ''}</option>`).join('');
    document.getElementById('line-items').innerHTML = '';
    lineItemCount = 0;
    addLineItem();
}

// Customer form
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

// --- Line Items ---
const MATERIALS = ['mild_steel','stainless_304','stainless_316','aluminum_6061','aluminum_5052','dom_tubing','square_tubing','angle_iron','flat_bar','plate'];
const PROCESSES = ['cutting','welding','bending','grinding','drilling','cnc_plasma','cnc_router','powder_coat','paint','assembly','design'];

function addLineItem() {
    const id = lineItemCount++;
    const div = document.createElement('div');
    div.className = 'line-item-row';
    div.id = `li-${id}`;
    div.innerHTML = `
        <label>Description<input type="text" name="li_desc_${id}" placeholder="e.g. 2x4x1/4 steel tube frame" oninput="calcTotals()"></label>
        <label>Material
            <select name="li_mat_${id}" onchange="calcTotals()">
                <option value="">—</option>
                ${MATERIALS.map(m => `<option value="${m}">${m.replace(/_/g,' ')}</option>`).join('')}
            </select>
        </label>
        <label>Process
            <select name="li_proc_${id}" onchange="calcTotals()">
                <option value="">—</option>
                ${PROCESSES.map(p => `<option value="${p}">${p.replace(/_/g,' ')}</option>`).join('')}
            </select>
        </label>
        <label>Qty<input type="number" name="li_qty_${id}" value="1" min="0" step="0.01" oninput="calcTotals()"></label>
        <label>Mat $<input type="number" name="li_matcost_${id}" value="0" min="0" step="0.01" oninput="calcTotals()"></label>
        <label>Labor Hrs<input type="number" name="li_hrs_${id}" value="0" min="0" step="0.25" oninput="calcTotals()"></label>
        <label>Unit<input type="text" name="li_unit_${id}" value="ea"></label>
        <button type="button" class="btn-remove" onclick="removeLineItem(${id})" title="Remove">×</button>
    `;
    document.getElementById('line-items').appendChild(div);
    calcTotals();
}

function removeLineItem(id) {
    const el = document.getElementById(`li-${id}`);
    if (el) el.remove();
    calcTotals();
}

function calcTotals() {
    const laborRate = parseFloat(document.querySelector('[name="labor_rate"]')?.value || 85);
    const markup = parseFloat(document.querySelector('[name="markup"]')?.value || 1.35);
    let subtotal = 0;

    document.querySelectorAll('[id^="li-"]').forEach(row => {
        const idNum = row.id.replace('li-', '');
        const qty = parseFloat(document.querySelector(`[name="li_qty_${idNum}"]`)?.value || 1);
        const matCost = parseFloat(document.querySelector(`[name="li_matcost_${idNum}"]`)?.value || 0);
        const hrs = parseFloat(document.querySelector(`[name="li_hrs_${idNum}"]`)?.value || 0);
        const laborCost = hrs * laborRate;
        subtotal += (matCost + laborCost) * qty;
    });

    const total = subtotal * markup;
    const preview = document.getElementById('totals-preview');
    if (subtotal > 0) {
        preview.style.display = 'flex';
        document.getElementById('preview-subtotal').textContent = '$' + subtotal.toFixed(2);
        document.getElementById('preview-total').textContent = '$' + total.toFixed(2);
    } else {
        preview.style.display = 'none';
    }
}

// Quote form submit
document.getElementById('quote-form').addEventListener('submit', async e => {
    e.preventDefault();
    const form = new FormData(e.target);
    const laborRate = parseFloat(form.get('labor_rate'));
    const markup = parseFloat(form.get('markup'));
    const lineItems = [];

    document.querySelectorAll('[id^="li-"]').forEach(row => {
        const id = row.id.replace('li-', '');
        const desc = document.querySelector(`[name="li_desc_${id}"]`)?.value;
        if (!desc) return;
        lineItems.push({
            description: desc,
            material_type: document.querySelector(`[name="li_mat_${id}"]`)?.value || null,
            process_type: document.querySelector(`[name="li_proc_${id}"]`)?.value || null,
            quantity: parseFloat(document.querySelector(`[name="li_qty_${id}"]`)?.value || 1),
            unit: document.querySelector(`[name="li_unit_${id}"]`)?.value || 'ea',
            material_cost: parseFloat(document.querySelector(`[name="li_matcost_${id}"]`)?.value || 0),
            labor_hours: parseFloat(document.querySelector(`[name="li_hrs_${id}"]`)?.value || 0),
        });
    });

    const payload = {
        customer_id: parseInt(form.get('customer_id')),
        project_description: form.get('project_description'),
        notes: form.get('notes'),
        labor_rate: laborRate,
        markup: markup,
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
    fetch(`${API}/materials/seed`);
});
