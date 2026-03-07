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
    offroad_bumper: 'Off-Road Bumper',
    rock_slider: 'Rock Slider',
    roll_cage: 'Roll Cage',
    exhaust_custom: 'Custom Exhaust',
    trailer_fab: 'Custom Trailer',
    structural_frame: 'Structural Frame',
    furniture_other: 'Furniture / Fixtures',
    sign_frame: 'Sign Frame',
    led_sign_custom: 'LED Sign',
    product_firetable: 'FireTable',
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
    sessionPhotoUrls: [],
    extractedFields: {},
    allQuestions: [],

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
        this._initPhotoUpload();
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

                <div class="photo-upload-section">
                    <input type="file" id="photo-input" accept="image/jpeg,image/png,image/webp,image/heic" multiple hidden>
                    <button class="btn btn-secondary btn-sm" id="photo-upload-btn" onclick="document.getElementById('photo-input').click()">
                        + Add Photos
                    </button>
                    <span class="photo-hint">Photos help us extract dimensions, materials, and damage</span>
                    <div id="photo-previews" class="photo-previews"></div>
                </div>

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

    _initPhotoUpload() {
        const input = document.getElementById('photo-input');
        if (!input) return;
        input.addEventListener('change', async (e) => {
            for (const file of e.target.files) {
                QuoteFlow._showPhotoUploading(file.name);
                const formData = new FormData();
                formData.append('file', file);
                try {
                    const result = await API.uploadPhoto(formData);
                    QuoteFlow.sessionPhotoUrls.push(result.photo_url);
                    QuoteFlow._showPhotoPreview(result.photo_url, file.name);
                } catch (err) {
                    QuoteFlow._showPhotoError(file.name, err.message);
                }
            }
            input.value = '';
        });
    },

    _showPhotoUploading(name) {
        const container = document.getElementById('photo-previews');
        if (!container) return;
        const el = document.createElement('div');
        el.className = 'photo-preview uploading';
        el.id = 'uploading-' + name.replace(/[^a-zA-Z0-9]/g, '_');
        el.innerHTML = '<div class="spinner-sm"></div><span class="photo-name">' + name + '</span>';
        container.appendChild(el);
    },

    _showPhotoPreview(url, name) {
        const container = document.getElementById('photo-previews');
        if (!container) return;
        const uploading = document.getElementById('uploading-' + name.replace(/[^a-zA-Z0-9]/g, '_'));
        if (uploading) uploading.remove();
        const el = document.createElement('div');
        el.className = 'photo-preview';
        el.innerHTML = `
            <img src="${url}" alt="${name}" />
            <span class="photo-name">${name}</span>
            <button class="photo-remove" onclick="QuoteFlow._removePhoto(this, '${url}')">&times;</button>
        `;
        container.appendChild(el);
    },

    _showPhotoError(name, msg) {
        const uploading = document.getElementById('uploading-' + name.replace(/[^a-zA-Z0-9]/g, '_'));
        if (uploading) uploading.remove();
    },

    _removePhoto(btn, url) {
        QuoteFlow.sessionPhotoUrls = QuoteFlow.sessionPhotoUrls.filter(u => u !== url);
        btn.closest('.photo-preview').remove();
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
        this._showProcessing(this.sessionPhotoUrls.length > 0
            ? 'Analyzing photos and starting quote...'
            : 'Starting quote...');
        try {
            const data = await API.startSession(description, jobType, this.sessionPhotoUrls);
            this.sessionId = data.session_id;
            this.extractedFields = data.extracted_fields || {};
            this.allQuestions = data.next_questions || [];

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
        const answered = completion.required_answered || 0;
        const total = completion.required_total || 0;
        const extracted = data.extracted_fields || {};
        const photoExtracted = data.photo_extracted_fields || {};
        const photoObs = data.photo_observations || '';

        // Merge all confirmed fields for display
        const allConfirmed = Object.assign({}, extracted, photoExtracted);
        this.extractedFields = allConfirmed;

        el.innerHTML = `
            <div class="clarify-card">
                <div class="clarify-header">
                    <h2>${jobName}</h2>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width:${pct}%"></div>
                    </div>
                    <span class="progress-text">${answered}/${total} fields</span>
                </div>

                ${photoObs ? `
                    <div class="photo-obs">
                        <span class="photo-obs-icon">&#128247;</span>
                        <span>${photoObs.split('\\n')[0]}</span>
                    </div>
                ` : ''}

                <div id="confirmed-fields"></div>

                <div id="questions-container"></div>

                <div class="clarify-actions">
                    <button class="btn btn-primary btn-lg" id="btn-submit-answers" onclick="QuoteFlow.submitAnswers()">
                        Next &rarr;
                    </button>
                </div>
            </div>
        `;

        this._showConfirmedFields(allConfirmed, photoExtracted, data.next_questions || []);
        this._renderQuestions(data.next_questions || []);
    },

    _showConfirmedFields(allConfirmed, photoExtracted, allQuestions) {
        const el = document.getElementById('confirmed-fields');
        if (!el) return;
        el.innerHTML = '';

        const keys = Object.keys(allConfirmed);
        if (keys.length === 0) return;

        const header = document.createElement('div');
        header.className = 'confirmed-header';
        header.textContent = 'Already captured';
        el.appendChild(header);

        for (const [fieldId, value] of Object.entries(allConfirmed)) {
            const question = allQuestions.find(q => q.id === fieldId);
            const label = question
                ? question.text.split('?')[0].trim()
                : fieldId.replace(/_/g, ' ');
            const isPhoto = fieldId in (photoExtracted || {});

            const fieldDiv = document.createElement('div');
            fieldDiv.className = 'confirmed-field';
            fieldDiv.innerHTML = `
                <span class="confirmed-check">${isPhoto ? '&#128247; &#10003;' : '&#10003;'}</span>
                <span class="confirmed-label">${label}:</span>
                <span class="confirmed-value">${value}</span>
                <button class="confirmed-edit" onclick="QuoteFlow.editExtractedField('${fieldId}')">Edit</button>
            `;
            el.appendChild(fieldDiv);
        }
    },

    editExtractedField(fieldId) {
        delete this.extractedFields[fieldId];
        // Re-fetch session status to get updated questions
        if (this.sessionId) {
            API.submitAnswers(this.sessionId, {}).then(data => {
                // The field will now appear in next_questions since we remove it client-side
                // For now, just reload the clarify step
                this._renderClarifyStep({
                    job_type: document.querySelector('.clarify-header h2')?.textContent || '',
                    completion: data.completion,
                    extracted_fields: this.extractedFields,
                    photo_extracted_fields: {},
                    next_questions: data.next_questions,
                });
                this._showStep('clarify');
            }).catch(() => {});
        }
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
                    input = `<div class="photo-question-upload">
                        <input type="file" id="photo-q-${q.id}" accept="image/jpeg,image/png,image/webp" hidden>
                        <button class="btn btn-secondary btn-sm" onclick="document.getElementById('photo-q-${q.id}').click()">
                            + Upload Photo
                        </button>
                        <div id="photo-q-preview-${q.id}" class="photo-q-preview"></div>
                    </div>
                    <input type="text" id="q-${q.id}" class="text-input" placeholder="Or describe what you see">`;
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
        if (text) text.textContent = `${completion.required_answered || 0}/${completion.required_total || 0} fields`;
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
                        <button class="btn btn-secondary btn-sm" onclick="QuoteFlow.downloadPdf()">Shop PDF</button>
                        <button class="btn btn-secondary btn-sm" onclick="QuoteFlow.downloadPdf('client')">Client PDF</button>
                        <button class="btn btn-secondary btn-sm" onclick="QuoteFlow.downloadPdf('materials')">Materials PDF</button>
                        <button class="btn btn-ghost btn-sm" onclick="QuoteFlow.downloadCsv()">Materials CSV</button>
                        <button class="btn btn-ghost btn-sm" onclick="QuoteFlow.newQuote()">+ New Quote</button>
                    </div>
                </div>

                <div class="customer-section">
                    <h3 class="section-title">Customer Information</h3>
                    <div class="form-grid">
                        <label class="form-label">
                            Name
                            <input type="text" id="customer-name" placeholder="Client name" value="${(pq._customer && pq._customer.name) || ''}">
                        </label>
                        <label class="form-label">
                            Phone
                            <input type="text" id="customer-phone" placeholder="(555) 123-4567" value="${(pq._customer && pq._customer.phone) || ''}">
                        </label>
                        <label class="form-label">
                            Email
                            <input type="email" id="customer-email" placeholder="client@example.com" value="${(pq._customer && pq._customer.email) || ''}">
                        </label>
                        <label class="form-label">
                            Address
                            <input type="text" id="customer-address" placeholder="123 Main St, City, ST 12345" value="${(pq._customer && pq._customer.address) || ''}">
                        </label>
                    </div>
                    <div class="customer-actions">
                        <button class="btn btn-secondary btn-sm" onclick="QuoteFlow.saveCustomer()">Save Customer Info</button>
                        <span id="customer-save-status" class="save-status"></span>
                    </div>
                </div>

                ${this._renderValidationWarnings(pq)}

                ${pq.job_description ? `
                    <div class="job-description-section">
                        <h3 class="section-title">Job Description</h3>
                        <p class="job-description-text">${pq.job_description}</p>
                    </div>
                ` : ''}

                ${this._renderSection('Materials', this._renderMaterialsTable(pq))}
                ${this._renderSection('Hardware & Parts', this._renderHardwareTable(pq))}
                ${pq.consumables && pq.consumables.length ? this._renderSection('Consumables', this._renderConsumablesTable(pq)) : ''}

                ${pq.detailed_cut_list && pq.detailed_cut_list.length ? this._renderSection('Cut List', this._renderCutListTable(pq)) : ''}
                ${pq.build_instructions && pq.build_instructions.length
                    ? this._renderSection('Build Sequence', this._renderBuildInstructions(pq))
                    : this._renderBuildInstructionsRetry(pq)}

                ${this._renderSection('Labor', this._renderLaborTable(pq))}
                ${this._renderSection('Finishing', this._renderFinishing(pq))}

                <div class="totals-section">
                    <div class="rate-input-section">
                        <label class="rate-label">Shop Rate:</label>
                        <div class="rate-input-wrap">
                            <span class="rate-prefix">$</span>
                            <input type="number" id="shop-rate-input" class="rate-input"
                                value="${this._getShopRate(pq)}" step="5" min="0"
                                onchange="QuoteFlow.changeRate(parseFloat(this.value))">
                            <span class="rate-suffix">/hr</span>
                        </div>
                    </div>

                    <div class="totals-grid">
                        <div class="total-row"><span>Materials</span><span>${this._fmt(pq.material_subtotal)}</span></div>
                        <div class="total-row"><span>Hardware</span><span>${this._fmt(pq.hardware_subtotal)}</span></div>
                        <div class="total-row"><span>Consumables</span><span>${this._fmt(pq.consumable_subtotal)}</span></div>
                        <div class="total-row"><span>Labor</span><span id="labor-subtotal-amount">${this._fmt(pq.labor_subtotal)}</span></div>
                        <div class="total-row"><span>Finishing</span><span>${this._fmt(pq.finishing_subtotal)}</span></div>
                        <div class="total-row subtotal"><span>Subtotal</span><span id="subtotal-amount">${this._fmt(pq.subtotal)}</span></div>
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
                    <button class="btn btn-primary" onclick="QuoteFlow.downloadPdf()">Shop PDF</button>
                    <button class="btn btn-secondary" onclick="QuoteFlow.downloadPdf('client')">Client PDF</button>
                    <button class="btn btn-secondary" onclick="QuoteFlow.downloadPdf('materials')">Materials PDF</button>
                    <button class="btn btn-ghost" onclick="QuoteFlow.downloadCsv()">Materials CSV</button>
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
        const summary = pq.materials_summary || [];
        const items = pq.materials || [];
        if (!items.length && !summary.length) return '<p class="empty-section">No materials</p>';

        // Primary view: aggregated stock order by profile
        if (summary.length > 0) {
            const steelRows = summary.filter(s => !s.is_concrete);
            const concreteRows = summary.filter(s => s.is_concrete);

            return `
                <table class="data-table">
                    <thead><tr>
                        <th>Profile</th><th>Pcs</th><th>Total</th>
                        <th>Sticks</th><th>Remainder</th><th>Weight</th><th class="r">Cost</th>
                    </tr></thead>
                    <tbody>
                        ${steelRows.map(s => {
                            const profile = (s.profile || '').replace(/_/g, ' ');
                            const isArea = s.is_area_sold;
                            const totalCol = isArea ? (s.piece_count + ' pcs') : (s.total_length_ft.toFixed(1) + "'");
                            const sticksCol = isArea ? '-' : (s.sticks_needed + ' x ' + s.stock_length_ft + "'");
                            const remainCol = (!isArea && s.remainder_ft > 0) ? (s.remainder_ft.toFixed(1) + "' left") : '-';
                            const weightCol = s.weight_lbs > 0 ? (Math.round(s.weight_lbs) + ' lbs') : '-';
                            return `<tr>
                                <td>${profile}</td>
                                <td>${s.piece_count || ''}</td>
                                <td>${totalCol}</td>
                                <td>${sticksCol}</td>
                                <td>${remainCol}</td>
                                <td>${weightCol}</td>
                                <td class="r">${this._fmt(s.total_cost)}</td>
                            </tr>`;
                        }).join('')}
                        ${concreteRows.map(s => `<tr>
                            <td>Concrete (${s.piece_count} x 80lb bags)</td>
                            <td>${s.piece_count}</td>
                            <td>-</td><td>-</td><td>-</td>
                            <td>${Math.round(s.weight_lbs)} lbs</td>
                            <td class="r">${this._fmt(s.total_cost)}</td>
                        </tr>`).join('')}
                        <tr class="subtotal-row">
                            <td colspan="6">Material Subtotal</td>
                            <td class="r"><strong>${this._fmt(pq.material_subtotal)}</strong></td>
                        </tr>
                    </tbody>
                </table>
            `;
        }

        // Fallback: per-piece table if no summary
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
                    ${items.map((h, idx) => {
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
                                <td>
                                    <input type="number" class="inline-edit inline-edit-sm" step="1" min="0"
                                        value="${qty}" data-hw-idx="${idx}"
                                        onchange="QuoteFlow.adjustHardwareQty(${idx}, parseInt(this.value))">
                                </td>
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
                    ${items.map((c, idx) => `
                        <tr>
                            <td>${c.description || ''}</td>
                            <td>
                                <input type="number" class="inline-edit inline-edit-sm" step="0.5" min="0"
                                    value="${parseFloat(c.quantity || 1).toFixed(1)}" data-cons-idx="${idx}"
                                    onchange="QuoteFlow.adjustConsumableQty(${idx}, parseFloat(this.value))">
                            </td>
                            <td class="r">${this._fmt(c.unit_price)}</td>
                            <td class="r">${this._fmt((c.unit_price || 0) * (c.quantity || 1))}</td>
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
                            <td class="r">
                                <input type="number" class="inline-edit" step="0.5" min="0"
                                    value="${parseFloat(p.hours).toFixed(1)}"
                                    data-process="${p.process}"
                                    onchange="QuoteFlow.adjustLaborHours('${p.process}', parseFloat(this.value))">
                            </td>
                            <td class="r">${this._fmt(p.rate)}/hr</td>
                            <td class="r labor-line-total" data-process="${p.process}">${this._fmt(p.hours * p.rate)}</td>
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

    _renderValidationWarnings(pq) {
        const warnings = pq.validation_warnings || [];
        if (!warnings.length) return '';
        const errors = warnings.filter(w => w.startsWith('[ERROR]'));
        const warns = warnings.filter(w => w.startsWith('[WARNING]'));
        const infos = warnings.filter(w => !w.startsWith('[ERROR]') && !w.startsWith('[WARNING]'));
        return `
            <div class="validation-warnings">
                <h3 class="validation-title">REVIEW REQUIRED</h3>
                ${errors.map(w => `<div class="vw-error">${w}</div>`).join('')}
                ${warns.map(w => `<div class="vw-warn">${w}</div>`).join('')}
                ${infos.map(w => `<div class="vw-info">${w}</div>`).join('')}
            </div>
        `;
    },

    _renderCutListTable(pq) {
        const items = pq.detailed_cut_list || [];
        if (!items.length) return '<p class="empty-section">No cut list</p>';
        return `
            <table class="data-table">
                <thead><tr>
                    <th>Piece</th><th>Profile</th><th>Length</th><th>Cut</th><th>Qty</th>
                </tr></thead>
                <tbody>
                    ${items.map(c => {
                        const lenIn = parseFloat(c.length_inches || 0);
                        const lenStr = lenIn >= 12
                            ? (lenIn / 12).toFixed(1) + ' ft'
                            : lenIn.toFixed(1) + ' in';
                        return `
                            <tr>
                                <td>${c.piece_name || c.description || ''}</td>
                                <td class="profile-cell">${(c.profile || '').replace(/_/g, ' ')}</td>
                                <td class="r">${lenStr}</td>
                                <td>${c.cut_type || 'square'}</td>
                                <td class="r">${c.quantity || 1}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    },

    _renderBuildInstructions(pq) {
        const steps = pq.build_instructions || [];
        if (!steps.length) return '<p class="empty-section">No build instructions</p>';
        return `
            <ol class="build-steps">
                ${steps.map(s => {
                    const hasReview = (s.description || '').includes('[REVIEW');
                    return `
                        <li class="build-step ${hasReview ? 'build-step-flagged' : ''}">
                            <strong>${s.title || 'Step ' + (s.step || '')}</strong>
                            <p>${s.description || ''}</p>
                            ${s.safety_notes ? `<p class="safety-note">Safety: ${s.safety_notes}</p>` : ''}
                        </li>
                    `;
                }).join('')}
            </ol>
        `;
    },

    _renderBuildInstructionsRetry(pq) {
        const error = pq._build_instructions_error || '';
        return `
            <div class="result-section build-retry-section">
                <h3 class="section-title">Build Sequence</h3>
                <div class="build-retry-banner">
                    <span class="build-retry-icon">&#9888;&#65039;</span>
                    <span class="build-retry-text">Fabrication sequence unavailable</span>
                    <button class="btn btn-accent btn-sm" id="btn-retry-build" onclick="QuoteFlow.retryBuildInstructions()">
                        Retry
                    </button>
                </div>
                ${error ? `<p class="build-retry-detail">${error}</p>` : ''}
            </div>
        `;
    },

    async retryBuildInstructions() {
        if (!this.sessionId) return;
        const btn = document.getElementById('btn-retry-build');
        if (btn) { btn.disabled = true; btn.textContent = 'Generating...'; }
        try {
            const result = await API.retryBuildInstructions(this.sessionId);
            if (result.build_instructions && result.build_instructions.length) {
                this.pricedQuote.build_instructions = result.build_instructions;
                delete this.pricedQuote._build_instructions_error;
                // Re-render the build section in place
                const section = document.querySelector('.build-retry-section');
                if (section) {
                    section.outerHTML = this._renderSection('Build Sequence', this._renderBuildInstructions(this.pricedQuote));
                }
            }
        } catch (e) {
            if (btn) { btn.disabled = false; btn.textContent = 'Retry'; }
            const detail = document.querySelector('.build-retry-detail');
            if (detail) {
                detail.textContent = e.message;
            } else {
                const banner = document.querySelector('.build-retry-banner');
                if (banner) banner.insertAdjacentHTML('afterend', `<p class="build-retry-detail">${e.message}</p>`);
            }
        }
    },

    _getShopRate(pq) {
        const procs = pq.labor || [];
        for (const p of procs) {
            if (p.rate && p.rate > 0) return p.rate;
        }
        return 125;
    },

    changeRate(newRate) {
        if (!this.pricedQuote || !newRate || newRate <= 0) return;
        const pq = this.pricedQuote;
        (pq.labor || []).forEach(p => { p.rate = newRate; });
        this._recalcTotals();

        // Re-render labor table to show updated rates
        const laborSections = document.querySelectorAll('.result-section');
        laborSections.forEach(sec => {
            const title = sec.querySelector('.section-title');
            if (title && title.textContent === 'Labor') {
                sec.innerHTML = '<h3 class="section-title">Labor</h3>' + this._renderLaborTable(pq);
            }
        });
    },

    adjustLaborHours(process, newHours) {
        if (!this.pricedQuote || isNaN(newHours) || newHours < 0) return;
        const pq = this.pricedQuote;
        const proc = (pq.labor || []).find(p => p.process === process);
        if (!proc) return;
        proc.hours = Math.round(newHours * 10) / 10;

        // Update line total display
        const lineEl = document.querySelector(`td.labor-line-total[data-process="${process}"]`);
        if (lineEl) lineEl.textContent = this._fmt(proc.hours * proc.rate);

        // Recalculate labor subtotal
        this._recalcTotals();

        // Persist to backend (debounced)
        this._debouncedAdjust('labor', { [process]: proc.hours });
    },

    adjustHardwareQty(idx, newQty) {
        if (!this.pricedQuote || isNaN(newQty) || newQty < 0) return;
        const pq = this.pricedQuote;
        const hw = (pq.hardware || [])[idx];
        if (!hw) return;
        hw.quantity = Math.max(0, Math.round(newQty));

        // Recalculate hardware subtotal
        let hwTotal = 0;
        (pq.hardware || []).forEach(h => {
            const opts = h.options || [];
            const valid = opts.filter(o => o.price != null);
            if (valid.length) {
                const cheapest = valid.reduce((a, b) => a.price < b.price ? a : b);
                hwTotal += cheapest.price * (h.quantity || 1);
            }
        });
        pq.hardware_subtotal = Math.round(hwTotal * 100) / 100;

        this._recalcTotals();
        this._debouncedAdjust('hardware', { [idx]: hw.quantity });
    },

    adjustConsumableQty(idx, newQty) {
        if (!this.pricedQuote || isNaN(newQty) || newQty < 0) return;
        const pq = this.pricedQuote;
        const item = (pq.consumables || [])[idx];
        if (!item) return;
        item.quantity = Math.round(newQty * 10) / 10;
        item.line_total = Math.round(item.unit_price * item.quantity * 100) / 100;

        // Recalculate consumable subtotal
        pq.consumable_subtotal = Math.round(
            (pq.consumables || []).reduce((s, c) => s + (c.line_total || 0), 0) * 100
        ) / 100;

        this._recalcTotals();
        this._debouncedAdjust('consumable', { [idx]: item.quantity });
    },

    _recalcTotals() {
        const pq = this.pricedQuote;
        if (!pq) return;
        // Recalculate labor subtotal
        pq.labor_subtotal = Math.round(
            (pq.labor || []).reduce((s, p) => s + (p.hours || 0) * (p.rate || 0), 0) * 100
        ) / 100;

        pq.subtotal = Math.round((
            (pq.material_subtotal || 0) +
            (pq.hardware_subtotal || 0) +
            (pq.consumable_subtotal || 0) +
            pq.labor_subtotal +
            (pq.finishing_subtotal || 0)
        ) * 100) / 100;

        const markupPct = pq.selected_markup_pct || 0;
        pq.total = Math.round(pq.subtotal * (1 + markupPct / 100) * 100) / 100;

        // Update display
        const laborEl = document.getElementById('labor-subtotal-amount');
        const subEl = document.getElementById('subtotal-amount');
        const totalEl = document.getElementById('grand-total-amount');
        if (laborEl) laborEl.textContent = this._fmt(pq.labor_subtotal);
        if (subEl) subEl.textContent = this._fmt(pq.subtotal);
        if (totalEl) totalEl.textContent = this._fmt(pq.total);
    },

    _adjustTimers: {},
    _debouncedAdjust(type, data) {
        if (this._adjustTimers[type]) clearTimeout(this._adjustTimers[type]);
        // Accumulate adjustments
        if (!this._pendingAdjustments) this._pendingAdjustments = {};
        if (!this._pendingAdjustments[type]) this._pendingAdjustments[type] = {};
        Object.assign(this._pendingAdjustments[type], data);

        this._adjustTimers[type] = setTimeout(() => {
            if (!this.quoteId || !this._pendingAdjustments) return;
            const payload = {};
            if (this._pendingAdjustments.labor) payload.labor_adjustments = this._pendingAdjustments.labor;
            if (this._pendingAdjustments.hardware) payload.hardware_adjustments = this._pendingAdjustments.hardware;
            if (this._pendingAdjustments.consumable) payload.consumable_adjustments = this._pendingAdjustments.consumable;
            this._pendingAdjustments = {};
            API.adjustLineItems(this.quoteId, payload).catch(e => console.error('Adjust failed:', e));
        }, 800);
    },

    async changeMarkup(pct, btn) {
        if (!this.quoteId) return;
        // Update UI immediately
        document.querySelectorAll('.markup-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Local recalculation (handles rate changes)
        if (this.pricedQuote) {
            this.pricedQuote.selected_markup_pct = pct;
            this.pricedQuote.total = Math.round(
                (this.pricedQuote.subtotal || 0) * (1 + pct / 100) * 100
            ) / 100;
            document.getElementById('grand-total-amount').textContent = this._fmt(this.pricedQuote.total);
        }

        try {
            await API.updateMarkup(this.quoteId, pct);
        } catch (e) {
            console.error('Markup update failed:', e);
        }
    },

    async saveCustomer() {
        if (!this.sessionId) return;
        const data = {
            name: (document.getElementById('customer-name') || {}).value || '',
            phone: (document.getElementById('customer-phone') || {}).value || '',
            email: (document.getElementById('customer-email') || {}).value || '',
            address: (document.getElementById('customer-address') || {}).value || '',
        };
        const statusEl = document.getElementById('customer-save-status');
        try {
            await API.updateCustomer(this.sessionId, data);
            if (this.pricedQuote) {
                this.pricedQuote._customer = data;
                this.pricedQuote.client_name = data.name;
            }
            if (statusEl) {
                statusEl.textContent = 'Saved';
                statusEl.className = 'save-status save-ok';
                setTimeout(() => { statusEl.textContent = ''; }, 2000);
            }
        } catch (e) {
            if (statusEl) {
                statusEl.textContent = 'Failed to save';
                statusEl.className = 'save-status save-err';
            }
        }
    },

    downloadPdf(mode) {
        if (!this.quoteId) return;
        // For client PDF, require customer name
        if (mode === 'client') {
            const nameInput = document.getElementById('customer-name');
            if (nameInput && !nameInput.value.trim()) {
                nameInput.focus();
                nameInput.style.borderColor = 'var(--error)';
                setTimeout(() => { nameInput.style.borderColor = ''; }, 3000);
                return;
            }
        }
        // Open PDF in new tab with auth token as query param
        const url = API.getPdfUrl(this.quoteId, mode || null);
        window.open(url, '_blank');
    },

    downloadCsv() {
        if (!this.quoteId) return;
        // CSV downloads as a file — use same URL pattern with materials-csv mode
        const url = API.getPdfUrl(this.quoteId, 'materials-csv');
        window.open(url, '_blank');
    },

    async openSwapModal(itemIndex) {
        if (!this.quoteId) return;
        const container = document.getElementById('swap-modal-container');
        if (!container) return;
        container.innerHTML = `
            <div class="swap-modal-overlay" onclick="QuoteFlow.closeSwapModal()">
                <div class="swap-modal" onclick="event.stopPropagation()">
                    <div class="swap-modal-header">
                        <h3>Swap Material</h3>
                        <button class="swap-close" onclick="QuoteFlow.closeSwapModal()">&times;</button>
                    </div>
                    <div class="swap-modal-body">
                        <div class="spinner-sm"></div> Loading alternatives...
                    </div>
                </div>
            </div>
        `;
        try {
            const alts = await API.getMaterialAlternatives(this.quoteId);
            const match = alts.find(a => a.item_index === itemIndex);
            if (!match || !match.alternatives.length) {
                container.querySelector('.swap-modal-body').innerHTML =
                    '<p class="empty-section">No alternative profiles available for this material.</p>';
                return;
            }
            container.querySelector('.swap-modal-body').innerHTML = `
                <p class="swap-current">Current: <strong>${match.current_profile.replace(/_/g, ' ')}</strong> at ${this._fmt(match.current_price)}/ft</p>
                <table class="data-table swap-table">
                    <thead><tr><th>Profile</th><th class="r">Price/ft</th><th class="r">Delta</th><th></th></tr></thead>
                    <tbody>
                        ${match.alternatives.map(a => `
                            <tr>
                                <td>${a.description}</td>
                                <td class="r">${this._fmt(a.price)}</td>
                                <td class="r ${a.delta < 0 ? 'delta-savings' : a.delta > 0 ? 'delta-increase' : ''}">${a.delta >= 0 ? '+' : ''}${this._fmt(a.delta)}</td>
                                <td><button class="btn btn-accent btn-xs" onclick="QuoteFlow.confirmSwap(${itemIndex}, '${a.profile}')">Select</button></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        } catch (e) {
            container.querySelector('.swap-modal-body').innerHTML =
                '<p class="error-text">' + e.message + '</p>';
        }
    },

    closeSwapModal() {
        const container = document.getElementById('swap-modal-container');
        if (container) container.innerHTML = '';
    },

    async confirmSwap(itemIndex, newProfile) {
        if (!this.quoteId) return;
        try {
            const updated = await API.swapMaterial(this.quoteId, itemIndex, newProfile);
            this.pricedQuote = updated;
            this.closeSwapModal();
            this._renderResults({
                quote_number: updated.quote_number || '',
                priced_quote: updated,
            });
            this._showStep('results');
        } catch (e) {
            alert('Swap failed: ' + e.message);
        }
    },

    newQuote() {
        this.sessionId = null;
        this.quoteId = null;
        this.pricedQuote = null;
        this.sessionPhotoUrls = [];
        this.extractedFields = {};
        this.allQuestions = [];
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
