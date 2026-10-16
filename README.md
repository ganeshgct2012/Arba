# ArBa – Promo Volume Planner

ArBa is a web application for **weekly promotion volume planning**. Planners
maintain a weekly baseline (in cases) per plan account and product, add
promotions on top of it, send them for approval, and ArBa produces a weekly
volume feed for **P10 Arete** (demand planning).

> **Status:** Prototype / MVP foundation. It runs locally with SQLite and demo
> data. SAP and P10 connectors are mocked; see [Known limitations](#known-limitations).

---

## Contents

1. [What the app does](#what-the-app-does)
2. [Tech stack](#tech-stack)
3. [Folder structure](#folder-structure)
4. [Prerequisites](#prerequisites)
5. [First-time setup](#first-time-setup)
6. [Running the app (daily)](#running-the-app-daily)
7. [First login and demo users](#first-login-and-demo-users)
8. [Frontend development mode](#frontend-development-mode)
9. [Configuration (environment variables)](#configuration-environment-variables)
10. [Business concepts and glossary](#business-concepts-and-glossary)
11. [File formats](#file-formats)
12. [Common tasks](#common-tasks)
13. [Troubleshooting](#troubleshooting)
14. [Known limitations](#known-limitations)

---

## What the app does

```
SAP S/4HANA ──(customer & product master)──▶ ArBa
                                              │
        Baseline (weekly cases) + Promotions (extra cases, approved)
                                              │
                                              ▼
                              P10 Arete weekly volume feed (XLSX)
```

| Screen | Purpose |
|---|---|
| **Weekly Volume** | Baseline grid: product × ISO week, in cases. Export to XLSX, edit, upload back. |
| **Promotions** | Create a promotion for a plan account: dates, tactic, products, total cases. Uplift = total − baseline. Approval workflow. |
| **Promo Calendar** | Promotions by sub-brand across ISO weeks, coloured by status. |
| **Sales History** | Last 52 weeks of actual sell-in. |
| **Volume Report** | Monthly view: actuals for past weeks, baseline + approved uplift for future weeks. |
| **Product Listing** | Which products are listed for which plan account. |
| **Configuration** (admin) | Users and access, master data upload, pipeline schedules, inbound/outbound files. |

### Promotion workflow

| UI label | Stored status | Who can move it |
|---|---|---|
| Entry | `NEW` | Planner / Approver creates |
| Planned | `SAVED` | Planner / Approver saves |
| Approval Pending | `CHANGED` | Planner / Approver confirms |
| Approved | `APPROVED` | **Approver only** |

A future **Approved** promotion can be reverted to **Planned** for editing.
Only **Approved** promotions contribute uplift to the P10 feed and reports.

### User roles

| Role | Can do |
|---|---|
| `ADMIN` | Everything, including Configuration |
| `APPROVER` | Plan and approve promotions for assigned accounts |
| `PLANNER` | Plan baselines and promotions for assigned accounts |
| `VIEWER` | Read only |

Users only see plan accounts assigned to them (per Sales Org).

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn, SQLite (standard library `sqlite3`) |
| Frontend | React 18, TypeScript, Vite |
| Auth | Local email/password (PBKDF2), signed session cookie, optional Microsoft Entra SSO |
| Files | CSV / XLSX import and XLSX export (no extra Python libraries needed) |

---

## Folder structure

```
Arbo_Clean/
├── backend/
│   ├── app/
│   │   ├── main.py            ← START HERE: creates FastAPI app, includes routers, serves frontend
│   │   ├── config.py          ← settings, paths, env vars, demo master data constants
│   │   ├── db.py              ← SQLite connection + table creation / migrations
│   │   ├── seed.py            ← demo data loaded on first run
│   │   ├── security.py        ← password hashing, session cookie signing
│   │   ├── deps.py            ← current user + permission checks (get_user, require_role…)
│   │   ├── schemas.py         ← request payload models (Pydantic)
│   │   ├── utils.py           ← ISO week / date helpers
│   │   ├── routers/           ← API endpoints, one file per screen
│   │   │   ├── auth.py            login, signup, logout, SSO
│   │   │   ├── bootstrap.py       data loaded after login
│   │   │   ├── baseline.py        Weekly Volume
│   │   │   ├── promotions.py      Promotions + approval workflow
│   │   │   ├── listing.py         Product Listing
│   │   │   ├── reports.py         Sales History, Volume Report, Promo Calendar
│   │   │   ├── files.py           Configuration › master data & files
│   │   │   ├── admin_users.py     Configuration › Access Management, audit
│   │   │   └── pipelines.py       Configuration › Batch Job Configuration
│   │   └── services/          ← business logic used by routers
│   │       ├── promotions.py      baseline over promo weeks, uplift
│   │       ├── p10_feed.py        P09 → P10 split, P10 feed rows
│   │       ├── pipeline_runner.py runs a pipeline (manual / scheduled)
│   │       ├── scheduler.py       background schedule + inactive-user job
│   │       ├── master_data.py     customer/product master import
│   │       ├── planning.py  access.py  audit.py  files.py  sso.py  xlsx.py
│   ├── tests/                 ← backend tests (to be added)
│   └── requirements.txt       ← Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.tsx            ← top bar, left menu, page switching
│   │   ├── main.tsx           ← React entry point
│   │   ├── api.ts             ← fetch helper for /api/v1
│   │   ├── types.ts           ← shared data types
│   │   ├── constants.ts       ← menu names, roles, weekdays
│   │   ├── utils.ts           ← shared helpers
│   │   ├── styles.css
│   │   ├── components/        ← Heading, LoginScreen
│   │   └── pages/             ← one file per menu
│   │       ├── WeeklyVolume.tsx  Promotions.tsx  PromoCalendar.tsx
│   │       ├── SalesHistory.tsx  VolumeReport.tsx  ProductListing.tsx
│   │       ├── PlanningPage.tsx  ← picks the page for the selected menu
│   │       └── configuration/    ← Configuration tabs
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts         ← dev server + proxy to backend
├── data/                      ← created at runtime: SQLite DB + arba_files (NOT in Git)
├── docs/
│   └── assumptions.md         ← business/implementation assumptions
├── .gitignore
└── README.md
```

Generated folders (not committed): `venv/`, `frontend/node_modules/`,
`frontend/dist/`, `data/`.

### Where to change what

| I want to change… | Backend file | Frontend file |
|---|---|---|
| Weekly Volume screen | `routers/baseline.py` | `pages/WeeklyVolume.tsx` |
| Promotions / approval flow | `routers/promotions.py`, `services/promotions.py` | `pages/Promotions.tsx` |
| Promo Calendar, Sales History, Volume Report | `routers/reports.py` | `pages/PromoCalendar.tsx`, `SalesHistory.tsx`, `VolumeReport.tsx` |
| Product Listing | `routers/listing.py` | `pages/ProductListing.tsx` |
| P10 feed calculation | `services/p10_feed.py` | – |
| Pipelines / schedules | `routers/pipelines.py`, `services/pipeline_runner.py`, `services/scheduler.py` | `pages/configuration/BatchConfiguration.tsx` |
| Users and access | `routers/admin_users.py`, `services/access.py`, `deps.py` | `pages/configuration/AccessManagement.tsx` |
| Master data upload | `routers/files.py`, `services/master_data.py` | `pages/configuration/MasterDataConfig.tsx` |
| Database tables | `db.py` | `types.ts` |
| Login / SSO | `routers/auth.py`, `security.py`, `services/sso.py` | `components/LoginScreen.tsx` |

**Rule of thumb:** routers receive the HTTP request and check permissions;
services hold the business logic; `db.py` owns the schema.

---

## Prerequisites

Install these once:

| Tool | Version | Check with | Download |
|---|---|---|---|
| Python | 3.11 or later | `python3 --version` | https://www.python.org/downloads/ |
| Node.js | 20 or later (LTS) | `node --version` | https://nodejs.org (macOS: choose **macOS Installer (.pkg)**) |
| Git | any | `git --version` | https://git-scm.com |
| VS Code | any | – | https://code.visualstudio.com |

> After installing Node.js, **close and reopen** the VS Code terminal so the
> `node` and `npm` commands are found.

---

## First-time setup

Open the `Arbo_Clean` folder in VS Code, then open a terminal
(**Terminal → New Terminal**). Run the commands one at a time.

### macOS / Linux

```bash
# 1. Create and activate a Python virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install backend dependencies
pip install -r backend/requirements.txt

# 3. Install and build the frontend
cd frontend
npm install
npm run build
cd ..
```

### Windows (PowerShell)

```powershell
# 1. Create and activate a Python virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install backend dependencies
pip install -r backend\requirements.txt

# 3. Install and build the frontend
Set-Location frontend
npm install
npm run build
Set-Location ..
```

> **Why the frontend build?** Browsers cannot run React/TypeScript (`.tsx`)
> directly. `npm run build` compiles it into plain HTML/JS in `frontend/dist`,
> which the Python server then serves. Re-run it whenever you change frontend code.

> `npm install` may show "vulnerabilities" or "install-scripts" warnings.
> These are safe to ignore for local development. **Do not** run
> `npm audit fix --force`; it upgrades major versions and can break the build.

---

## Running the app (daily)

From the `Arbo_Clean` folder:

**macOS / Linux**
```bash
source venv/bin/activate
python backend/app/main.py
```

**Windows (PowerShell)**
```powershell
.\venv\Scripts\Activate.ps1
python backend\app\main.py
```

Open **http://127.0.0.1:8171** in your browser.

| URL | What |
|---|---|
| http://127.0.0.1:8171 | Application |
| http://127.0.0.1:8171/docs | Interactive API documentation (Swagger) |
| http://127.0.0.1:8171/health | Health check |

Stop the server with **Ctrl + C**.

---

## First login and demo users

On the **very first run** (when `data/arba_volume_planner.sqlite3` does not
exist yet) the server creates the database, loads demo data and prints a
password in the terminal:

```
ArBa first-run password (admin@arba.local): xxxxxxxxxxxxxxxx
```

**Save this password.** It is printed only once.

All demo users share that password:

| Email | Role |
|---|---|
| `admin@arba.local` | ADMIN |
| `planner@arba.local` | PLANNER |
| `approver@arba.local` | APPROVER |
| `viewer@arba.local` | VIEWER |

To choose the password yourself, set `ARBA_INITIAL_PASSWORD` (at least 12
characters) **before** the first run, or [reset the database](#reset-the-database).

Demo data: 7 markets (DE, ES, PT, CH, NL, AT, BE), 6 plan accounts per market,
15 products (Kleenex, Scottex, Hakle, Huggies), one year of actuals and one
year of future baseline.

Other first-time behaviour:
- The first **non-demo** user who signs up becomes the global admin.
  Later sign-ups start as `VIEWER` until an admin assigns access.
- Users who have not logged in for **30 days** are deactivated automatically.

---

## Frontend development mode

Use this when changing React code, so the page reloads automatically without
running `npm run build` each time.

Terminal 1 – backend:
```bash
source venv/bin/activate
python backend/app/main.py
```

Terminal 2 – frontend:
```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**. Vite forwards `/api` and `/health` requests to
the backend on port 8171.

---

## Configuration (environment variables)

All settings are optional for local development.

| Variable | Default | Purpose |
|---|---|---|
| `ARBA_DB_PATH` | `data/arba_volume_planner.sqlite3` | SQLite database file |
| `ARBA_FILES_DIR` | `data/arba_files` | Root for `Inbound Queue`, `Inbound Processed`, `Outbound` |
| `ARBA_SECRET` | random on each start | Session signing key. **Set it**, otherwise everyone is logged out on restart |
| `ARBA_INITIAL_PASSWORD` | random (printed) | Password for demo users on first run (min. 12 chars) |
| `ARBA_HOST` | `127.0.0.1` | Server bind address |
| `ARBA_PORT` | `8171` | Server port |
| `ARBA_COOKIE_SECURE` | `0` | Set to `1` when served over HTTPS |
| `ARBA_ENTRA_TENANT_ID` | – | Microsoft Entra SSO (all four needed to enable SSO) |
| `ARBA_ENTRA_CLIENT_ID` | – | 〃 |
| `ARBA_ENTRA_CLIENT_SECRET` | – | 〃 |
| `ARBA_ENTRA_REDIRECT_URI` | – | 〃 |

Example (macOS):
```bash
export ARBA_SECRET="a-long-random-string-at-least-32-characters"
python backend/app/main.py
```

Example (Windows PowerShell):
```powershell
$env:ARBA_SECRET = "a-long-random-string-at-least-32-characters"
python backend\app\main.py
```

---

## Business concepts and glossary

| Term | Meaning |
|---|---|
| **Market** | Country, e.g. `AT` (Austria). Has a P10 Sales Org (`AT10`) and a plan mode. |
| **Plan mode** | `VOL` = baseline only; `PROMO` = baseline + approved promotion uplift. |
| **Plan account (L04)** | Customer level used for planning, e.g. Rossmann, Kaufland. |
| **P09** | Planning product (e.g. `P09-1001` Kleenex Facial Tissues 3-ply). |
| **P10 material** | SAP material number(s) under a P09. One P09 can have several P10s. |
| **P09 → P10 split** | Share % used to distribute P09 volume to P10 materials (must total 100%). |
| **Listing** | A product being sold at a plan account. Only listed products can be planned. |
| **ISO week** | Planning bucket, e.g. `2026-W42` (Monday–Sunday). |
| **CS** | Cases – unit for all volumes. |
| **Baseline** | Expected volume without promotion. |
| **Uplift / Lift** | Promotion total cases − baseline over the shipment weeks. |
| **Shipment dates** | `start_date`–`end_date`: when goods ship to the customer. |
| **Consumption dates** | `cons_start`–`cons_end`: when the promotion runs in store. |
| **Tactic** | Promotion type: Feature, Display, Price Promotion, Coupon. |
| **P10 Arete** | Downstream demand planning system that receives the weekly feed. |

### How the P10 feed is calculated

For every active plan account × listed product × future ISO week:

1. **Base** = baseline cases for that week.
2. **Lift** = for each approved promotion covering the week,
   `(total cases − baseline over the promo weeks) ÷ number of promo weeks`.
3. Split base and lift to P10 materials by share % (largest-remainder rounding,
   so whole cases add up exactly).
4. Write one row per material per week:
   `Start Date, End Date, Plan Account, Material Number, BaseVolume, LiftVolume,
   TotalVolume, PromoNumber, Consumption Start, Consumption End, Sales Org`.

---

## File formats

### Baseline workbook (Weekly Volume → export / upload)

| Column | Example |
|---|---|
| `Customer ID` | `12` |
| `Product P09` | `P09-1001` |
| `Week` | `2026-W45` |
| `Baseline Cases` | `120` |

Upload validates the account, listed products, future weeks only, and duplicate rows.

### Master data extracts (Configuration → Master Data), CSV or XLSX

- **Customer master:** market code or sales org, plan-account L04 code, plan-account name.
- **Product master:** P09 code, description, brand, P10 material number.
  Optional: sub-brand, category, material description, split share
  (shares per P09 must total 100%). One P09 may have several rows (one per P10).

Files are staged in `Inbound Queue`, validated, then moved to `Inbound Processed`.
Generated feeds are written to `Outbound`.

---

## Common tasks

### Reset the database
Stop the server, then delete the database and files, and start again
(a new first-run password is printed):

```bash
rm -rf data/*
python backend/app/main.py
```

### Rebuild the frontend after code changes
```bash
cd frontend
npm run build
cd ..
```

### Save your work to Git
```bash
git add .
git commit -m "Describe what you changed"
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `zsh: command not found: node` | Install Node.js LTS, then close and reopen the terminal. |
| Browser shows *"React frontend is not built"* | Run `npm install` and `npm run build` inside `frontend/`. |
| `ModuleNotFoundError: No module named 'fastapi'` | Activate the venv (`source venv/bin/activate`) and run `pip install -r backend/requirements.txt`. |
| `ImportError: cannot import name 'UTC' from 'datetime'` | Python is older than 3.11. Install Python 3.11+ and recreate the venv. |
| Forgot the first-run password | [Reset the database](#reset-the-database), or set `ARBA_INITIAL_PASSWORD` before resetting. |
| Logged out after every restart | Set `ARBA_SECRET` to a fixed value. |
| `Address already in use` (port 8171) | Another server is still running. Stop it with Ctrl + C, or use `ARBA_PORT=8172`. |
| `npm run build` fails with an **esbuild** error | Run `npm install-scripts approve esbuild`, then `npm install` and build again. |

---

## Known limitations

Prototype scope. Items to address in the MVP:

- **No tests** for the main backend yet.
- **Mock integrations.** SAP S/4 and P10 connectors are mocked; only file upload
  and XLSX feed generation work.
- **SQLite + one global lock.** Fine for local use, not for many concurrent users.
  Move to PostgreSQL for production.
- **Performance.** P10 feed and Volume Report run one query per account × product
  × week; needs bulk queries for real data volumes.
- **No financials.** No price, discount depth, trade spend, budget or ROI yet.
- **No forecasting.** Baseline and promotion volumes are entered manually.
- **Approval control.** An APPROVER can approve their own promotion; ADMIN bypasses
  role checks.
- **Consumption dates** are stored but not used in calculations.

See also [`docs/assumptions.md`](docs/assumptions.md).