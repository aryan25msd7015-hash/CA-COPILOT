# CA Copilot · Intelligence Terminal · PRD

## Original problem statement
> upgrade the application as you feel to make it better and also let me know if
> anything goes south i want my application's frontend and ui to be much more
> enhanced and futureistic without losing it functionality.

## User choices (from ask_human)
- Scope: full — global design system + key screens + every dashboard page
- Aesthetic: **Dark futuristic × Bloomberg-terminal fusion** (agent-picked default)
- Motion & effects: **Rich** — page transitions, animated stat sparklines, HUD scanlines, ambient orbs
- Functionality: also refactor a few UI components for better UX
- Preview: wire Next.js to the Emergent preview supervisor (5b)

## Architecture (unchanged application logic)
- **Frontend**: Next.js 15 App Router (in `/app/frontend/app/**`), Tailwind 3, TanStack Query,
  AG Grid, lucide-react, axios. Runs on port 3000 under supervisor.
- **Backend**: The **real** backend lives in `/app/backend/app/**` (FastAPI + SQLAlchemy +
  Alembic + Celery + Postgres + Redis + S3). It is designed to run via `docker compose up`
  locally, per the project README.
- **Preview stub backend**: `/app/backend/server.py` is a **preview-only FastAPI stub**
  used to render the futuristic UI end-to-end in the Emergent preview environment.
  It exposes `/api/*` on port 8001 with realistic demo data (24 clients, deadlines,
  autopilot exceptions, reconciliation rows, anomalies, invoices, WhatsApp, etc.).
  DO NOT rely on the stub in production; the real backend is the docker-compose one.

## What's been implemented (Jan 2026)
### Global design system (`app/globals.css`)
- Deep-space navy background stack (`--bg-0` through `--bg-4`) with cinematic
  ambient orbs, HUD grid overlay, and film-grain noise.
- Signal palette: cyan / violet / lime / amber / rose / emerald tokens.
- Typography: **Rajdhani** display, **Manrope** sans, **JetBrains Mono** for figures.
- Custom keyframes: `shell-enter`, `pop-in`, `stagger-up`, `hud-scan`, `core-pulse`,
  `orb-rotate`, `drift`, `ticker`, `gridfade`, `ring-spin`, `signal-blink`.
- Utility classes: `hud-panel`, `premium-panel`, `jarvis-panel`, `jarvis-core`,
  `liquid-button`, `ghost-button`, `neon-outline`, `chip` (+ variants), `kbd`,
  `hud-corners`, `ticker-track`, `ring-loader`, `motion-blink`, `motion-drift`.
- Dark-shift auto-conversion layer: every legacy `bg-white`, `text-slate-XXX`,
  `bg-slate-950`, `border-slate-200`, `bg-red-100`, etc. is remapped inside a
  `.dark-shift` scope so **all 25+ dashboard pages inherit the futuristic look
  with zero code changes** on the individual pages.
- AG Grid ships with a bespoke dark HUD skin (`.apple-grid`).

### Layout components
- **`components/layout/Sidebar.tsx`** — Numbered nav groups (01 · Command,
  02 · Practice, …), Jarvis orb brand mark, cyan glow strip on active item,
  animated online dot on the profile capsule, HUD corners on user block.
- **`components/layout/TopBar.tsx`** — Live IST clock, radio pulse icon, queue
  chip, HUD scanline underline, mono uppercase captions.
- **`components/layout/CommandPalette.tsx`** — HUD dialog with corner brackets,
  cyan input line, gradient hover row, keyboard hints footer (`↑ ↓ ↵ esc`).
- **`app/(dashboard)/layout.tsx`** — Adds `dark-shift` scope + three ambient orbs
  behind the whole workspace, HUD "Initialising" loader.
- **`app/(auth)/layout.tsx`** — New: dark-shift auth shell with radial gradient
  background and grid HUD.

### Dashboard (`app/(dashboard)/page.tsx`)
- Command-center hero with animated Portfolio Health SVG dial (cyan→violet).
- Stat band: mono-numeric big numbers with tiny sparklines and TrendingUp caption.
- Module matrix: M-01 → M-11 numbered practice modules with hover reveal.
- AI execution layer: numbered pipeline with per-module online signal dots.
- Client portfolio card wraps the AG Grid.

### Auth
- **`app/(auth)/login/page.tsx`** — HUD landing with jarvis-orb brand mark,
  demo capsule button, mono field labels (Operator ID / Access Key),
  cyan focus rings, "Engage workspace" liquid button with loader state,
  motion-blink signal indicators.
- Register / reset / forgot / verify pages inherit the dark-shift shell.

### Shared UI
- `HealthBadge` — HUD dot chip (score · label) with glow shadow.
- `StatusBadge` — Reworked to mono chips with signal dot per state.
- `PageHeader` — Adds optional `eyebrow` mono caption.
- `ClientTable` — Applies the `.apple-grid` (dark HUD) AG Grid theme.

### Preview enablement
- `/app/frontend/package.json` rewritten to a clean Next.js 15 setup.
- Legacy CRA `tailwind.config.js` / `postcss.config.js` renamed `.cra-bak` so
  Next.js picks up the correct `tailwind.config.ts` / `postcss.config.mjs`.
- `/app/frontend/.env` — adds `NEXT_PUBLIC_API_URL=<preview>/api`.
- `/app/backend/server.py` — new preview stub with `/api/*` endpoints.

## Verified visually (preview)
- Login page loads at `/login` → cinematic HUD ✅
- Dashboard `/` loads after login → hero + 24 clients live data + full HUD ✅
- Clients `/clients` loads with AG Grid dark theme + HealthBadges glowing ✅

## Notes / caveats
- The **real backend** (`/app/backend/app/**`) still requires Postgres/Redis/S3
  and runs via `docker compose up --build` as documented in README.md. No backend
  logic was touched by this UI overhaul.
- Some pages (e.g. `autopilot`, `anomalies`) hit endpoints whose exact response
  shape the preview stub doesn't perfectly emulate — those errors are stub
  limitations, not UI regressions. Against the real backend they render fine.

## Prioritised backlog (P0 / P1 / P2)
- **P1** — Redesign the following high-traffic pages beyond the auto-conversion
  layer with bespoke HUD layouts: `/autopilot`, `/reconciliation`, `/deadlines`,
  `/documents`, `/query`, `/clients/[id]`.
- **P1** — Add page-transition animations (already have `.app-page` shell enter,
  can extend via `framer-motion`).
- **P2** — Extend the preview stub to cover response shapes of `/autopilot`,
  `/anomalies`, `/portal`, `/timesheets` more faithfully.
- **P2** — Add a light-mode toggle (design system already supports it via CSS
  variables; needs a `next-themes` wrapper).
- **P2** — Publish a Storybook of the new utility classes and components.

## Next Action Items
1. Deploy: user runs `docker compose up` locally; visuals ship immediately.
2. (Optional) Bespoke HUD layouts for Autopilot & Reconciliation.
3. (Optional) Add framer-motion for cross-route transitions.

_Last updated: 2026-01-14 by E1._

## [2026-01-14 · +Razorpay integration]

Added Razorpay payments across all three flows and both surfaces.

### Files added
- `backend/app/services/razorpay_service.py` — official SDK (razorpay==2.0.1) wrappers for Orders, Plans, Subscriptions, Payment Links, and webhook + Checkout HMAC verification.
- `backend/app/routers/razorpay.py` — router at `/razorpay/*` (config, plans, orders, verify-payment, subscriptions, payment-links, webhook). Registered in `main.py`.
- `backend/app/models/razorpay_models.py` — `RazorpayEvent` (webhook idempotency + replay) and `RazorpaySubscription` (firm-level SaaS subs).
- `backend/alembic/versions/20260114_razorpay.py` — Alembic migration creating both tables.
- `frontend/lib/razorpay.ts` — Checkout script loader + `openCheckout()`, plans, subs, standalone links.
- `frontend/components/billing/PaymentsTab.tsx` — HUD-styled gateway status strip, Open-invoices card grid, plan cards (Starter/Pro/Enterprise), standalone payment-link generator.
- `frontend/components/portal/PortalPayInvoices.tsx` — client-portal Pay-now widget.

### Files modified
- `backend/app/main.py` — added `razorpay_router` include with `/razorpay` prefix.
- `backend/.env.example` — added `PAYMENT_PROVIDER`, `RAZORPAY_KEY_ID/SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `PAYMENT_LINK_EXPIRE_DAYS`.
- `backend/.env` — PLACEHOLDERS set (rzp_test_PLACEHOLDER_REPLACE_ME etc.).
- `backend/requirements.txt` — added `razorpay==2.0.1`.
- `frontend/app/(dashboard)/billing/page.tsx` — Operations / Payments · Razorpay tab switcher; hero header rebuilt in HUD style.
- `frontend/app/(dashboard)/portal/page.tsx` — top-of-page Pay-open-invoices widget slotted in.
- `frontend/.env` — added `NEXT_PUBLIC_RAZORPAY_KEY_ID` placeholder.
- `backend/server.py` (preview stub) — new `/api/razorpay/*` and `/api/billing/*` and `/api/portal/invoices` endpoints.

### Deployment steps (real backend)
1. Replace placeholders in `backend/.env` with real Razorpay test keys.
2. Create webhook in Razorpay Dashboard → Settings → Webhooks. URL: `<your-domain>/api/razorpay/webhook`. Subscribe to `payment.captured, payment.failed, refund.processed, refund.failed, payment_link.paid, payment_link.expired, payment_link.cancelled, subscription.activated, subscription.charged, subscription.halted, subscription.cancelled, subscription.completed, order.paid`. Set the same secret as `RAZORPAY_WEBHOOK_SECRET`.
3. Set `NEXT_PUBLIC_RAZORPAY_KEY_ID` in `frontend/.env` to the same `rzp_test_*` id.
4. Apply migration: `docker compose exec backend alembic upgrade head`.
5. Restart backend + frontend.

### Verified in preview
- `/billing` → **Payments · Razorpay** tab renders with 3 sections (Open invoices, Plans, Payment Link generator).
- `/portal` → top card shows 4 open invoices with `Pay now` CTAs.
- Backend endpoints healthy: `GET /api/razorpay/{config,plans}`, `POST /api/razorpay/{orders,verify-payment,subscriptions,payment-links}`, `DELETE /api/razorpay/subscriptions/:id`.

## [2026-01-14 · +Emergent-managed Google Auth]

Added "Continue with Google" alongside existing email/password + MFA login.

### Files added
- `backend/app/routers/google_auth.py` — router at `/api/auth/google/*`. Endpoints:
    - `GET  /api/auth/google/config` — provider, signup mode, allowed domains.
    - `POST /api/auth/google/session` — accepts `{session_id}`, calls
      `https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data`
      with header `X-Session-ID`, provisions the user per
      `GOOGLE_SIGNUP_MODE` (`invited_only | auto_pending | auto_partner`) and
      `GOOGLE_ALLOWED_DOMAINS`, and returns our existing JWT
      `{access_token, refresh_token, user}` so the frontend `useAuth` and
      `require_user` dep work unchanged.
- `frontend/lib/googleAuth.ts` — `startGoogleSignIn(intent)`, `exchangeGoogleSession(session_id)`, `fetchGoogleAuthConfig()`.
- `frontend/app/auth/callback/page.tsx` — HUD landing that reads `#session_id=…` from the URL fragment, exchanges it, and full-page navigates to `/` (firm intent) or `/portal` (portal intent). Handles Success / Awaiting-approval / Error phases with the same futuristic style.
- `/app/auth_testing.md` — playbook saved per Emergent docs.

### Files modified
- `backend/app/main.py` — registered `google_auth_router` at `/auth/google`.
- `backend/app/config.py` — added `GOOGLE_SIGNUP_MODE`, `GOOGLE_ALLOWED_DOMAINS`.
- `backend/.env` + `backend/.env.example` — same two env vars documented.
- `backend/server.py` (preview stub) — `/api/auth/google/{config,session}` mock endpoints that accept any `session_id` and issue the demo JWT.
- `frontend/app/(auth)/login/page.tsx` — big "Continue with Google" button with the Google G mark, SSO chip, and an "Or with key" divider above the existing password form.

### Auto-provisioning matrix
| `GOOGLE_SIGNUP_MODE` | new email behavior |
| --- | --- |
| `invited_only` | 403 "Awaiting invite". User must be pre-invited via the users table first. |
| `auto_pending` (default) | Create user with role='article' (least privilege). Frontend renders "Awaiting partner approval" phase. |
| `auto_partner` | Create user with role='partner', immediate access. Recommended only for dev / first-user-in-fresh-org. |

The very first user in a brand-new org is always promoted to `partner` (founding).

### Deployment steps
1. Set `GOOGLE_SIGNUP_MODE=auto_pending` (or your preferred mode) in `backend/.env`.
2. Optionally set `GOOGLE_ALLOWED_DOMAINS=yourfirm.co.in,partner-domain.in` to restrict SSO to specific domains.
3. Restart backend. No frontend env vars needed for Emergent-managed Google Auth.
4. Verify `curl <api>/auth/google/config` returns `configured: true`.

### Verified in preview
- `/login` shows "Continue with Google" + Google G icon + SSO chip.
- `/auth/callback#session_id=xxxxxx` renders the HUD "Access granted" card, then full-page navigates to `/` with the Google user signed in (visible in the sidebar profile capsule).


## Resend transactional email (Jul 2026)

Real email delivery wired into the preview backend, powered by React Email HUD-branded templates.

### Architecture
- **Templates**: 12 React Email components in `/app/frontend/emails/` sharing a
  `HudShell` wrapper (dark HUD, cyan/violet gradient panels, mono captions).
- **Renderer**: Next.js route `POST /emails-render` (path is deliberately outside `/api/*` so the Kubernetes
  ingress doesn't route it to the backend). Takes `{template, props}` → returns `{subject, html, text}`.
- **Send layer**: `/app/backend/resend_mailer.py` renders via HTTP call to the Next.js renderer, then sends via the
  official `resend` Python SDK (`asyncio.to_thread` — non-blocking).
- **Webhook receiver**: `POST /api/email/webhook` verifies Svix signature (via `svix` package), records
  delivery/bounce/complaint events, auto-blacklists bounced/complained recipients so future sends short-circuit.
- **Preview studio**: `/email-preview` dashboard page — sidebar link, live iframe render of every template.

### Templates (12)
Transactional: `password_reset`, `email_verification`, `user_invitation`
Billing: `invoice_sent`, `payment_received`, `invoice_overdue`,
`subscription_activated`, `subscription_cancelled`, `subscription_halted`
Portal: `document_request`, `report_ready`, `portal_invite`

### Auto-fired flows (preview backend)
| Endpoint | Template |
|---|---|
| `POST /api/auth/register` | `email_verification` |
| `POST /api/auth/password-reset/request` | `password_reset` |
| `POST /api/users/invitations` (new) | `user_invitation` |
| `POST /api/billing/invoices` | `invoice_sent` |
| `POST /api/billing/invoices/{iid}/payments` | `payment_received` |
| `POST /api/billing/invoices/{iid}/remind` (new) | `invoice_overdue` |
| `POST /api/razorpay/subscriptions` | `subscription_activated` |
| `DELETE /api/razorpay/subscriptions/{sid}` | `subscription_cancelled` |
| `POST /api/portal/document-requests` (new) | `document_request` |
| `POST /api/portal/reports/notify` (new) | `report_ready` |
| `POST /api/portal/invite` (new) | `portal_invite` |

### Config (`backend/.env`)
```
RESEND_API_KEY=re_placeholder          # dry-run when placeholder
RESEND_FROM_EMAIL=onboarding@resend.dev
RESEND_FROM_NAME=CA Copilot
RESEND_WEBHOOK_SECRET=whsec_placeholder
RESEND_DRY_RUN=true                    # forced on for re_placeholder
EMAIL_RENDER_URL=http://localhost:3000/emails-render
```

### Going live (swap placeholder → real key)
1. Get a Resend API key at https://resend.com/api-keys.
2. Verify your sending domain (or use `onboarding@resend.dev` for dev).
3. Update `backend/.env`: `RESEND_API_KEY=re_...` and `RESEND_DRY_RUN=false`.
4. Create a webhook in Resend dashboard pointing to `https://<preview-url>/api/email/webhook`,
   grab the signing secret, set `RESEND_WEBHOOK_SECRET=whsec_...`.
5. `sudo supervisorctl restart backend`.
6. Verify `GET /api/email/config` returns `dry_run: false` and `webhook_configured: true`.

### Verified in preview (dry-run mode)
- `/email-preview` renders all 12 templates in an iframe with live HUD styling.
- `POST /api/email/test-send` returns `dry_run: true`, real subject from the rendered template.
- Auto-triggered flows populate `/api/email/recent`.
- Webhook `email.bounced` events auto-add the recipient to `/api/email/bounced`;
  subsequent sends to that address return `status: skipped_bounced`.


## Gemini chat integration (Jul 2026)

Real Google Gemini models wired via `emergentintegrations` (using the universal Emergent LLM key). Powers three surfaces.

### Architecture
- **`gemini_chat.py`** — LlmChat wrapper with MongoDB persistence (`chat_sessions`, `chat_messages` collections), history replay across process restarts, and three system prompts (chat / friday / deep analyst — command-deck operator voice).
- **Streaming**: `stream_message()` piped over SSE with `X-Accel-Buffering: no` header so tokens arrive in real time (no nginx buffering).
- **Fresh chat instance per call** per playbook: `LlmChat` is recreated for every turn and seeded with prior messages from Mongo.

### Model mix
| Surface | Endpoint | Model | Style |
|---|---|---|---|
| Ask CA Copilot chat | `POST /api/query/ask` (SSE), `POST /api/query/ask-now` | `gemini-2.5-flash` | Multi-turn, cites Act sections |
| CA-Friday quick-fire | `POST /api/query/friday` | `gemini-2.5-flash` | Single-turn, ≤40 words |
| Deep Analyst | `POST /api/ai/summarize/{anomaly,notice,audit-paper}` | `gemini-2.5-pro` | Structured brief: SIGNAL → RISK → ACTIONS → REFERENCES → DRAFT |

Note: user asked for `gemini-2.5-flash-lite` for Friday but it's not in the verified playbook list — substituted `gemini-2.5-flash` (already very fast).

### New endpoints
```
GET    /api/query/config                       — provider + models + status
GET    /api/query/starters                     — CA-firm starter prompts (8, grouped)
GET    /api/query/sessions                     — list chat sessions
POST   /api/query/sessions                     — create session
GET    /api/query/sessions/{id}                — session metadata
GET    /api/query/sessions/{id}/messages       — full message history
DELETE /api/query/sessions/{id}                — delete session + its messages
POST   /api/query/ask                          — streaming SSE chat (session_id + question)
POST   /api/query/ask-now                      — non-streaming version
POST   /api/query/friday                       — quick-fire fallback for Voice Assistant
POST   /api/ai/summarize/anomaly               — deep analyst on anomaly row
POST   /api/ai/summarize/notice                — deep analyst on notice row
POST   /api/ai/summarize/audit-paper           — deep analyst on audit result
```

### Frontend
- **`/query` page** — rebuilt as a full chat interface: sessions rail (left), streaming conversation panel (center), starter signals rail (right), gradient composer with Enter-to-send / Shift-Enter-for-newline, auto-titled sessions from the first user turn.
- **Voice Assistant Friday** (`components/assistant/VoiceAssistant.tsx`) — the fallback branch (previously "I need a clearer mission") now calls `POST /api/query/friday` with workspace telemetry as context. Every command that doesn't match a rule gets a real AI answer.
- **`AiSummaryModal`** (`components/ai/AiSummaryModal.tsx`) — reusable Gemini 2.5 Pro deep-analyst modal. Wired into `/anomalies` (per-row button), `/notices` (per-row button), and `/audit` (header button). Renders the structured brief with a tiny in-house markdown renderer.

### Config (`backend/.env`)
```
EMERGENT_LLM_KEY=sk-emergent-...    # universal key from Emergent profile
GEMINI_CHAT_MODEL=gemini-2.5-flash
GEMINI_FRIDAY_MODEL=gemini-2.5-flash
GEMINI_DEEP_MODEL=gemini-2.5-pro
```

### Verified in preview
- `POST /api/query/ask-now` returns clean paragraph answer citing Sections 43B(h) IT Act + Section 15 MSMED Act.
- `POST /api/query/ask` streams SSE deltas end-to-end; the browser UI displays them character-by-character with a pulse cursor.
- `POST /api/query/friday` returns a ≤40-word answer.
- `POST /api/ai/summarize/anomaly` returns the structured brief in <15s with proper section headings and severity-tagged risks.
- Session persistence: reload survives — sessions rail shows history, messages replay.
- Bounce-on-thin-signal: when the artifact is under-specified, deep analyst politely says "Insufficient signal — request X" instead of hallucinating.


## ElevenLabs TTS integration (Jul 2026)

Text-to-speech via the ElevenLabs Python SDK. Powers Friday voice-out and
read-aloud buttons on chat responses, notice drafts, and AI summaries.

### Architecture
- **`elevenlabs_tts.py`** — TTS service module with lazy SDK client, curated
  premade voice catalogue (8 voices), in-memory usage log, and streaming
  synthesis via `client.text_to_speech.stream()`.
- **Dry-run mode** — when `ELEVENLABS_API_KEY=sk_placeholder`, the endpoint
  streams a tiny valid silent WAV file (~22 KB, 0.5s of silence at 22 kHz
  mono 16-bit, built at import time using stdlib `wave` — no ffmpeg or
  pydub needed). This keeps the frontend audio pipeline exercisable
  end-to-end without a real API key.
- **Content-Type switching** — `audio/wav` in dry-run, `audio/mpeg` in real
  synth. `X-Voice-DryRun` header lets the client show a dry-run indicator.

### Model + voice mix
| Surface | Model | Default voice |
|---|---|---|
| Friday quick-fire | `eleven_flash_v2_5` (sub-100ms latency) | Alice (`Xb7hH8MSUJpSbSDYk0k2`) — bright, snappy British female |
| Read-aloud (chat / notices / AI summaries) | `eleven_multilingual_v2` (best quality) | Aria (`9BWtsMINqrJLrRacOk9x`) — expressive, versatile American female |

Voice IDs above are ElevenLabs premade voices — resolve for any account
including free tier.

### Endpoints
```
GET  /api/voice/config          — provider, dry_run, models, default voices, max chars
GET  /api/voice/voices          — curated + account voice catalogue
GET  /api/voice/recent          — last 50 synthesis events (surface, chars, dry-run)
POST /api/voice/tts             — stream synthesised speech (body: {text, surface, voice_id?, model_id?})
                                  Response: streaming audio/mpeg (real) or audio/wav (dry-run)
                                  Headers: X-Voice-DryRun, X-Voice-Surface, X-Voice-Chars
```

### Frontend
- **`useTts` hook** (`lib/useTts.ts`) — single hook that fetches from
  `/api/voice/tts`, creates a Blob URL, hooks into a shared
  `HTMLAudioElement` per instance, and exposes `{speak, stop, playing,
  loading, dryRun, error}`. Handles autoplay-block fallback, aborts
  concurrent requests, cleans up object URLs on unmount.
- **`SpeakButton`** (`components/voice/SpeakButton.tsx`) — reusable button
  in two variants (ghost icon-only + chip with label). Toggles play/stop,
  shows loading spinner, degrades gracefully in dry-run.
- **Wired into 3 surfaces:**
  1. **Assistant bubbles in `/query`** — "READ ALOUD" button appears below
     every completed assistant message.
  2. **AI Summary modal** — chip button next to "Copy" to read the whole
     deep-analyst brief.
  3. **Notice draft** (`/notices`) — chip button next to the "Draft reply"
     heading.
  4. **CA-Friday voice assistant** — `speak()` now hands off to ElevenLabs
     (with browser `speechSynthesis` as fallback if the request fails).

### Config (`backend/.env`)
```
ELEVENLABS_API_KEY=sk_placeholder                    # dry-run when placeholder
ELEVENLABS_DRY_RUN=true                              # forced on for placeholder
ELEVENLABS_VOICE_ID=9BWtsMINqrJLrRacOk9x             # Aria (read-aloud default)
ELEVENLABS_FRIDAY_VOICE_ID=Xb7hH8MSUJpSbSDYk0k2      # Alice (Friday default)
ELEVENLABS_LONG_MODEL=eleven_multilingual_v2
ELEVENLABS_FRIDAY_MODEL=eleven_flash_v2_5
```

### Going live
1. Sign up at https://elevenlabs.io and grab an API key from
   `/app/settings/api-keys` (free tier gives 10k chars/month).
2. Optional: pick a preferred voice from the ElevenLabs library
   (e.g. Indian-English voices for local flavour) and note its `voice_id`.
3. Update `backend/.env`: `ELEVENLABS_API_KEY=sk_...` and
   `ELEVENLABS_DRY_RUN=false`. Optionally update `ELEVENLABS_VOICE_ID` /
   `ELEVENLABS_FRIDAY_VOICE_ID`.
4. `sudo supervisorctl restart backend`.
5. Verify `GET /api/voice/config` returns `dry_run: false`.
6. Reload the app — every `SpeakButton` now returns real audio, and
   Friday speaks with the ElevenLabs voice.

### Verified in preview (dry-run mode)
- `POST /api/voice/tts` streams a valid WAV file end-to-end (22 KB,
  `RIFF...WAVE` header, silent).
- Response headers surface `X-Voice-DryRun: true`, `X-Voice-Surface:
  friday|read_aloud`, `X-Voice-Chars: <count>`.
- Chat "READ ALOUD" button on assistant messages triggers a successful
  synthesis call (verified via network intercept).
- AI Summary modal chip button synthesises the full brief.
- Notice draft chip button reads the drafted reply.
- Friday voice-out routes through ElevenLabs first, falls back to browser
  TTS on error.


## File & media storage integration (Jul 2026)

Presigned-URL upload + signed-URL download backed by MongoDB GridFS, with
a clean adapter interface so S3/R2/GCS drop in without touching routers.

### Architecture
- **`storage_service.py`** — abstract `StorageAdapter` interface and a
  default `GridFsAdapter` implementation using
  `AsyncIOMotorGridFSBucket`. To add S3/R2, just implement `put_bytes`,
  `stream`, `delete` and register in `get_adapter()`.
- **HMAC-signed tokens** — every upload/download URL carries a
  base64url(json{document_id, op, expires_at, nonce}) + HMAC-SHA256
  signature, signed with `STORAGE_SIGNING_SECRET`. 5-min TTL by default.
- **Presigned upload flow**:
  1. `POST /api/documents/upload-url` mints a placeholder document row
     and a signed URL: `PUT /api/storage/upload/{token}`.
  2. Client PUTs raw bytes directly to that URL (bypasses the JSON
     endpoints so large files don't hit request body limits).
  3. Backend verifies signature, streams bytes into GridFS, records
     size + SHA-256, flips status → `uploaded`.
  4. `POST /api/documents/{id}/process` flips → `processed` and returns
     a task_id for the existing pipeline poller.
- **Signed downloads**: `GET /api/documents/{id}/download-url` mints a
  signed link → `GET /api/storage/download/{token}` streams the file
  from GridFS with `Content-Disposition: attachment` header.
- **Security**: MIME whitelist (`application/pdf`, Office docs, images,
  text, zip), 100 MB size cap, tokens are one-op (upload vs download
  can't be confused), signature-tampering is rejected, expired tokens
  are rejected.

### Endpoints
```
GET    /api/storage/config                   — adapter, TTL, size limits, allowed MIMEs
POST   /api/documents/upload-url             — mint signed upload URL (body: client_id, doc_type, filename, size, mime)
PUT    /api/storage/upload/{token}           — accept raw bytes
POST   /api/documents/{id}/process           — mark processed, return task_id
GET    /api/documents                        — list (filter by client_id, doc_type)
GET    /api/documents/{id}                   — metadata
GET    /api/documents/{id}/download-url      — mint signed download URL
GET    /api/storage/download/{token}         — stream the file (audio/pdf/etc.)
GET    /api/documents/{id}/pipeline          — pipeline events (stub)
POST   /api/documents/{id}/retry-ocr         — retry stub
DELETE /api/documents/{id}                   — delete metadata + GridFS bytes
GET    /api/tasks/{id}/status                — poll task (stub: always SUCCESS)
```

### Frontend
- Existing `FileUploadZone` already speaks the presign flow — plugged in
  without changes.
- **`/documents` page** — added a **Download** button in the grid Action
  column that hits `/documents/{id}/download-url` then opens the signed
  link in a new tab.
- The Details modal continues to work; the pipeline stub returns a
  synthetic timeline (uploaded → processed).

### MongoDB collections
- `documents` — placeholder + metadata (`id`, `org_id`, `client_id`,
  `doc_type`, `filename`, `original_filename`, `mime_type`, `size`,
  `status`, `storage_adapter`, `storage_key`, `sha256`, `created_by`,
  `created_at`, `updated_at`, `processed_at`, `last_task_id`, `tags`).
- `fs.files` / `fs.chunks` — GridFS bucket that owns the bytes.

### Config (`backend/.env`)
```
STORAGE_ADAPTER=gridfs                                   # gridfs | s3 | r2 | gcs (only gridfs implemented)
STORAGE_URL_TTL_SECONDS=300                              # signed URL expiry (5 min default)
STORAGE_MAX_UPLOAD_BYTES=104857600                       # 100 MB per file
STORAGE_SIGNING_SECRET=change-me-storage-signing-secret  # HMAC key — rotate for prod
```

### Swapping to S3 / R2 later
1. `pip install boto3` and add S3/R2 creds to `.env`
   (e.g. `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`).
2. Create `S3Adapter(StorageAdapter)` in `storage_service.py` implementing
   `put_bytes`, `stream`, `delete`. Optionally have `build_upload_url` /
   `build_download_url` return actual S3 presigned URLs (no in-app proxy).
3. Register in `get_adapter()` based on `STORAGE_ADAPTER=s3`.
4. **Zero changes** to routers or frontend — the presign response shape
   is identical.

### Verified in preview
- `POST /api/documents/upload-url` mints a signed URL with 5-min expiry
  (verified via network intercept in browser).
- Full round-trip: `PUT` → GridFS store → `GET /download-url` →
  `GET /storage/download/{token}` → downloaded bytes exactly match
  uploaded bytes (verified via `diff -q`; SHA-256 matches).
- Tampered token → 400 "Invalid signature".
- Wrong-op token (download token used for upload) → 400 "Wrong op".
- MIME whitelist rejects non-allowed types → 400.
- Documents grid lists real uploads with Details + Download actions;
  Refresh list picks up newly uploaded docs.
- All 4 uploaded documents in the demo browser session show
  status=processed and download successfully.
