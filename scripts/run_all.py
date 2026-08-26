import subprocess
import sys
import time
from dataclasses import dataclass

from scripts.paths import PROJECT_ROOT


@dataclass(frozen=True)
class AppProcess:
    name: str
    module: str
    url: str


APPS = [
    AppProcess("Email app", "apps.email_app.main", "http://127.0.0.1:8011"),
    AppProcess("Email MCP server", "apps.email_MCP.main", "http://127.0.0.1:8111/mcp"),
    AppProcess("Todo App", "apps.todo_app.main", "http://127.0.0.1:8012"),
    AppProcess("Calendar App", "apps.calendar_app.main", "http://127.0.0.1:8013"),
]


def run_all() -> None:
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for app in APPS:
            process = subprocess.Popen(
                [sys.executable, "-m", app.module],
                cwd=PROJECT_ROOT,
            )
            processes.append(process)
            print(f"{app.name}: {app.url}")

        print("All apps started. Press Ctrl+C to stop.")
        while True:
            stopped = [process for process in processes if process.poll() is not None]
            if stopped:
                print("One or more app processes stopped. Remaining apps continue running.")
                processes = [process for process in processes if process.poll() is None]
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping apps...")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> None:
    run_all()


if __name__ == "__main__":
    main()
