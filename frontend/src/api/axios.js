import axios from 'axios';
import { auth } from '../auth/firebase';

let configError = null;
let API_BASE_URL = 'http://localhost:8000';

try {
  const configured = import.meta.env.VITE_API_URL?.trim();
  if (configured) {
    const parsed = new URL(configured);
    const isPlainHttpLocalhost =
      parsed.protocol === 'http:' &&
      (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1');

    if (
      typeof window !== 'undefined' &&
      window.location.hostname &&
      isPlainHttpLocalhost
    ) {
      // Rewrite hostname only for plain localhost/LAN over http (e.g. browsing from mobile on LAN)
      parsed.hostname = window.location.hostname;
      API_BASE_URL = parsed.origin;
    } else {
      // Preserve tunnels (ngrok, cloudflare, etc.), HTTPS, and custom ports without modification
      API_BASE_URL = configured.replace(/\/$/, '');
    }
  } else if (typeof window !== 'undefined' && window.location.hostname) {
    API_BASE_URL = `http://${window.location.hostname}:8000`;
  }
} catch (err) {
  configError = `Configuration Error: Failed to parse VITE_API_URL (${err.message}). Check frontend/.env.`;
  console.error(configError);
  API_BASE_URL = 'http://localhost:8000';
}

export { API_BASE_URL, configError };

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: Attach fresh Firebase ID token if available
api.interceptors.request.use(
  async (config) => {
    try {
      let token = null;
      if (auth.currentUser) {
        token = await auth.currentUser.getIdToken();
        localStorage.setItem('token', token);
      } else {
        token = localStorage.getItem('token');
      }

      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch (e) {
      console.warn('Could not attach token to outgoing request:', e);
    }
    return config;
  },
  (error) => Promise.reject(error)
);

let sessionExpiredHandler = null;

export const setSessionExpiredHandler = (handler) => {
  sessionExpiredHandler = handler;
};

// Response interceptor: Refresh token once on 401 for authenticated requests without redirect loops
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401) {
      if (
        originalRequest &&
        !originalRequest._retry &&
        auth.currentUser
      ) {
        originalRequest._retry = true;
        try {
          const freshToken = await auth.currentUser.getIdToken(true);
          localStorage.setItem('token', freshToken);
          originalRequest.headers.Authorization = `Bearer ${freshToken}`;
          return api(originalRequest);
        } catch (refreshError) {
          console.warn('Automatic token refresh failed:', refreshError);
        }
      }

      // If retry already failed or user not authenticated, trigger session expiration
      if (sessionExpiredHandler) {
        try {
          sessionExpiredHandler();
        } catch (e) {
          console.warn('Error invoking sessionExpiredHandler:', e);
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;
