import { api } from './api';

export interface TokenResponse {
  access_token?: string;
  refresh_token?: string;
  token_type: string;
  mfa_required?: boolean;
  mfa_challenge?: string;
}

export async function login(email: string, password: string, mfaCode?: string, recoveryCode?: string): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>('/auth/login', {
    email,
    password,
    mfa_code: mfaCode || undefined,
    recovery_code: recoveryCode || undefined,
  });
  if (res.data.mfa_required) return res.data;
  if (!res.data.access_token || !res.data.refresh_token) {
    throw new Error('Login did not return tokens');
  }
  localStorage.setItem('access_token', res.data.access_token);
  localStorage.setItem('refresh_token', res.data.refresh_token);
  return res.data;
}

export function logout(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  window.location.href = '/login';
}

export function getAccessToken(): string | null {
  return typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
}

export function decodeToken(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const decoded = JSON.parse(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, '=')));
    if (decoded.exp && Number(decoded.exp) * 1000 < Date.now()) return null;
    return decoded;
  } catch {
    return null;
  }
}
