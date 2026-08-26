# Agent Training Suite

Agent Training Suite is a local educational project for practicing MCP integration and agentic workflows on top of existing applications.

The repository contains three small, independent web applications. They are intentionally simple, local-only, and built as regular applications first. This makes them useful as a training base: learners can later build MCP servers and agent scenarios that interact with the apps through their REST APIs, without changing the application internals.

The project is not a production system. It does not include real email delivery, external service integrations, authentication, cloud deployment, or multi-user support.

## Applications

- **Email app**: a fake local mailbox for creating, reading, searching, moving to trash, and deleting email-like messages.
- **Todo App**: a local task tracker for creating tasks, changing status and priority, completing tasks, and archiving them.
- **Calendar App**: a local calendar for creating events, changing schedules, cancelling/restoring events, deleting events, and checking overlaps. Calendar times are treated as local naive values without timezone conversion.

The Email app also has a separate MCP server skeleton using the official MCP Python SDK v2, `MCPServer`, and Streamable HTTP. It currently contains only the shared wrapper where tools can be registered later. Future MCP tools should talk to the Email app through its REST API, not through direct database access.

The Calendar App exposes an embedded MCP server in the same Uvicorn process as its FastAPI API and NiceGUI UI. Future Calendar MCP tools should use the Calendar service layer with the same session factory used by the API.

## MCP Integration Approaches

The suite demonstrates two ways to add MCP to an existing application.

The Email MCP server is a separate Uvicorn process. It owns its own `MCPServer` instance
and exposes it through Streamable HTTP, but it treats the Email app as an external
local service. Its tools communicate with the Email app through the existing REST API.
This keeps the application boundary strict and is useful for practicing agent workflows
that integrate through public API contracts.

The Calendar MCP server is embedded into the Calendar app process. The main FastAPI app
creates an `MCPServer`, turns it into an ASGI app with `streamable_http_app()`, mounts it
under `/mcp`, and starts the MCP session manager from the FastAPI lifespan. In this mode,
future tools should call the same Calendar service layer used by the REST API and NiceGUI
UI. Tools should close over the shared SQLAlchemy session factory stored on the FastAPI
application state, then open a short-lived service/session scope for each tool call. They
should not keep a `Session` object alive between MCP calls. This shows how MCP can be
added inside an existing ASGI application without introducing a second server process or
an HTTP hop back into the same application.

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
Email MCP:    http://127.0.0.1:8111/mcp
Todo App:     http://127.0.0.1:8012
Calendar App: http://127.0.0.1:8013
Calendar MCP: http://127.0.0.1:8013/mcp
```

OpenAPI documentation is available at `/docs` in each application.
