# Preview environments proof of concept

A small TypeScript frontend and Python API for exercising database migrations,
browser checks and delivery. It runs locally with Docker Compose and publishes
matching immutable images/migration artifacts. Kubernetes acceptance wiring is
prepared; no application deployment to AKS has been proved.

[deploy/values.yaml](deploy/values.yaml) owns the application chart values for the
manual acceptance caller: components, selected artifacts, database requests and
access migrations. It contains no passwords. The hostname is an example; GitOps
supplies the environment binding. The values deliberately select the verified
artifact set from source `a429264`, independently of this deployment-config commit.

[deploy/application.yaml](deploy/application.yaml) owns the Argo registration and
environment binding. [deploy/credentials.yaml](deploy/credentials.yaml) supplies
credential settings to the reusable application chart. GitOps contains shared
platform packages only; no application registration or application values live there.
Registration/sync requires separate deployment approval. Automatic PR lifecycle and
deployed Testkube checks remain later work.

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

## Artifact publication

`.github/workflows/publish.yml` runs on PR updates, main pushes and manual runs.
It does not deploy anything. This caller owns its job graph and combined artifact
record: Docker builds use the existing shared template, while Atlas setup/tests/
publication use official actions. Checksum/replay validation calls the small shared action at merged commit
`7b7b2c3ab2552e5dc2fb7e954a090a63054981a4`. This credential-free replay runs
before the bot-token preflight; Pro tests and publication still require the bot.
Both images call the shared `ops-shared` workflow
at an immutable commit pin and explicitly select one source SHA: the PR head or
the push/manual event commit. Their tags are `preview-pr-N-SHA` on PRs and
`commit-SHA` otherwise. Publishing is limited to same-repository PRs and main.
Fork PRs and manual runs on other branches build images without publishing;
they replay migrations without an Atlas login and skip Pro lint/tests.

Publishing requires these GitHub Actions secrets, via existing organization
secret access or repository configuration:

- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`: the existing
  organization secrets for native Azure OIDC login. The image jobs request
  `id-token: write`; the identity needs matching GitHub federated trust and push
  access to `localacrk8s`. No JSON credential or client secret is required.
- `ATLAS_CLOUD_TOKEN`: an Atlas CI bot for `ai-platform-portfolio`, with permission
  to publish to the `preview-environments` migration repository. The first push
  creates that repository. A local user's Atlas login does not configure CI.

Same-repository PR authors must be trusted with those publishing credentials.
No production database credentials are provided to CI. `atlas.ci.hcl` pins the
Atlas organization and describes a disposable PostgreSQL 18.6 dev database;
the separate file keeps local Compose usable without a Cloud login. CI validates
the migration checksum/replay, lints changes relative to the event's Git base,
and runs native migration tests before publishing. Git comparison works before
the first main Registry baseline exists. Atlas CLI is pinned to 1.3.6 and actions
are pinned to commits.

The native Atlas push action publishes the migration directory under the same
full source SHA. PR pushes set `latest: false`; main pushes also advance the
Registry's `latest` baseline. Deployment must use
`atlas://preview-environments?tag=<full-source-SHA>`, never `latest`. Tagged-only
pushes do not upload the expected schema state used by Registry drift checks;
preview drift acceptance therefore still needs an explicitly configured dev
database and live operator testing. Image digests are immutable identities;
commit-named migration tags plus `atlas.sum` identify migration content. This
workflow does not configure Registry retention or server-enforced tag locking.

After all publishers succeed, `artifacts.json` records repository/source SHA,
workflow run/attempt, both image tags and digest references, and the migration
repository/tag/URL/checksum. It is uploaded as an Actions artifact named
`artifacts-SHA-runId-attempt`, retained for seven days. The record is refused if
revisions disagree, a digest is missing, or the migration checksum changed.
Partial publications can remain when another publisher fails; they produce no
complete record. No deployment selector is updated in this PR.

The workflow checks current open PR head (or current main head) before starting,
then rechecks after publishers finish. PR concurrency cancels superseded runs.
These checks cannot make GitHub head changes and artifact upload atomic. Future
consumers must require a successful run and compare the record's SHA with the
current PR head immediately before deployment or reporting a merge check.
Seven-day Actions record retention is separate from ACR/Atlas artifact retention.

Run the focused handoff checks locally with Python's standard library and `jq`:

```sh
python3 -m unittest discover -s tests -p 'test_publication.py' -v
```

### Fintech and proprietary-information boundary

This public portfolio deliberately uses hosted Atlas Registry: `migrate push`
uploads the migration SQL and schema information to Atlas. That is not an offline
or company-boundary deployment. CI licensing also involves identified usage and
error reporting; disabling anonymous telemetry is not a zero-egress guarantee.
[Atlas data collection documentation](https://atlasgo.io/cli/data-privacy).

For a fintech employer that prohibits customer or proprietary information leaving
its approved boundary, recommend assessing Atlas Enterprise's **custom offline
CI licence**, with migrations/plans stored in internal artifacts and operator
ConfigMaps instead of hosted Registry, and internally operated CI where required.
Confirm the licence and supported CLI/operator versions with Atlas, remove Cloud
reporting/Registry dependencies, restrict egress, and verify network behavior
before claiming zero vendor egress. An Enterprise licence alone does not redirect
`migrate push` to internal storage. This is an alternative employer deployment
recommendation, not a capability implemented or licensed by this portfolio.
[Atlas offline licensing guidance](https://atlasgo.io/faq/atlas-without-cloud).

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
