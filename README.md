# Preview environments proof of concept

A small TypeScript frontend and Python API for exercising database migrations,
browser checks and delivery. This PR runs locally with Docker Compose. Kubernetes
delivery, artifact publication, preview lifecycle and deployed Testkube checks are
separate work; this repository does not yet deploy the application to AKS.

## Run locally

Requires Docker Compose v2 supporting `up --wait`, OpenSSL, and Node 24 for browser
checks. PostgreSQL 18.6 and Atlas 1.3.6 are pinned by image digest. The API uses
Psycopg 3 with parameterised SQL; its binary distribution avoids adding a compiler
or system libpq to the slim runtime image. There is no ORM or second migration
framework. See [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).

```sh
./scripts/local-env.sh
docker compose up --build -d --wait
```

The setup script creates an ignored `.env` with random local passwords and mode
0600; rerunning it preserves existing credentials. Do not regenerate it while
retaining the database volume: the PostgreSQL init script runs only on first
initialisation. Local PostgreSQL is reachable only on the Compose network and uses
unencrypted local connections. Kubernetes delivery must use verified TLS and
Secret references, not these local settings.

Startup waits for PostgreSQL, runs Atlas as the restricted migrator, then waits
for API database readiness before starting the frontend. The API never creates
tables or runs migrations. Only the frontend publishes a host port, bound to
loopback (override with `FRONTEND_PORT`).

Open <http://localhost:8080>, enter a message and select **Save message**. Copy its
Message ID, reload the page, enter the ID and select **Read message**. The saved
text comes from PostgreSQL, not browser storage. `POST /api/messages` accepts
`{"text":"a message"}`; `GET /api/messages/{uuid}` returns the persisted record.
Text is trimmed and limited to 1–500 characters. Unknown IDs return 404; invalid
input returns 422; database errors return a generic 503 without connection details.

`/api/healthz` reports process health. `/api/readyz` checks connectivity and the
migrated table. API connections and SQL statements have three-second timeouts.

## Validate locally

Install the Playwright browser once:

```sh
cd frontend
npm ci
npx playwright install chromium
cd ..
```

Then run:

```sh
./scripts/test-local.sh
```

This builds the stack, runs API and actual runtime-login permission assertions,
seeds a record, reapplies migrations, restarts the API and verifies that record.
It briefly stops this Compose project's database to verify generic 503 responses
while process health remains successful, then restores it. Finally it builds the
frontend and runs Playwright through the frontend proxy to the real API/database.
The script restores PostgreSQL on failure during the outage checks; it leaves the
local stack available for inspection. It never targets an external database.

Use a distinct `COMPOSE_PROJECT_NAME` and `FRONTEND_PORT` if another instance is
running, and set `PREVIEW_URL` to the matching URL for Playwright. Playwright is a
frontend development dependency and is absent from runtime images. No deployed
Testkube or pre-merge integration check is added here.

Native migration validation uses Atlas CLI 1.3.6 and an Atlas login for lint/test:

```sh
atlas whoami
DEV_DATABASE_URL='docker://postgres/18.6/dev?search_path=public' atlas migrate lint --env local --latest 1
DEV_DATABASE_URL='docker://postgres/18.6/dev?search_path=public' atlas migrate test --env local
```

Atlas creates a separate disposable dev database for these checks. The native test
applies the migration, seeds a row and checks constraints. Before changing an
unpublished migration, run `atlas migrate hash --env local`; never edit a migration
that has been delivered to an environment. There is no automatic schema downgrade.

For a local dry run or status check without printing credentials:

```sh
docker compose run --rm migrate migrate apply --env local --revisions-schema atlas --dry-run
docker compose run --rm migrate migrate status --env local --revisions-schema atlas
```

## Database requirements and ownership

The migration is environment-independent SQL: one `public.messages` table with a
UUID primary key, bounded nonempty text and a timestamp. It contains no role
creation, passwords, environment-specific role names or database creation.

| Object/access | Local fixture | Kubernetes delivery requirement (not implemented here) |
| --- | --- | --- |
| Database lifecycle | PostgreSQL init creates `app` | CNPG owns each preview database |
| Roles and membership | `local/init.sh` creates test roles | Application chart values render scoped Atlas roles |
| Database owner | `app_owner`, no login | Explicit preview-specific owner role |
| Migrator | `app_migrator`, member of owner | Own migrated objects; direct TLS connection and separate Secret |
| Runtime | `app_runtime` | CONNECT, schema USAGE, SELECT/INSERT on messages only |
| Table and constraints | Versioned Atlas migration | Same immutable migration artifact through AtlasMigration |
| Atlas revision metadata | Private `atlas` schema | Keep inaccessible to runtime login |

The local fixture grants default SELECT/INSERT privileges on future `public`
tables created by the migrator. This makes the initial table accessible without
putting role names into its migration. It gives no runtime DDL, role management,
UPDATE, DELETE, database creation or access to Atlas revision metadata. UUIDs are
created by Python, so no sequence privileges are needed. The only table in the
application schema is `messages`.

Before Kubernetes delivery, establish equivalent database/schema/table grants
under one owner, including the role that actually creates tables. The current
chart's role-only AtlasSchema has permission management disabled; it does not
supply these SQL grants. That integration must be resolved explicitly in the
later delivery PR. This local fixture is not a production role-management layer,
and does not adopt or change existing platform database objects.

## Stop or reset

```sh
docker compose down
```

The named PostgreSQL volume preserves local records. To explicitly discard this
Compose project's disposable database and recreate it on the next startup:

```sh
docker compose down --volumes
```

Keep the same project name for validation and cleanup. This local volume removal
does not prove Kubernetes preview cleanup ordering or backup/recovery.
