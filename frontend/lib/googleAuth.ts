/**
 * Emergent-managed Google Auth client helpers.
 *
 * Flow:
 *   1. `startGoogleSignIn()` computes the callback URL from `window.location.origin`
 *      (never hardcoded; per Emergent playbook this breaks the auth) and redirects
 *      to `https://auth.emergentagent.com/?redirect=<callback>`.
 *   2. Emergent bounces the user back to `/auth/callback#session_id=<sid>`.
 *   3. `/auth/callback/page.tsx` reads the fragment and calls
 *      `exchangeGoogleSession(session_id)` which POSTs to
 *      `/api/auth/google/session` — the backend does the actual /session-data
 *      handshake and returns our normal JWT `{access_token, refresh_token, user}`.
 *   4. Tokens are stored in localStorage the same way the password flow does,
 *      so the existing `useAuth` hook picks up the user with zero changes.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
import { api } from '@/lib/api';

const CALLBACK_PATH = '/auth/callback';
const EMERGENT_AUTH = 'https://auth.emergentagent.com/';

export function startGoogleSignIn(intent: 'firm' | 'portal' = 'firm'): void {
  if (typeof window === 'undefined') return;
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const redirectUrl = window.location.origin + CALLBACK_PATH + `?intent=${intent}`;
  window.location.href = `${EMERGENT_AUTH}?redirect=${encodeURIComponent(redirectUrl)}`;
}

export interface GoogleSessionResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  user: {
    id: string;
    org_id: string;
    email: string;
    role: string;
    name?: string | null;
    picture?: string | null;
  };
}

export async function exchangeGoogleSession(session_id: string): Promise<GoogleSessionResponse> {
  const { data } = await api.post<GoogleSessionResponse>('/auth/google/session', { session_id });
  if (typeof window !== 'undefined') {
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    if (data.user?.picture) localStorage.setItem('avatar_url', data.user.picture);
    if (data.user?.name) localStorage.setItem('display_name', data.user.name);
  }
  return data;
}

export async function fetchGoogleAuthConfig() {
  const { data } = await api.get('/auth/google/config');
  return data as {
    provider: string;
    configured: boolean;
    signup_mode: 'invited_only' | 'auto_pending' | 'auto_partner';
    allowed_domains: string[];
    auth_url: string;
    preview_stub?: boolean;
  };
}
