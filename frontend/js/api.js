// ============ API CONFIGURATION ============
// Resolve the backend base URL:
//  1. If build.sh injected window.AVIRA_CONFIG.backendUrl (deployed on Render), use it.
//  2. Otherwise prefer the proxied same-origin API and fall back to the direct backend.
const INJECTED = (typeof window !== 'undefined' && window.AVIRA_CONFIG && window.AVIRA_CONFIG.backendUrl)
  ? window.AVIRA_CONFIG.backendUrl
  : null;

const API_BASE_URLS = INJECTED
  ? [INJECTED]
  : window.location.protocol === 'file:'
    ? ['http://localhost:5000/api', 'http://127.0.0.1:5000/api']
    : ['/api', 'http://localhost:5000/api', 'http://127.0.0.1:5000/api'];

const api = {
  // Token management
  getToken() {
    return localStorage.getItem('aviraaToken') || '';
  },

  setToken(token) {
    localStorage.setItem('aviraaToken', token);
  },

  removeToken() {
    localStorage.removeItem('aviraaToken');
    localStorage.removeItem('aviraaUser');
    localStorage.removeItem('aviraaLoggedIn');
  },

  // Auth helpers
  isAuthenticated() {
    return !!(localStorage.getItem('aviraaToken'));
  },

  getUser() {
    try {
      return JSON.parse(localStorage.getItem('aviraaUser'));
    } catch {
      return null;
    }
  },

  setUser(user) {
    localStorage.setItem('aviraaUser', JSON.stringify(user));
    localStorage.setItem('aviraaLoggedIn', 'true');
  },

  getLoginUrl() {
    return window.location.pathname.includes('/pages/') ? '../login.html' : 'login.html';
  },

  requireAuth() {
    if (!this.isAuthenticated()) {
      const loginUrl = this.getLoginUrl();
      const nextPath = window.location.pathname + window.location.search + window.location.hash;
      window.location.href = `${loginUrl}?next=${encodeURIComponent(nextPath)}`;
      return false;
    }
    return true;
  },

  // API request handler
  async request(endpoint, options = {}) {
    const token = this.getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` })
    };

    let lastError = null;

    for (const baseUrl of API_BASE_URLS) {
      try {
        const response = await fetch(`${baseUrl}${endpoint}`, {
          ...options,
          headers
        });

        // If the response is not JSON, this base URL is not an API server
        // (e.g. a static host returning index.html or an HTML 404 page).
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
          const error = new Error(`Non-JSON response from ${baseUrl} (${response.status})`);
          error.status = response.status;
          lastError = error;
          if (baseUrl !== API_BASE_URLS[API_BASE_URLS.length - 1]) {
            continue;
          }
          break;
        }

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const error = new Error(errorData.message || `Request failed: ${response.status}`);
          error.status = response.status;

          // Redirect to login only for expired/authenticated sessions on
          // protected endpoints — never for a failed login/signup attempt.
          const isAuthAttempt = endpoint.includes('/auth/login') || endpoint.includes('/auth/signup');
          if (response.status === 401 && !isAuthAttempt) {
            this.removeToken();
            window.location.href = this.getLoginUrl();
          }

          if ([404, 405, 502, 503].includes(response.status) && baseUrl !== API_BASE_URLS[API_BASE_URLS.length - 1]) {
            lastError = error;
            continue;
          }

          throw error;
        }

        return await response.json();
      } catch (error) {
        lastError = error;
        const isNetworkError = error instanceof TypeError;
        const isRetryableStatus = error.status && [404, 405, 502, 503].includes(error.status);

        if ((isNetworkError || isRetryableStatus) && baseUrl !== API_BASE_URLS[API_BASE_URLS.length - 1]) {
          continue;
        }

        break;
      }
    }

    if (lastError instanceof TypeError) {
      const networkError = new Error('Unable to reach the server. Please try again.');
      networkError.cause = lastError;
      throw networkError;
    }

    throw lastError || new Error('Request failed');
  },

  async get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  },

  async post(endpoint, body) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(body)
    });
  },

async put(endpoint, body) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body)
    });
  },

  async delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  },

};
