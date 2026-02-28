/**
 * Auth UI — login, register, guest, profile setup.
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
        el.innerHTML = `
            <div class="auth-card">
                <h1 class="auth-title">Fabrication Quoting</h1>
                <p class="auth-subtitle">Get an accurate quote in minutes, not hours.</p>

                <div id="auth-form">
                    <div id="auth-error" class="auth-error" style="display:none"></div>

                    <div class="auth-fields">
                        <input type="email" id="auth-email" placeholder="Email" autocomplete="email">
                        <input type="password" id="auth-password" placeholder="Password" autocomplete="current-password">
                    </div>

                    <div class="auth-buttons">
                        <button class="btn btn-primary" onclick="Auth.handleLogin()">Log In</button>
                        <button class="btn btn-secondary" onclick="Auth.handleRegister()">Register</button>
                    </div>

                    <div class="auth-divider"><span>or</span></div>

                    <button class="btn btn-accent btn-full" onclick="Auth.handleGuest()">
                        Start Quoting Now &rarr;
                    </button>
                    <p class="auth-hint">No account needed. Create one later to save your work.</p>
                </div>
            </div>
        `;
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
        const email = document.getElementById('auth-email').value.trim();
        const password = document.getElementById('auth-password').value;
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
        const email = document.getElementById('auth-email').value.trim();
        const password = document.getElementById('auth-password').value;
        if (!email || !password) return this.showError('auth-error', 'Email and password required.');
        if (password.length < 6) return this.showError('auth-error', 'Password must be at least 6 characters.');
        try {
            const data = await API.register(email, password);
            this.currentUser = data.user;
            App.showView('profile');
        } catch (e) {
            this.showError('auth-error', e.message);
        }
    },

    async handleGuest() {
        try {
            const data = await API.guest();
            this.currentUser = data.user;
            App.showView('quote');
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

    logout() {
        API.clearTokens();
        this.currentUser = null;
        App.showView('auth');
    },
};
