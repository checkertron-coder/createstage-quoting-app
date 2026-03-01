/* ============================================
   CreateStage AI Quoting — App Logic
   ============================================ */

let currentEstimate = null;
let conversationHistory = [];

// ---- VIEW SWITCHING ----

function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById(`view-${name}`).classList.add('active');
  document.querySelectorAll('.hdr-btn').forEach(b => b.classList.remove('active'));
  if (name === 'chat') {
    document.querySelectorAll('.hdr-btn')[1].classList.add('active');
  } else if (name === 'quotes') {
    document.querySelectorAll('.hdr-btn')[0].classList.add('active');
    loadQuotes();
  }
}

// ---- INPUT HANDLING ----

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    submitJob();
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function useExample(btn) {
  const input = document.getElementById('job-input');
  input.value = btn.textContent;
  autoResize(input);
  input.focus();
}

// ---- SAFE JSON PARSING ----

async function safeJson(res) {
  const ct = (res.headers.get('content-type') || '');
  if (!ct.includes('application/json')) {
    return null;
  }
  try {
    return await res.json();
  } catch (_) {
    return null;
  }
}

// ---- POLLING FOR ASYNC RESULTS ----

async function pollForResult(jobId, typingId) {
  const stages = [
    { at: 0,  text: 'Analyzing job description...' },
    { at: 6,  text: 'Calculating materials...' },
    { at: 12, text: 'Estimating labor...' },
    { at: 20, text: 'Finalizing estimate...' },
  ];
  const startTime = Date.now();
  const maxPolls = 100; // 200s safety limit

  for (let i = 0; i < maxPolls; i++) {
    // Update typing indicator text based on elapsed time
    const elapsed = (Date.now() - startTime) / 1000;
    for (let s = stages.length - 1; s >= 0; s--) {
      if (elapsed >= stages[s].at) {
        updateTypingText(typingId, stages[s].text);
        break;
      }
    }

    await new Promise(r => setTimeout(r, 2000));

    try {
      const res = await fetch('/api/ai/job/' + jobId);
      const data = await safeJson(res);
      if (!data) continue; // non-JSON response, retry

      if (data.status === 'complete') {
        return data.result || data;
      }
      if (data.status === 'failed' || data.status === 'timeout') {
        return { _error: data.error || 'AI processing failed' };
      }
      // pending or running — keep polling
    } catch (_) {
      // Network error — keep polling
    }
  }

  return { _error: 'Timed out waiting for AI response. Please try again.' };
}

// ---- SUBMIT JOB ----

async function submitJob() {
  const input = document.getElementById('job-input');
  const text = input.value.trim();
  if (!text) return;

  const btn = document.getElementById('send-btn');
  btn.disabled = true;
  input.value = '';
  input.style.height = 'auto';

  // Clear welcome screen on first message
  const welcome = document.querySelector('.chat-welcome');
  if (welcome) welcome.remove();

  // Add user message
  appendUserMessage(text);
  conversationHistory.push({ role: 'user', text });

  // Show typing
  const typingId = showTyping();

  try {
    // Build prompt with history context
    let prompt = text;
    if (conversationHistory.length > 1) {
      const prev = conversationHistory
        .slice(-4)
        .filter(m => m.role === 'user')
        .map(m => m.text)
        .join('\n');
      prompt = `Previous context: ${prev}\n\nLatest request: ${text}`;
    }

    const res = await fetch('/api/ai/estimate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_description: prompt })
    });

    const data = await safeJson(res);

    if (!data) {
      removeTyping(typingId);
      appendError('Server error — please try again');
      btn.disabled = false;
      return;
    }

    if (!res.ok) {
      removeTyping(typingId);
      appendError(data.detail || `Error ${res.status} — try again`);
      btn.disabled = false;
      return;
    }

    // Check for async job
    if (data.status === 'pending' && data.job_id) {
      const result = await pollForResult(data.job_id, typingId);
      removeTyping(typingId);

      if (result && result._error) {
        appendError(result._error);
        btn.disabled = false;
        return;
      }

      currentEstimate = result;
      conversationHistory.push({ role: 'ai', data: result });
      appendAIResponse(result);
      updateQuotePanel(result);
      btn.disabled = false;
      return;
    }

    // Synchronous response (cache hit)
    removeTyping(typingId);
    currentEstimate = data;
    conversationHistory.push({ role: 'ai', data });
    appendAIResponse(data);
    updateQuotePanel(data);

  } catch (err) {
    removeTyping(typingId);
    appendError('Connection error — is the server running?');
  }

  btn.disabled = false;
}

// ---- CHAT THREAD ----

function appendUserMessage(text) {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'chat-msg user';
  div.innerHTML = `
    <div class="msg-label">You</div>
    <div class="msg-bubble">${escHtml(text)}</div>
  `;
  thread.appendChild(div);
  scrollThread();
}

function appendAIResponse(data) {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'ai-response';

  const items = data.raw_estimate?.line_items || [];
  const warnings = data.warnings || [];
  const assumptions = data.assumptions || [];

  // Build line items rows
  let itemRows = items.map(item => {
    const matCost = item.material_cost || 0;
    const laborCost = (item.labor_hours || 0) * (data.raw_estimate?.labor_rate_fallback || 125);
    const lineCost = item.outsourced
      ? (item.outsource_rate_per_sqft || 2.5) * (item.sq_ft || 0)
      : matCost + laborCost;

    const details = [];
    if (item.labor_hours > 0) details.push(`${item.labor_hours}h labor`);
    if (item.weight_lbs) details.push(`${item.weight_lbs} lbs`);
    if (item.process_type) details.push(item.process_type.replace(/_/g, ' '));

    return `
      <tr>
        <td>
          <div class="item-desc">${escHtml(item.description)}</div>
          ${details.length ? `<div class="item-detail">${details.join(' · ')}</div>` : ''}
        </td>
        <td class="item-num">${item.quantity}× ${item.unit}</td>
        <td class="item-num item-highlight">${fmt(lineCost)}</td>
      </tr>
    `;
  }).join('');

  // Notes
  let notesHtml = '';
  if (warnings.length || assumptions.length) {
    notesHtml = '<div class="ai-notes">';
    warnings.forEach(w => {
      notesHtml += `<div class="ai-note warning"><span class="ai-note-icon">⚠️</span><span>${escHtml(w)}</span></div>`;
    });
    assumptions.forEach(a => {
      notesHtml += `<div class="ai-note assumption"><span class="ai-note-icon">ℹ️</span><span>${escHtml(a)}</span></div>`;
    });
    notesHtml += '</div>';
  }

  div.innerHTML = `
    <div class="msg-label">CreateStage AI</div>
    <div class="ai-job-summary">
      <div class="ai-summary-top">
        <div class="ai-summary-text">${escHtml(data.job_summary)}</div>
        <span class="confidence-badge ${data.confidence}">${data.confidence}</span>
      </div>
      <div class="ai-tags">
        <span class="ai-tag">${data.job_type?.replace(/_/g, ' ')}</span>
        <span class="ai-tag">${items.length} line items</span>
      </div>
    </div>

    ${items.length ? `
    <table class="line-items-table">
      <thead>
        <tr>
          <th>Item</th>
          <th>Qty</th>
          <th>Cost</th>
        </tr>
      </thead>
      <tbody>${itemRows}</tbody>
    </table>` : ''}

    ${notesHtml}

    ${(() => {
      const cutList = data.raw_estimate?.cut_list || [];
      if (!cutList.length) return '';
      const rows = cutList.map(p => `
        <tr>
          <td>${escHtml(p.piece_description || '')}</td>
          <td>${escHtml(String(p.material || ''))}</td>
          <td>${p.quantity || 1}</td>
          <td>${[p.length ? p.length + '"' : null, p.width ? p.width + '"' : null, p.thickness || null].filter(Boolean).join(' × ')}</td>
          <td>${escHtml(p.notes || '')}</td>
        </tr>`).join('');
      return `
        <div class="section-header">✂️ Cut List</div>
        <table class="line-items-table cut-list-table">
          <thead><tr><th>Piece</th><th>Material</th><th>Qty</th><th>Dimensions</th><th>Notes</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>`;
    })()}

    ${(() => {
      const buildOrder = data.raw_estimate?.build_order || [];
      if (!buildOrder.length) return '';
      const steps = buildOrder.map((s, i) => `<li>${escHtml(s)}</li>`).join('');
      return `
        <div class="section-header">🔧 Build Order</div>
        <ol class="build-order-list">${steps}</ol>`;
    })()}

    <div class="ai-totals-bar">
      <div class="at-item">
        <div class="at-label">Shop Cost</div>
        <div class="at-value">${fmt(data.estimated_cost)}</div>
      </div>
      <div class="at-divider"></div>
      <div class="at-item">
        <div class="at-label">Quote Total</div>
        <div class="at-value total">${fmt(data.estimated_total)}</div>
      </div>
      <div class="at-divider"></div>
      <div class="at-item">
        <div class="at-label">Margin</div>
        <div class="at-value">${data.raw_estimate?.profit_margin_pct || 20}%</div>
      </div>
    </div>
  `;

  thread.appendChild(div);
  scrollThread();
}

function appendError(msg) {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'chat-msg ai';
  div.innerHTML = `
    <div class="msg-label">Error</div>
    <div class="msg-bubble" style="border-color: rgba(239,68,68,0.3); color: #ef4444;">${escHtml(msg)}</div>
  `;
  thread.appendChild(div);
  scrollThread();
}

let typingCounter = 0;

function showTyping() {
  const id = `typing-${++typingCounter}`;
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.id = id;
  div.className = 'typing-indicator';
  div.innerHTML = `
    <span class="typing-text">Analyzing job description...</span>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
  `;
  thread.appendChild(div);
  scrollThread();
  return id;
}

function updateTypingText(id, text) {
  const el = document.getElementById(id);
  if (!el) return;
  const span = el.querySelector('.typing-text');
  if (span) span.textContent = text;
}

function removeTyping(id) {
  document.getElementById(id)?.remove();
}

function scrollThread() {
  const thread = document.getElementById('chat-thread');
  thread.scrollTop = thread.scrollHeight;
}

// ---- QUOTE PANEL ----

function updateQuotePanel(data) {
  const panel = document.getElementById('qp-body');
  const footer = document.getElementById('qp-footer');
  const status = document.getElementById('qp-status');
  const items = data.raw_estimate?.line_items || [];

  status.textContent = `${items.length} items`;
  footer.style.display = 'block';
  document.getElementById('qp-cost').textContent = fmt(data.estimated_cost);
  document.getElementById('qp-total').textContent = fmt(data.estimated_total);

  panel.innerHTML = items.map(item => {
    const matCost = item.material_cost || 0;
    const laborCost = (item.labor_hours || 0) * (data.raw_estimate?.labor_rate_fallback || 125);
    const lineCost = item.outsourced
      ? (item.outsource_rate_per_sqft || 2.5) * (item.sq_ft || 0)
      : matCost + laborCost;

    return `
      <div class="qp-item">
        <div class="qp-item-desc">${escHtml(item.description)}</div>
        <div class="qp-item-detail">
          <span>${item.quantity}× ${item.unit}</span>
          <span>${fmt(lineCost)}</span>
        </div>
      </div>
    `;
  }).join('');
}

// ---- SAVE QUOTE MODAL ----

function showSaveModal() {
  if (!currentEstimate) return;
  document.getElementById('save-modal').style.display = 'flex';
  setTimeout(() => document.getElementById('save-customer-name').focus(), 50);
}

function closeSaveModal(e) {
  if (e && e.target !== document.getElementById('save-modal')) return;
  document.getElementById('save-modal').style.display = 'none';
}

async function saveQuote() {
  const name = document.getElementById('save-customer-name').value.trim();
  if (!name) {
    document.getElementById('save-customer-name').focus();
    return;
  }

  const btn = document.querySelector('.btn-save');
  btn.textContent = 'Saving...';
  btn.disabled = true;

  try {
    // Create customer first
    const custRes = await fetch('/api/customers/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        company: document.getElementById('save-company').value.trim() || null,
        email: document.getElementById('save-email').value.trim() || null,
      })
    });

    const custData = await safeJson(custRes);
    if (!custRes.ok || !custData) throw new Error('Failed to create customer');

    // Get last user message for description
    const lastUserMsg = [...conversationHistory].reverse().find(m => m.role === 'user');
    const description = lastUserMsg?.text || 'AI-generated quote';

    // Create quote — pass the raw estimate so the backend skips the second Gemini call
    // and saves exactly what was shown to the user
    const notes = document.getElementById('save-notes').value.trim();
    const quoteRes = await fetch('/api/ai/quote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_description: description,
        customer_id: custData.id,
        additional_context: notes || null,
        pre_computed_estimate: currentEstimate?.raw_estimate || null
      })
    });

    const quoteData = await safeJson(quoteRes);
    if (!quoteRes.ok || !quoteData) throw new Error('Failed to create quote');

    document.getElementById('save-modal').style.display = 'none';
    appendSavedConfirmation(quoteData.quote);

  } catch (err) {
    appendError(`Save failed: ${err.message}`);
    document.getElementById('save-modal').style.display = 'none';
  } finally {
    btn.textContent = 'Save Quote';
    btn.disabled = false;
  }
}

function appendSavedConfirmation(quote) {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'chat-msg ai';
  div.innerHTML = `
    <div class="msg-label">Saved</div>
    <div class="msg-bubble" style="border-color: rgba(34,197,94,0.3);">
      ✅ Quote <strong>${quote.quote_number}</strong> saved for <strong>${quote.customer?.name || 'customer'}</strong> —
      total <strong style="color: var(--accent)">${fmt(quote.total)}</strong>
      <br><br>
      <a href="#" onclick="showView('quotes'); return false;" style="color: var(--accent); font-size: 13px;">View all quotes →</a>
    </div>
  `;
  thread.appendChild(div);
  scrollThread();
}

// ---- QUOTES LIST ----

async function loadQuotes() {
  const list = document.getElementById('quotes-list');
  list.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';

  try {
    const res = await fetch('/api/quotes/');
    const quotes = await safeJson(res);
    if (!res.ok || !quotes) throw new Error('Failed to load');

    if (!quotes.length) {
      list.innerHTML = `
        <div class="empty-state">
          <p>No quotes yet. Describe your first job to get started.</p>
          <button class="hdr-btn active" onclick="showView('chat')">Start a Quote</button>
        </div>
      `;
      return;
    }

    list.innerHTML = quotes.map(q => `
      <div class="quote-card" onclick="showQuoteDetail(${q.id})">
        <div class="qc-num">${q.quote_number}</div>
        <div class="qc-customer">${escHtml(q.customer?.name || 'No customer')}</div>
        <div class="qc-desc">${escHtml(q.project_description || '').slice(0, 80)}${q.project_description?.length > 80 ? '...' : ''}</div>
        <div class="qc-meta">
          <span class="qc-total">${fmt(q.total || 0)}</span>
          <span class="qc-date">${formatDate(q.created_at)}</span>
        </div>
      </div>
    `).join('');

  } catch (err) {
    list.innerHTML = `<div class="empty-state"><p>Error loading quotes: ${err.message}</p></div>`;
  }
}

async function showQuoteDetail(id) {
  const modal = document.getElementById('detail-modal');
  const body = document.getElementById('detail-body');
  const title = document.getElementById('detail-title');

  modal.style.display = 'flex';
  body.innerHTML = '<p style="color: var(--text3); padding: 20px 0;">Loading...</p>';

  try {
    const res = await fetch(`/api/quotes/${id}`);
    const q = await safeJson(res);
    if (!res.ok || !q) throw new Error('Not found');

    title.textContent = `Quote ${q.quote_number}`;

    const items = q.line_items || [];
    const itemRows = items.map(item => {
      const matCost = item.material_cost || 0;
      const laborCost = (item.labor_hours || 0) * (q.labor_rate || 125);
      const lineCost = item.outsourced
        ? (item.outsource_rate_per_sqft || 2.5) * (item.sq_ft || 0)
        : matCost + laborCost;
      return `
        <tr>
          <td><div class="item-desc">${escHtml(item.description)}</div></td>
          <td class="item-num">${item.quantity}× ${item.unit}</td>
          <td class="item-num">${item.labor_hours > 0 ? item.labor_hours + 'h' : '—'}</td>
          <td class="item-num item-highlight">${fmt(lineCost)}</td>
        </tr>
      `;
    }).join('');

    body.innerHTML = `
      <div class="detail-meta">
        <div class="detail-field"><label>Customer</label><span>${escHtml(q.customer?.name || '—')}</span></div>
        <div class="detail-field"><label>Job Type</label><span>${q.job_type?.replace(/_/g, ' ') || '—'}</span></div>
        <div class="detail-field"><label>Description</label><span>${escHtml(q.project_description || '—')}</span></div>
        <div class="detail-field"><label>Created</label><span>${formatDate(q.created_at)}</span></div>
      </div>

      ${items.length ? `
      <table class="line-items-table">
        <thead>
          <tr><th>Item</th><th>Qty</th><th>Labor</th><th>Cost</th></tr>
        </thead>
        <tbody>${itemRows}</tbody>
      </table>` : ''}

      <div class="detail-totals">
        <div class="detail-total-row"><span>Labor Rate</span><span>$${q.labor_rate}/hr</span></div>
        <div class="detail-total-row"><span>Material Markup</span><span>${q.material_markup_pct}%</span></div>
        <div class="detail-total-row"><span>Waste Factor</span><span>${(q.waste_factor * 100).toFixed(0)}%</span></div>
        ${q.contingency_pct > 0 ? `<div class="detail-total-row"><span>Contingency</span><span>${q.contingency_pct}%</span></div>` : ''}
        <div class="detail-total-row"><span>Profit Margin</span><span>${q.profit_margin_pct}%</span></div>
        <div class="detail-total-row big"><span>Quote Total</span><span>${fmt(q.total || 0)}</span></div>
      </div>
    `;

  } catch (err) {
    body.innerHTML = `<p style="color: var(--red);">Error: ${err.message}</p>`;
  }
}

function closeDetailModal(e) {
  if (e && e.target !== document.getElementById('detail-modal')) return;
  document.getElementById('detail-modal').style.display = 'none';
}

// ---- UTILS ----

function fmt(n) {
  return '$' + (n || 0).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDate(str) {
  if (!str) return '—';
  const d = new Date(str);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
