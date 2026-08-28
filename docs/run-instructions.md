# Run Instructions

The project runs locally for a single user, without Docker, uv, Conda, server deployment, or external infrastructure.

It uses a standard Python `venv` environment created with `python -m venv .venv`. Dependencies are installed only into `.venv` so the system Python stays untouched.

Choose the instruction set for your platform:

- [Windows PowerShell](run-instructions-windows.md)
- [macOS/Linux shell](run-instructions-macos-linux.md)

Local addresses after startup:

```text
Email app:    http://127.0.0.1:8011
Email MCP:    http://127.0.0.1:8111/mcp
Todo App:     http://127.0.0.1:8012
Calendar App: http://127.0.0.1:8013
Calendar MCP: http://127.0.0.1:8013/mcp/
```

OpenAPI is available at `/docs` in each application.

The agent defaults to local Ollama:

```text
AGENT_LLM_PROVIDER=ollama
AGENT_LLM_MODEL=gemma4:31b
AGENT_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Supported `AGENT_LLM_PROVIDER` values are `ollama` and `openai`. To use OpenAI,
set `AGENT_LLM_PROVIDER=openai`, set `AGENT_OPENAI_API_KEY`, and choose an
OpenAI model in `AGENT_LLM_MODEL`.

After the apps and LLM runtime are available, start the single-thread agent CLI:

```bash
python -m apps.agent_app.cli
```

The CLI keeps one LangGraph thread for the session. Type normal requests to run
the agent, `:thread` to show the current thread id, `:help` for commands, and
`exit` or `quit` to stop.

Todo MCP is local stdio-only and has no URL. An MCP client launches it as a child
process when needed:

```bash
python -m apps.todo_MCP.main
```
