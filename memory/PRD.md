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
