# TALBROS SECURITY AWARENESS CENTER — PRD

## Original Problem Statement

Full-stack enterprise Security Awareness & Phishing Simulation platform for TALBROS. Authorized IT/Security team runs controlled internal phishing-awareness simulations and measures employee recognition of suspicious emails/links/forms. Requires real frontend + backend + DB + auth, recipient/department management, email composition, authorized sending, sender-identity simulation (preview/sandbox), unique per-recipient tracking, landing pages, awareness forms, analytics, reports, audit logs, sandbox mode, security controls. Nothing hard-coded — all config dynamic and editable via UI.

## Architecture

- **Frontend**: React (CRA + craco), Tailwind + shadcn/ui, recharts, lucide-react, sonner. Dark enterprise theme (Outfit/Manrope/JetBrains Mono).

- **Backend**: FastAPI, all routes under `/api`. Modules: `server.py` (routes), `security.py` (bcrypt + JWT cookies + auth dep), `email_service.py` (Resend + safe-content gate), `db.py` (Motor/Mongo).

- **DB**: MongoDB. Collections: users, departments, recipients, senders, simulations, simulation_recipients, simulation_events, landing_pages, forms, form_submissions, audit_logs, settings, login_attempts.

- **Auth**: JWT httpOnly+secure+samesite=none cookies; 5-attempt lockout; admin seeded from env, password reset deterministically on startup.

## User Personas

- **Security Administrator** (admin role): creates simulations, manages recipients/departments/senders/landing pages/forms, launches sends (sandbox or live), views analytics/timelines, exports reports, manages retention.

## Core Requirements (static)

- No campaign-name field; auto SIM-YYYY-NNNNNN id. Multiple recipients per simulation; optional department; no mandatory display name. Unique crypto-random token per recipient (no PII/DB-id in tracking URLs). Truthful delivery status. Simulated spoofed sender identity is preview/sandbox only (never bypass SPF/DKIM/DMARC). Forms never collect secrets/credentials.

## Implemented (2026-09-01)

- JWT admin auth (login/logout/me/refresh), protected routes, audit logging, rate-limit lockout.

- Recipients: single/bulk/CSV-import (validate + preview valid/invalid/duplicate + confirm), search, department filter, edit, enable/disable, delete.

- Departments: create/rename/delete/search with recipient counts.

- Email senders: CRUD, ACTIVE/DISABLED; seeded editable default.

- Create Simulation: multi-recipient, sender select, subject, rich-text body (uncontrolled contentEditable + templates), destination URL, 5 tracking toggles, sender-identity simulation (preview), landing/form select, sandbox/live mode, schedule, live email preview, Send Test, Send Now, Save Draft (PUT persists edits).

- Sending: sandbox simulates events; live delivers real tracked email via configured Resend provider under authorized identity (safe-content gate; spoofed identity refused for live).

- Tracking (public, tokenized): open pixel, click redirect, landing page visit, form start, form submit. Per-recipient counters + full event timeline.

- Analytics: dashboard KPI cards + rates + charts (activity, opens vs clicks, department perf, recent activity/simulations); department analytics; empty states.

- Reports: CSV export (simulation summary, recipient, department, event).

- Audit logs with action filter. Settings: retention (30/90/180/365) + expired-data purge + default mode.

- Public landing page `/lp/{token}` renders awareness page + optional form.

- Mobile nav drawer; responsive layout.

- Verified: backend 43/43 pytest; all reported bugs fixed (login, reversed rich-text typing, mobile nav, stale-draft send).

## Backlog / Remaining

- **P1**: Replace native selects/datetime/window.confirm with shadcn Select/date-picker/AlertDialog; fix `<span>`-in-`<option>` console warning.

- **P2**: Dashboard activity via Mongo aggregation (scale); split server.py into routers; preserve recipient tokens on draft PUT; recipient_groups; lifespan handler instead of on_event.