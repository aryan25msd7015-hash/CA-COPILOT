/**
 * Client portal auth — separate storage & HTTP client from firm workspace.
 * Never reuse the firm access_token key.
 */
import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const PORTAL_TOKEN_KEY = 'ca_portal_access_token';
const PORTAL_PROFILE_KEY = 'ca_portal_profile';

const portalApi = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

portalApi.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem(PORTAL_TOKEN_KEY) : null;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

portalApi.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem(PORTAL_TOKEN_KEY);
      localStorage.removeItem(PORTAL_PROFILE_KEY);
      if (!window.location.pathname.includes('/client-portal/login')) {
        window.location.href = '/client-portal/login';
      }
    }
    return Promise.reject(error);
  },
);

export function getPortalToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(PORTAL_TOKEN_KEY);
}

export function setPortalSession(token: string, profile: unknown) {
  localStorage.setItem(PORTAL_TOKEN_KEY, token);
  localStorage.setItem(PORTAL_PROFILE_KEY, JSON.stringify(profile));
}

export function clearPortalSession() {
  localStorage.removeItem(PORTAL_TOKEN_KEY);
  localStorage.removeItem(PORTAL_PROFILE_KEY);
}

export function getPortalProfile<T = Record<string, unknown>>(): T | null {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem(PORTAL_PROFILE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function requestPortalMagicLink(email: string) {
  const { data } = await portalApi.post('/client-portal/auth/magic-link', { email });
  return data as { detail: string; token?: string; delivery_mode?: string };
}

export async function confirmPortalMagicLink(token: string) {
  const { data } = await portalApi.post('/client-portal/auth/confirm', { token });
  setPortalSession(data.access_token, { contact: data.contact, client: data.client });
  return data;
}

export async function portalGet<T>(path: string): Promise<T> {
  const { data } = await portalApi.get(path);
  return data as T;
}
