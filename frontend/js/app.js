/**
 * App — main controller. Shows/hides views, manages navigation.
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
            this.showView('quote');
        } else {
            this.showView('auth');
        }
    },

    showView(view) {
        this.currentView = view;
        const views = ['auth', 'profile', 'quote', 'history'];
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

        // Reset quote view to describe step
        if (view === 'quote' && QuoteFlow.currentStep === 'describe') {
            QuoteFlow.renderQuoteView();
        }
    },

    _setupNav() {
        const nav = document.getElementById('main-nav');
        if (!nav) return;

        const shopName = Auth.currentUser?.shop_name || 'Quoting';
        const nameEl = document.getElementById('nav-shop-name');
        if (nameEl) nameEl.textContent = shopName;
    },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
