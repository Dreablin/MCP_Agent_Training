# Agent Training Suite

Agent Training Suite is a local educational project for practicing MCP integration and agentic workflows on top of existing applications.

The repository contains three small, independent web applications. They are intentionally simple, local-only, and built as regular applications first. This makes them useful as a training base: learners can later build MCP servers and agent scenarios that interact with the apps through their REST APIs, without changing the application internals.

The project is not a production system. It does not include real email delivery, external service integrations, authentication, cloud deployment, or multi-user support.

## Applications

- **Email app**: a fake local mailbox for creating, reading, searching, moving to trash, and deleting email-like messages.
- **Todo App**: a local task tracker for creating tasks, changing status and priority, completing tasks, and archiving them.
- **Calendar App**: a local calendar for creating events, changing schedules, cancelling/restoring events, deleting events, and checking overlaps.

## Documentation

- [Architecture](docs/architecture.md)
- [Run instructions](docs/run-instructions.md)
- [Windows run instructions](docs/run-instructions-windows.md)
- [macOS/Linux run instructions](docs/run-instructions-macos-linux.md)
- [Email app API](docs/api-email.md)
- [Todo App API](docs/api-todo.md)
- [Calendar App API](docs/api-calendar.md)
- [Database schema](docs/database-schema.md)

## Local URLs

After startup, the applications are available at:

```text
Email app:    http://127.0.0.1:8011
Todo App:     http://127.0.0.1:8012
Calendar App: http://127.0.0.1:8013
```

OpenAPI documentation is available at `/docs` in each application.
