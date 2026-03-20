/**
 * App — main controller for /app. Shows/hides views, manages navigation.
 * Landing page is at /. This runs only on /app (app.html).
 */

const App = {
    currentView: 'auth',

    async init() {
        const isAuth = await Auth.init();

        // Render all views
        Auth.renderAuthView();
        Auth.renderProfileView();
        QuoteFlow.renderQuoteView();

        // Nav buttons
        this._setupNav();

        // Handle URL action params (verify-email, reset-password)
        const params = new URLSearchParams(window.location.search);
        const action = params.get('action');
        const actionToken = params.get('token');

        if (action === 'verify-email' && actionToken) {
            // Call verify-email endpoint, show result on auth screen
            this.showView('auth');
            try {
                const resp = await fetch(`/api/auth/verify-email?token=${encodeURIComponent(actionToken)}`);
                const data = await resp.json();
                if (resp.ok) {
                    Auth.showError('auth-error', data.message || 'Email verified! You can now log in.');
                    const el = document.getElementById('auth-error');
                    if (el) el.classList.add('auth-success');
                } else {
                    Auth.showError('auth-error', data.detail || 'Verification failed.');
                }
            } catch (e) {
                Auth.showError('auth-error', 'Verification failed. Please try again.');
            }
            history.replaceState(null, '', '/app');
            return;
        }

        if (action === 'reset-password' && actionToken) {
            this.showView('auth');
            Auth.showResetPassword(actionToken);
            return;
        }

        if (isAuth) {
            // Handle return from Stripe checkout
            if (params.get('checkout') === 'success') {
                // Refresh user data to pick up new tier
                try { Auth.currentUser = await API.getMe(); } catch(e) {}
                history.replaceState(null, '', '/app');
            } else if (params.get('checkout') === 'cancelled') {
                history.replaceState(null, '', '/app');
            }

            // Check if user needs onboarding
            const user = Auth.currentUser;
            if (user && !user.onboarding_complete && !user.is_provisional) {
                ShopOnboarding.render();
                this.showView('onboarding');
            } else {
                this.showView('quote');
            }
            // Show demo banner or upgrade banner
            Auth.renderDemoBanner();
            Auth.renderUpgradeBanner();
        } else {
            this.showView('auth');
        }
    },

    showView(view) {
        this.currentView = view;
        const views = ['auth', 'profile', 'onboarding', 'quote', 'history', 'bid'];
        views.forEach(v => {
            const el = document.getElementById(`view-${v}`);
            if (el) el.style.display = v === view ? 'block' : 'none';
        });

        // Update nav
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === view);
        });

        // Show/hide nav based on auth state
        const nav = document.getElementById('main-nav');
        if (nav) {
            nav.style.display = (view === 'auth' || view === 'onboarding') ? 'none' : 'flex';
        }

        // Load history data when showing history view
        if (view === 'history') {
            QuoteHistory.render();
        }

        // Init bid upload when showing bid view
        if (view === 'bid') {
            BidUpload.initBidUpload();
        }

        // Note: quote view rendering is handled by QuoteFlow.newQuote() or
        // QuoteFlow.renderQuoteView() — not triggered here to avoid
        // double-render and unwanted state restoration.
    },

    _setupNav() {
        const nav = document.getElementById('main-nav');
        if (!nav) return;

        const shopName = Auth.currentUser?.shop_name || 'CreateQuote';
        const nameEl = document.getElementById('nav-shop-name');
        if (nameEl) nameEl.textContent = shopName;
    },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
