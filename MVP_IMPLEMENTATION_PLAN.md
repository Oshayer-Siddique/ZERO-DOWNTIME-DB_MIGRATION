# Zero-Downtime Database Migration — MVP Implementation Plan

## 1. Goal and scope

Build the demonstration described in `MVP_PLAN.text`: migrate a PostgreSQL `users` table from `full_name` to `first_name` and `last_name` while legacy and modern API versions remain compatible during the transition.

Use the **Expand → Synchronize and Backfill → Contract** workflow. GitHub Actions must reject unsafe compatibility-phase migrations and run integration tests against a temporary PostgreSQL database.

### Included features

1. PostgreSQL 15 running with Docker Compose.
2. Initial `users` schema and API v1.
3. An additive migration introducing separate name columns.
4. Backfill of existing names.
5. API v1 and API v2 operating against the expanded schema.
6. Database-trigger synchronization between old and new name fields.
7. A simple SQL safety checker in CI.
8. Automated migration and API compatibility tests.

The final contract migration is included to complete the original plan's migration lifecycle. It runs only after the compatibility tests and retirement of v1 in the demonstration.

### Excluded features

No frontend, authentication, Kubernetes, Terraform, AWS deployment, multi-region database, replication, Kafka, huge datasets, monitoring stack, advanced migration tooling, or automatic production deployment.

## 2. Implementation decisions

| Area | Decision |
| --- | --- |
| Database | PostgreSQL 15 |
| Local environment | Docker Compose with database and FastAPI services |
| API | Python FastAPI |
| Database access | SQLAlchemy with a PostgreSQL driver |
| Migrations | Alembic revision files as the single source of truth |
| Synchronization | PostgreSQL row trigger; no application dual-write implementation |
| Testing | pytest integration tests using real PostgreSQL and FastAPI's test client |
| CI | GitHub Actions |
| SQL checking | Check SQL generated from Alembic's compatibility revisions |

### Fixed API contract

- `POST /v1/users`: accepts `{"name": "John Smith"}` and returns `{"name": "John Smith"}` with HTTP 201.
- `GET /v1/users`: returns a list such as `[{"name": "John Smith"}]` with HTTP 200.
- `POST /v2/users`: accepts `{"first_name": "John", "last_name": "Smith"}` and returns those fields with HTTP 201.
- `GET /v2/users`: returns a list such as `[{"first_name": "John", "last_name": "Smith"}]` with HTTP 200.
- List results use ascending user ID order for predictable tests.
- API v1 queries and writes only the legacy name column; API v2 queries and writes only the new name columns. Both can use `id` for ordering.
- No update, delete, search, pagination, or additional business endpoints.

### Name conversion rules

- Trim leading and trailing whitespace and collapse repeated whitespace.
- Split a legacy name at the first space: `Mary Jane Watson` becomes `Mary` and `Jane Watson`.
- A single-word name such as `Alice` becomes `first_name = 'Alice'`, `last_name = ''`.
- Join the new fields with one space, omitting an empty last name.
- Reject empty or whitespace-only legacy names and first names. Allow an empty last name.
- Preserve the original `full_name` value when backfilling old rows; normalize its derived fields only. Later writes may normalize the stored representations.
- These are explicit demonstration rules, not a general solution for real-world personal names.

## 3. Planned file structure

```text
.
├── MVP_PLAN.text
├── MVP_IMPLEMENTATION_PLAN.md
├── README.md
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── api/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── v1/
│   │   ├── __init__.py
│   │   └── users.py
│   └── v2/
│       ├── __init__.py
│       └── users.py
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_create_users.py
│       ├── 002_expand_name_fields.py
│       ├── 003_sync_and_backfill_names.py
│       └── 004_contract_remove_full_name.py
├── scripts/
│   └── check_migration_sql.py
├── tests/
│   ├── conftest.py
│   ├── test_migration_lifecycle.py
│   ├── test_name_synchronization.py
│   └── test_sql_safety.py
└── .github/
    └── workflows/
        └── migration-test.yml
```

## Phase 1 — Create the runnable environment

**Purpose:** Make the database and API environment reproducible locally and in CI.

### Tasks

1. Define the Python dependencies for FastAPI, the API server, SQLAlchemy, the PostgreSQL driver, Alembic, pytest, and the HTTP test client.
2. Add a Dockerfile for the Python application.
3. Add `docker-compose.yml` with PostgreSQL 15 and the API service.
4. Configure database credentials and connection settings for the local demonstration through environment variables.
5. Add PostgreSQL readiness checking so the API service can wait for a healthy database.
6. Create `api/database.py` for database connections and transaction handling.
7. Create the FastAPI application entry point and initialize Alembic with the same database configuration.
8. Keep migration execution explicit; application startup must not automatically migrate to the final contract revision.

### Completion criteria

- `docker compose up --build -d` starts PostgreSQL and the API service.
- A database connection succeeds from the application container.
- Alembic can connect to PostgreSQL.
- Starting the containers does not silently apply schema changes.

## Phase 2 — Build the original schema and legacy API

**Depends on:** Phase 1.

### Tasks

1. Create revision `001_create_users` with:
   - `id`: generated primary key.
   - `full_name`: required text.
   - `created_at`: timestamp with time zone, defaulting to the database's current time.
2. Implement `POST /v1/users` and `GET /v1/users` using only the legacy schema.
3. Apply the defined input validation and return the exact response fields listed above.
4. Commit successful inserts and roll back failed transactions.
5. Establish the integration test setup using a disposable PostgreSQL database.
6. Add tests that create and list legacy users at revision `001`.

### Completion criteria

- Alembic can create the initial schema from an empty database.
- API v1 creates and lists users before the new columns exist.
- Invalid blank names are rejected.
- Persisted users have IDs and creation timestamps.

## Phase 3 — Expand the schema without breaking v1

**Depends on:** Phase 2.

### Tasks

1. Create revision `002_expand_name_fields`.
2. Add nullable text columns `first_name` and `last_name` without dropping or renaming existing columns.
3. Insert legacy users before applying revision `002`.
4. Apply the revision with the v1 application still available.
5. Verify old rows and their original names remain unchanged.
6. Verify v1 can still insert and list users after expansion.

### Completion criteria

- All original columns and data remain available.
- The two new columns exist and can initially contain null values.
- v1 reads and writes succeed before and after expansion.

## Phase 4 — Add synchronization and backfill existing data

**Depends on:** Phase 3.

### Tasks

1. Create revision `003_sync_and_backfill_names`.
2. Define a PostgreSQL function and a `BEFORE INSERT OR UPDATE` row trigger that modifies the incoming row without issuing a recursive update.
3. Handle legacy writes: a new or changed `full_name` populates `first_name` and `last_name`.
4. Handle modern writes: new or changed name fields populate `full_name`. This must also satisfy the legacy column's required-value constraint on v2 inserts.
5. If both representations are explicitly changed to conflicting values in one write, reject the write. Normal API requests write only one representation.
6. Install the trigger before backfill so subsequent writes remain synchronized.
7. Backfill missing new fields using the defined split rule while preserving IDs, creation timestamps, row count, and existing `full_name` values.
8. Ensure the trigger recognizes legacy rows being populated during backfill and preserves their existing `full_name` values.
9. Verify no legacy row remains without its derived name fields.
10. Keep synchronization installation and backfill in the same migration transaction for this small-data MVP.

### Completion criteria

- Existing users have populated new fields.
- Writes using either representation produce a consistent row.
- SQL-level update tests verify both synchronization directions without adding API update endpoints.
- Single-word and multi-word names follow the documented rules.
- Backfill preserves original rows and legacy name values.

## Phase 5 — Add API v2 and prove coexistence

**Depends on:** Phase 4.

### Tasks

1. Implement `POST /v2/users` and `GET /v2/users` against the new columns.
2. Register both routers in the default FastAPI application after the compatibility migration is applied.
3. Verify a user created through v1 can be read through v2.
4. Verify a user created through v2 can be read through v1.
5. Verify pre-migration users remain readable through both versions.
6. Add a simple application setting to disable registration of the v1 router for the contract demonstration; the default compatibility mode keeps v1 enabled.

### Completion criteria

- Both versions operate against revision `003`.
- Each API writes its own name representation; the trigger performs synchronization.
- Both APIs return the same logical users in their respective response formats.
- No additional endpoints are introduced.

## Phase 6 — Implement the SQL safety check

**Depends on:** Phase 4; uses the completed compatibility migrations.

### Tasks

1. Add `scripts/check_migration_sql.py` to read an SQL file and report prohibited statements with a nonzero exit code.
2. Generate SQL from the Alembic upgrade range `001_create_users:003_sync_and_backfill_names`; do not maintain separate SQL migrations alongside Alembic revisions.
3. Reject compatibility-phase operations that drop a column, drop a table, truncate a table, or rename a column.
4. Make matching case-insensitive and handle multiline statements and comments so simple formatting changes do not bypass the checker.
5. Print the prohibited operation and a readable failure message.
6. Add focused tests for safe additive SQL and each prohibited operation, including lowercase and multiline examples.
7. Include a deliberately unsafe SQL fixture or test input containing `DROP COLUMN full_name` and verify rejection.
8. Keep revision `004` outside the compatibility check: it is the explicitly separate contract stage, after v1 is disabled. No general-purpose bypass flag is needed.

### Completion criteria

- The actual generated compatibility SQL passes.
- The destructive examples fail with a clear reason and nonzero exit status.
- The checker remains a limited guardrail; it does not claim to prove arbitrary SQL safe or lock-free.

## Phase 7 — Complete the contract migration

**Depends on:** Phases 5 and 6.

### Tasks

1. Create revision `004_contract_remove_full_name`.
2. Check that new name fields are populated before removing the legacy representation; fail if the required backfill is incomplete.
3. Disable the v1 router and retire the compatibility-mode application instance before running this revision in the demonstration.
4. Remove the synchronization trigger and its function, then drop `full_name`.
5. Keep API v2's queries independent of the removed column.
6. Verify v2 still creates and lists users, including all migrated users.
7. Document that database migration code cannot itself prove every old application instance has stopped; retiring v1 is an explicit prerequisite.

### Completion criteria

- `full_name` and the legacy synchronization objects are absent.
- `id`, `first_name`, `last_name`, and `created_at` remain available.
- Existing users are preserved and v2 reads and writes pass.
- The contracted application does not expose v1 routes.

## Phase 8 — Assemble the full automated migration tests

**Depends on:** Phases 2–7; extend the tests introduced in earlier phases.

### Main lifecycle test

1. Start with an empty disposable database.
2. Apply revision `001`.
3. Create representative users through v1 and record their database IDs, timestamps, and names.
4. Keep the v1 test application active while applying revision `002`.
5. Verify v1 reads and writes still work.
6. Apply revision `003` and verify the backfill.
7. Exercise v1 reads and writes repeatedly while the expand and backfill migrations execute on a separate database connection; record any request exceptions or non-success responses.
8. Enable v2 and verify both directions of cross-version visibility.
9. Verify row count, identities, timestamps, and expected name values.
10. Retire the compatibility application and start the application with v1 disabled.
11. Apply revision `004` while exercising v2 reads and writes.
12. Verify the final schema, preserved users, and successful v2 operations.

### Required focused cases

| Case | Expected result |
| --- | --- |
| Existing `John Smith` | v2 reads `John` and `Smith` |
| Existing `Alice` | v2 reads `Alice` and an empty last name |
| Existing `Mary Jane Watson` | v2 reads `Mary` and `Jane Watson` |
| Existing name with extra whitespace | Original legacy value survives backfill; new fields are normalized |
| Create user through v1 after backfill | v2 immediately sees derived fields |
| Create user through v2 | v1 immediately sees the joined name |
| Change legacy name using SQL | New fields synchronize |
| Change modern name fields using SQL | Legacy field synchronizes |
| Conflicting changes to both representations | Write is rejected |
| Apply compatibility migrations with active v1 requests | Requests succeed and data stays consistent |
| Apply contract with active v2 requests and v1 retired | v2 requests succeed |
| Dangerous compatibility SQL | Safety check fails |
| Contract after retiring v1 | v2 works and legacy column is absent |

### Completion criteria

- All tests pass against PostgreSQL 15, not an SQLite substitute.
- Tests apply revisions in stages, not only the final schema.
- Migration/request overlap is coordinated explicitly in tests rather than assumed from timing sleeps.
- The demonstration shows compatibility and successful requests for this workload. It does not claim PostgreSQL DDL takes no locks or guarantee zero latency impact at production scale.

## Phase 9 — Wire GitHub Actions and document the demonstration

**Depends on:** Phases 6–8.

### CI tasks

1. Add `.github/workflows/migration-test.yml` for pushes and pull requests.
2. Check out the repository and build the application/test image.
3. Generate compatibility migration SQL and run the safety checker first.
4. Start a fresh PostgreSQL 15 service using Docker Compose and wait for readiness.
5. Run the safety-checker tests and PostgreSQL integration tests.
6. Fail the job on unsafe SQL, migration errors, API failures, synchronization failures, or data-preservation failures.
7. Run the contract portion only after compatibility assertions pass.
8. Clean up the temporary containers and database volumes even when tests fail.

### README tasks

1. Explain the migration example and the three-stage workflow.
2. List Docker and Docker Compose prerequisites.
3. Provide exact commands to build/start the services and apply revisions `001`, `002`, `003`, and `004` individually.
4. Provide example v1 and v2 requests at the appropriate stages.
5. Explain how to disable v1 before contract and why `alembic upgrade head` must not be used at the beginning of the compatibility demonstration.
6. Provide exact commands for tests and SQL safety checking.
7. Explain the name-conversion rules, checker scope, and the small-data demonstration limit.
8. State that CI success means the configured checks passed; it does not deploy or authorize a production migration.

### Completion criteria

- A fresh checkout can run the documented demonstration.
- GitHub Actions runs the same migration and compatibility checks.
- An unsafe compatibility migration causes CI to fail.
- The completed valid migration sequence passes CI.

## 4. Execution order

```text
Phase 1: Environment
  → Phase 2: Initial schema and v1
  → Phase 3: Expand
  → Phase 4: Synchronization and backfill
  → Phase 5: v2 coexistence
  → Phase 6: SQL safety checker
  → Phase 7: Contract
  → Phase 8: Complete lifecycle tests
  → Phase 9: GitHub Actions and README
```

Complete each phase's acceptance criteria before moving to the next phase. Tests for an implemented feature are added with that feature; Phase 8 assembles and completes the overall lifecycle validation.

## 5. MVP definition of done

- [ ] Docker Compose runs PostgreSQL 15 and FastAPI.
- [ ] The original schema and v1 work before expansion.
- [ ] Expansion keeps the legacy schema usable.
- [ ] Existing data is correctly backfilled.
- [ ] Database triggers synchronize writes in both directions.
- [ ] v1 and v2 coexist successfully at the compatibility revision.
- [ ] The SQL checker rejects prohibited compatibility changes.
- [ ] Automated tests preserve data and exercise API requests during migrations.
- [ ] Contract completes only after v1 is retired, and v2 remains usable.
- [ ] GitHub Actions runs the safety and integration checks successfully.
- [ ] README instructions reproduce the complete demonstration.

No additional product features are required for MVP completion.
