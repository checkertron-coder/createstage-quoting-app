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
        // Restore active session first, then completed quote
        this._tryRestoreSession();
    },

    async _tryRestoreSession() {
        // 1. Try active (in-progress) session
        if (await this._tryRestoreActiveSession()) return;
        // 2. Try completed quote
        await this._tryRestoreLastQuote();
    },

    async _tryRestoreActiveSession() {
        try {
            const savedId = localStorage.getItem('cq_active_session_id');
            if (!savedId) return false;

            const status = await API.getSessionStatus(savedId);

            // Error or gone — clear and fall through
            if (!status || status.status === 'error') {
                localStorage.removeItem('cq_active_session_id');
                return false;
            }
            // Completed — let the quote restore path handle it
            if (status.status === 'completed' || status.stage === 'complete') {
                localStorage.removeItem('cq_active_session_id');
                return false;
            }
            // Processing — resume polling (P71: check which stage is processing)
            if (status.status === 'processing') {
                this.sessionId = savedId;
                this._currentJobType = status.job_type || '';
                this._showStep('processing');

                // P71: Pipeline stages (calculate/estimate/price) use stage-aware polling
                const pipelineStage = status.pipeline_stage || status.stage;
                if (pipelineStage === 'calculate' || pipelineStage === 'estimate' || pipelineStage === 'price') {
                    await this._resumePipelineFromStage(savedId, pipelineStage);
                    return true;
                }

                // Default: intake stage polling
                this._showProcessing('Still analyzing your job...');
                await this._pollForIntakeResult(savedId);
                return true;
            }
            // Active — restore clarify step
            if (status.status === 'active' && status.next_questions && status.next_questions.length > 0) {
                this.sessionId = savedId;
                this._currentJobType = status.job_type || '';
                await this._handleIntakeResult(status);
                return true;
            }
            // Active but no questions (calculate stage) — let user continue pipeline
            if (status.status === 'active' && status.stage === 'calculate') {
                this.sessionId = savedId;
                this._currentJobType = status.job_type || '';
                this.extractedFields = status.extracted_fields || {};
                this._showStep('processing');
                this._showProcessing('Resuming your quote...');
                await this._runPipeline();
                return true;
            }
            // P71: Active in estimate/price stage — continue pipeline from that stage
            if (status.status === 'active' && (status.stage === 'estimate' || status.stage === 'price')) {
                this.sessionId = savedId;
                this._currentJobType = status.job_type || '';
                this._showStep('processing');
                // Stage tells us what to run NEXT (not what's currently running)
                await this._continuePipelineFromStage(savedId, status.stage);
                return true;
            }
            // P71: Complete session — show results directly
            if (status.status === 'complete' && status.stage === 'output' && status.quote_id) {
                this.sessionId = savedId;
                this._currentJobType = status.job_type || '';
                this.quoteId = status.quote_id;
                this.pricedQuote = status.priced_quote;
                try { localStorage.setItem('cq_last_quote_id', String(status.quote_id)); } catch (e) {}
                try { localStorage.removeItem('cq_active_session_id'); } catch (e) {}
                this._renderResults({
                    quote_id: status.quote_id,
                    quote_number: status.quote_number,
                    priced_quote: status.priced_quote,
                });
                this._showStep('results');
                return true;
            }

            // Unknown state — clear
            localStorage.removeItem('cq_active_session_id');
            return false;
        } catch (e) {
            // Any error (404, 403, network) — clear silently
            localStorage.removeItem('cq_active_session_id');
            return false;
        }
    },

    async _tryRestoreLastQuote() {
        if (this.quoteId) return; // Already have an active quote
        try {
            const savedId = localStorage.getItem('cq_last_quote_id');
            if (!savedId) return;
            const resp = await fetch(`/api/quotes/${savedId}/detail`, {
                headers: API.headers(),
            });
            if (!resp.ok) { localStorage.removeItem('cq_last_quote_id'); return; }
            const data = await resp.json();
            const outputs = data.outputs || data.outputs_json;
            if (data && outputs) {
                this.quoteId = parseInt(savedId);
                this.pricedQuote = outputs;
                this._renderResults({
                    quote_id: this.quoteId,
                    quote_number: data.quote_number || '',
                    priced_quote: outputs,
                });
                this._showStep('results');
            }
        } catch (e) {
            // Non-critical — just show fresh describe step
        }
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
            this._currentJobType = data.job_type || jobType || '';
            try { localStorage.setItem('cq_active_session_id', data.session_id); } catch (e) {}

            // Async intake: backend returns immediately, AI runs in background
            if (data.status === 'processing') {
                await this._pollForIntakeResult(data.session_id);
                return;
            }

            // Legacy sync path (fallback)
            await this._handleIntakeResult(data);
        } catch (e) {
            this._showError(e.message);
        }
    },

    async _pollForIntakeResult(sessionId) {
        const MAX_POLLS = 60;  // 2s interval x 60 = 2 minutes max
        for (let i = 0; i < MAX_POLLS; i++) {
            await new Promise(r => setTimeout(r, 2000));
            try {
                const status = await API.getSessionStatus(sessionId);
                if (status.status === 'processing') continue;
                if (status.status === 'error') {
                    this._showError('AI analysis failed. Please try again.');
                    return;
                }
                // status is "active" — intake complete
                await this._handleIntakeResult(status);
                return;
            } catch (e) {
                console.error('Poll error:', e);
            }
        }
        this._showError('Analysis timed out. Please try again.');
    },

    async _handleIntakeResult(data) {
        this.extractedFields = data.extracted_fields || {};
        this.allQuestions = data.next_questions || [];

        if (data.next_questions && data.next_questions.length > 0) {
            this._renderClarifyStep(data);
            this._showStep('clarify');
        } else if (data.completion && data.completion.is_complete) {
            await this._runPipeline();
        } else {
            this._showProcessing('No questions available for this job type yet.');
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

        // Disable Edit buttons while questions are being answered
        const hasActiveQuestions = allQuestions.length > 0;

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
                <button class="confirmed-edit" onclick="QuoteFlow.editExtractedField('${fieldId}')" ${hasActiveQuestions ? 'disabled' : ''}>Edit</button>
            `;
            el.appendChild(fieldDiv);
        }
    },

    editExtractedField(fieldId) {
        try {
            const oldValue = this.extractedFields[fieldId];
            delete this.extractedFields[fieldId];

            // Find the question definition from previously seen questions
            let question = this.allQuestions.find(q => q.id === fieldId);
            if (!question) {
                // Construct a generic text question for this field
                const label = fieldId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                question = {
                    id: fieldId,
                    text: label + '?',
                    type: 'text',
                    required: true,
                    hint: oldValue ? 'Previously: ' + oldValue : null,
                };
            }

            // Re-render clarify step with this field shown as an editable question
            const nKnown = Object.keys(this.extractedFields).length;
            this._renderClarifyStep({
                job_type: this._currentJobType || '',
                completion: {
                    completion_pct: Math.round(nKnown / (nKnown + 1) * 100),
                    required_answered: nKnown,
                    required_total: nKnown + 1,
                },
                extracted_fields: this.extractedFields,
                photo_extracted_fields: {},
                next_questions: [question],
            });
            this._showStep('clarify');
        } catch (err) {
            console.error('editExtractedField error:', err);
            alert('Error editing field — check console');
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
                        <button class="choice-btn choice-btn-other" onclick="QuoteFlow.selectOther(this, '${q.id}')" data-value="__other__">
                            Other
                        </button>
                    </div>
                    <div class="other-input-wrap" id="other-wrap-${q.id}" style="display:none">
                        <input type="text" class="text-input other-text-input" id="other-${q.id}" placeholder="Type your answer...">
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
                <div class="question-card" data-qid="${q.id}" data-required="${q.required ? 'true' : 'false'}">
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
        // Hide "Other" text input when a regular option is selected
        const wrap = document.getElementById('other-wrap-' + qid);
        if (wrap) wrap.style.display = 'none';
    },

    selectOther(btn, qid) {
        const group = btn.closest('.choice-group');
        group.querySelectorAll('.choice-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        // Show the "Other" text input and focus it
        const wrap = document.getElementById('other-wrap-' + qid);
        if (wrap) {
            wrap.style.display = 'block';
            const input = wrap.querySelector('input');
            if (input) input.focus();
        }
    },

    _collectAnswers() {
        const answers = {};
        const container = document.getElementById('questions-container');
        if (!container) return answers;

        // Choice groups
        container.querySelectorAll('.choice-group').forEach(group => {
            const qid = group.dataset.qid;
            const selected = group.querySelector('.choice-btn.selected');
            if (selected) {
                if (selected.dataset.value === '__other__') {
                    const otherInput = document.getElementById('other-' + qid);
                    if (otherInput && otherInput.value.trim()) {
                        answers[qid] = otherInput.value.trim();
                    }
                } else {
                    answers[qid] = selected.dataset.value;
                }
            }
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

        // Validate required fields before submitting
        const container = document.getElementById('questions-container');
        const missing = [];
        if (container) {
            container.querySelectorAll('.question-card[data-required="true"]').forEach(card => {
                const qid = card.dataset.qid;
                card.classList.remove('missing-required');
                if (!answers[qid] || !answers[qid].trim()) {
                    missing.push(qid);
                    card.classList.add('missing-required');
                }
            });
        }
        if (missing.length > 0) {
            const first = container.querySelector('.missing-required');
            if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }

        const btn = document.getElementById('btn-submit-answers');
        btn.disabled = true;
        btn.textContent = 'Submitting...';

        try {
            const data = await API.submitAnswers(this.sessionId, answers);

            if (data.is_complete && (!data.next_questions || data.next_questions.length === 0)) {
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
            // Stage 3: Calculate materials
            this._showProcessing('Calculating materials...');
            const calcResult = await API.calculate(this.sessionId);

            // P71: If async, poll until calculate completes
            if (calcResult.status === 'processing') {
                await this._pollForStageComplete(this.sessionId, 'Calculating materials...');
            }

            // Scope readiness check — backend may ask for more info
            if (calcResult.status === 'needs_more_info' && calcResult.additional_questions) {
                this._showStep('questions');
                this.allQuestions = calcResult.additional_questions;
                this._renderQuestions(calcResult.additional_questions);
                const container = document.getElementById('questions-container');
                if (container) {
                    container.insertAdjacentHTML('afterbegin',
                        '<div class="scope-notice" style="background:#fff3cd;padding:12px;'
                        + 'border-radius:8px;margin-bottom:16px;border:1px solid #ffc107">'
                        + '<strong>More details needed for an accurate quote.</strong></div>');
                }
                return;
            }

            // Stage 4: Estimate labor
            this._showProcessing('Estimating labor...');
            const estResult = await API.estimate(this.sessionId);

            // P71: If async, poll until estimate completes
            if (estResult.status === 'processing') {
                await this._pollForStageComplete(this.sessionId, 'Estimating labor...');
            }

            // Stage 5: Price quote
            this._showProcessing('Building quote...');
            const priceResult = await API.price(this.sessionId);

            let result;
            // P71: If async, poll until price completes — status endpoint returns quote data
            if (priceResult.status === 'processing') {
                const finalStatus = await this._pollForStageComplete(this.sessionId, 'Building quote...');
                result = {
                    quote_id: finalStatus.quote_id,
                    quote_number: finalStatus.quote_number,
                    priced_quote: finalStatus.priced_quote,
                };
            } else {
                result = priceResult;
            }

            this.quoteId = result.quote_id;
            this.pricedQuote = result.priced_quote;
            // Persist quote ID so user can return after navigating away
            try { localStorage.setItem('cq_last_quote_id', String(result.quote_id)); } catch (e) {}
            try { localStorage.removeItem('cq_active_session_id'); } catch (e) {}
            this._renderResults(result);
            this._showStep('results');
            // Track quote completion in Plausible
            if (window.plausible) plausible('quote_completed');
        } catch (e) {
            this._showError(e.message);
        }
    },

    /**
     * P71: Poll GET /session/{id}/status until status is no longer "processing".
     * Returns the final status response. Throws on error or timeout.
     */
    async _pollForStageComplete(sessionId, progressMsg) {
        const TIMEOUT_MS = 5 * 60 * 1000;  // 5 minutes wall-clock time
        const startTime = Date.now();
        while (Date.now() - startTime < TIMEOUT_MS) {
            await new Promise(r => setTimeout(r, 2000));
            try {
                const status = await API.getSessionStatus(sessionId);
                if (status.status === 'processing') {
                    const elapsed = Math.round((Date.now() - startTime) / 1000);
                    let msg = progressMsg || 'Processing...';
                    if (status.pipeline_stage === 'estimate') {
                        msg = 'Estimating labor...';
                    } else if (status.pipeline_stage === 'price') {
                        msg = 'Building quote...';
                    }
                    if (elapsed > 30) {
                        msg += ` (${elapsed}s)`;
                    }
                    this._showProcessing(msg);
                    continue;
                }
                if (status.status === 'error') {
                    throw new Error(status.stage_error || 'Quote processing failed. Please try again.');
                }
                // Done — status is "active" or "complete"
                return status;
            } catch (e) {
                if (e.message && !e.message.includes('fetch')) throw e;
                console.error('Poll error:', e);
            }
        }
        throw new Error('Quote processing timed out after 5 minutes. Please try again.');
    },

    /**
     * P71: Resume pipeline from a given stage after page restore.
     * Polls current stage to completion, then runs remaining stages.
     */
    async _resumePipelineFromStage(sessionId, stage) {
        try {
            const stageLabels = {
                calculate: 'Calculating materials...',
                estimate: 'Estimating labor...',
                price: 'Building quote...',
            };

            // Poll current stage to completion
            this._showProcessing(stageLabels[stage] || 'Processing...');
            const status = await this._pollForStageComplete(sessionId, stageLabels[stage]);

            // If price stage just completed, we have the result
            if (stage === 'price' && status.quote_id) {
                this.quoteId = status.quote_id;
                this.pricedQuote = status.priced_quote;
                try { localStorage.setItem('cq_last_quote_id', String(status.quote_id)); } catch (e) {}
                try { localStorage.removeItem('cq_active_session_id'); } catch (e) {}
                this._renderResults({
                    quote_id: status.quote_id,
                    quote_number: status.quote_number,
                    priced_quote: status.priced_quote,
                });
                this._showStep('results');
                return;
            }

            // Continue pipeline from the next stage
            if (stage === 'calculate') {
                // Estimate next
                this._showProcessing('Estimating labor...');
                const estResult = await API.estimate(sessionId);
                if (estResult.status === 'processing') {
                    await this._pollForStageComplete(sessionId, 'Estimating labor...');
                }
                // Then price
                this._showProcessing('Building quote...');
                const priceResult = await API.price(sessionId);
                let result;
                if (priceResult.status === 'processing') {
                    const finalStatus = await this._pollForStageComplete(sessionId, 'Building quote...');
                    result = {
                        quote_id: finalStatus.quote_id,
                        quote_number: finalStatus.quote_number,
                        priced_quote: finalStatus.priced_quote,
                    };
                } else {
                    result = priceResult;
                }
                this.quoteId = result.quote_id;
                this.pricedQuote = result.priced_quote;
                try { localStorage.setItem('cq_last_quote_id', String(result.quote_id)); } catch (e) {}
                try { localStorage.removeItem('cq_active_session_id'); } catch (e) {}
                this._renderResults(result);
                this._showStep('results');
            } else if (stage === 'estimate') {
                // Price next
                this._showProcessing('Building quote...');
                const priceResult = await API.price(sessionId);
                let result;
                if (priceResult.status === 'processing') {
                    const finalStatus = await this._pollForStageComplete(sessionId, 'Building quote...');
                    result = {
                        quote_id: finalStatus.quote_id,
                        quote_number: finalStatus.quote_number,
                        priced_quote: finalStatus.priced_quote,
                    };
                } else {
                    result = priceResult;
                }
                this.quoteId = result.quote_id;
                this.pricedQuote = result.priced_quote;
                try { localStorage.setItem('cq_last_quote_id', String(result.quote_id)); } catch (e) {}
                try { localStorage.removeItem('cq_active_session_id'); } catch (e) {}
                this._renderResults(result);
                this._showStep('results');
            }
            if (window.plausible) plausible('quote_completed');
        } catch (e) {
            this._showError(e.message);
        }
    },

    /**
     * P71: Continue pipeline from a given stage (session is active, stage is ready).
     * Unlike _resumePipelineFromStage, this calls the API endpoints directly.
     */
    async _continuePipelineFromStage(sessionId, stage) {
        try {
            if (stage === 'estimate') {
                // Run estimate, then price
                this._showProcessing('Estimating labor...');
                const estResult = await API.estimate(sessionId);
                if (estResult.status === 'processing') {
                    await this._pollForStageComplete(sessionId, 'Estimating labor...');
                }
                this._showProcessing('Building quote...');
                const priceResult = await API.price(sessionId);
                let result;
                if (priceResult.status === 'processing') {
                    const finalStatus = await this._pollForStageComplete(sessionId, 'Building quote...');
                    result = {
                        quote_id: finalStatus.quote_id,
                        quote_number: finalStatus.quote_number,
                        priced_quote: finalStatus.priced_quote,
                    };
                } else {
                    result = priceResult;
                }
                this.quoteId = result.quote_id;
                this.pricedQuote = result.priced_quote;
                try { localStorage.setItem('cq_last_quote_id', String(result.quote_id)); } catch (e) {}
                try { localStorage.removeItem('cq_active_session_id'); } catch (e) {}
                this._renderResults(result);
                this._showStep('results');
            } else if (stage === 'price') {
                // Run price only
                this._showProcessing('Building quote...');
                const priceResult = await API.price(sessionId);
                let result;
                if (priceResult.status === 'processing') {
                    const finalStatus = await this._pollForStageComplete(sessionId, 'Building quote...');
                    result = {
                        quote_id: finalStatus.quote_id,
                        quote_number: finalStatus.quote_number,
                        priced_quote: finalStatus.priced_quote,
                    };
                } else {
                    result = priceResult;
                }
                this.quoteId = result.quote_id;
                this.pricedQuote = result.priced_quote;
                try { localStorage.setItem('cq_last_quote_id', String(result.quote_id)); } catch (e) {}
                try { localStorage.removeItem('cq_active_session_id'); } catch (e) {}
                this._renderResults(result);
                this._showStep('results');
            }
            if (window.plausible) plausible('quote_completed');
        } catch (e) {
            this._showError(e.message);
        }
    },

    _isPreviewMode() {
        const user = Auth.currentUser;
        if (!user) return true;
        const tier = user.tier || 'free';
        const status = user.subscription_status || 'free';
        // Free/trial users without active subscription see preview
        if (tier === 'free' && status !== 'active') return true;
        if (status === 'trial' && tier === 'free') return true;
        return false;
    },

    _renderResults(result) {
        const el = document.getElementById('quote-step-results');
        const pq = result.priced_quote;
        const qn = result.quote_number || '';
        const isPreview = this._isPreviewMode();

        el.innerHTML = `
            <div class="results-card ${isPreview ? 'preview-mode' : ''}">
                <div class="results-header">
                    <div>
                        <h2>Quote #${qn}</h2>
                        <p class="results-meta">${JOB_TYPES[pq.job_type] || pq.job_type} &middot; ${new Date(pq.created_at).toLocaleDateString()}</p>
                    </div>
                    <div class="results-actions-top">
                        ${isPreview ? `
                        <button class="btn btn-secondary btn-sm btn-locked" onclick="QuoteFlow._previewGate()">Shop PDF</button>
                        <button class="btn btn-secondary btn-sm" onclick="QuoteFlow.downloadPdf('client')">Client PDF</button>
                        <button class="btn btn-secondary btn-sm btn-locked" onclick="QuoteFlow._previewGate()">Materials PDF</button>
                        <button class="btn btn-ghost btn-sm btn-locked" onclick="QuoteFlow._previewGate()">CSV</button>
                        ` : `
                        <button class="btn btn-secondary btn-sm" onclick="QuoteFlow.downloadPdf()">Shop PDF</button>
                        <button class="btn btn-secondary btn-sm" onclick="QuoteFlow.downloadPdf('client')">Client PDF</button>
                        <button class="btn btn-secondary btn-sm" onclick="QuoteFlow.downloadPdf('materials')">Materials PDF</button>
                        <button class="btn btn-ghost btn-sm" onclick="QuoteFlow.downloadCsv()">Materials CSV</button>
                        `}
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

                <div class="${isPreview ? 'preview-limit-4 preview-blur-prices' : ''}">
                ${this._renderSection('Materials', this._renderMaterialsTable(pq))}
                </div>
                <div class="${isPreview ? 'preview-limit-4' : ''}">
                ${this._renderSection('Hardware & Parts', this._renderHardwareTable(pq, isPreview))}
                </div>
                ${pq.consumables && pq.consumables.length ? `
                <div class="${isPreview ? 'preview-limit-2 preview-blur-prices' : ''}">
                ${this._renderSection('Consumables', this._renderConsumablesTable(pq))}
                </div>` : ''}

                ${isPreview ? this._renderPreviewCTA() : ''}

                <div class="${isPreview ? 'preview-limit-4' : ''}">
                ${pq.detailed_cut_list && pq.detailed_cut_list.length ? this._renderSection('Cut List', this._renderCutListTable(pq)) : ''}
                </div>
                <div class="${isPreview ? 'preview-limit-4' : ''}">
                ${pq.build_instructions && pq.build_instructions.length
                    ? this._renderSection('Build Sequence', this._renderBuildInstructions(pq))
                    : this._renderBuildInstructionsRetry(pq)}
                </div>

                <div class="${isPreview ? 'preview-limit-4 preview-blur-prices' : ''}">
                ${this._renderSection('Labor', this._renderLaborTable(pq))}
                </div>
                <div class="${isPreview ? 'preview-limit-2' : ''}">
                ${this._renderSection('Finishing', this._renderFinishing(pq))}
                </div>

                <div class="totals-section">
                    ${isPreview ? '' : `
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
                    `}

                    <div class="totals-grid">
                        <div class="total-row"><span>Materials</span><span id="material-subtotal-amount">${isPreview ? '<span class="preview-price">$---</span>' : this._fmt(pq.material_subtotal)}</span></div>
                        <div class="total-row"><span>Hardware</span><span id="hardware-subtotal-amount">${isPreview ? '<span class="preview-price">$---</span>' : this._fmt(pq.hardware_subtotal)}</span></div>
                        <div class="total-row"><span>Consumables</span><span id="consumable-subtotal-amount">${isPreview ? '<span class="preview-price">$---</span>' : this._fmt(pq.consumable_subtotal)}</span></div>
                        ${(pq.shop_stock_subtotal || 0) > 0 ? `<div class="total-row"><span>Shop Stock</span><span id="shop-stock-subtotal-amount">${isPreview ? '<span class="preview-price">$---</span>' : this._fmt(pq.shop_stock_subtotal)}</span></div>` : ''}
                        <div class="total-row"><span>Labor</span><span id="labor-subtotal-amount">${isPreview ? '<span class="preview-price">$---</span>' : this._fmt(pq.labor_subtotal)}</span></div>
                        <div class="total-row"><span>Finishing</span><span id="finishing-subtotal-amount">${isPreview ? '<span class="preview-price">$---</span>' : this._fmt(pq.finishing_subtotal)}</span></div>
                        <div class="total-row subtotal"><span>Subtotal</span><span id="subtotal-amount">${isPreview ? '<span class="preview-price">$---</span>' : this._fmt(pq.subtotal)}</span></div>
                    </div>

                    ${isPreview ? '' : `
                    <div class="markup-section">
                        <label class="markup-label">Markup:</label>
                        <div class="markup-buttons">
                            ${[0, 5, 10, 15, 20, 25, 30].map(pct => `
                                <button class="markup-btn ${pct === pq.selected_markup_pct ? 'active' : ''}"
                                    onclick="QuoteFlow.changeMarkup(${pct}, this)">${pct}%</button>
                            `).join('')}
                        </div>
                    </div>
                    `}

                    <div class="grand-total${isPreview ? ' preview-total-locked' : ''}">
                        ${isPreview ? `
                        <span>ESTIMATED RANGE</span>
                        <span class="ballpark-range" id="grand-total-amount">${this._fmtRange(pq.total)}</span>
                        <span class="ballpark-subtext">Upgrade to <a href="#" onclick="Auth.showUpgradeOptions();return false;">CreateQuote Starter</a> for your exact quote</span>
                        ` : `
                        <span>ESTIMATED RANGE</span>
                        <span id="grand-total-amount">${this._fmt(pq.total)}</span>
                        `}
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
                    ${isPreview ? `
                    <button class="btn btn-primary btn-locked" onclick="QuoteFlow._previewGate()">Shop PDF</button>
                    <button class="btn btn-secondary" onclick="QuoteFlow.downloadPdf('client')">Client PDF</button>
                    <button class="btn btn-secondary btn-locked" onclick="QuoteFlow._previewGate()">Materials PDF</button>
                    <button class="btn btn-ghost btn-locked" onclick="QuoteFlow._previewGate()">CSV</button>
                    ` : `
                    <button class="btn btn-primary" onclick="QuoteFlow.downloadPdf()">Shop PDF</button>
                    <button class="btn btn-secondary" onclick="QuoteFlow.downloadPdf('client')">Client PDF</button>
                    <button class="btn btn-secondary" onclick="QuoteFlow.downloadPdf('materials')">Materials PDF</button>
                    <button class="btn btn-ghost" onclick="QuoteFlow.downloadCsv()">Materials CSV</button>
                    `}
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
                        <th>Material</th><th>Qty</th><th>Stock Size</th>
                        <th>Remainder</th><th>Weight</th><th class="r">Cost</th>
                    </tr></thead>
                    <tbody>
                        ${steelRows.map((s, idx) => {
                            const profile = (s.profile || '').replace(/_/g, ' ');
                            const isArea = s.is_area_sold;
                            const isSheet = (s.profile || '').includes('sheet') || (s.profile || '').includes('plate');
                            let qtyCol, stockCol;
                            if (isArea && isSheet && s.sheet_size) {
                                const sw = s.sheet_size[0] / 12, sh = s.sheet_size[1] / 12;
                                const sheets = s.sheets_needed || s.sticks_needed || 0;
                                qtyCol = `<input type="number" class="inline-edit inline-edit-sm" step="1" min="1" value="${sheets}" data-mat-idx="${idx}" onchange="QuoteFlow.adjustSheetQty(${idx}, parseInt(this.value))">`;
                                stockCol = sw + "'x" + sh + "' sheet" + (s.seaming_required ? ' SEAM' : '');
                            } else if (isArea) {
                                qtyCol = s.sticks_needed || '-';
                                stockCol = '-';
                            } else {
                                const sticks = s.sticks_needed || 0;
                                const stockLen = s.stock_length_ft || 20;
                                qtyCol = `<input type="number" class="inline-edit inline-edit-sm" step="1" min="1" value="${sticks}" data-mat-idx="${idx}" onchange="QuoteFlow.adjustMaterialQty(${idx}, parseInt(this.value))">`;
                                stockCol = stockLen + " ft";
                            }
                            let remainCol;
                            if (isArea && s.remainder_sqft > 0) {
                                remainCol = s.remainder_sqft.toFixed(1) + ' sqft';
                            } else if (!isArea && s.remainder_ft > 0) {
                                remainCol = s.remainder_ft.toFixed(1) + "'";
                            } else {
                                remainCol = '-';
                            }
                            const weightCol = s.weight_lbs > 0 ? (Math.round(s.weight_lbs) + ' lbs') : '-';
                            return `<tr>
                                <td>${profile}</td>
                                <td>${qtyCol}</td>
                                <td>${stockCol}</td>
                                <td>${remainCol}</td>
                                <td>${weightCol}</td>
                                <td class="r">${this._fmt(s.total_cost)}</td>
                            </tr>`;
                        }).join('')}
                        ${concreteRows.map(s => `<tr>
                            <td>${s.description || 'Concrete'}</td>
                            <td>${s.sticks_needed || 0}</td>
                            <td>80lb bags</td>
                            <td>-</td>
                            <td>${Math.round(s.weight_lbs)} lbs</td>
                            <td class="r">${this._fmt(s.total_cost)}</td>
                        </tr>`).join('')}
                        <tr style="font-style:italic;border-top:1px solid #ddd">
                            <td colspan="4" style="text-align:right">Total Weight</td>
                            <td>${Math.round(summary.reduce((sum, s) => sum + (s.weight_lbs || 0), 0) + concreteRows.reduce((sum, s) => sum + (s.weight_lbs || 0), 0))} lbs</td>
                            <td></td>
                        </tr>
                        <tr class="subtotal-row">
                            <td colspan="5">Material Subtotal</td>
                            <td class="r" id="mat-table-subtotal"><strong>${this._fmt(pq.material_subtotal)}</strong></td>
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
                        <td class="r" id="mat-table-subtotal"><strong>${this._fmt(pq.material_subtotal)}</strong></td>
                    </tr>
                </tbody>
            </table>
        `;
    },

    _renderHardwareTable(pq, isPreview) {
        const items = pq.hardware || [];
        if (!items.length) return '<p class="empty-section">No hardware</p>';

        // P72: Free tier — show 4 items max, no dollar values, upgrade prompt
        if (isPreview) {
            const visible = items.slice(0, 4);
            const remaining = items.length - visible.length;
            return `
                <table class="data-table">
                    <thead><tr><th>Item</th><th>Qty</th></tr></thead>
                    <tbody>
                        ${visible.map(h => `
                            <tr>
                                <td>${h.description || ''}</td>
                                <td>${h.quantity || 1}</td>
                            </tr>
                        `).join('')}
                        ${remaining > 0 ? `
                        <tr class="preview-upgrade-row">
                            <td colspan="2" style="text-align:center;padding:12px;color:var(--text-secondary);font-style:italic;">
                                + ${remaining} more item${remaining > 1 ? 's' : ''} &mdash;
                                <a href="#" onclick="Auth.showUpgradeOptions();return false;" style="color:var(--accent,#f97316);font-weight:600;">Upgrade to see full parts list</a>
                            </td>
                        </tr>` : ''}
                    </tbody>
                </table>
            `;
        }

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
                        <td class="r" id="hw-table-subtotal"><strong>${this._fmt(pq.hardware_subtotal)}</strong></td>
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
                        <td class="r" id="con-table-subtotal"><strong>${this._fmt(pq.consumable_subtotal)}</strong></td>
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
                    <tr style="font-style:italic;border-top:1px solid #ddd">
                        <td>Total Hours</td>
                        <td class="r" id="labor-total-hours">${procs.reduce((sum, p) => sum + p.hours, 0).toFixed(1)}</td>
                        <td colspan="2"></td>
                    </tr>
                    <tr class="subtotal-row">
                        <td colspan="3">Labor Subtotal</td>
                        <td class="r" id="labor-table-subtotal"><strong>${this._fmt(pq.labor_subtotal)}</strong></td>
                    </tr>
                </tbody>
            </table>
        `;
    },

    _detectMaterialLabel(pq) {
        const materials = pq.materials || [];
        const total = materials.length || 1;
        const alCount = materials.filter(m => (m.profile || '').startsWith('al_')).length;
        if (alCount > total * 0.3) return 'Aluminum';
        const ssCount = materials.filter(m => (m.material_type || '').toLowerCase().includes('stainless')).length;
        if (ssCount > total * 0.3) return 'Stainless Steel';
        return '';
    },

    _renderFinishing(pq) {
        const f = pq.finishing || {};
        const matLabel = this._detectMaterialLabel(pq) || 'Steel';
        const FINISH_DISPLAY = {
            clearcoat: 'Clear Coat', clear_coat: 'Clear Coat',
            powder_coat: 'Powder Coat', paint: 'Paint',
            galvanized: 'Galvanized', anodized: 'Anodized',
            ceramic_coat: 'Ceramic Coat', patina: 'Patina / Blackened',
            brushed: 'Brushed / Polished', raw: 'Raw ' + matLabel,
        };
        const methodRaw = f.method || 'raw';
        const method = FINISH_DISPLAY[methodRaw] || methodRaw.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        if (methodRaw === 'raw') {
            return `<p>Method: <strong>Raw ${matLabel}</strong> — no finish applied.</p>`;
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

    adjustMaterialQty(idx, newSticks) {
        if (!this.pricedQuote || isNaN(newSticks) || newSticks < 1) return;
        const pq = this.pricedQuote;
        const summary = pq.materials_summary || [];
        const steelRows = summary.filter(s => !s.is_concrete);
        const item = steelRows[idx];
        if (!item || item.is_area_sold) return;

        // Update sticks count and recalculate cost
        const oldSticks = item.sticks_needed || 1;
        item.sticks_needed = newSticks;
        const ratio = newSticks / oldSticks;
        item.total_cost = Math.round((item.total_cost || 0) * ratio * 100) / 100;
        item.remainder_ft = Math.round((newSticks * (item.stock_length_ft || 20) - (item.total_length_ft || 0)) * 10) / 10;

        // Recalculate material subtotal
        pq.material_subtotal = Math.round(
            summary.reduce((s, m) => s + (m.total_cost || 0), 0) * 100
        ) / 100;

        this._recalcTotals();
        this._debouncedAdjust('material', { [idx]: newSticks });
    },

    adjustSheetQty(idx, newSheets) {
        if (!this.pricedQuote || isNaN(newSheets) || newSheets < 1) return;
        const pq = this.pricedQuote;
        const summary = pq.materials_summary || [];
        const steelRows = summary.filter(s => !s.is_concrete);
        const item = steelRows[idx];
        if (!item) return;

        const oldSheets = item.sheets_needed || item.sticks_needed || 1;
        item.sheets_needed = newSheets;
        const ratio = newSheets / oldSheets;
        item.total_cost = Math.round((item.total_cost || 0) * ratio * 100) / 100;

        // Recalculate material subtotal
        pq.material_subtotal = Math.round(
            summary.reduce((s, m) => s + (m.total_cost || 0), 0) * 100
        ) / 100;

        this._recalcTotals();
        this._debouncedAdjust('material', { [idx]: newSheets });
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
            (pq.shop_stock_subtotal || 0) +
            pq.labor_subtotal +
            (pq.finishing_subtotal || 0)
        ) * 100) / 100;

        const markupPct = pq.selected_markup_pct || 0;
        pq.total = Math.round(pq.subtotal * (1 + markupPct / 100) * 100) / 100;

        // Update totals grid in sidebar
        const matEl = document.getElementById('material-subtotal-amount');
        const hwEl = document.getElementById('hardware-subtotal-amount');
        const conEl = document.getElementById('consumable-subtotal-amount');
        const ssEl = document.getElementById('shop-stock-subtotal-amount');
        const laborEl = document.getElementById('labor-subtotal-amount');
        const finEl = document.getElementById('finishing-subtotal-amount');
        const subEl = document.getElementById('subtotal-amount');
        const totalEl = document.getElementById('grand-total-amount');
        if (matEl) matEl.textContent = this._fmt(pq.material_subtotal);
        if (hwEl) hwEl.textContent = this._fmt(pq.hardware_subtotal);
        if (conEl) conEl.textContent = this._fmt(pq.consumable_subtotal);
        if (ssEl) ssEl.textContent = this._fmt(pq.shop_stock_subtotal);
        if (laborEl) laborEl.textContent = this._fmt(pq.labor_subtotal);
        if (finEl) finEl.textContent = this._fmt(pq.finishing_subtotal);
        if (subEl) subEl.textContent = this._fmt(pq.subtotal);
        if (totalEl) totalEl.textContent = this._fmt(pq.total);

        // Update in-table subtotal cells
        const matTbl = document.getElementById('mat-table-subtotal');
        const hwTbl = document.getElementById('hw-table-subtotal');
        const conTbl = document.getElementById('con-table-subtotal');
        const laborTbl = document.getElementById('labor-table-subtotal');
        if (matTbl) matTbl.innerHTML = '<strong>' + this._fmt(pq.material_subtotal) + '</strong>';
        if (hwTbl) hwTbl.innerHTML = '<strong>' + this._fmt(pq.hardware_subtotal) + '</strong>';
        if (conTbl) conTbl.innerHTML = '<strong>' + this._fmt(pq.consumable_subtotal) + '</strong>';
        if (laborTbl) laborTbl.innerHTML = '<strong>' + this._fmt(pq.labor_subtotal) + '</strong>';
        const hoursEl = document.getElementById('labor-total-hours');
        if (hoursEl) {
            const totalHrs = (pq.labor || []).filter(p => p.hours > 0).reduce((s, p) => s + p.hours, 0);
            hoursEl.textContent = totalHrs.toFixed(1);
        }
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

    async downloadPdf(mode) {
        if (this._isPreviewMode() && mode !== 'client') { this._previewGate(); return; }
        if (!this.quoteId) {
            alert('No quote ID — please run the quote pipeline first.');
            return;
        }
        // Refresh access token before opening — window.open can't auto-refresh
        if (API._refreshToken) {
            await API._tryRefresh();
        }
        if (!API._accessToken) {
            alert('Session expired — please log in again.');
            return;
        }
        // Open PDF in new tab with auth token as query param
        const url = API.getPdfUrl(this.quoteId, mode || null);
        const win = window.open(url, '_blank');
        if (!win) {
            window.location.href = url;
        }
    },

    async downloadCsv() {
        if (this._isPreviewMode()) { this._previewGate(); return; }
        if (!this.quoteId) {
            alert('No quote ID — please run the quote pipeline first.');
            return;
        }
        if (API._refreshToken) {
            await API._tryRefresh();
        }
        if (!API._accessToken) {
            alert('Session expired — please log in again.');
            return;
        }
        const url = API.getPdfUrl(this.quoteId, 'materials-csv');
        const win = window.open(url, '_blank');
        if (!win) window.location.href = url;
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
        this._currentJobType = '';
        this.currentStep = 'describe';
        try { localStorage.removeItem('cq_last_quote_id'); } catch (e) {}
        try { localStorage.removeItem('cq_active_session_id'); } catch (e) {}
        this.renderQuoteView();
    },

    // --- Helpers ---
    _showStep(step) {
        this.currentStep = step;
        // Stop loading message rotation when leaving processing
        if (step !== 'processing' && this._loadingInterval) {
            clearInterval(this._loadingInterval);
            this._loadingInterval = null;
        }
        ['describe', 'clarify', 'processing', 'results'].forEach(s => {
            const el = document.getElementById(`quote-step-${s}`);
            if (el) el.style.display = s === step ? 'block' : 'none';
        });
    },

    _loadingInterval: null,

    LOADING_MESSAGES: [
        "Measuring twice, cutting once...",
        "Calculating weld inches...",
        "Checking stock lengths...",
        "Optimizing your cut list...",
        "Arguing with the tape measure...",
        "Squaring up the layout table...",
        "Sharpening the soapstone...",
        "If Lincoln could see us now...",
        "Checking if it'll fit through the shop door...",
        "Flipping through the metals catalog...",
        "Doing math so you don't have to...",
        "Converting fractions to decimals (the hard part)...",
        "Double-checking the miter angles...",
        "Trying to remember where we put the level...",
        "Asking the foreman for a second opinion...",
        "Making coffee while the numbers crunch...",
        "Figuring out if it fits on a 20-footer...",
        "Reminding everyone to wear their safety glasses...",
        "Drawing it out on the shop floor with soapstone...",
        "Sorting the BOM by profile...",
        "Making sure nobody forgot the base plates...",
        "Adding hardware — yes, the bolts too...",
        "Accounting for kerf width...",
        "Rounding up to the next full stick...",
        "Cross-referencing supplier pricing...",
        "Building your fabrication sequence...",
        "Wondering who left the grinder plugged in...",
        "Checking if the quote is heavy enough to weld...",
        "Almost done — just checking the math one more time...",
        "Generating a quote that would make your accountant proud...",
    ],

    _showProcessing(msg) {
        // Clear any existing rotation interval
        if (this._loadingInterval) {
            clearInterval(this._loadingInterval);
            this._loadingInterval = null;
        }

        const el = document.getElementById('quote-step-processing');
        el.innerHTML = `
            <div class="processing-card">
                <div class="spinner"></div>
                <p class="processing-text" id="processing-msg">${msg}</p>
                <p class="processing-flavor" id="processing-flavor"></p>
                <p class="processing-stay">Please don't leave this page while your quote is being built.</p>
            </div>
        `;

        // Start rotating funny messages after a short delay
        const flavorEl = document.getElementById('processing-flavor');
        if (!flavorEl) return;

        const msgs = this.LOADING_MESSAGES;
        let idx = Math.floor(Math.random() * msgs.length);

        const showNext = () => {
            flavorEl.classList.remove('flavor-visible');
            setTimeout(() => {
                idx = (idx + 1) % msgs.length;
                flavorEl.textContent = msgs[idx];
                flavorEl.classList.add('flavor-visible');
            }, 400);
        };

        // Show first message after 2 seconds
        setTimeout(() => {
            flavorEl.textContent = msgs[idx];
            flavorEl.classList.add('flavor-visible');
        }, 2000);

        // Rotate every 8 seconds
        this._loadingInterval = setInterval(showNext, 8000);
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

    _fmtRange(total) {
        // P72: Ballpark range — ×0.80 to ×1.25, rounded to nearest $50
        const t = parseFloat(total) || 0;
        const lo = Math.round(t * 0.80 / 50) * 50;
        const hi = Math.round(t * 1.25 / 50) * 50;
        return '$' + lo.toLocaleString() + ' \u2013 $' + hi.toLocaleString();
    },

    _previewGate() {
        Auth.showUpgradeOptions();
    },

    _renderPreviewCTA() {
        return `
            <div class="preview-upgrade-cta">
                <h3>Want the full quote?</h3>
                <p>Subscribe to unlock exact pricing, complete cut lists, build instructions, and professional PDF downloads.</p>
                <a href="#" class="btn btn-primary" onclick="Auth.showUpgradeOptions();return false;">Subscribe &mdash; Starting at $79/mo</a>
            </div>
        `;
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
                        <button class="btn btn-primary" onclick="QuoteFlow.newQuote(); App.showView('quote')">+ New Quote</button>
                    </div>
                `;
                return;
            }

            el.innerHTML = `
                <div class="history-card">
                    <div class="history-header">
                        <h2>Your Quotes</h2>
                        <button class="btn btn-primary btn-sm" onclick="QuoteFlow.newQuote(); App.showView('quote')">+ New Quote</button>
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
                QuoteFlow.currentStep = 'results'; // Prevent showView from re-rendering
                App.showView('quote');
                QuoteFlow._renderResults({
                    quote_id: quoteId,
                    quote_number: detail.quote_number,
                    priced_quote: detail.outputs,
                });
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
