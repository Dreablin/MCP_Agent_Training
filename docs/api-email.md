# Email app API

Base URL:

```text
http://127.0.0.1:8011
```

OpenAPI UI:

```text
http://127.0.0.1:8011/docs
```

## General Rules

- Authentication is not used.
- Data format: JSON.
- All dates and times are sent in ISO 8601 format with timezone information.
- Main email message identifier: UUID string.
- When creating a message, `id` can be omitted and will be generated automatically.

## System Endpoints

### `GET /health`

Checks application health.

Response `200`:

```json
{
  "status": "ok",
  "app_name": "Email app",
  "version": "0.1.0"
}
```

## Email Message Model

### Response Fields

```json
{
  "id": "00000000-0000-4000-8000-000000000101",
  "sender_name": "Anna",
  "sender_email": "anna@example.test",
  "recipient_email": "me@example.test",
  "subject": "Meeting with Anna",
  "body": "Let's meet on August 12, 2026 at 14:30.",
  "received_at": "2026-08-06T15:00:00+00:00",
  "folder": "inbox",
  "is_read": false,
  "created_at": "2026-08-06T15:00:00+00:00",
  "updated_at": "2026-08-06T15:00:00+00:00"
}
```

### Enum `folder`

- `inbox`
- `sent`
- `spam`
- `friends`
- `work`
- `logs`
- `trash`

## Endpoints

### `POST /api/messages`

Create a fake incoming email message.

Request body:

```json
{
  "sender_name": "Anna",
  "sender_email": "anna@example.test",
  "recipient_email": "me@example.test",
  "subject": "Meeting with Anna",
  "body": "Let's meet on August 12, 2026 at 14:30.",
  "received_at": "2026-08-06T10:00:00-05:00"
}
```

Optional field:

- `id`: UUID string.

Response:

- `201 Created`
- body: Email Message.

### `GET /api/messages`

Get a list of messages. Results are ordered by `received_at` ascending, so the oldest
messages are returned first. If two messages have the same `received_at`, `created_at`
ascending is used as the tie-breaker.

Query parameters:

| Parameter | Type | Default | Description |
|---|---:|---:|---|
| `query` | string | `null` | Search by sender, email, subject, and body |
| `folder` | enum | `null` | `inbox`, `sent`, `spam`, `friends`, `work`, `logs`, `trash` |
| `is_read` | boolean | `null` | Filter by read state |
| `sender` | string | `null` | Search by sender name or email |
| `subject` | string | `null` | Search by subject |
| `limit` | integer | `100` | From 1 to 500 |
| `offset` | integer | `0` | Offset, starting at 0 |

Example:

```text
GET /api/messages?folder=inbox&is_read=false&query=meeting
```

Get the oldest unread message:

```text
GET /api/messages?is_read=false&limit=1
```

Get the second page of 100 messages:

```text
GET /api/messages?limit=100&offset=100
```

Response:

- `200 OK`
- body: array of Email Message objects.

### `GET /api/messages/folders`

Get the list of available message folders.

Response `200`:

```json
[
  {
    "id": "inbox",
    "label": "Inbox"
  },
  {
    "id": "sent",
    "label": "Sent"
  },
  {
    "id": "spam",
    "label": "Spam"
  },
  {
    "id": "friends",
    "label": "Friends"
  },
  {
    "id": "work",
    "label": "Work"
  },
  {
    "id": "logs",
    "label": "Logs"
  },
  {
    "id": "trash",
    "label": "Trash"
  }
]
```

### `GET /api/messages/{message_id}`

Get a message by ID.

Response:

- `200 OK`: Email Message.
- `404 Not Found`: message not found.

### `POST /api/messages/{message_id}/read`

Mark a message as read.

Response:

- `200 OK`: Email Message.
- `404 Not Found`: message not found.

### `POST /api/messages/{message_id}/unread`

Mark a message as unread.

Response:

- `200 OK`: Email Message.
- `404 Not Found`: message not found.

### `POST /api/messages/{message_id}/move`

Move a message to a folder.

Request body:

```json
{
  "folder": "work"
}
```

Response:

- `200 OK`: Email Message with the selected `folder`.
- `404 Not Found`: message not found.

### `DELETE /api/messages/{message_id}`

Permanently delete a message from trash.

Rule:

- only a message with `folder = "trash"` can be deleted.

Response:

- `204 No Content`: message deleted.
- `404 Not Found`: message not found.
- `422 Unprocessable Entity`: message is not in trash.

### `DELETE /api/messages/trash`

Empty trash.

Response `200`:

```json
{
  "deleted_count": 3
}
```

## Errors

Error format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": {
      "errors": []
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
