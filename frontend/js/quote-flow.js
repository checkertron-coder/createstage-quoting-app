/**
 * Quote Flow — the main quoting pipeline UI.
 *
 * Step 1: Job Description (intake)
 * Step 2: Clarify (question flow)
 * Step 3: Results (calculate → estimate → price → display)
 */

const JOB_TYPES = {
    cantilever_gate: 'Cantilever Gate',
    swing_gate: 'Swing Gate',
    straight_railing: 'Straight Railing',
    stair_railing: 'Stair Railing',
    repair_decorative: 'Repair (Decorative)',
    ornamental_fence: 'Ornamental Fence',
    complete_stair: 'Complete Staircase',
    spiral_stair: 'Spiral Staircase',
    window_security_grate: 'Security Grate',
    balcony_railing: 'Balcony Railing',
    furniture_table: 'Steel Furniture',
    utility_enclosure: 'Utility Enclosure',
    bollard: 'Bollard',
    repair_structural: 'Repair (Structural)',
    custom_fab: 'Custom Fab',
};

const PROCESS_NAMES = {
    layout_setup: 'Layout & Setup',
    cut_prep: 'Cut & Prep',
    fit_tack: 'Fit & Tack',
    full_weld: 'Full Weld',
    grind_clean: 'Grind & Clean',
    finish_prep: 'Finish Prep',
    clearcoat: 'Clear Coat',
    paint: 'Paint',
    hardware_install: 'Hardware Install',
    site_install: 'Site Install',
    final_inspection: 'Final Inspection',
};

const QuoteFlow = {
    sessionId: null,
    quoteId: null,
    pricedQuote: null,
    currentStep: 'describe', // describe | clarify | processing | results

    renderQuoteView() {
        const el = document.getElementById('view-quote');
        el.innerHTML = `
            <div id="quote-step-describe" class="quote-step">
                ${this._renderDescribeStep()}
            </div>
            <div id="quote-step-clarify" class="quote-step" style="display:none"></div>
            <div id="quote-step-processing" class="quote-step" style="display:none"></div>
            <div id="quote-step-results" class="quote-step" style="display:none"></div>
        `;
    },

    _renderDescribeStep() {
        const primaryTypes = ['cantilever_gate', 'swing_gate', 'straight_railing', 'stair_railing', 'repair_decorative'];
        const moreTypes = Object.keys(JOB_TYPES).filter(k => !primaryTypes.includes(k));

        return `
            <div class="describe-card">
                <h2>What are you quoting?</h2>

                <textarea id="job-description" class="job-textarea"
                    placeholder="Describe the job... e.g. '10 foot cantilever gate with motor, powder coat black, full install'"
                    rows="3"></textarea>

                <div class="job-type-section">
                    <p class="job-type-label">Or pick a job type:</p>
                    <div class="job-type-grid">
                        ${primaryTypes.map(jt => `
                            <button class="job-type-btn" onclick="QuoteFlow.startWithType('${jt}')">
                                ${JOB_TYPES[jt]}
                            </button>
                        `).join('')}
                        <button class="job-type-btn job-type-more" onclick="QuoteFlow.toggleMoreTypes()">
                            More...
                        </button>
                    </div>
                    <div id="more-job-types" class="job-type-grid" style="display:none">
                        ${moreTypes.map(jt => `
                            <button class="job-type-btn" onclick="QuoteFlow.startWithType('${jt}')">
                                ${JOB_TYPES[jt]}
                            </button>
                        `).join('')}
                    </div>
                </div>

                <button class="btn btn-primary btn-full btn-lg" onclick="QuoteFlow.startWithDescription()">
                    Start Quote &rarr;
                </button>
            </div>
        `;
    },

    toggleMoreTypes() {
        const el = document.getElementById('more-job-types');
        el.style.display = el.style.display === 'none' ? 'grid' : 'none';
    },

    async startWithDescription() {
        const desc = document.getElementById('job-description').value.trim();
        if (!desc) return;
        await this._startSession(desc);
    },

    async startWithType(jobType) {
        const desc = document.getElementById('job-description').value.trim() || `New ${JOB_TYPES[jobType] || jobType}`;
        await this._startSession(desc, jobType);
    },

    async _startSession(description, jobType = null) {
        this._showStep('processing');
        this._showProcessing('Starting quote...');
        try {
            const data = await API.startSession(description, jobType);
            this.sessionId = data.session_id;

            if (data.completion && data.completion.is_complete) {
                await this._runPipeline();
            } else if (data.next_questions && data.next_questions.length > 0) {
                this._renderClarifyStep(data);
                this._showStep('clarify');
            } else {
                this._showProcessing('No questions available for this job type yet.');
            }
        } catch (e) {
            this._showError(e.message);
        }
    },

    _renderClarifyStep(data) {
        const el = document.getElementById('quote-step-clarify');
        const jobName = JOB_TYPES[data.job_type] || data.job_type;
        const completion = data.completion || {};
        const pct = Math.round((completion.completion_pct || 0));
        const answered = completion.total_answered || 0;
        const total = completion.required_total || 0;
        const extracted = data.extracted_fields || {};

        el.innerHTML = `
            <div class="clarify-card">
                <div class="clarify-header">
                    <h2>${jobName}</h2>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width:${pct}%"></div>
                    </div>
                    <span class="progress-text">${answered}/${total} fields</span>
                </div>

                ${Object.keys(extracted).length > 0 ? `
                    <div class="extracted-fields">
                        <p class="extracted-title">Already captured:</p>
                        ${Object.entries(extracted).map(([k, v]) => `
                            <div class="extracted-item">&check; ${k.replace(/_/g, ' ')}: <strong>${v}</strong></div>
                        `).join('')}
                    </div>
                ` : ''}

                <div id="questions-container"></div>

                <div class="clarify-actions">
                    <button class="btn btn-primary btn-lg" id="btn-submit-answers" onclick="QuoteFlow.submitAnswers()">
                        Next &rarr;
                    </button>
                </div>
            </div>
        `;

        this._renderQuestions(data.next_questions || []);
    },

    _renderQuestions(questions) {
        const container = document.getElementById('questions-container');
        if (!container) return;

        if (questions.length === 0) {
            container.innerHTML = '<p class="all-done">All questions answered!</p>';
            document.getElementById('btn-submit-answers').textContent = 'Calculate Quote →';
            document.getElementById('btn-submit-answers').onclick = () => QuoteFlow._runPipeline();
            return;
        }

        container.innerHTML = questions.map(q => {
            const hint = q.hint ? `<p class="q-hint">${q.hint}</p>` : '';
            let input = '';

            switch (q.type) {
                case 'choice':
                    input = `<div class="choice-group" data-qid="${q.id}">
                        ${(q.options || []).map(opt => `
                            <button class="choice-btn" onclick="QuoteFlow.selectChoice(this, '${q.id}')" data-value="${opt}">
                                ${opt}
                            </button>
                        `).join('')}
                    </div>`;
                    break;
                case 'multi_choice':
                    input = `<div class="multi-choice-group" data-qid="${q.id}">
                        ${(q.options || []).map(opt => `
                            <label class="checkbox-label">
                                <input type="checkbox" value="${opt}" data-qid="${q.id}">
                                ${opt}
                            </label>
                        `).join('')}
                    </div>`;
                    break;
                case 'measurement':
                    input = `<div class="measure-input">
                        <input type="number" id="q-${q.id}" step="0.1" min="0" placeholder="Enter value">
                        <span class="measure-unit">${q.unit || ''}</span>
                    </div>`;
                    break;
                case 'number':
                    input = `<input type="number" id="q-${q.id}" class="text-input" step="1" min="0" placeholder="Enter number">`;
                    break;
                case 'boolean':
                    input = `<div class="choice-group" data-qid="${q.id}">
                        <button class="choice-btn" onclick="QuoteFlow.selectChoice(this, '${q.id}')" data-value="Yes">Yes</button>
                        <button class="choice-btn" onclick="QuoteFlow.selectChoice(this, '${q.id}')" data-value="No">No</button>
                    </div>`;
                    break;
                case 'text':
                    input = `<input type="text" id="q-${q.id}" class="text-input" placeholder="Enter text">`;
                    break;
                case 'photo':
                    input = `<div class="photo-placeholder">Photo upload coming soon — describe what you see instead</div>
                             <input type="text" id="q-${q.id}" class="text-input" placeholder="Describe the photo or skip">`;
                    break;
                default:
                    input = `<input type="text" id="q-${q.id}" class="text-input" placeholder="Enter value">`;
            }

            const required = q.required ? '<span class="required-badge">Required</span>' : '';

            return `
                <div class="question-card" data-qid="${q.id}">
                    <div class="q-header">
                        <label class="q-label">${q.text}</label>
                        ${required}
                    </div>
                    ${hint}
                    ${input}
                </div>
            `;
        }).join('');
    },

    selectChoice(btn, qid) {
        // Deselect siblings
        const group = btn.closest('.choice-group');
        group.querySelectorAll('.choice-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
    },

    _collectAnswers() {
        const answers = {};
        const container = document.getElementById('questions-container');
        if (!container) return answers;

        // Choice groups
        container.querySelectorAll('.choice-group').forEach(group => {
            const qid = group.dataset.qid;
            const selected = group.querySelector('.choice-btn.selected');
            if (selected) answers[qid] = selected.dataset.value;
        });

        // Multi-choice
        container.querySelectorAll('.multi-choice-group').forEach(group => {
            const qid = group.dataset.qid;
            const checked = group.querySelectorAll('input:checked');
            if (checked.length > 0) {
                answers[qid] = Array.from(checked).map(c => c.value).join(', ');
            }
        });

        // Text/number/measurement inputs
        container.querySelectorAll('input[type="text"], input[type="number"]').forEach(input => {
            const qid = input.id.replace('q-', '');
            if (input.value.trim()) answers[qid] = input.value.trim();
        });

        return answers;
    },

    async submitAnswers() {
        const answers = this._collectAnswers();
        if (Object.keys(answers).length === 0) return;

        const btn = document.getElementById('btn-submit-answers');
        btn.disabled = true;
        btn.textContent = 'Submitting...';

        try {
            const data = await API.submitAnswers(this.sessionId, answers);

            if (data.is_complete) {
                await this._runPipeline();
            } else {
                // Update progress and show next questions
                this._updateProgress(data.completion);
                this._renderQuestions(data.next_questions || []);
                btn.disabled = false;
                btn.textContent = 'Next →';
            }
        } catch (e) {
            this._showError(e.message);
            btn.disabled = false;
            btn.textContent = 'Next →';
        }
    },

    _updateProgress(completion) {
        if (!completion) return;
        const fill = document.querySelector('.progress-fill');
        const text = document.querySelector('.progress-text');
        if (fill) fill.style.width = `${Math.round(completion.completion_pct || 0)}%`;
        if (text) text.textContent = `${completion.total_answered || 0}/${completion.required_total || 0} fields`;
    },

    async _runPipeline() {
        this._showStep('processing');

        try {
            this._showProcessing('Calculating materials...');
            await API.calculate(this.sessionId);

            this._showProcessing('Estimating labor...');
            await API.estimate(this.sessionId);

            this._showProcessing('Building quote...');
            const result = await API.price(this.sessionId);

            this.quoteId = result.quote_id;
            this.pricedQuote = result.priced_quote;
            this._renderResults(result);
            this._showStep('results');
        } catch (e) {
            this._showError(e.message);
        }
    },

    _renderResults(result) {
        const el = document.getElementById('quote-step-results');
        const pq = result.priced_quote;
        const qn = result.quote_number || '';

        el.innerHTML = `
            <div class="results-card">
                <div class="results-header">
                    <div>
                        <h2>Quote #${qn}</h2>
                        <p class="results-meta">${JOB_TYPES[pq.job_type] || pq.job_type} &middot; ${new Date(pq.created_at).toLocaleDateString()}</p>
                    </div>
                    <div class="results-actions-top">
                        <button class="btn btn-secondary btn-sm" onclick="QuoteFlow.downloadPdf()">Download PDF</button>
                        <button class="btn btn-ghost btn-sm" onclick="QuoteFlow.newQuote()">+ New Quote</button>
                    </div>
                </div>

                ${this._renderSection('Materials', this._renderMaterialsTable(pq))}
                ${this._renderSection('Hardware & Parts', this._renderHardwareTable(pq))}
                ${pq.consumables && pq.consumables.length ? this._renderSection('Consumables', this._renderConsumablesTable(pq)) : ''}
                ${this._renderSection('Labor', this._renderLaborTable(pq))}
                ${this._renderSection('Finishing', this._renderFinishing(pq))}

                <div class="totals-section">
                    <div class="totals-grid">
                        <div class="total-row"><span>Materials</span><span>${this._fmt(pq.material_subtotal)}</span></div>
                        <div class="total-row"><span>Hardware</span><span>${this._fmt(pq.hardware_subtotal)}</span></div>
                        <div class="total-row"><span>Consumables</span><span>${this._fmt(pq.consumable_subtotal)}</span></div>
                        <div class="total-row"><span>Labor</span><span>${this._fmt(pq.labor_subtotal)}</span></div>
                        <div class="total-row"><span>Finishing</span><span>${this._fmt(pq.finishing_subtotal)}</span></div>
                        <div class="total-row subtotal"><span>Subtotal</span><span>${this._fmt(pq.subtotal)}</span></div>
                    </div>

                    <div class="markup-section">
                        <label class="markup-label">Markup:</label>
                        <div class="markup-buttons">
                            ${[0, 5, 10, 15, 20, 25, 30].map(pct => `
                                <button class="markup-btn ${pct === pq.selected_markup_pct ? 'active' : ''}"
                                    onclick="QuoteFlow.changeMarkup(${pct}, this)">${pct}%</button>
                            `).join('')}
                        </div>
                    </div>

                    <div class="grand-total">
                        <span>QUOTE TOTAL</span>
                        <span id="grand-total-amount">${this._fmt(pq.total)}</span>
                    </div>
                </div>

                ${pq.assumptions && pq.assumptions.length ? `
                    <div class="notes-section">
                        <h3>Assumptions</h3>
                        <ul>${pq.assumptions.map(a => `<li>${a}</li>`).join('')}</ul>
                    </div>
                ` : ''}

                ${pq.exclusions && pq.exclusions.length ? `
                    <div class="notes-section">
                        <h3>Exclusions</h3>
                        <ul>${pq.exclusions.map(e => `<li>${e}</li>`).join('')}</ul>
                    </div>
                ` : ''}

                <div class="results-footer">
                    <button class="btn btn-primary" onclick="QuoteFlow.downloadPdf()">Download PDF</button>
                    <button class="btn btn-secondary" onclick="QuoteFlow.newQuote()">+ New Quote</button>
                </div>
            </div>
        `;
    },

    _renderSection(title, content) {
        return `
            <div class="result-section">
                <h3 class="section-title">${title}</h3>
                ${content}
            </div>
        `;
    },

    _renderMaterialsTable(pq) {
        const items = pq.materials || [];
        if (!items.length) return '<p class="empty-section">No materials</p>';
        return `
            <table class="data-table">
                <thead><tr><th>Material</th><th>Qty</th><th class="r">Unit</th><th class="r">Total</th></tr></thead>
                <tbody>
                    ${items.map(m => `
                        <tr>
                            <td>${m.description || ''}</td>
                            <td>${m.quantity || 1}</td>
                            <td class="r">${this._fmt(m.unit_price)}</td>
                            <td class="r">${this._fmt(m.line_total)}</td>
                        </tr>
                    `).join('')}
                    <tr class="subtotal-row">
                        <td colspan="3">Material Subtotal</td>
                        <td class="r"><strong>${this._fmt(pq.material_subtotal)}</strong></td>
                    </tr>
                </tbody>
            </table>
        `;
    },

    _renderHardwareTable(pq) {
        const items = pq.hardware || [];
        if (!items.length) return '<p class="empty-section">No hardware</p>';
        return `
            <table class="data-table">
                <thead><tr><th>Item</th><th>Supplier</th><th>Qty</th><th class="r">Unit</th><th class="r">Total</th></tr></thead>
                <tbody>
                    ${items.map(h => {
                        const opts = h.options || [];
                        const valid = opts.filter(o => o.price != null);
                        const cheap = valid.length ? valid.reduce((a, b) => a.price < b.price ? a : b) : null;
                        const alts = valid.filter(o => o !== cheap);
                        const price = cheap ? cheap.price : 0;
                        const qty = h.quantity || 1;
                        return `
                            <tr>
                                <td>${h.description || ''}</td>
                                <td>${cheap ? cheap.supplier : '—'}</td>
                                <td>${qty}</td>
                                <td class="r">${this._fmt(price)}</td>
                                <td class="r">${this._fmt(price * qty)}</td>
                            </tr>
                            ${alts.length ? `<tr class="alt-row"><td colspan="5" class="alt-text">Alt: ${alts.map(a => `${a.supplier} ${this._fmt(a.price)}`).join(', ')}</td></tr>` : ''}
                        `;
                    }).join('')}
                    <tr class="subtotal-row">
                        <td colspan="4">Hardware Subtotal</td>
                        <td class="r"><strong>${this._fmt(pq.hardware_subtotal)}</strong></td>
                    </tr>
                </tbody>
            </table>
        `;
    },

    _renderConsumablesTable(pq) {
        const items = pq.consumables || [];
        return `
            <table class="data-table">
                <thead><tr><th>Item</th><th>Qty</th><th class="r">Unit</th><th class="r">Total</th></tr></thead>
                <tbody>
                    ${items.map(c => `
                        <tr>
                            <td>${c.description || ''}</td>
                            <td>${c.quantity || 1}</td>
                            <td class="r">${this._fmt(c.unit_price)}</td>
                            <td class="r">${this._fmt(c.line_total)}</td>
                        </tr>
                    `).join('')}
                    <tr class="subtotal-row">
                        <td colspan="3">Consumable Subtotal</td>
                        <td class="r"><strong>${this._fmt(pq.consumable_subtotal)}</strong></td>
                    </tr>
                </tbody>
            </table>
        `;
    },

    _renderLaborTable(pq) {
        const procs = (pq.labor || []).filter(p => p.hours > 0);
        if (!procs.length) return '<p class="empty-section">No labor</p>';
        return `
            <table class="data-table">
                <thead><tr><th>Process</th><th class="r">Hours</th><th class="r">Rate</th><th class="r">Total</th></tr></thead>
                <tbody>
                    ${procs.map(p => `
                        <tr>
                            <td>${PROCESS_NAMES[p.process] || p.process}</td>
                            <td class="r">${parseFloat(p.hours).toFixed(1)}</td>
                            <td class="r">${this._fmt(p.rate)}/hr</td>
                            <td class="r">${this._fmt(p.hours * p.rate)}</td>
                        </tr>
                    `).join('')}
                    <tr class="subtotal-row">
                        <td colspan="3">Labor Subtotal</td>
                        <td class="r"><strong>${this._fmt(pq.labor_subtotal)}</strong></td>
                    </tr>
                </tbody>
            </table>
        `;
    },

    _renderFinishing(pq) {
        const f = pq.finishing || {};
        const method = (f.method || 'raw').replace(/_/g, ' ');
        if (f.method === 'raw') {
            return `<p>Method: <strong>Raw Steel</strong> — no finish applied.</p>`;
        }
        const isOutsourced = (f.outsource_cost || 0) > 0;
        return `
            <p>Method: <strong>${method}</strong> ${isOutsourced ? '(outsourced)' : '(in-house)'}</p>
            <p>Area: ${(f.area_sq_ft || 0).toFixed(0)} sq ft</p>
            <p>Cost: <strong>${this._fmt(f.total)}</strong></p>
        `;
    },

    async changeMarkup(pct, btn) {
        if (!this.quoteId) return;
        // Update UI immediately
        document.querySelectorAll('.markup-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        try {
            const data = await API.updateMarkup(this.quoteId, pct);
            document.getElementById('grand-total-amount').textContent = this._fmt(data.total);
            if (this.pricedQuote) {
                this.pricedQuote.selected_markup_pct = pct;
                this.pricedQuote.total = data.total;
            }
        } catch (e) {
            console.error('Markup update failed:', e);
        }
    },

    downloadPdf() {
        if (!this.quoteId) return;
        // Open PDF in new tab with auth token as query param
        const url = API.getPdfUrl(this.quoteId);
        window.open(url, '_blank');
    },

    newQuote() {
        this.sessionId = null;
        this.quoteId = null;
        this.pricedQuote = null;
        this.currentStep = 'describe';
        this.renderQuoteView();
    },

    // --- Helpers ---
    _showStep(step) {
        this.currentStep = step;
        ['describe', 'clarify', 'processing', 'results'].forEach(s => {
            const el = document.getElementById(`quote-step-${s}`);
            if (el) el.style.display = s === step ? 'block' : 'none';
        });
    },

    _showProcessing(msg) {
        const el = document.getElementById('quote-step-processing');
        el.innerHTML = `
            <div class="processing-card">
                <div class="spinner"></div>
                <p class="processing-text">${msg}</p>
            </div>
        `;
    },

    _showError(msg) {
        const el = document.getElementById('quote-step-processing');
        el.innerHTML = `
            <div class="processing-card error">
                <p class="error-text">${msg}</p>
                <button class="btn btn-secondary" onclick="QuoteFlow.newQuote()">Try Again</button>
            </div>
        `;
        this._showStep('processing');
    },

    _fmt(n) {
        try {
            return '$' + parseFloat(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        } catch {
            return '$0.00';
        }
    },
};


// --- Quote History ---
const QuoteHistory = {
    async render() {
        const el = document.getElementById('view-history');
        el.innerHTML = '<div class="history-loading"><div class="spinner"></div><p>Loading quotes...</p></div>';

        try {
            const quotes = await API.listMyQuotes();
            if (quotes.length === 0) {
                el.innerHTML = `
                    <div class="history-empty">
                        <h2>No quotes yet</h2>
                        <p>Start your first quote to see it here.</p>
                        <button class="btn btn-primary" onclick="App.showView('quote')">+ New Quote</button>
                    </div>
                `;
                return;
            }

            el.innerHTML = `
                <div class="history-card">
                    <div class="history-header">
                        <h2>Your Quotes</h2>
                        <button class="btn btn-primary btn-sm" onclick="App.showView('quote')">+ New Quote</button>
                    </div>
                    <div class="history-list">
                        ${quotes.map(q => `
                            <div class="history-item" onclick="QuoteHistory.viewQuote(${q.id})">
                                <div class="hi-main">
                                    <span class="hi-number">${q.quote_number || '—'}</span>
                                    <span class="hi-type">${JOB_TYPES[q.job_type] || q.job_type || ''}</span>
                                </div>
                                <div class="hi-meta">
                                    <span class="hi-total">${QuoteFlow._fmt(q.total)}</span>
                                    <span class="hi-date">${q.created_at ? new Date(q.created_at).toLocaleDateString() : ''}</span>
                                    <span class="hi-status badge-${q.status || 'draft'}">${q.status || 'draft'}</span>
                                </div>
                                <div class="hi-actions">
                                    <button class="btn btn-ghost btn-xs" onclick="event.stopPropagation(); QuoteHistory.downloadPdf(${q.id})">PDF</button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        } catch (e) {
            el.innerHTML = `<div class="history-empty"><p>Failed to load quotes. ${e.message}</p></div>`;
        }
    },

    async viewQuote(quoteId) {
        try {
            const detail = await API.getQuoteDetail(quoteId);
            if (detail.outputs) {
                QuoteFlow.quoteId = quoteId;
                QuoteFlow.pricedQuote = detail.outputs;
                QuoteFlow._renderResults({
                    quote_number: detail.quote_number,
                    priced_quote: detail.outputs,
                });
                App.showView('quote');
                QuoteFlow._showStep('results');
            }
        } catch (e) {
            console.error('Failed to view quote:', e);
        }
    },

    downloadPdf(quoteId) {
        window.open(API.getPdfUrl(quoteId), '_blank');
    },
};
