# Agent Training Suite

Agent Training Suite is a local educational project for practicing MCP integration and agentic workflows on top of existing applications.

The repository contains three small, independent web applications. They are intentionally simple, local-only, and built as regular applications first. This makes them useful as a training base for MCP servers and agent scenarios that integrate with existing app boundaries instead of replacing the applications themselves.

The project is not a production system. It does not include real email delivery, external service integrations, authentication, cloud deployment, or multi-user support.

## Applications

- **Email app**: a fake local mailbox for creating, reading, searching, moving to trash, and deleting email-like messages.
- **Todo App**: a local task tracker for creating tasks, changing status and priority, completing tasks, and archiving them.
- **Calendar App**: a local calendar for creating events, changing schedules, cancelling/restoring events, deleting events, and checking overlaps. Calendar times are treated as local naive values without timezone conversion.

## MCP Integration Approaches

The suite intentionally demonstrates three different MCP integration styles. They are not competing implementations of the same design; they are separate training examples for different deployment and ownership boundaries.

| App | MCP style | Transport | How tools reach app logic |
| --- | --- | --- | --- |
| Email | Separate MCP server process | Streamable HTTP | Existing Email REST API |
| Calendar | MCP embedded in the app process | Streamable HTTP mounted under FastAPI | Calendar service layer and shared session factory |
| Todo | Local child process launched by the agent | stdio JSON-RPC | Todo App REST API |

The Email MCP server is a separate Uvicorn process. It owns its own `MCPServer` instance
and exposes it through Streamable HTTP, but it treats the Email app as an external
local service. Its tools communicate with the Email app through the existing REST API.
This keeps the application boundary strict and is useful for practicing agent workflows
that integrate through public API contracts.

The Calendar MCP server is embedded into the Calendar app process. The main FastAPI app
creates an `MCPServer`, turns it into an ASGI app with `streamable_http_app()`, mounts it
under `/mcp`, and starts the MCP session manager from the FastAPI lifespan. Tools call the
same Calendar service layer used by the REST API and NiceGUI UI. They close over the shared
SQLAlchemy session factory stored on the FastAPI application state, then open a short-lived
service/session scope for each tool call. They should not keep a `Session` object alive
between MCP calls. This shows how MCP can be added inside an existing ASGI application
without introducing a second server process or an HTTP hop back into the same application.

The Todo MCP server is a local stdio process. An MCP client starts it as a child
process, sends JSON-RPC messages through stdin, and reads responses from stdout.
It does not expose a port, does not run Uvicorn, and is not mounted into FastAPI.
Todo MCP tools call the Todo App REST API, so the Todo App remains the single owner of
its database transactions and event notifications.

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
Calendar MCP: http://127.0.0.1:8013/mcp/
```

OpenAPI documentation is available at `/docs` in each application.

Todo MCP has no URL. It is launched by an MCP client over stdio, for example:

```bash
python -m apps.todo_MCP.main
```

## Agent Skeleton

`apps/agent_app/` contains a LangGraph-based agent shell for coordinating the
three MCP servers. The first implementation focuses on orchestration mechanics:

- MCP tool discovery through Email HTTP MCP, Calendar HTTP MCP, and Todo stdio MCP;
- an agent-local `get_current_datetime` tool for resolving relative dates and
  times using this computer's local clock;
- an agent-local `ask_human` tool for model-selected clarification, implemented
  with LangGraph interrupt/resume;
- persistent graph checkpoints for pause/resume human-in-the-loop flows;
- LangGraph-native message history, including AI tool calls and ToolMessage results;
- a simple `LLM -> tools -> LLM` loop using standard LangGraph ToolNode execution;
- a system prompt that tells the model to use MCP tools as the source of truth
  and not claim action success before a successful tool result;
- tool errors return to the LLM as `ToolMessage(status="error")` before any human
  clarification is considered;
- a pass-through human gate after tool execution, ready for future deterministic
  interrupt rules without adding those rules yet;
- structured SQLite audit logging for runs, node events, tool calls, human
  interrupts, and state snapshots.

The default LLM provider is local Ollama with `AGENT_LLM_MODEL=gemma4:31b`.
Supported provider values are `ollama` and `openai`. To switch to OpenAI, set
`AGENT_LLM_PROVIDER=openai`, choose an OpenAI model in `AGENT_LLM_MODEL`, and
set `AGENT_OPENAI_API_KEY` in `.env`.

Tests use a scripted chat model and fake LangChain tools so the real graph loop,
ToolMessage handling, and audit behavior can be verified without model
credentials.

`langgraph.json` exposes `apps.agent_app.studio:make_graph` for LangGraph Studio.
That async context-manager entrypoint uses a lightweight fallback model by
default so the graph can be loaded without credentials. Set
`AGENT_STUDIO_USE_REAL_RUNTIME=true` to make the entrypoint load the configured
LLM and persistent MCP tool registry when the local MCP apps are running. In real
runtime mode, MCP tools are async-only, so use the async graph execution path.

The single-thread interactive CLI can be started with:

```bash
python -m apps.agent_app.cli
```

After installing the project, the same CLI is also available as `agent-cli`. The
CLI opens the MCP registry once, keeps one LangGraph thread for the session,
streams LLM/tool/human/final updates for each command, resumes after a human
answer when `ask_human` interrupts, and then waits for the next command.
