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
Calendar MCP: http://127.0.0.1:8013/mcp
```

OpenAPI is available at `/docs` in each application.

Todo MCP is local stdio-only and has no URL. An MCP client launches it as a child
process when needed:

```bash
python -m apps.todo_MCP.main
```
