/**
 * Auth UI — login, register, profile setup, demo mode.
 * P53: Registration with invite codes. P53B: Demo magic links, passwordless beta.
 */

const Auth = {
    currentUser: null,
    demoStatus: null, // { is_demo, quotes_remaining, max_quotes, demo_token }

    async init() {
        API.init();

        // Check for demo token in URL (e.g., /demo/abc123)
        const demoMatch = window.location.pathname.match(/^\/demo\/(.+)$/);
        if (demoMatch) {
            const redeemed = await this._redeemDemo(demoMatch[1]);
            if (redeemed) return true;
        }

        if (API.isAuthenticated()) {
            try {
                this.currentUser = await API.getMe();
                await this._checkDemoStatus();
                return true;
            } catch (e) {
                API.clearTokens();
                return false;
            }
        }
        return false;
    },

    async _redeemDemo(token) {
        try {
            const resp = await fetch(`/api/auth/redeem-demo?token=${encodeURIComponent(token)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!resp.ok) return false;
            const data = await resp.json();
            API.setTokens(data.access_token, data.refresh_token);
            this.currentUser = data.user;
            // Store demo token for upgrade flow
            localStorage.setItem('demo_token', token);
            await this._checkDemoStatus();
            // Replace URL to /app (clean up demo token from address bar)
            history.replaceState(null, '', '/app');
            return true;
        } catch (e) {
            return false;
        }
    },

    async _checkDemoStatus() {
        try {
            const resp = await fetch('/api/auth/demo-status', {
                headers: API.headers(),
            });
            if (resp.ok) {
                this.demoStatus = await resp.json();
            }
        } catch (e) {
            // Non-critical
        }
    },

    renderDemoBanner() {
        // Remove existing banner if any
        const existing = document.getElementById('demo-banner');
        if (existing) existing.remove();

        if (!this.demoStatus || !this.demoStatus.is_demo) return;

        const banner = document.createElement('div');
        banner.id = 'demo-banner';
        banner.className = 'demo-banner';

        const remaining = this.demoStatus.quotes_remaining;
        const max = this.demoStatus.max_quotes;

        if (remaining <= 0) {
            banner.innerHTML = `
                <span>Demo limit reached</span>
                <a href="/app#register" onclick="Auth.showRegisterFromDemo();return false;">Register for full access &rarr;</a>
            `;
            banner.classList.add('demo-banner-expired');
        } else {
            banner.innerHTML = `
                <span>Demo Mode &mdash; ${remaining} of ${max} quotes remaining</span>
                <a href="/app#register" onclick="Auth.showRegisterFromDemo();return false;">Register for full access &rarr;</a>
            `;
        }

        document.body.insertBefore(banner, document.body.firstChild);
    },

    renderUpgradeBanner() {
        // Remove existing upgrade banner
        const existing = document.getElementById('upgrade-banner');
        if (existing) existing.remove();

        if (!this.currentUser) return;
        // Don't show if demo (demo banner handles that)
        if (this.demoStatus && this.demoStatus.is_demo) return;

        const tier = this.currentUser.tier || 'free';
        const subStatus = this.currentUser.subscription_status || 'free';

        // Show banner for free/trial users (not paid subscribers or beta invite users)
        if (tier === 'free' && subStatus !== 'active') {
            const banner = document.createElement('div');
            banner.id = 'upgrade-banner';
            banner.className = 'upgrade-banner';
            banner.innerHTML = `
                <span>You're on the Free plan &mdash; 1 preview quote included.</span>
                <a href="/#pricing">Subscribe to unlock full quotes &rarr;</a>
            `;
            document.body.insertBefore(banner, document.body.firstChild);
        } else if (subStatus === 'past_due') {
            const banner = document.createElement('div');
            banner.id = 'upgrade-banner';
            banner.className = 'upgrade-banner upgrade-banner-warning';
            banner.innerHTML = `
                <span>Payment past due &mdash; update your billing to continue quoting.</span>
                <a href="#" onclick="Auth.openBillingPortal();return false;">Update Billing &rarr;</a>
            `;
            document.body.insertBefore(banner, document.body.firstChild);
        }
    },

    async startCheckout(tier) {
        try {
            const resp = await fetch('/api/stripe/create-checkout', {
                method: 'POST',
                headers: API.headers(),
                body: JSON.stringify({
                    tier: tier,
                    success_url: window.location.origin + '/app?checkout=success',
                    cancel_url: window.location.origin + '/app?checkout=cancelled',
                }),
            });
            const data = await resp.json();
            if (data.url) {
                window.location.href = data.url;
            } else {
                alert(data.detail || 'Unable to start checkout. Please try again.');
            }
        } catch (e) {
            alert('Unable to connect to billing. Please try again later.');
        }
    },

    async openBillingPortal() {
        try {
            const resp = await fetch('/api/stripe/portal', {
                headers: API.headers(),
            });
            const data = await resp.json();
            if (data.url) {
                window.location.href = data.url;
            } else {
                alert(data.detail || 'Unable to open billing portal. Please try again.');
            }
        } catch (e) {
            alert('Unable to connect to billing. Please try again later.');
        }
    },

    showRegisterFromDemo() {
        App.showView('auth');
        setTimeout(() => Auth.showTab('register'), 50);
    },

    renderAuthView() {
        const el = document.getElementById('view-auth');
        // Check URL hash for register mode
        const showRegister = window.location.hash === '#register';

        el.innerHTML = `
            <div class="auth-card">
                <h1 class="auth-title">CreateQuote</h1>
                <p class="auth-subtitle">AI-Powered Metal Fabrication Quoting</p>

                <div id="auth-form">
                    <div id="auth-error" class="auth-error" style="display:none"></div>

                    <!-- Tab switcher -->
                    <div class="auth-tabs">
                        <button class="auth-tab ${showRegister ? '' : 'active'}" id="tab-login" onclick="Auth.showTab('login')">Log In</button>
                        <button class="auth-tab ${showRegister ? 'active' : ''}" id="tab-register" onclick="Auth.showTab('register')">Register</button>
                    </div>

                    <!-- Login fields -->
                    <div id="login-fields" style="${showRegister ? 'display:none' : ''}">
                        <div class="auth-fields">
                            <input type="email" id="login-email" placeholder="Email" autocomplete="email">
                            <div class="password-wrapper">
                                <input type="password" id="login-password" placeholder="Password" autocomplete="current-password">
                                <button type="button" class="password-toggle" onclick="Auth.togglePassword('login-password', this)" aria-label="Show password">
                                    <svg class="eye-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                                    <svg class="eye-off-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                                </button>
                            </div>
                        </div>
                        <div id="unverified-notice" class="auth-notice" style="display:none">
                            <p>Your email hasn't been verified yet. Check your inbox for the verification link.</p>
                            <button class="btn btn-secondary btn-sm" onclick="Auth.resendVerification()">Resend Verification Email</button>
                        </div>
                        <div class="auth-buttons">
                            <button class="btn btn-primary btn-full" onclick="Auth.handleLogin()">Log In</button>
                        </div>
                        <p class="auth-hint">
                            <a href="#" onclick="Auth.showForgotPassword();return false;">Forgot password?</a>
                            &nbsp;&middot;&nbsp;
                            Don't have an account? <a href="#" onclick="Auth.showTab('register');return false;">Register here</a>
                        </p>
                    </div>

                    <!-- Forgot password -->
                    <div id="forgot-fields" style="display:none">
                        <div class="auth-fields">
                            <input type="email" id="forgot-email" placeholder="Email" autocomplete="email">
                        </div>
                        <div class="auth-buttons">
                            <button class="btn btn-primary btn-full" onclick="Auth.handleForgotPassword()">Send Reset Link</button>
                        </div>
                        <p class="auth-hint"><a href="#" onclick="Auth.showTab('login');return false;">&larr; Back to login</a></p>
                    </div>

                    <!-- Reset password (shown when ?action=reset-password) -->
                    <div id="reset-fields" style="display:none">
                        <div class="auth-fields">
                            <div class="password-wrapper">
                                <input type="password" id="reset-password" placeholder="New password (min 8 characters)" autocomplete="new-password">
                                <button type="button" class="password-toggle" onclick="Auth.togglePassword('reset-password', this)" aria-label="Show password">
                                    <svg class="eye-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                                    <svg class="eye-off-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                                </button>
                            </div>
                            <div class="password-wrapper">
                                <input type="password" id="reset-password-confirm" placeholder="Confirm new password" autocomplete="new-password">
                                <button type="button" class="password-toggle" onclick="Auth.togglePassword('reset-password-confirm', this)" aria-label="Show password">
                                    <svg class="eye-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                                    <svg class="eye-off-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                                </button>
                            </div>
                        </div>
                        <div class="auth-buttons">
                            <button class="btn btn-primary btn-full" onclick="Auth.handleResetPassword()">Reset Password</button>
                        </div>
                    </div>

                    <!-- Register fields -->
                    <div id="register-fields" style="${showRegister ? '' : 'display:none'}">
                        <div class="auth-fields">
                            <input type="email" id="reg-email" placeholder="Email" autocomplete="email">
                            <div class="password-wrapper">
                                <input type="password" id="reg-password" placeholder="Password (min 8 characters)" autocomplete="new-password">
                                <button type="button" class="password-toggle" onclick="Auth.togglePassword('reg-password', this)" aria-label="Show password">
                                    <svg class="eye-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                                    <svg class="eye-off-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                                </button>
                            </div>
                            <input type="text" id="reg-invite-code" placeholder="Invite Code (optional)" autocomplete="off">
                        </div>
                        <div id="invite-code-status" class="invite-code-status" style="display:none"></div>
                        <div class="auth-terms">
                            <label class="terms-checkbox">
                                <input type="checkbox" id="reg-terms">
                                <span>I agree to the <a href="/terms" target="_blank">Terms of Service</a></span>
                            </label>
                        </div>
                        <div class="auth-buttons">
                            <button class="btn btn-primary btn-full" onclick="Auth.handleRegister()">Get Started</button>
                        </div>
                        <p class="auth-hint">Already have an account? <a href="#" onclick="Auth.showTab('login');return false;">Log in here</a></p>
                    </div>
                </div>
            </div>
        `;

        // Bind invite code validation + password toggle
        const codeInput = document.getElementById('reg-invite-code');
        if (codeInput) {
            codeInput.addEventListener('blur', () => Auth.validateInviteCode());
            codeInput.addEventListener('input', () => Auth._updatePasswordRequirement());
        }
    },

    _updatePasswordRequirement() {
        const codeInput = document.getElementById('reg-invite-code');
        const passInput = document.getElementById('reg-password');
        if (!codeInput || !passInput) return;

        if (codeInput.value.trim()) {
            passInput.placeholder = 'Set a password (optional — you can do this later)';
            passInput.required = false;
        } else {
            passInput.placeholder = 'Password (min 8 characters)';
            passInput.required = true;
        }
    },

    showTab(tab) {
        const loginFields = document.getElementById('login-fields');
        const registerFields = document.getElementById('register-fields');
        const forgotFields = document.getElementById('forgot-fields');
        const resetFields = document.getElementById('reset-fields');
        const tabLogin = document.getElementById('tab-login');
        const tabRegister = document.getElementById('tab-register');
        const unverifiedNotice = document.getElementById('unverified-notice');

        // Hide all form sections
        if (forgotFields) forgotFields.style.display = 'none';
        if (resetFields) resetFields.style.display = 'none';
        if (unverifiedNotice) unverifiedNotice.style.display = 'none';

        if (tab === 'login') {
            loginFields.style.display = '';
            registerFields.style.display = 'none';
            tabLogin.classList.add('active');
            tabRegister.classList.remove('active');
        } else {
            loginFields.style.display = 'none';
            registerFields.style.display = '';
            tabLogin.classList.remove('active');
            tabRegister.classList.add('active');
        }
    },

    async validateInviteCode() {
        const code = document.getElementById('reg-invite-code').value.trim();
        const statusEl = document.getElementById('invite-code-status');
        if (!code) {
            statusEl.style.display = 'none';
            return;
        }
        try {
            const resp = await fetch('/api/auth/validate-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            const data = await resp.json();
            statusEl.style.display = 'block';
            if (data.valid) {
                statusEl.className = 'invite-code-status valid';
                statusEl.textContent = 'Valid invite code — ' + data.tier + ' tier';
            } else {
                statusEl.className = 'invite-code-status invalid';
                statusEl.textContent = 'Invalid or expired invite code';
            }
        } catch (e) {
            statusEl.style.display = 'none';
        }
    },

    renderProfileView() {
        const el = document.getElementById('view-profile');
        const u = this.currentUser || {};
        el.innerHTML = `
            <div class="profile-card">
                <h2>Set Up Your Shop</h2>
                <p class="profile-hint">This info appears on your quotes and PDFs. You can change it anytime.</p>

                <div id="profile-error" class="auth-error" style="display:none"></div>

                <div class="form-grid">
                    <label class="form-label">
                        Shop Name
                        <input type="text" id="prof-shop-name" value="${u.shop_name || ''}" placeholder="e.g. Burton Iron Works">
                    </label>
                    <label class="form-label">
                        In-Shop Rate ($/hr)
                        <input type="number" id="prof-rate-inshop" value="${u.rate_inshop || 125}" step="5" min="0">
                    </label>
                    <label class="form-label">
                        On-Site Rate ($/hr)
                        <input type="number" id="prof-rate-onsite" value="${u.rate_onsite || 145}" step="5" min="0">
                    </label>
                    <label class="form-label">
                        Default Markup (%)
                        <input type="number" id="prof-markup" value="${u.markup_default || 15}" step="5" min="0" max="30">
                    </label>
                    <label class="form-label">
                        Shop Phone
                        <input type="text" id="prof-phone" value="${u.shop_phone || ''}" placeholder="(555) 123-4567">
                    </label>
                    <label class="form-label">
                        Shop Email
                        <input type="email" id="prof-email" value="${u.shop_email || ''}" placeholder="quotes@myshop.com">
                    </label>
                    <label class="form-label full-width">
                        Shop Address
                        <input type="text" id="prof-address" value="${u.shop_address || ''}" placeholder="123 Industrial Ave, Chicago IL">
                    </label>
                    ${u.is_provisional ? `
                    <label class="form-label full-width">
                        Set Password
                        <input type="password" id="prof-password" placeholder="Set a password for your account" autocomplete="new-password">
                    </label>
                    ` : ''}
                    <div class="form-label full-width">
                        Shop Logo
                        <div class="logo-upload-section">
                            ${u.logo_url ? `<img src="${u.logo_url}" class="logo-preview-img" id="logo-preview" alt="Shop logo">` : '<span id="logo-preview"></span>'}
                            <div class="logo-upload-btn btn btn-secondary btn-sm">
                                ${u.logo_url ? 'Change Logo' : 'Upload Logo'}
                                <input type="file" id="logo-file-input" accept="image/jpeg,image/png,image/webp" onchange="Auth.handleLogoUpload(this)">
                            </div>
                        </div>
                    </div>
                </div>

                ${this._renderPlanSection(u)}

                <div id="equipment-section-container"></div>

                <div class="profile-actions">
                    <button class="btn btn-primary" onclick="Auth.saveProfile()">Save & Continue</button>
                    <button class="btn btn-ghost" onclick="App.showView('quote')">Skip for Now &rarr;</button>
                </div>
            </div>
        `;

        // Load equipment section async
        const eqContainer = document.getElementById('equipment-section-container');
        if (eqContainer && typeof ShopOnboarding !== 'undefined') {
            ShopOnboarding.renderEquipmentSection(eqContainer);
        }
    },

    _renderPlanSection(u) {
        const tier = (u.tier || 'free').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const rawTier = u.tier || 'free';
        const status = u.subscription_status || 'trial';
        const hasBilling = u.has_billing;
        const isPaid = status === 'active' && rawTier !== 'free';

        let statusLabel = status;
        if (status === 'active') statusLabel = 'Active';
        else if (status === 'trial' || status === 'free') statusLabel = 'Free';
        else if (status === 'past_due') statusLabel = 'Past Due';
        else if (status === 'cancelled') statusLabel = 'Cancelled';
        else if (status === 'demo') statusLabel = 'Demo';

        // Show upgrade for anyone not on a paid subscription (trial, free, cancelled, demo)
        const showUpgrade = !isPaid && rawTier !== 'shop';

        return `
            <div class="plan-section">
                <h3>Your Plan</h3>
                <p class="plan-info">
                    <strong>${tier}</strong> &mdash; ${statusLabel}
                </p>
                <div class="plan-actions">
                    ${hasBilling ? '<button class="btn btn-secondary btn-sm" onclick="Auth.openBillingPortal()">Manage Billing</button>' : ''}
                    ${showUpgrade ? '<button class="btn btn-accent btn-sm" onclick="Auth.showUpgradeOptions()">Upgrade</button>' : ''}
                </div>
            </div>
        `;
    },

    showUpgradeOptions() {
        // Redirect to landing page pricing section (works whether or not Stripe is configured)
        window.location.href = '/#pricing';
    },

    togglePassword(inputId, btn) {
        const input = document.getElementById(inputId);
        if (!input) return;
        const isPassword = input.type === 'password';
        input.type = isPassword ? 'text' : 'password';
        const eyeOn = btn.querySelector('.eye-icon');
        const eyeOff = btn.querySelector('.eye-off-icon');
        if (eyeOn) eyeOn.style.display = isPassword ? 'none' : '';
        if (eyeOff) eyeOff.style.display = isPassword ? '' : 'none';
        btn.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');
    },

    showError(containerId, msg) {
        const el = document.getElementById(containerId);
        if (el) {
            el.textContent = msg;
            el.style.display = 'block';
            setTimeout(() => el.style.display = 'none', 5000);
        }
    },

    async handleLogin() {
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;
        if (!email || !password) return this.showError('auth-error', 'Email and password required.');
        try {
            const data = await API.login(email, password);
            this.currentUser = data.user;
            await this._checkDemoStatus();
            App.showView('quote');
        } catch (e) {
            if (e.message && e.message.toLowerCase().includes('not verified')) {
                // Show the unverified notice with resend button
                const notice = document.getElementById('unverified-notice');
                if (notice) notice.style.display = 'block';
                // Store email for resend
                this._unverifiedEmail = email;
            }
            this.showError('auth-error', e.message);
        }
    },

    showForgotPassword() {
        const loginFields = document.getElementById('login-fields');
        const registerFields = document.getElementById('register-fields');
        const forgotFields = document.getElementById('forgot-fields');
        const tabLogin = document.getElementById('tab-login');
        const tabRegister = document.getElementById('tab-register');

        if (loginFields) loginFields.style.display = 'none';
        if (registerFields) registerFields.style.display = 'none';
        if (forgotFields) forgotFields.style.display = '';
        if (tabLogin) tabLogin.classList.remove('active');
        if (tabRegister) tabRegister.classList.remove('active');
    },

    async handleForgotPassword() {
        const email = document.getElementById('forgot-email').value.trim();
        if (!email) return this.showError('auth-error', 'Please enter your email address.');
        try {
            const resp = await fetch('/api/auth/forgot-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            });
            const data = await resp.json();
            this.showError('auth-error', data.message || 'If that email is registered, a reset link has been sent.');
            // Style as success (green) not error
            const el = document.getElementById('auth-error');
            if (el) el.classList.add('auth-success');
            setTimeout(() => { if (el) el.classList.remove('auth-success'); }, 5000);
        } catch (e) {
            this.showError('auth-error', 'Unable to send reset link. Please try again.');
        }
    },

    showResetPassword(token) {
        this._resetToken = token;
        // Ensure auth view is rendered
        if (!document.getElementById('reset-fields')) {
            this.renderAuthView();
        }
        const loginFields = document.getElementById('login-fields');
        const registerFields = document.getElementById('register-fields');
        const forgotFields = document.getElementById('forgot-fields');
        const resetFields = document.getElementById('reset-fields');
        const tabLogin = document.getElementById('tab-login');
        const tabRegister = document.getElementById('tab-register');

        if (loginFields) loginFields.style.display = 'none';
        if (registerFields) registerFields.style.display = 'none';
        if (forgotFields) forgotFields.style.display = 'none';
        if (resetFields) resetFields.style.display = '';
        if (tabLogin) tabLogin.classList.remove('active');
        if (tabRegister) tabRegister.classList.remove('active');
    },

    async handleResetPassword() {
        const password = document.getElementById('reset-password').value;
        const confirm = document.getElementById('reset-password-confirm').value;

        if (!password || password.length < 8) {
            return this.showError('auth-error', 'Password must be at least 8 characters.');
        }
        if (password !== confirm) {
            return this.showError('auth-error', 'Passwords do not match.');
        }
        if (!this._resetToken) {
            return this.showError('auth-error', 'Invalid reset link. Please request a new one.');
        }

        try {
            const resp = await fetch('/api/auth/reset-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: this._resetToken, password }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || 'Password reset failed.');

            // Auto-login with returned tokens
            API.setTokens(data.access_token, data.refresh_token);
            this.currentUser = data.user;
            this._resetToken = null;
            // Clean URL
            history.replaceState(null, '', '/app');
            App.showView('quote');
        } catch (e) {
            this.showError('auth-error', e.message);
        }
    },

    async resendVerification() {
        const email = this._unverifiedEmail || document.getElementById('login-email').value.trim();
        if (!email) return this.showError('auth-error', 'Please enter your email address first.');
        try {
            const resp = await fetch('/api/auth/resend-verification', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
            });
            const data = await resp.json();
            this.showError('auth-error', data.message || 'Verification email sent.');
            const el = document.getElementById('auth-error');
            if (el) el.classList.add('auth-success');
            setTimeout(() => { if (el) el.classList.remove('auth-success'); }, 5000);
        } catch (e) {
            this.showError('auth-error', 'Unable to resend verification email. Please try again.');
        }
    },

    async handleRegister() {
        const email = document.getElementById('reg-email').value.trim();
        const password = document.getElementById('reg-password').value;
        const inviteCode = document.getElementById('reg-invite-code').value.trim();
        const termsChecked = document.getElementById('reg-terms').checked;

        if (!email) return this.showError('auth-error', 'Email is required.');
        if (!inviteCode && (!password || password.length < 8)) {
            return this.showError('auth-error', 'Password must be at least 8 characters.');
        }
        if (password && password.length > 0 && password.length < 8) {
            return this.showError('auth-error', 'Password must be at least 8 characters.');
        }
        if (!termsChecked) return this.showError('auth-error', 'You must agree to the Terms of Service to continue.');

        try {
            // Include demo token if upgrading from demo
            const demoToken = localStorage.getItem('demo_token');
            const data = await API.register(email, password || null, inviteCode, termsChecked, demoToken);
            this.currentUser = data.user;
            // Clear demo state on successful registration
            localStorage.removeItem('demo_token');
            this.demoStatus = null;
            const demoBanner = document.getElementById('demo-banner');
            if (demoBanner) demoBanner.remove();
            App.showView('profile');
        } catch (e) {
            this.showError('auth-error', e.message);
        }
    },

    async saveProfile() {
        const data = {
            shop_name: document.getElementById('prof-shop-name').value.trim() || null,
            rate_inshop: parseFloat(document.getElementById('prof-rate-inshop').value) || 125,
            rate_onsite: parseFloat(document.getElementById('prof-rate-onsite').value) || 145,
            markup_default: parseInt(document.getElementById('prof-markup').value) || 15,
            shop_phone: document.getElementById('prof-phone').value.trim() || null,
            shop_email: document.getElementById('prof-email').value.trim() || null,
            shop_address: document.getElementById('prof-address').value.trim() || null,
        };

        // Handle password set from profile (for provisional users)
        const passInput = document.getElementById('prof-password');
        if (passInput && passInput.value && passInput.value.length >= 8) {
            // Set password via a separate register call to claim the account
            try {
                const currentEmail = this.currentUser.email;
                await API.register(currentEmail, passInput.value, null, true, null);
            } catch (e) {
                // Ignore if account already claimed
            }
        }

        try {
            this.currentUser = await API.updateProfile(data);
            App.showView('quote');
        } catch (e) {
            this.showError('profile-error', e.message);
        }
    },

    async handleLogoUpload(input) {
        if (!input.files || !input.files[0]) return;
        const file = input.files[0];
        if (file.size > 2 * 1024 * 1024) {
            this.showError('profile-error', 'Logo must be under 2MB.');
            return;
        }
        const formData = new FormData();
        formData.append('file', file);
        try {
            await API.uploadLogo(formData);
            // Show preview with local URL
            const preview = document.getElementById('logo-preview');
            if (preview) {
                if (preview.tagName === 'IMG') {
                    preview.src = URL.createObjectURL(file);
                } else {
                    const img = document.createElement('img');
                    img.src = URL.createObjectURL(file);
                    img.className = 'logo-preview-img';
                    img.id = 'logo-preview';
                    img.alt = 'Shop logo';
                    preview.replaceWith(img);
                }
            }
        } catch (e) {
            this.showError('profile-error', e.message);
        }
    },

    logout() {
        API.clearTokens();
        localStorage.removeItem('demo_token');
        this.currentUser = null;
        this.demoStatus = null;
        // Redirect to landing page
        window.location.href = '/';
    },
};
