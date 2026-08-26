import os
import re
import signal
import subprocess

DEFAULT_PORTS = [8011, 8012, 8013, 8111]


def parse_netstat_pids(output: str, ports: list[int]) -> set[int]:
    pids: set[int] = set()
    port_tokens = {f":{port}" for port in ports}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        state = parts[3].upper()
        pid_text = parts[-1]
        if state != "LISTENING":
            continue
        if not any(local_address.endswith(port_token) for port_token in port_tokens):
            continue
        if pid_text.isdigit():
            pids.add(int(pid_text))
    return pids


def parse_lsof_pids(output: str) -> set[int]:
    pids: set[int] = set()
    for line in output.splitlines():
        pid_text = line.strip()
        if pid_text.isdigit():
            pids.add(int(pid_text))
    return pids


def parse_ss_pids(output: str, ports: list[int]) -> set[int]:
    pids: set[int] = set()
    port_tokens = {f":{port}" for port in ports}
    for line in output.splitlines():
        if not any(port_token in line for port_token in port_tokens):
            continue
        for pid_text in re.findall(r"pid=(\d+)", line):
            pids.add(int(pid_text))
    return pids


def run_command(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None


def find_windows_listening_pids(ports: list[int]) -> set[int]:
    result = run_command(["netstat", "-ano", "-p", "tcp"])
    if result is None:
        return set()
    return parse_netstat_pids(result.stdout, ports)


def find_posix_listening_pids(ports: list[int]) -> set[int]:
    pids: set[int] = set()
    for port in ports:
        result = run_command(["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"])
        if result is not None and result.returncode == 0:
            pids.update(parse_lsof_pids(result.stdout))

    if pids:
        return pids

    result = run_command(["ss", "-ltnp"])
    if result is None:
        return set()
    return parse_ss_pids(result.stdout, ports)


def find_listening_pids(ports: list[int] | None = None) -> set[int]:
    selected_ports = ports or DEFAULT_PORTS
    if os.name == "nt":
        return find_windows_listening_pids(selected_ports)
    return find_posix_listening_pids(selected_ports)


def stop_windows_pids(pids: set[int]) -> list[int]:
    stopped: list[int] = []
    current_pid = os.getpid()
    for pid in sorted(pids):
        if pid == current_pid:
            continue
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            stopped.append(pid)
    return stopped


def stop_posix_pids(pids: set[int]) -> list[int]:
    stopped: list[int] = []
    current_pid = os.getpid()
    for pid in sorted(pids):
        if pid == current_pid:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            continue
        stopped.append(pid)
    return stopped


def stop_pids(pids: set[int]) -> list[int]:
    if os.name == "nt":
        return stop_windows_pids(pids)
    return stop_posix_pids(pids)


def stop_all(ports: list[int] | None = None) -> list[int]:
    return stop_pids(find_listening_pids(ports))


def main() -> None:
    stopped = stop_all()
    if not stopped:
        print("No local app processes found on ports 8011, 8012, 8013, 8111.")
        return
    print("Stopped local app processes:")
    for pid in stopped:
        print(f"- PID {pid}")


if __name__ == "__main__":
    main()
