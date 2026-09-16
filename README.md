# Zero-Downtime Database Migration Demo

A PostgreSQL 15 and FastAPI demonstration of changing `users.full_name` into
`first_name` and `last_name` while legacy and modern APIs coexist. Alembic manages
the schema, PostgreSQL triggers synchronize writes, and GitHub Actions checks
migration SQL and runs integration tests.

The frontend dashboard is included in the MVP. It is a single local workspace for the migration controls, both API versions, live user data, and request results. Interactive API documentation is available at `/docs`.

## Run the dashboard

The complete Compose environment serves the dashboard at **http://localhost:5173** and
proxies its requests to the API. The API remains available directly at
**http://localhost:8000/docs**.

```bash
docker compose up --build -d --wait
```

For frontend development with Vite:

```bash
cd frontend
npm ci
npm run dev
```

The Vite server proxies `/api/*` to `http://127.0.0.1:8000`. Build and browser-test
the dashboard with `npm run build` and `npm run test:e2e`.

## Start the backend

Prerequisites: Docker Engine or Docker Desktop with Docker Compose, and a free
local port 8000. Run these commands from the repository root.

```bash
docker compose up --build -d --wait
curl -sS http://localhost:8000/demo/status
```

Open **http://localhost:8000/docs**. The stage starts at `uninitialized`; startup
does not run migrations. PostgreSQL data persists in the project's named volume.
The API binds to loopback only, and PostgreSQL has no published host port.
If port 8000 is occupied, start with `API_PORT=8001 docker compose up --build -d --wait`
and substitute that port in the URLs below.

## Run the demonstration

Every request below can also be made through **Try it out** in `/docs`.

### 1. Initialize and create a legacy user

```bash
curl -sS -X POST http://localhost:8000/demo/migrations/next \
  -H 'Content-Type: application/json' -d '{"expected_stage":"uninitialized"}'
curl -sS -X POST http://localhost:8000/v1/users \
  -H 'Content-Type: application/json' -d '{"name":"John Smith"}'
curl -sS http://localhost:8000/v1/users
```

The `users` table contains `id`, `full_name`, and `created_at`. API v1 returns
`[{"name":"John Smith"}]`.

### 2. Expand the schema

```bash
curl -sS -X POST http://localhost:8000/demo/migrations/next \
  -H 'Content-Type: application/json' -d '{"expected_stage":"initial"}'
curl -sS -X POST http://localhost:8000/v1/users \
  -H 'Content-Type: application/json' -d '{"name":"Alice"}'
```

The new nullable columns exist. API v1 still works. API v2 is unavailable until
synchronization and backfill complete.

### 3. Synchronize, backfill, and use both versions

```bash
curl -sS -X POST http://localhost:8000/demo/migrations/next \
  -H 'Content-Type: application/json' -d '{"expected_stage":"expanded"}'
curl -sS http://localhost:8000/v2/users
curl -sS -X POST http://localhost:8000/v2/users \
  -H 'Content-Type: application/json' -d '{"first_name":"Ada","last_name":"Lovelace"}'
curl -sS http://localhost:8000/v1/users
```

API v2 sees John/Smith and Alice/empty-last-name. API v1 sees Ada Lovelace.
The trigger synchronizes inserts and SQL updates in both directions. It is
installed before backfill in the same migration transaction.

### 4. Retire v1, then contract

```bash
curl -sS -X POST http://localhost:8000/demo/v1/retire
curl -sS -X POST http://localhost:8000/demo/migrations/next \
  -H 'Content-Type: application/json' -d '{"expected_stage":"synchronized"}'
curl -sS -X POST http://localhost:8000/v2/users \
  -H 'Content-Type: application/json' -d '{"first_name":"Grace","last_name":"Hopper"}'
curl -sS http://localhost:8000/v2/users
```

Retirement drains in-flight v1 requests and persistently disables legacy
operations. Later v1 requests return **410 Gone**, including after API restarts.
The routes remain documented so retirement is visible to the future dashboard.
Contract checks retirement and data consistency before removing `full_name` and
the synchronization objects. The modern columns become required; empty last
names remain valid. API v2 continues working.

## API contract for the frontend

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/demo/status` | Current stage and permitted actions |
| POST | `/demo/migrations/next` | Apply exactly one predefined revision; send `expected_stage` |
| POST | `/demo/v1/retire` | Drain v1 requests and persist retirement |
| GET | `/v1/users` | List legacy names, ordered by ID |
| POST | `/v1/users` | Create with `{"name":"John Smith"}`; returns the name, HTTP 201 |
| GET | `/v2/users` | List modern name fields, ordered by ID |
| POST | `/v2/users` | Create with `{"first_name":"John","last_name":"Smith"}`; returns those fields, HTTP 201 |

Example status after synchronization:

```json
{
  "stage": "synchronized",
  "revision": "003",
  "v1_available": true,
  "v2_available": true,
  "v1_retired": false,
  "next_stage": "contracted",
  "can_migrate": false,
  "can_retire_v1": true,
  "controls_enabled": true
}
```

| Stage | Revision | v1 | v2 | Next action |
| --- | --- | --- | --- | --- |
| `uninitialized` | none | unavailable | unavailable | Initialize |
| `initial` | `001` | available | unavailable | Expand |
| `expanded` | `002` | available | unavailable | Synchronize and backfill |
| `synchronized` | `003` | available until retired | available | Retire v1, then contract |
| `contracted` | `004` | retired | available | Finished |

Read `/demo/status` after each action or error. `expected_stage` prevents stale
or repeated button clicks from advancing another step. Database locks serialize
control operations across workers. There is no arbitrary SQL execution endpoint.

Stage/database errors return `{"detail":"..."}`. Input validation returns
FastAPI's standard `detail` list.

- **403:** controls disabled.
- **409:** incorrect stage, concurrent migration, retirement required, database
  validation failure, or database lock/statement timeout.
- **410:** v1 retired.
- **422:** invalid input.
- **503:** unexpected database failure; inspect API logs for the cause.

## Tests and CI

```bash
docker compose build api
docker compose run --rm --no-deps api python -m scripts.check_migration_sql --generate
docker compose up -d --wait db
docker compose run --rm api python -m pytest -q
```

Tests use real PostgreSQL 15. Each database test creates a randomly named
`migration_test_*` database and removes only that database afterward. The
configured user needs `CREATEDB` permission; the local Compose user has it.
Tests preserve the interactive demo's users and migration stage.

Coverage includes staged migrations, cross-version reads/writes, data
preservation, name edge cases, conflicting writes, rollback, retirement,
disabled controls, contract gates, and SQL safety examples. Concurrency tests
observe actual PostgreSQL lock waits to establish that API reads/writes overlap
migration transactions and complete successfully afterward.

GitHub Actions runs the same build, checker, and tests on pushes and pull
requests. A passing pipeline does not deploy or approve a production migration.

### Inspect or check SQL explicitly

```bash
docker compose run --rm --no-deps api alembic upgrade 001:003 --sql > compatibility.sql
docker compose run --rm --no-deps -v "$PWD/compatibility.sql:/tmp/compatibility.sql:ro" \
  api python -m scripts.check_migration_sql --file /tmp/compatibility.sql
```

The checker rejects `DROP TABLE`, `DROP COLUMN`, `ALTER TABLE ... DROP`
(including optional `COLUMN` syntax), `TRUNCATE`, and table/column renames.
It handles case, whitespace, comments, and static statements inside dollar-quoted
function bodies. Dynamic `EXECUTE` is refused because the checker cannot verify
its effect. This is a conservative guardrail, not a complete SQL safety analyzer.

CI checks Alembic-generated compatibility revisions `002` and `003`. Contract
revision `004` is separate and tested only after retirement in the lifecycle.

## Alembic command-line alternative

On a fresh database, the equivalent commands are below. Choose the API or CLI
for each stage; do not repeat both workflows from the beginning on one database.

```bash
docker compose run --rm api alembic upgrade 001
# Create legacy users before continuing.
docker compose run --rm api alembic upgrade 002
docker compose run --rm api alembic upgrade 003
# Retire API v1 using POST /demo/v1/retire first.
docker compose run --rm api alembic upgrade 004
```

Do not start with `alembic upgrade head`: contract refuses to run until v1 has
been retired. These migrations are forward-only; no downgrade or data-recovery
feature is included.

## Configuration and operation

- `DATABASE_URL`: SQLAlchemy PostgreSQL URL for API and Alembic.
- `DEMO_CONTROLS_ENABLED`: defaults to `false` in Python. Local Compose explicitly
  enables it. This demo has no authentication; keep its controls on loopback.
- `TEST_DATABASE_URL`: optional administrative connection for creating isolated
  test databases; defaults to `DATABASE_URL`.
- `API_PORT`: local API port, default `8000`.

Compose credentials are fixed for this isolated local demonstration. PostgreSQL
has no published host port. Inspect rows and logs with:

```bash
docker compose exec db psql -U migration_demo -d migration_demo -c 'TABLE users;'
docker compose logs api
```

Stop containers while keeping data:

```bash
docker compose down
```

To repeat from scratch, these commands **delete this Compose project's stored
PostgreSQL data** and start a new empty environment:

```bash
docker compose down --volumes
docker compose up --build -d --wait
```

## Name rules and limits

Legacy names split at the first space after whitespace normalization:
`Mary Jane Watson` becomes `Mary` / `Jane Watson`; `Alice` becomes `Alice` / `""`.
Modern input preserves the chosen first/last boundary, including multi-word
first names. A later legacy name change uses the first-space split again.
Backfill preserves original legacy strings, IDs, and creation timestamps;
subsequent writes may normalize whitespace. Blank legacy/first names are rejected.
These are demonstration rules, not universal personal-name parsing.

PostgreSQL DDL still takes locks. This small-data example tests compatibility and
successful requests during migration; it does not prove production-scale zero
latency impact. Migration lock waits time out after 5 seconds and statements
after 30 seconds. Failed migrations roll back and can be retried. Backfill uses
one transaction, not production-scale batches.

The retirement marker controls this demo's API workers. It cannot detect
unrelated applications or external SQL clients. A real deployment must retire
all old application instances before removing the legacy column.

Implementation references: [PostgreSQL triggers](https://www.postgresql.org/docs/15/plpgsql-trigger.html),
[Alembic shared connections](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands),
and [FastAPI dependency cleanup](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/).
