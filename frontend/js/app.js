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

        if (isAuth) {
            // Handle return from Stripe checkout
            const params = new URLSearchParams(window.location.search);
            if (params.get('checkout') === 'success') {
                // Refresh user data to pick up new tier
                try { Auth.currentUser = await API.getMe(); } catch(e) {}
                history.replaceState(null, '', '/app');
            } else if (params.get('checkout') === 'cancelled') {
                history.replaceState(null, '', '/app');
            }

            this.showView('quote');
            // Show demo banner or upgrade banner
            Auth.renderDemoBanner();
            Auth.renderUpgradeBanner();
        } else {
            this.showView('auth');
        }
    },

    showView(view) {
        this.currentView = view;
        const views = ['auth', 'profile', 'quote', 'history', 'bid'];
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
            nav.style.display = (view === 'auth') ? 'none' : 'flex';
        }

        // Load history data when showing history view
        if (view === 'history') {
            QuoteHistory.render();
        }

        // Init bid upload when showing bid view
        if (view === 'bid') {
            BidUpload.initBidUpload();
        }

        // Reset quote view to describe step
        if (view === 'quote' && QuoteFlow.currentStep === 'describe') {
            QuoteFlow.renderQuoteView();
        }
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
