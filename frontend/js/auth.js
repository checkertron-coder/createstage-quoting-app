/**
 * Auth UI — login, register, profile setup.
 * Guest access removed in P53. All users must register.
 */

const Auth = {
    currentUser: null,

    async init() {
        API.init();
        if (API.isAuthenticated()) {
            try {
                this.currentUser = await API.getMe();
                return true;
            } catch (e) {
                API.clearTokens();
                return false;
            }
        }
        return false;
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
                            <input type="password" id="login-password" placeholder="Password" autocomplete="current-password">
                        </div>
                        <div class="auth-buttons">
                            <button class="btn btn-primary btn-full" onclick="Auth.handleLogin()">Log In</button>
                        </div>
                        <p class="auth-hint">Don't have an account? <a href="#" onclick="Auth.showTab('register');return false;">Register here</a></p>
                    </div>

                    <!-- Register fields -->
                    <div id="register-fields" style="${showRegister ? '' : 'display:none'}">
                        <div class="auth-fields">
                            <input type="email" id="reg-email" placeholder="Email" autocomplete="email">
                            <input type="password" id="reg-password" placeholder="Password (min 8 characters)" autocomplete="new-password">
                            <input type="text" id="reg-invite-code" placeholder="Invite Code (optional)" autocomplete="off">
                        </div>
                        <div id="invite-code-status" class="invite-code-status" style="display:none"></div>
                        <div class="auth-terms">
                            <label class="terms-checkbox">
                                <input type="checkbox" id="reg-terms">
                                <span>I agree to the <a href="/terms" target="_blank">Terms of Service</a> and <a href="/nda" target="_blank">Non-Disclosure Agreement</a></span>
                            </label>
                        </div>
                        <div class="auth-buttons">
                            <button class="btn btn-primary btn-full" onclick="Auth.handleRegister()">Create Account</button>
                        </div>
                        <p class="auth-hint">Already have an account? <a href="#" onclick="Auth.showTab('login');return false;">Log in here</a></p>
                    </div>
                </div>
            </div>
        `;

        // Bind invite code validation
        const codeInput = document.getElementById('reg-invite-code');
        if (codeInput) {
            codeInput.addEventListener('blur', () => Auth.validateInviteCode());
        }
    },

    showTab(tab) {
        const loginFields = document.getElementById('login-fields');
        const registerFields = document.getElementById('register-fields');
        const tabLogin = document.getElementById('tab-login');
        const tabRegister = document.getElementById('tab-register');
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

                <div class="profile-actions">
                    <button class="btn btn-primary" onclick="Auth.saveProfile()">Save & Continue</button>
                    <button class="btn btn-ghost" onclick="App.showView('quote')">Skip for Now &rarr;</button>
                </div>
            </div>
        `;
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
            App.showView('quote');
        } catch (e) {
            this.showError('auth-error', e.message);
        }
    },

    async handleRegister() {
        const email = document.getElementById('reg-email').value.trim();
        const password = document.getElementById('reg-password').value;
        const inviteCode = document.getElementById('reg-invite-code').value.trim();
        const termsChecked = document.getElementById('reg-terms').checked;

        if (!email || !password) return this.showError('auth-error', 'Email and password required.');
        if (password.length < 8) return this.showError('auth-error', 'Password must be at least 8 characters.');
        if (!termsChecked) return this.showError('auth-error', 'You must agree to the Terms of Service and NDA to continue.');

        try {
            const data = await API.register(email, password, inviteCode, termsChecked);
            this.currentUser = data.user;
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
        this.currentUser = null;
        // Redirect to landing page
        window.location.href = '/';
    },
};
