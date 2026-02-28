/**
 * API Client — all fetch calls to the FastAPI backend.
 * Handles JWT token management and automatic refresh.
 */

const API = {
    base: '/api',

    // Token storage
    _accessToken: null,
    _refreshToken: null,

    init() {
        this._accessToken = localStorage.getItem('access_token');
        this._refreshToken = localStorage.getItem('refresh_token');
    },

    setTokens(access, refresh) {
        this._accessToken = access;
        this._refreshToken = refresh;
        if (access) localStorage.setItem('access_token', access);
        if (refresh) localStorage.setItem('refresh_token', refresh);
    },

    clearTokens() {
        this._accessToken = null;
        this._refreshToken = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
    },

    isAuthenticated() {
        return !!this._accessToken;
    },

    headers() {
        const h = { 'Content-Type': 'application/json' };
        if (this._accessToken) h['Authorization'] = `Bearer ${this._accessToken}`;
        return h;
    },

    async _fetch(path, opts = {}) {
        const url = `${this.base}${path}`;
        const resp = await fetch(url, {
            headers: this.headers(),
            ...opts,
        });

        // Handle 401 — try refresh
        if (resp.status === 401 && this._refreshToken) {
            const refreshed = await this._tryRefresh();
            if (refreshed) {
                const retry = await fetch(url, {
                    headers: this.headers(),
                    ...opts,
                });
                return retry;
            }
            // Refresh failed — clear tokens, redirect to auth
            this.clearTokens();
            if (window.App) window.App.showView('auth');
            throw new Error('Session expired. Please log in again.');
        }

        return resp;
    },

    async _tryRefresh() {
        try {
            const resp = await fetch(`${this.base}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: this._refreshToken }),
            });
            if (resp.ok) {
                const data = await resp.json();
                this._accessToken = data.access_token;
                localStorage.setItem('access_token', data.access_token);
                return true;
            }
        } catch (e) { /* refresh failed */ }
        return false;
    },

    // --- Auth ---
    async register(email, password) {
        const resp = await fetch(`${this.base}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Registration failed');
        this.setTokens(data.access_token, data.refresh_token);
        return data;
    },

    async login(email, password) {
        const resp = await fetch(`${this.base}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Login failed');
        this.setTokens(data.access_token, data.refresh_token);
        return data;
    },

    async guest() {
        const resp = await fetch(`${this.base}/auth/guest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Guest login failed');
        this.setTokens(data.access_token, data.refresh_token);
        return data;
    },

    async getMe() {
        const resp = await this._fetch('/auth/me');
        if (!resp.ok) throw new Error('Failed to get user profile');
        return resp.json();
    },

    async updateProfile(data) {
        const resp = await this._fetch('/auth/profile', {
            method: 'PUT',
            body: JSON.stringify(data),
        });
        const result = await resp.json();
        if (!resp.ok) throw new Error(result.detail || 'Profile update failed');
        return result;
    },

    // --- Photos ---
    async uploadPhoto(formData) {
        const resp = await fetch(`${this.base}/photos/upload`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${this._accessToken}` },
            body: formData,
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Photo upload failed');
        return data;
    },

    // --- Sessions ---
    async startSession(description, jobType, photoUrls) {
        const body = { description };
        if (jobType) body.job_type = jobType;
        if (photoUrls && photoUrls.length) body.photo_urls = photoUrls;
        const resp = await this._fetch('/session/start', {
            method: 'POST',
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Failed to start session');
        return data;
    },

    async submitAnswers(sessionId, answers, photoUrl) {
        const body = { answers };
        if (photoUrl) body.photo_url = photoUrl;
        const resp = await this._fetch(`/session/${sessionId}/answer`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Failed to submit answers');
        return data;
    },

    async getSessionStatus(sessionId) {
        const resp = await this._fetch(`/session/${sessionId}/status`);
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Failed to get session status');
        return data;
    },

    async calculate(sessionId) {
        const resp = await this._fetch(`/session/${sessionId}/calculate`, {
            method: 'POST',
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Calculation failed');
        return data;
    },

    async estimate(sessionId) {
        const resp = await this._fetch(`/session/${sessionId}/estimate`, {
            method: 'POST',
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Labor estimation failed');
        return data;
    },

    async price(sessionId) {
        const resp = await this._fetch(`/session/${sessionId}/price`, {
            method: 'POST',
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Pricing failed');
        return data;
    },

    // --- Quotes ---
    async listMyQuotes() {
        const resp = await this._fetch('/quotes/mine');
        if (!resp.ok) return [];
        return resp.json();
    },

    async getQuoteDetail(quoteId) {
        const resp = await this._fetch(`/quotes/${quoteId}/detail`);
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Failed to get quote');
        return data;
    },

    async updateMarkup(quoteId, markupPct) {
        const resp = await this._fetch(`/quotes/${quoteId}/markup`, {
            method: 'PUT',
            body: JSON.stringify({ markup_pct: markupPct }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Markup update failed');
        return data;
    },

    getPdfUrl(quoteId) {
        return `${this.base}/quotes/${quoteId}/pdf?token=${this._accessToken}`;
    },
};
