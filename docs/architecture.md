# Architecture

Agent Training Suite is a local cross-platform training suite made of three independent applications:

- Email app on `127.0.0.1:8011`;
- Email MCP server on `127.0.0.1:8111/mcp`;
- Todo App on `127.0.0.1:8012`;
- Todo MCP server over local stdio, with no port or URL;
- Calendar App on `127.0.0.1:8013`.
- Calendar MCP endpoint on `127.0.0.1:8013/mcp/`.

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

Todo MCP stdio process
  -> MCPServer tools
  -> Todo service layer
  -> Todo repository layer
  -> Todo SQLite database

Agent App
  -> LangGraph state graph
  -> LangGraph-native messages
  -> ToolNode
  -> MCP v2 client backed LangChain tools
  -> Email MCP / Calendar MCP / Todo MCP
  -> SQLite checkpoints and audit log
```

The UI and API use the same service layer. The UI does not run SQL queries directly.

## Application Isolation

- Email app uses `data/email.db`.
- Email MCP server is a separate Uvicorn process. It does not connect to SQLite directly; future MCP tools should call the Email app REST API.
- Todo App uses `data/todo.db`.
- Todo MCP server is launched by an MCP client as a local stdio child process. It has no HTTP server, port, Uvicorn process, or FastAPI mount. Future tools should create a short-lived session per call and must not store a SQLAlchemy `Session` between MCP calls.
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

## Agent Layer

`apps/agent_app/` is a separate orchestration layer. It does not import business
models or repositories from Email, Todo, or Calendar. It talks to those apps
through their existing MCP surfaces:

- Email MCP over Streamable HTTP;
- Calendar MCP over Streamable HTTP mounted in the Calendar app;
- Todo MCP over stdio as a local child process.

The agent graph is intentionally small: user messages go to one LLM node, the
LLM may emit tool calls, `ToolNode` executes them, and the resulting
`ToolMessage` objects go back to the LLM until it returns a final answer.

The LLM node prepends a system prompt from `apps.agent_app.prompts` to every
model call. The prompt instructs the model to treat MCP tools as the source of
truth, avoid fabricated tool results, and avoid claiming successful changes until
successful `ToolMessage` results are present.

Tool execution is a loop. After every tool result, including
`ToolMessage(status="error")`, the graph returns to the LLM so the model can
decide whether to correct the call, use another tool, ask for clarification, or
finish.

Before `ToolNode` runs, the graph enforces a simple execution policy:
state-changing tools cannot be batched with any other tool calls. If the LLM
emits a batch containing a state-changing tool, the batch is not executed; the
graph returns `ToolMessage(status="error")` entries telling the model to re-plan
and call one state-changing tool, then wait for its result. Read-only tool
batches are allowed.

Human-in-the-loop remains a design goal for uncertainty, not blanket approval.
The current first agent loop does not route every tool failure to a human. Human
clarification should be added as an explicit model-selected path for ambiguity,
missing required information, risky actions, or unrecoverable cases.

The agent state stores conversation history using LangGraph's `add_messages`
reducer and LangChain message types. AI tool calls and `ToolMessage` responses are
therefore part of the standard graph state rather than a parallel custom result
list.

MCP tools are exposed to the graph as LangChain `StructuredTool` instances and
executed by LangGraph `ToolNode`. MCP `is_error` results are converted into tool
errors so the resulting `ToolMessage(status="error")` is visible to the LLM as
part of the standard message history.

The agent can also use local non-MCP tools. The first local tool is
`get_current_datetime`, which reads this computer's local clock and returns only
the local `datetime`, `date`, `time`, and `weekday`. CLI and real Studio runtime
include this local tool together with MCP tools.

LLM construction is centralized in `apps.agent_app.llm.create_chat_model`.
`AGENT_LLM_PROVIDER` accepts `ollama` or `openai`. The default is local Ollama at
`AGENT_OLLAMA_BASE_URL=http://127.0.0.1:11434` with
`AGENT_LLM_MODEL=gemma4:31b`. OpenAI can be enabled by setting
`AGENT_LLM_PROVIDER=openai`, choosing an OpenAI model, and providing
`AGENT_OPENAI_API_KEY`.

The Todo MCP client is designed to run inside a persistent async MCP registry
context. That keeps the stdio subprocess/session open for the lifetime of the
agent runtime using it, instead of creating a new Todo subprocess for every tool
call.

Real MCP-backed tools are async-only in the current implementation. The sync
`AgentGraphRuntime.run()` and `resume()` methods are intended for tests or
synchronous tools; real MCP execution should use `arun()` and `aresume()`.

Agent checkpoints are stored separately from the application databases. The audit
log is also separate and records runs, graph node events, tool calls, human
interrupts, and state snapshots for later debugging against historical behavior.
Audit snapshots merge message updates with LangGraph's `add_messages` semantics
so snapshots show the accumulated conversation rather than only the latest
message update.

`langgraph.json` exports `apps.agent_app.studio:make_graph` for LangGraph Studio.
The Studio entrypoint is an async context-manager factory, so MCP clients are
opened and closed in the same runtime lifecycle. It uses a fallback model only
when `AGENT_STUDIO_USE_REAL_RUNTIME=false`. When
`AGENT_STUDIO_USE_REAL_RUNTIME=true`, startup fails fast if the configured LLM or
MCP registry cannot be loaded.

## v1 Boundaries

v1 does not include production-grade prompts, external services, authentication,
real email, cloud deployment, or multi-user mode. The current LangGraph agent
layer is a local LLM/tool-loop skeleton with pluggable model and tool-loading
interfaces.
