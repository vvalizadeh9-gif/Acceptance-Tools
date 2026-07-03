# USO Platform — Project Handoff / Context

Prepared for continuation in Claude Code. This captures decisions and hard-won
gotchas from the chat history that produced this codebase — read this before
changing anything, especially the CPM import logic.

## What this is

Enterprise web platform for MTN Irancell's USO (Universal Service Obligation)
telecom deployment program: tracking site rollout, drive tests, ICT/CRA
regulatory acceptance, across 31 provinces / 9-10 regions. Owner (Vahid
Valizadeh) has no coding background — code must stay debuggable by an AI
assistant working with him interactively, not just "correct."

## Architecture

- **Backend**: FastAPI + SQLAlchemy 2.0 + PostgreSQL, JWT auth, Alembic migrations
- **Frontend**: React (plain JS, no TypeScript) + Vite, built to static files, served by Nginx
- **Deployment**: Docker Compose, 3 containers (db, backend, frontend/nginx), on a single Ubuntu 24.04 VPS at `5.202.6.30`
- **Nginx**: serves the React build AND reverse-proxies `/api/*` → backend:8000 (strips `/api` prefix)
- **Critical infra note**: Docker Hub is blocked from this server's IP (Iran-based). ALL images must use the ArvanCloud mirror: `docker.arvancloud.ir/library/<image>` instead of `<image>` directly. This applies to postgres, python, node, nginx base images.
- Nginx `client_max_body_size` is set to 50M (default 1M silently rejected the ~3MB real CPM file with no backend error — cost significant debugging time).

## Roles (6, not 4 — differs from an earlier architecture doc)

Admin (full control) / Project Manager (read-only dashboards) / DT Coordinator
/ Field Subcontractor (Contractor) / Regional Manager (scoped to one region) /
Viewer (read-only). Enforced server-side via `require_role()` dependency —
tested extensively, including that a non-admin genuinely gets 403, not just a
hidden UI button.

## CPM Import — hard-won business rules (import_cpm.py)

**Read this before touching the importer.** Several wrong assumptions were
made and corrected against the real file (`CPM_1_.xlsx` / `MTN-14050406.xlsx`):

1. **Sheet name varies** ("CPM" vs "Sheet1") — code auto-detects by probing for the required column, don't hardcode a sheet name.
2. **Header row is row 3** (index 2), not row 1 — there are 2 junk rows above it in every real export.
3. **Target/Hadaf filter is column AD, `هدف/ اقماری`** — NOT the column named "Village Type (MCI Tracker)" (that's a different, mostly-irrelevant column that was wrongly used initially). Filter is an **exact match** on `هدف` — excludes `اقماری` (satellite), `هدف (Verbally)`, `هدف (Removed Verbally)`. Only ~6,056 of ~9,839 rows are real targets — everything downstream must filter to this subset first.
4. **Site identity is hybrid**: prefer `کد سایت ایرانسل` (official Irancell ID) when it has a real value; fall back to `کدسایت موقت` (temp code) when official is blank OR literally the placeholder string `"No Site ID"` (which ~150 rows share — treating it as one shared value would wrongly collapse ~150 distinct real sites into one). The two ID formats never collide in practice (official looks like `CE0131`/`E1043`; temp looks like `AMUSONEW141`).
5. **Village code `---` is also a placeholder** (same pattern as "No Site ID") — never create a Village record for it, or unrelated villages sharing this placeholder get wrongly merged.
6. **"Villages" count = unique (Site, VillageCode) pairs**, not raw unique village codes — this matches the operational doc's own "Index 2" definition (Site+Village is the real regulatory tracking key). A pure global unique-village-code count is a *different*, smaller number — don't confuse the two.
7. **On-air status** comes from `آخرین مرحله انجام شده` (last stage), exact values `راه_اندازی_دائم` (permanent) or `راه_اندازی_موقت` (temporary) — note the underscores, not spaces.
8. **"Total On-Air"** (a key dashboard metric) = unique (Site, SiteType) pairs that are on-air — this is "Index 1" from the ops doc, modeled as the `WorkItem` table (site_id + site_type). NOT the same as total site count.
9. Requested-technology column values include `MW` (microwave/transmission — not a cellular acceptance technology, maps to zero acceptance rows, but the site/village still import normally).
10. **Import must be idempotent** (safe to re-run with an updated file) and **fast** — an earlier version did per-row DB queries (tens of thousands of round-trips) and took 30s–2min; rewritten to preload existing keys as lightweight column-only queries (not full ORM object hydration) and bulk-insert/bulk-update. Runs in ~7s cold, ~3s on re-import, for ~6,000 target rows.
11. Real column list (57 columns) — see `import_cpm.py` constants (`COL_*`) for exact Persian header strings currently mapped. Persian column names are NOT valid Python identifiers — never use `df.itertuples()` (it silently mangles them); use `df.to_dict("records")` instead.

## What's LIVE (built, deployed, tested against the real file)

- Auth (JWT, bcrypt — NOT passlib, which has an unfixed compatibility break with modern bcrypt versions)
- User Management (Admin-only): create/edit/deactivate all 6 roles, self-lockout guard, region_name-based scoping for Regional Manager (a plain string like "R9", matched against `Site.region_name` — NOT a Region table, doesn't exist yet)
- CPM import (Admin-only), with all rules above
- Sites & Villages: searchable/paginated/filterable table (province, region, on-air, search), with real province/region names (not raw UUIDs)
- **Per-role data scoping on `/sites`**: Contractor sees ONLY sites with an active assignment to them; Regional Manager sees only their region. This was the biggest closed security gap.
- Site Assignment: Admin/PM can bulk-... actually NOT bulk yet — currently ONE SITE AT A TIME (this was just flagged as inadequate UX by the user — see "Immediate next task" below). Assigns ALL work items under one site to one contractor at once; ends prior active assignment automatically.
- `/contractors` lightweight endpoint (Admin+PM) separate from full `/users` (Admin-only) so PM can pick a contractor without full user-management access.

## What's NOT built yet

Health Check submission, Drive Test workflow, ICT/CRA Acceptance, Letters,
Notifications, Action Center, the bottleneck/KPI dashboards, per-role
dashboards (see below — just specified in detail), HTTPS, backups, Alembic
CPM Change Review Center (risky CPM changes currently apply directly, no
pending-approval staging despite the `PendingChange` table existing unused).

## Immediate next task (specified by user, NOT YET BUILT — awaiting 2 answers)

User rejected one-at-a-time site assignment. Agreed direction (schematic
approved in principle, pending final review): an **Assignment Queue** —
sites that are on-air + DT not done + not currently assigned, bulk-selectable
via checkboxes, bulk-assign to one contractor in one action.

User will ALSO add 6 new column groups to CPM (one-time historical import,
then app-managed going forward):
1. Drive Test Status: Done / Ongoing / Problematic
2. DT Problematic Category: On-Site Issue / Temp Power / MS Responsibility / NWG Responsibility / Other (note: 5 categories now, not the earlier 4 — MS = "Managed Service")
3. Drive Test Subcontractor (historical, text)
4. ICT approval: 2G / 3G / 4G / Final / Comment / letter date / letter number
5. CRA approval: 2G / 3G / 4G / Final / Comment / Commitment / letter date / letter number
6. Depreciation Status: Depreciated / Waiting for Depreciation / Remain

**User has NOT yet sent this updated file — do not build the importer changes
until it's provided AND until the 2 open questions below are answered.**

Then, detailed **role-specific dashboards** were specified (verbatim, since
precision matters here):

**Project Manager** wants: project brief; On-Air vs DT-Done gap (+ Ongoing
qty, + Problematic qty per category); count of on-air-but-unassigned sites
(assignable queue, with province shown); Pending ICT approval (total + per
coordinator); Pending CRA approval (total + per coordinator); villages with
ICT-but-not-CRA approval; villages with CRA-but-not-ICT approval; this-month
ICT+CRA approvals (total + per person).

**DT Coordinator** wants (scoped to "their area" — see open question below):
sites/villages in their area; ICT approved/remained; CRA approved/remained;
ICT broken down by province; CRA broken down by CRA region.

**Contractor** wants: total sites/villages in scope; DT done (site+village);
pending; new assignments; ICT approved/remained (total + per province); CRA
approved/remained (total + per CRA region).

**Regional Manager** wants: total on-air per province (within their region,
under their PM); total DT; total CRA/ICT approval; remained, per province.

## Open questions — ANSWER BEFORE BUILDING THE ABOVE

1. **ICT/CRA "Final" field**: is it a computed result of 2G+3G+4G approval
   (i.e. Final = true when all requested techs are approved), or an
   independent manual flag someone sets separately? Affects whether "Final"
   needs its own column at all vs. being derived.
2. **DT Coordinator's "area"**: is it a fixed set of provinces/regions
   assigned to that person's account (like Regional Manager's region_name),
   or determined some other way (e.g. per-site coordinator assignment,
   similar to contractor assignment)? This determines whether we need a
   `coordinator_region_name` field on User (simple) or a whole assignment
   table (more like ContractorAssignment).

## Working conventions established with this user

- **No large unreviewed code dumps.** Build one complete feature at a time, test it (locally, against the REAL uploaded CPM file when data-related), then hand over deployable packages with exact deploy commands.
- User has no dev environment — everything is copy-paste terminal commands over SSH (Windows PowerShell client) or file upload/download through this chat. `scp` from Windows needs the source file referenced by bare filename from within its directory (`cd` first) — `C:\...` paths directly in the scp argument have caused repeated confusion (colon-parsing issues, and once a filename typo `uso_backedn.tar.gz`).
- Always test schema migrations against a simulated **pre-existing populated database** (via raw SQL matching the old schema, not the current ORM models) before shipping — SQLite (local dev) needs `batch_alter_table` for column alters; Postgres (production) doesn't but must be given `server_default` for any new NOT NULL column since real data already exists in most tables by now.
- User will push back hard (correctly) on wrong assumptions — several real bugs were caught by him cross-checking against his own Excel pivots (wrong site-ID column, wrong village-type column, a duplicate-row crash at real data volume that didn't show up in small samples). Treat his corrections as authoritative on business logic; he treats correctness over speed.
- Style: dark navy sidebar (`#0f1b2d`), slate canvas (`#1a2332`), blue accent (`#2563eb`) — matches his existing "Budget Tool" aesthetic that he explicitly approved. An earlier NOC/alarm-panel dashboard style was explicitly rejected — don't revisit that direction.
