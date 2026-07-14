# Auth Testing Playbook (Emergent Google Auth)

## Flow
1. Frontend redirects to `https://auth.emergentagent.com/?redirect=<origin>/auth/callback`
2. User lands back at `<origin>/auth/callback#session_id=<sid>`
3. Frontend posts `{session_id}` to `POST /api/auth/google/session`
4. Backend calls `GET https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data` with header `X-Session-ID: <sid>`
5. Backend receives `{id, email, name, picture, session_token}`
6. Backend applies GOOGLE_SIGNUP_MODE + GOOGLE_ALLOWED_DOMAINS logic:
   - `invited_only` → only users with a pending invitation may pass; otherwise 403 "awaiting invite"
   - `auto_pending` → create user with status='pending', return 202 "awaiting approval"
   - `auto_partner` → create/activate user with role='partner', return tokens
7. Backend issues the existing JWT `{access_token, refresh_token, user, org}` so the existing frontend `useAuth` hook + `require_user` dep just work.

## curl smoke tests

```bash
API=https://upgrade-preview-4.preview.emergentagent.com/api

# 1. Confirm the config endpoint reports Google Auth is ready
curl -sS $API/auth/google/config

# 2. Simulate the callback (replace SID_FROM_URL with the real fragment)
curl -sS -X POST $API/auth/google/session \
     -H 'Content-Type: application/json' \
     -d '{"session_id":"SID_FROM_URL"}'
```

## Preview stub (no real Emergent auth handshake)
The preview stub at `/app/backend/server.py` accepts ANY `session_id` and
returns a signed demo JWT. Real Emergent Auth handshake happens only when the
real backend (docker-compose) is running.

## Checklist
- [x] `/api/auth/google/config` returns `configured=true` and the correct signup mode
- [x] `POST /api/auth/google/session` with a valid session_id returns `{access_token, refresh_token, user, org}`
- [x] Domain allowlist rejects emails outside `GOOGLE_ALLOWED_DOMAINS`
- [x] `invited_only` mode returns 403 for uninvited emails
- [x] `auto_pending` mode creates user with status='pending' and returns 202
- [x] `auto_partner` mode creates + activates + returns tokens
- [x] Frontend `/auth/callback` reads `#session_id=...` from URL fragment, POSTs to backend, stores tokens, redirects to `/`

## Test identities (dev only)
See `/app/memory/test_credentials.md`.
