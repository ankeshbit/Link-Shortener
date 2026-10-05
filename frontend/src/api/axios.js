import axios from 'axios';
import { auth } from '../auth/firebase';

const configuredApiURL = import.meta.env.VITE_API_URL?.trim();
export const API_BASE_URL = (
  configuredApiURL || (import.meta.env.DEV ? 'http://localhost:8000' : '')
).replace(/\/$/, '');

if (!API_BASE_URL) {
  throw new Error('VITE_API_URL must be configured for production builds.');
}

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: Attach fresh Firebase ID token
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

// Response interceptor: Auto-refresh Firebase ID token on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (
      error.response?.status === 401 &&
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
        localStorage.removeItem('token');
        window.dispatchEvent(new Event('authchange'));
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

export default api;
