# Database Schema

The project uses three independent SQLite databases:

```text
data/email.db
data/todo.db
data/calendar.db
```

Each database belongs to one application. There are no shared tables between applications.

## General Storage Rules

- Primary identifiers are stored as UUID strings with a length of 36 characters.
- Meaningful dates and times are stored as ISO 8601 strings in UTC.
- Python code reads dates back as timezone-aware `datetime` values.
- SQLite files are local working data and must not be committed to Git.

## `data/email.db`

### Table `email_messages`

| Field | SQLite Type | Nullable | Description |
|---|---|---:|---|
| `id` | `VARCHAR(36)` | no | Primary key, email message UUID |
| `sender_name` | `VARCHAR(200)` | no | Sender name |
| `sender_email` | `VARCHAR(320)` | no | Sender email |
| `recipient_email` | `VARCHAR(320)` | no | Recipient email |
| `subject` | `VARCHAR(300)` | no | Message subject |
| `body` | `TEXT` | no | Message body |
| `received_at` | `VARCHAR(40)` | no | Receive time, ISO 8601 UTC |
| `folder` | `VARCHAR(20)` | no | `inbox`, `sent`, `spam`, `friends`, `work`, `logs`, `trash` |
| `is_read` | `BOOLEAN` | no | Read flag |
| `created_at` | `VARCHAR(40)` | no | Record creation time, ISO 8601 UTC |
| `updated_at` | `VARCHAR(40)` | no | Last update time, ISO 8601 UTC |

Primary key:

- `id`

Indexes:

- `ix_email_messages_folder` on `folder`
- `ix_email_messages_is_read` on `is_read`
- `ix_email_messages_received_at` on `received_at`

## `data/todo.db`

### Table `tasks`

| Field | SQLite Type | Nullable | Description |
|---|---|---:|---|
| `id` | `VARCHAR(36)` | no | Primary key, task UUID |
| `title` | `VARCHAR(300)` | no | Task title |
| `description` | `TEXT` | no | Task description |
| `status` | `VARCHAR(30)` | no | `open`, `in_progress`, `completed`, `cancelled` |
| `priority` | `VARCHAR(30)` | no | `low`, `normal`, `high`, `urgent` |
| `completed_at` | `VARCHAR(40)` | yes | Completion time, ISO 8601 UTC |
| `created_at` | `VARCHAR(40)` | no | Record creation time, ISO 8601 UTC |
| `updated_at` | `VARCHAR(40)` | no | Last update time, ISO 8601 UTC |

Primary key:

- `id`

Indexes:

- `ix_tasks_status` on `status`
- `ix_tasks_priority` on `priority`

## `data/calendar.db`

### Table `calendar_events`

| Field | SQLite Type | Nullable | Description |
|---|---|---:|---|
| `id` | `VARCHAR(36)` | no | Primary key, event UUID |
| `title` | `VARCHAR(300)` | no | Event title |
| `description` | `TEXT` | no | Event description |
| `start_at` | `VARCHAR(40)` | no | Event start, ISO 8601 UTC |
| `end_at` | `VARCHAR(40)` | no | Event end, ISO 8601 UTC |
| `timezone` | `VARCHAR(100)` | no | Timezone marker; defaults to `local`; can store a valid IANA timezone if explicitly provided |
| `status` | `VARCHAR(30)` | no | `confirmed`, `tentative`, `cancelled` |
| `location` | `VARCHAR(300)` | no | Event location |
| `participants` | `JSON` | no | Array of participants |
| `created_at` | `VARCHAR(40)` | no | Record creation time, ISO 8601 UTC |
| `updated_at` | `VARCHAR(40)` | no | Last update time, ISO 8601 UTC |

Primary key:

- `id`

Indexes:

- `ix_calendar_events_status` on `status`
- `ix_calendar_events_start_at` on `start_at`
- `ix_calendar_events_end_at` on `end_at`

### `participants` Format

`participants` is stored as a JSON array of objects:

```json
[
  {
    "name": "Anna",
    "email": "anna@example.test"
  }
]
```

## Schema Initialization

Each application owns one Alembic configuration:

```text
apps/email_app/alembic.ini
apps/todo_app/alembic.ini
apps/calendar_app/alembic.ini
```

The user does not need to run migrations manually. When an application starts and its SQLite file does not exist, the application creates the database and required tables automatically.

Reset local databases:

```bash
python -m scripts.reset_data
```

After reset, the next application startup recreates the required database and tables.
