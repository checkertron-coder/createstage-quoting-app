/**
 * API Client — all fetch calls to the FastAPI backend.
 * Handles JWT token management, automatic refresh, and proactive renewal.
 */

const API = {
    base: '/api',

    // Token storage
    _accessToken: null,
    _refreshToken: null,
    _refreshTimer: null,

    init() {
        this._accessToken = localStorage.getItem('access_token');
        this._refreshToken = localStorage.getItem('refresh_token');
        // Start proactive token refresh cycle
        this._startRefreshCycle();
    },

    setTokens(access, refresh) {
        this._accessToken = access;
        this._refreshToken = refresh;
        if (access) localStorage.setItem('access_token', access);
        if (refresh) localStorage.setItem('refresh_token', refresh);
        // Restart the refresh cycle with the new token
        this._startRefreshCycle();
    },

    clearTokens() {
        this._accessToken = null;
        this._refreshToken = null;
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        if (this._refreshTimer) {
            clearInterval(this._refreshTimer);
            this._refreshTimer = null;
        }
    },

    isAuthenticated() {
        return !!(this._accessToken || localStorage.getItem('access_token'));
    },

    headers() {
        // Always read the freshest token (another tab may have updated it)
        const token = this._accessToken || localStorage.getItem('access_token');
        const h = { 'Content-Type': 'application/json' };
        if (token) h['Authorization'] = `Bearer ${token}`;
        return h;
    },

    /**
     * Proactive token refresh — refreshes the access token every 45 minutes
     * so it never expires during a work session. The access token lasts 60 min,
     * so refreshing at 45 min gives a 15-min safety buffer.
     */
    _startRefreshCycle() {
        if (this._refreshTimer) clearInterval(this._refreshTimer);
        const refreshToken = this._refreshToken || localStorage.getItem('refresh_token');
        if (!refreshToken) return;

        // Refresh every 45 minutes (well before the 60-min access token expiry)
        this._refreshTimer = setInterval(() => {
            this._tryRefresh().then(ok => {
                if (ok) {
                    console.log('[API] Proactive token refresh succeeded');
                } else {
                    console.warn('[API] Proactive token refresh failed — user may need to re-login');
                }
            });
        }, 45 * 60 * 1000);
    },

    async _fetch(path, opts = {}) {
        const url = `${this.base}${path}`;
        const resp = await fetch(url, {
            headers: this.headers(),
            ...opts,
        });

        // Handle 401 — try refresh
        if (resp.status === 401) {
            // Always check localStorage as fallback (another tab may have set tokens)
            const refreshToken = this._refreshToken || localStorage.getItem('refresh_token');
            if (refreshToken) {
                this._refreshToken = refreshToken;
                const refreshed = await this._tryRefresh();
                if (refreshed) {
                    const retry = await fetch(url, {
                        headers: this.headers(),
                        ...opts,
                    });
                    return retry;
                }
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
            // Always read freshest refresh token from localStorage
            const refreshToken = this._refreshToken || localStorage.getItem('refresh_token');
            if (!refreshToken) return false;

            const resp = await fetch(`${this.base}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
            });
            if (resp.ok) {
                const data = await resp.json();
                this._accessToken = data.access_token;
                localStorage.setItem('access_token', data.access_token);
                return true;
            }
        } catch (e) {
            console.warn('[API] Token refresh error:', e.message);
        }
        return false;
    },

    // --- Auth ---
    async register(email, password, inviteCode, termsAccepted, demoToken) {
        const body = { email };
        if (password) body.password = password;
        if (inviteCode) body.invite_code = inviteCode;
        if (termsAccepted) body.terms_accepted = true;
        if (demoToken) body.demo_token = demoToken;
        const resp = await fetch(`${this.base}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
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
        // Re-read token for freshness
        const token = this._accessToken || localStorage.getItem('access_token');
        const resp = await fetch(`${this.base}/photos/upload`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
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
        console.log('[VISION-DEBUG] startSession body:', JSON.stringify(body));
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

    async getMaterialAlternatives(quoteId) {
        const resp = await this._fetch(`/quotes/${quoteId}/material-alternatives`);
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Failed to get alternatives');
        return data;
    },

    async swapMaterial(quoteId, itemIndex, newProfile) {
        const resp = await this._fetch(`/quotes/${quoteId}/swap-material`, {
            method: 'POST',
            body: JSON.stringify({ item_index: itemIndex, new_profile: newProfile }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Material swap failed');
        return data;
    },

    async adjustLineItems(quoteId, adjustments) {
        const resp = await this._fetch(`/quotes/${quoteId}/adjust`, {
            method: 'PATCH',
            body: JSON.stringify(adjustments),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Adjustment failed');
        return data;
    },

    async retryBuildInstructions(sessionId) {
        const resp = await this._fetch(`/session/${sessionId}/retry-build-instructions`, {
            method: 'POST',
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Build instructions retry failed');
        return data;
    },

    async updateCustomer(sessionId, customerData) {
        const resp = await this._fetch(`/session/${sessionId}/customer`, {
            method: 'PATCH',
            body: JSON.stringify(customerData),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Customer update failed');
        return data;
    },

    async uploadLogo(formData) {
        const token = this._accessToken || localStorage.getItem('access_token');
        const resp = await fetch(`${this.base}/auth/profile/logo`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData,
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || 'Logo upload failed');
        return data;
    },

    getPdfUrl(quoteId, mode) {
        const token = this._accessToken || localStorage.getItem('access_token');
        let url = `${this.base}/quotes/${quoteId}/pdf?token=${token}`;
        if (mode) url += `&mode=${mode}`;
        return url;
    },
};
