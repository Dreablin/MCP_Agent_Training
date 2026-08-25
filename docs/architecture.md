# Architecture

Agent Training Suite is a local cross-platform training suite made of three independent applications:

- Email app on `127.0.0.1:8011`;
- Todo App on `127.0.0.1:8012`;
- Calendar App on `127.0.0.1:8013`.

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
```

The UI and API use the same service layer. The UI does not run SQL queries directly.

## Application Isolation

- Email app uses `data/email.db`.
- Todo App uses `data/todo.db`.
- Calendar App uses `data/calendar.db`.
- Business models are not moved into `shared`.
- Applications do not import each other's business code.

## Shared Layer

`shared/` contains only technical utilities:

- base configuration;
- shared API error format;
- health endpoint helper;
- logging setup;
- timezone-aware datetime helpers;
- SQLAlchemy type for UTC datetimes;
- shared UI application status block.

## Dates And Time

All meaningful datetimes are accepted as timezone-aware values. SQLite stores them as UTC ISO strings through `shared.sqlalchemy_types.UTCDateTime`.

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

v1 does not include MCP, LLMs, LangGraph, external services, authentication, real email, cloud deployment, or multi-user mode.
