# Run Instructions: Windows PowerShell

This guide is for local startup in Windows PowerShell.

The project does not require Docker, uv, Conda, or other environment managers. It uses the standard Python `venv`.

Python 3.12 or newer is required.

## 1. Create A Virtual Environment

Open The Project Directory

```powershell
python -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

## 2. Install Dependencies

```powershell
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## 3. Create Local Configuration

This step is optional for the default local setup. Use it only if you want an editable local config file.

```powershell
Copy-Item .env.example .env
```

## 4. Start All Applications

```powershell
python -m scripts.run_all
```

On first startup, each application creates its own SQLite database and tables automatically if they do not exist.

After startup, open:

```text
http://127.0.0.1:8011
http://127.0.0.1:8111/mcp
http://127.0.0.1:8012
http://127.0.0.1:8013
```


To Start One Application

```powershell
python -m apps.email_app.main
python -m apps.email_MCP.main
python -m apps.todo_app.main
python -m apps.calendar_app.main
```

## Stop Applications

If applications were started through `python -m scripts.run_all`, press `Ctrl+C` in that PowerShell window.

If processes are still listening on the local ports:

```powershell
python -m scripts.stop_all
```

## Reset Local Data

```powershell
python -m scripts.reset_data
```

The command deletes only SQLite files inside `data/`. The next application startup will recreate the required database and tables.
