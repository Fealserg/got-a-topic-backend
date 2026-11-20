# Repository Guidelines

## Product and scope

«Есть тема» — conference networking by interests. Tagline: «Есть что обсудить. Осталось найти с кем.». Product messages/documentation are Russian. This repository owns FastAPI business logic and persistence; Next.js is a separate repository.

## Structure

`app/main.py`: routes, authorization and meeting rules. `app/schemas.py`: response/error contracts. `app/models.py`: database models. `app/database.py`: SQLite configuration and sessions. `app/seed.py`: reference/demo initialization. `alembic/`: migrations. `tests/`: isolated API and concurrency checks. `docs/`: specification, architecture, contexts, OpenAPI and prompts.

## Commands

Python 3.11+; deployment Python 3.12. `python3 -m venv .venv`; `.venv/bin/pip install -r requirements.lock`; `.venv/bin/alembic upgrade head`; `.venv/bin/python -m app.seed`; `.venv/bin/uvicorn app.main:app --port 8000`; `.venv/bin/python -m pytest tests -q`; `.venv/bin/alembic check`. Environment examples and demo instructions are in README.

## Invariants

All application paths begin `/api`. Swagger `/api/docs`, OpenAPI `/api/openapi.json`. Declare request/response schemas, use the common error envelope and preserve Retry-After. Never expose password/session hashes. Logs contain route templates, status, duration and input size; no bodies, query strings, credentials, IPs or participant names.

SQLite requires a writable persistent disk, one replica and one worker. Use BEGIN IMMEDIATE for writes. Accepting an invitation atomically reserves both users; `(user_id, slot_id)` is unique. Slots cannot overlap. Pending invitations do not reserve time. Recheck identity, visibility, availability and current time on the server.

## Changes and validation

For new routes update schemas, tests, specification and exported OpenAPI. For schema changes add an Alembic revision, do not silently recreate participant data. Focus tests on rights, state transitions, concurrency and persistence. TestClient uses a temporary database. Run focused tests then the relevant suite. A local test does not validate an external deployment.

Only explicit --demo creates synthetic profiles. Do not delete snapshots or real records without authorization. Commit .env.example, never .env/secrets/databases. Commit subjects are imperative; PRs explain problem, implementation, validation and limitations.
