# Run Instructions: macOS/Linux Shell

This guide is for local startup in a regular shell such as `bash`, `zsh`, or a compatible shell.

The project does not require Docker, uv, Conda, or other environment managers. It uses the standard Python `venv`.

Python 3.12 or newer is required.

## 1. Create A Virtual Environment

Open The Project Directory

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

## 2. Install Dependencies

```bash
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## 3. Create Local Configuration

This step is optional for the default local setup. Use it only if you want an editable local config file.

```bash
cp .env.example .env
```

## 4. Start All Applications

```bash
python -m scripts.run_all
```

On first startup, each application creates its own SQLite database and tables automatically if they do not exist.

After startup, open:

```text
http://127.0.0.1:8011
http://127.0.0.1:8111/mcp
http://127.0.0.1:8012
http://127.0.0.1:8013
http://127.0.0.1:8013/mcp
```


To Start One Application

```bash
python -m apps.email_app.main
python -m apps.email_MCP.main
python -m apps.todo_app.main
python -m apps.calendar_app.main
```

To run the local Todo MCP server manually, use:

```bash
python -m apps.todo_MCP.main
```

Todo MCP uses stdio for JSON-RPC. It has no URL and is normally launched by an
MCP client as a child process, not by `scripts.run_all`. It calls the Todo App at
`http://127.0.0.1:8012` by default.

## Stop Applications

If applications were started through `python -m scripts.run_all`, press `Ctrl+C` in that shell window.

If processes are still listening on the local ports:

```bash
python -m scripts.stop_all
```

## Reset Local Data

```bash
python -m scripts.reset_data
```

The command deletes only SQLite files inside `data/`. The next application startup will recreate the required database and tables.
