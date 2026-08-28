# Todo App API

Base URL:

```text
http://127.0.0.1:8012
```

OpenAPI UI:

```text
http://127.0.0.1:8012/docs
```

## General Rules

- Authentication is not used.
- Data format: JSON.
- All dates and times in responses are sent in ISO 8601 format with timezone information.
- Main task identifier: UUID string.
- When creating a task, `id` can be omitted and will be generated automatically.

## System Endpoints

### `GET /health`

Response `200`:

```json
{
  "status": "ok",
  "app_name": "Todo App",
  "version": "0.1.0"
}
```

## Task Model

### Response Fields

```json
{
  "id": "00000000-0000-4000-8000-000000000201",
  "title": "Prepare for the meeting",
  "description": "Collect materials and prepare questions.",
  "status": "open",
  "priority": "high",
  "completed_at": null,
  "created_at": "2026-08-06T15:00:00+00:00",
  "updated_at": "2026-08-06T15:00:00+00:00"
}
```

### Enum `status`

- `open`
- `in_progress`
- `completed`
- `cancelled`

### Enum `priority`

- `low`
- `normal`
- `high`
- `urgent`

## Endpoints

### `POST /api/tasks`

Create a task.

Request body:

```json
{
  "title": "Prepare for the meeting",
  "description": "Collect materials and prepare questions.",
  "priority": "high"
}
```

Optional fields:

- `id`: UUID string.
- `description`: defaults to an empty string.
- `priority`: defaults to `normal`.

Response:

- `201 Created`: Task.

### `GET /api/tasks`

Get a list of tasks.

Query parameters:

| Parameter | Type | Default | Description |
|---|---:|---:|---|
| `query` | string | `null` | Search by `title` and `description` |
| `status` | enum | `null` | Filter by status |
| `priority` | enum | `null` | Filter by priority |
| `limit` | integer | `100` | From 1 to 500 |
| `offset` | integer | `0` | Offset, starting at 0 |

Example:

```text
GET /api/tasks?status=in_progress&priority=high
```

Response:

- `200 OK`: array of Task objects.

### `GET /api/tasks/events`

Stream task changes as Server-Sent Events.

Events:

- `connected`: emitted when the stream is opened.
- `tasks_changed`: emitted after task create, update, complete, reopen, or cancel operations.

`tasks_changed` data:

```json
{
  "action": "completed",
  "task_id": "00000000-0000-4000-8000-000000000201",
  "status": "completed",
  "priority": "high"
}
```

Response:

- `200 OK`: SSE stream.

### `GET /api/tasks/{task_id}`

Get a task by ID.

Response:

- `200 OK`: Task.
- `404 Not Found`: task not found.

### `PATCH /api/tasks/{task_id}`

Partially update a task.

Allowed fields:

```json
{
  "title": "Updated title",
  "description": "Updated description",
  "status": "in_progress",
  "priority": "urgent",
  "completed_at": null
}
```

All fields are optional.

Business rules:

- if `status = "completed"`, `completed_at` is set automatically unless it is passed explicitly;
- if a task is moved to `open`, `in_progress`, or `cancelled`, `completed_at` is cleared.

Response:

- `200 OK`: Task.
- `404 Not Found`: task not found.

### `POST /api/tasks/{task_id}/complete`

Complete a task.

Response:

- `200 OK`: Task with `status = "completed"` and a populated `completed_at`.
- `404 Not Found`: task not found.

### `POST /api/tasks/{task_id}/reopen`

Reopen a task.

Response:

- `200 OK`: Task with `status = "open"` and `completed_at = null`.
- `404 Not Found`: task not found.

### `POST /api/tasks/{task_id}/cancel`

Cancel a task.

Response:

- `200 OK`: Task with `status = "cancelled"`.
- `404 Not Found`: task not found.

## Errors

Error format:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Task not found",
    "details": {
      "id": "missing"
    }
  }
}
```

Codes:

- `VALIDATION_ERROR`
- `NOT_FOUND`
- `CONFLICT`
- `DATABASE_ERROR`
- `INTERNAL_ERROR`
