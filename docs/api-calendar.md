# Calendar App API

Base URL:

```text
http://127.0.0.1:8013
```

OpenAPI UI:

```text
http://127.0.0.1:8013/docs
```

## General Rules

- Authentication is not used.
- Data format: JSON.
- All dates and times are sent in ISO 8601 format with timezone information.
- Main event identifier: UUID string.
- When creating an event, `id` can be omitted and will be generated automatically.

## System Endpoints

### `GET /health`

Response `200`:

```json
{
  "status": "ok",
  "app_name": "Calendar App",
  "version": "0.1.0"
}
```

## Calendar Event Model

### Response Fields

```json
{
  "id": "00000000-0000-4000-8000-000000000301",
  "title": "Meeting with Anna",
  "description": "Discuss the training project.",
  "start_at": "2026-08-12T19:30:00+00:00",
  "end_at": "2026-08-12T20:30:00+00:00",
  "timezone": "local",
  "status": "confirmed",
  "location": "Office",
  "participants": [
    {
      "name": "Anna",
      "email": "anna@example.test"
    }
  ],
  "created_at": "2026-08-06T15:00:00+00:00",
  "updated_at": "2026-08-06T15:00:00+00:00"
}
```

### Enum `status`

- `confirmed`
- `tentative`
- `cancelled`

### Participant

```json
{
  "name": "Anna",
  "email": "anna@example.test"
}
```

## Endpoints

### `POST /api/events`

Create an event.

Request body:

```json
{
  "title": "Meeting with Anna",
  "description": "Discuss the training project.",
  "start_at": "2026-08-12T14:30:00-05:00",
  "end_at": "2026-08-12T15:30:00-05:00",
  "participants": [
    {
      "name": "Anna",
      "email": "anna@example.test"
    }
  ]
}
```

Optional fields:

- `id`: UUID string.
- `description`: defaults to an empty string.
- `timezone`: defaults to `local`.
- `status`: defaults to `confirmed`.
- `location`: defaults to an empty string.
- `participants`: defaults to an empty array.

Rules:

- `start_at` and `end_at` must include timezone information;
- `end_at` must be later than `start_at`;
- if provided, `timezone` must be `local` or a valid IANA timezone.

Response:

- `201 Created`: Calendar Event.

### `GET /api/events`

Get a list of events.

Query parameters:

| Parameter | Type | Default | Description |
|---|---:|---:|---|
| `query` | string | `null` | Search by title, description, location, and participants |
| `status` | enum | `null` | Filter by status |
| `starts_before` | datetime | `null` | Event starts before the specified time |
| `ends_after` | datetime | `null` | Event ends after the specified time |
| `include_cancelled` | boolean | `true` | Include cancelled events |
| `limit` | integer | `100` | From 1 to 500 |
| `offset` | integer | `0` | Offset, starting at 0 |

To get events that overlap a period, use the pair:

```text
starts_before={period_end}&ends_after={period_start}
```

Response:

- `200 OK`: array of Calendar Event objects.

### `GET /api/events/overlaps`

Find events overlapping a given time range.

Query parameters:

| Parameter | Type | Required | Description |
|---|---:|---:|---|
| `start_at` | datetime | yes | Start of the checked range |
| `end_at` | datetime | yes | End of the checked range |
| `exclude_event_id` | string | no | Exclude an event from the result |

Example:

```text
GET /api/events/overlaps?start_at=2026-08-12T20:00:00+00:00&end_at=2026-08-12T21:00:00+00:00
```

Response:

- `200 OK`: array of overlapping Calendar Event objects.
- `422 Unprocessable Entity`: invalid range.

### `GET /api/events/{event_id}`

Get an event by ID.

Response:

- `200 OK`: Calendar Event.
- `404 Not Found`: event not found.

### `PATCH /api/events/{event_id}`

Partially update an event.

Allowed fields:

```json
{
  "title": "Updated title",
  "description": "Updated description",
  "start_at": "2026-08-12T14:30:00-05:00",
  "end_at": "2026-08-12T15:30:00-05:00",
  "status": "tentative",
  "location": "Office",
  "participants": [
    {
      "name": "Anna",
      "email": "anna@example.test"
    }
  ]
}
```

All fields are optional.

Rule:

- if the resulting update has `end_at <= start_at`, the API returns `422`.

Response:

- `200 OK`: Calendar Event.
- `404 Not Found`: event not found.
- `422 Unprocessable Entity`: invalid data.

### `POST /api/events/{event_id}/cancel`

Cancel an event.

Response:

- `200 OK`: Calendar Event with `status = "cancelled"`.
- `404 Not Found`: event not found.

### `POST /api/events/{event_id}/restore`

Restore a cancelled event.

Response:

- `200 OK`: Calendar Event with `status = "confirmed"`.
- `404 Not Found`: event not found.

### `DELETE /api/events/{event_id}`

Physically delete an event.

Response:

- `204 No Content`: event deleted.
- `404 Not Found`: event not found.

## Errors

Error format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Event end time must be later than start time",
    "details": {
      "field": "end_at"
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
