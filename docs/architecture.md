# Architecture

Agent Training Suite is a local cross-platform training suite made of three independent applications:

- Email app on `127.0.0.1:8011`;
- Email MCP server on `127.0.0.1:8111/mcp`;
- Todo App on `127.0.0.1:8012`;
- Calendar App on `127.0.0.1:8013`.
- Calendar MCP endpoint on `127.0.0.1:8013/mcp`.

## Core Principle

Each application runs as a separate process with its own UI, REST API, and SQLite database.

```text
NiceGUI UI
  -> Service layer
  -> Repository layer
  -> SQLite database

FastAPI REST API
  -> Service layer
  -> Repository layer
  -> SQLite database

Email MCP server
  -> MCPServer tools
  -> Email app REST API
  -> Email app service layer
  -> Email app repository layer
  -> Email app SQLite database

Calendar MCP endpoint
  -> MCPServer tools
  -> Calendar service layer
  -> Calendar repository layer
  -> Calendar SQLite database
```

The UI and API use the same service layer. The UI does not run SQL queries directly.

## Application Isolation

- Email app uses `data/email.db`.
- Email MCP server is a separate Uvicorn process. It does not connect to SQLite directly; future MCP tools should call the Email app REST API.
- Todo App uses `data/todo.db`.
- Calendar App uses `data/calendar.db`.
- Calendar MCP is mounted inside the Calendar App process and uses the same session factory as the Calendar API. Future tools should create a short-lived session per call and must not store a SQLAlchemy `Session` between MCP calls.
- Business models are not moved into `shared`.
- Applications do not import each other's business code.

## Shared Layer

`shared/` contains only technical utilities:

- base configuration;
- shared API error format;
- health endpoint helper;
- logging setup;
- timezone-aware and local-naive datetime helpers;
- SQLAlchemy types for UTC-aware and local-naive datetimes;
- shared UI application status block.

## Dates And Time

Email and Todo datetimes are accepted as timezone-aware values. SQLite stores them as UTC ISO strings through `shared.sqlalchemy_types.UTCDateTime`.

Calendar datetimes are intentionally local naive values. Calendar API, UI, and MCP tools use values such as `2026-08-27T15:00:00` to mean 15:00 local time, without timezone offsets or UTC conversion. SQLite stores these calendar values as local ISO strings through `shared.sqlalchemy_types.LocalNaiveDateTime`.

## Database Initialization

Each application has a separate Alembic configuration:

- `apps/email_app/alembic.ini`;
- `apps/todo_app/alembic.ini`;
- `apps/calendar_app/alembic.ini`.

The user does not need to run migrations manually. On startup, each application checks whether its SQLite database file exists. If it does not exist, the application applies its own Alembic migration automatically and creates the required tables.

## Demo Data And Reset

Data is created only by an explicit command:

```bash
python -m scripts.seed_demo_data
```

Reset local SQLite databases:

```bash
python -m scripts.reset_data
```

Reset deletes only SQLite files inside `data/`. The next application startup recreates the databases automatically.

## v1 Boundaries

v1 does not include LLMs, LangGraph, external services, authentication, real email, cloud deployment, or multi-user mode.
