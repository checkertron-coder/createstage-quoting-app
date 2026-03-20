/**
 * Shop Equipment Onboarding — conversational flow + profile settings section.
 *
 * Three-question conversational onboarding that runs after first login.
 * Also provides equipment profile display/edit in the Profile view.
 */

const ShopOnboarding = {
    currentStep: 0,
    answers: { welding: '', forming: '', finishing: '' },

    questions: [
        {
            key: 'welding',
            title: 'Welding & Cutting',
            question: 'What welding and cutting processes do you have in your shop?',
            hint: 'For example: MIG with flux core, TIG, stick, oxy-acetylene torch, hand plasma cutter, CNC plasma table, cold saw — or just tell us what you\'ve got.',
            placeholder: 'e.g. "MIG with flux core wire, hand plasma cutter, chop saw, angle grinder"',
        },
        {
            key: 'forming',
            title: 'Forming & Fabrication',
            question: 'What forming equipment do you work with?',
            hint: 'Press brake, tube bender, fixture table, slip roller — anything for shaping metal.',
            placeholder: 'e.g. "No press brake, I outsource bending. Got a welding table with clamps."',
        },
        {
            key: 'finishing',
            title: 'Finishing',
            question: 'How do you handle finishing?',
            hint: 'In-house spray paint, powder coat oven, media blaster — or do you send out for coating?',
            placeholder: 'e.g. "I spray paint in-house. Send out for powder coat."',
        },
    ],

    render() {
        const el = document.getElementById('view-onboarding');
        if (!el) return;

        this.currentStep = 0;
        this.answers = { welding: '', forming: '', finishing: '' };

        el.innerHTML = `
            <div class="onboarding-card">
                <h1 class="onboarding-title">Set Up Your Shop</h1>
                <p class="onboarding-subtitle">Tell us what equipment you have so quotes match your actual capabilities. This takes about 30 seconds.</p>

                <div id="onboarding-progress" class="onboarding-progress">
                    <div class="progress-step active" data-step="0">1</div>
                    <div class="progress-line"></div>
                    <div class="progress-step" data-step="1">2</div>
                    <div class="progress-line"></div>
                    <div class="progress-step" data-step="2">3</div>
                </div>

                <div id="onboarding-question" class="onboarding-question"></div>
                <div id="onboarding-summary" class="onboarding-summary" style="display:none"></div>
                <div id="onboarding-error" class="auth-error" style="display:none"></div>
            </div>
        `;

        this._renderQuestion();
    },

    _renderQuestion() {
        const q = this.questions[this.currentStep];
        const el = document.getElementById('onboarding-question');
        if (!el) return;

        // Update progress
        document.querySelectorAll('.progress-step').forEach((step, i) => {
            step.classList.toggle('active', i <= this.currentStep);
            step.classList.toggle('completed', i < this.currentStep);
        });

        el.innerHTML = `
            <h3>${q.title}</h3>
            <p class="onboarding-q-text">${q.question}</p>
            <p class="onboarding-hint">${q.hint}</p>
            <textarea id="onboarding-answer" class="onboarding-textarea"
                placeholder="${q.placeholder}"
                rows="3">${this.answers[q.key]}</textarea>
            <div class="onboarding-actions">
                ${this.currentStep > 0 ? '<button class="btn btn-ghost" onclick="ShopOnboarding.prev()">Back</button>' : '<button class="btn btn-ghost" onclick="ShopOnboarding.skip()">Skip for Now</button>'}
                <button class="btn btn-primary" onclick="ShopOnboarding.next()">${this.currentStep < 2 ? 'Next' : 'Review'}</button>
            </div>
        `;
    },

    next() {
        const answer = (document.getElementById('onboarding-answer')?.value || '').trim();
        const q = this.questions[this.currentStep];
        this.answers[q.key] = answer;

        if (this.currentStep < 2) {
            this.currentStep++;
            this._renderQuestion();
        } else {
            this._showSummary();
        }
    },

    prev() {
        // Save current answer
        const answer = (document.getElementById('onboarding-answer')?.value || '').trim();
        const q = this.questions[this.currentStep];
        this.answers[q.key] = answer;

        if (this.currentStep > 0) {
            this.currentStep--;
            this._renderQuestion();
        }
    },

    skip() {
        App.showView('quote');
    },

    _showSummary() {
        const qEl = document.getElementById('onboarding-question');
        const sEl = document.getElementById('onboarding-summary');
        if (qEl) qEl.style.display = 'none';
        if (sEl) sEl.style.display = 'block';

        // Update progress to show all complete
        document.querySelectorAll('.progress-step').forEach(step => {
            step.classList.add('active', 'completed');
        });

        sEl.innerHTML = `
            <h3>Review Your Shop Profile</h3>
            <div class="summary-section">
                <strong>Welding & Cutting:</strong>
                <p>${this.answers.welding || '<em>Not specified</em>'}</p>
            </div>
            <div class="summary-section">
                <strong>Forming & Fabrication:</strong>
                <p>${this.answers.forming || '<em>Not specified</em>'}</p>
            </div>
            <div class="summary-section">
                <strong>Finishing:</strong>
                <p>${this.answers.finishing || '<em>Not specified</em>'}</p>
            </div>
            <div class="onboarding-actions">
                <button class="btn btn-ghost" onclick="ShopOnboarding._editFromSummary()">Edit Answers</button>
                <button class="btn btn-primary" id="btn-save-profile" onclick="ShopOnboarding.save()">Save & Continue</button>
            </div>
        `;
    },

    _editFromSummary() {
        const qEl = document.getElementById('onboarding-question');
        const sEl = document.getElementById('onboarding-summary');
        if (qEl) qEl.style.display = 'block';
        if (sEl) sEl.style.display = 'none';
        this.currentStep = 0;
        this._renderQuestion();
    },

    async save() {
        const btn = document.getElementById('btn-save-profile');
        if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }

        try {
            const resp = await fetch('/api/shop/onboarding', {
                method: 'POST',
                headers: API.headers(),
                body: JSON.stringify({
                    welding_answer: this.answers.welding,
                    forming_answer: this.answers.forming,
                    finishing_answer: this.answers.finishing,
                }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || 'Failed to save profile');

            // Update user state
            if (Auth.currentUser) Auth.currentUser.onboarding_complete = true;

            App.showView('quote');
        } catch (e) {
            const errEl = document.getElementById('onboarding-error');
            if (errEl) { errEl.textContent = e.message; errEl.style.display = 'block'; }
            if (btn) { btn.disabled = false; btn.textContent = 'Save & Continue'; }
        }
    },

    // --- Profile settings section ---

    async renderEquipmentSection(container) {
        // Fetch current equipment profile
        let equipment = null;
        try {
            const resp = await fetch('/api/shop/equipment', { headers: API.headers() });
            if (resp.ok) equipment = await resp.json();
        } catch (e) { /* ignore */ }

        if (!equipment || !equipment.onboarding_complete) {
            container.innerHTML = `
                <div class="equipment-section">
                    <h3>Shop Equipment</h3>
                    <p class="text-secondary">You haven't set up your shop equipment profile yet.</p>
                    <button class="btn btn-secondary btn-sm" onclick="ShopOnboarding.render(); App.showView('onboarding')">Set Up Now</button>
                </div>
            `;
            return;
        }

        const w = (equipment.welding_processes || []).map(p => {
            let desc = p.process;
            if (p.wire_type) desc += ` (${p.wire_type})`;
            if (p.primary) desc += ' [primary]';
            return desc;
        }).join(', ') || 'None specified';

        const c = (equipment.cutting_capabilities || []).map(p => {
            let desc = p.tool;
            if (p.cnc) desc += ' (CNC)';
            return desc;
        }).join(', ') || 'None specified';

        const f = (equipment.forming_equipment || []).map(p => {
            let desc = p.tool;
            if (p.specs) desc += ` (${p.specs})`;
            return desc;
        }).join(', ') || 'None';

        const fin = (equipment.finishing_capabilities || []).map(p => {
            let desc = p.method;
            desc += p.in_house ? ' (in-house)' : ' (outsourced)';
            return desc;
        }).join(', ') || 'None specified';

        container.innerHTML = `
            <div class="equipment-section">
                <h3>Shop Equipment</h3>
                <div class="equipment-grid">
                    <div><strong>Welding & Cutting:</strong> ${w}</div>
                    <div><strong>Cutting:</strong> ${c}</div>
                    <div><strong>Forming:</strong> ${f}</div>
                    <div><strong>Finishing:</strong> ${fin}</div>
                </div>
                <button class="btn btn-secondary btn-sm" style="margin-top: 12px" onclick="ShopOnboarding.render(); App.showView('onboarding')">Update Equipment</button>
            </div>
        `;
    },
};
