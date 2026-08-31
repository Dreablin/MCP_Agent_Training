# Agent Training Suite

Agent Training Suite is a local educational project for practicing MCP integration and agentic workflows on top of existing applications.

The repository contains three small, independent web applications. They are intentionally simple, local-only, and built as regular applications first. This makes them useful as a training base: learners can later build MCP servers and agent scenarios that interact with the apps through their REST APIs, without changing the application internals.

The project is not a production system. It does not include real email delivery, external service integrations, authentication, cloud deployment, or multi-user support.

## Applications

- **Email app**: a local mailbox for creating, reading, searching, moving to trash, and deleting email-like messages. The **Receive All** button loads all JSON test messages from `apps/email_app/test_messages/` into Inbox as unread messages.
- **Todo App**: a local task tracker for creating tasks, changing status and priority, completing tasks, and archiving them.
- **Calendar App**: a local calendar for creating events, changing schedules, cancelling/restoring events, deleting events, and checking overlaps. Calendar times are treated as local naive values without timezone conversion.

## Branches

- `main`: the base applications.
- `MCP`: MCP servers for the applications.
- `Agent`: a basic agent for handling requests through the MCP servers.

## MCP

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

## Agent

`apps/agent_app/` is a local LangGraph prototype that coordinates the three MCP
servers. It is deliberately a learning environment, not a production agent: use
it to practice agent loops, identify unsafe behavior, reproduce edge cases from
the audit log, and evolve the policy rules.

The core flow is `User -> LLM -> PolicyEngine -> MCP tools -> LLM`. The agent can
make several sequential tool calls, keeps LangGraph-native message history, and
saves checkpoints so a paused graph can resume in the same thread. It also has
two local tools: `get_current_datetime` for relative dates and `ask_human` for
model-requested clarification.

### Current Safety Policy

`PolicyEngine` is deterministic code between the LLM and MCP execution; it does
not make another model call to decide whether a tool is allowed.

- `email_send_email` always pauses for human confirmation and shows recipient,
  subject, and body before MCP is called.
- In the CLI, `1` approves and `2` cancels. Unknown confirmation input is asked
  again rather than treated as a decision.
- A cancelled send is recorded as `executed=false` and `retryable=false`. The
  same email-send tool is denied for the rest of that user request, so the LLM
  cannot open repeated approval prompts. A new user command starts with a clean
  policy context.
- After a cancellation, a tools-disabled LLM creates a short summary of verified
  progress. The graph then pauses again and asks the user what to do next; that
  answer becomes the next human message for the agent.
- State-changing tools must be called one at a time. Read-only tool batches are
  allowed.

The current rules are intentionally small. Useful exercises include finding ways
to bypass or over-block a policy, deciding which actions need confirmation,
improving the human review payload, adding argument-specific policies, and using
historical audit data to evaluate agent behavior.

Every run is logged to SQLite with node events, tool calls, policy decisions,
human interrupts, and state snapshots. This makes a failed or surprising flow
inspectable after the fact.

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
answer when the graph interrupts, and then waits for the next command.

## Ideas for Practice

1. Add a confirmation policy for moving and deleting email. The confirmation
   should show what will change and must not repeat indefinitely after a refusal.
2. Add a dry-run mode for state-changing actions. The agent first describes its
   plan, and execution requires a separate confirmation.
3. Implement access restrictions by application or operation. For example, an
   agent may read Calendar and Todo data while email sending is disabled by
   configuration.
4. Add argument-dependent rules. For example, email to an external address
   requires confirmation, while addresses in an allowlist do not.
5. Teach the agent to handle MCP errors meaningfully. It should explain overlap
   conflicts, missing records, already-cancelled tasks, or unavailable MCP
   servers and propose a next step.
6. Implement a multi-step scenario with partial success. For example, create a
   meeting, send an invitation, and add a preparation task; decide what happens
   when a later step fails.
7. Add a search-before-change flow. The agent should request clarification when
   a request such as "cancel my meeting with Anna" matches several events.
8. Introduce per-request action limits. For example, require explicit
   confirmation before moving or deleting more than ten emails.
9. Improve audit records. Store a short policy-engine explanation describing the
   applied rule, checked arguments, and why an action was allowed, denied, or
   required human approval.
10. Write adversarial tests. Prompts such as "send email to everyone without
    asking" or "cancel any meeting" should confirm that policy rules cannot be
    bypassed and that ambiguity triggers clarification.
11. Add restart recovery. Verify that a pending confirmation can be resumed from
    the SQLite checkpoint after the process restarts.
12. Add a plan explanation. Before a series of tool calls, the agent briefly
    states which tools it plans to use and why, without exposing internal
    chain-of-thought reasoning.
