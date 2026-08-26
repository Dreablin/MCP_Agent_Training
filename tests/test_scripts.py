from pathlib import Path

import pytest

from scripts.paths import assert_inside_data_dir
from scripts.stop_all import DEFAULT_PORTS, parse_lsof_pids, parse_netstat_pids, parse_ss_pids


def test_default_stop_ports_include_email_mcp() -> None:
    assert DEFAULT_PORTS == [8011, 8012, 8013, 8111]


def test_assert_inside_data_dir_rejects_project_file() -> None:
    with pytest.raises(ValueError):
        assert_inside_data_dir(Path("README.md"))


def test_parse_netstat_pids_finds_listening_app_ports() -> None:
    output = """
      TCP    127.0.0.1:8011         0.0.0.0:0              LISTENING       111
      TCP    127.0.0.1:8012         0.0.0.0:0              ESTABLISHED     222
      TCP    127.0.0.1:8013         0.0.0.0:0              LISTENING       333
      TCP    127.0.0.1:9999         0.0.0.0:0              LISTENING       444
    """

    assert parse_netstat_pids(output, [8011, 8012, 8013]) == {111, 333}


def test_parse_lsof_pids_reads_numeric_lines() -> None:
    output = """
    111
    not-a-pid
    333
    """

    assert parse_lsof_pids(output) == {111, 333}


def test_parse_ss_pids_finds_listening_app_ports() -> None:
    output = """
    LISTEN 0 4096 127.0.0.1:8011 0.0.0.0:* users:(("python",pid=111,fd=10))
    LISTEN 0 4096 127.0.0.1:8013 0.0.0.0:* users:(("python",pid=333,fd=10))
    LISTEN 0 4096 127.0.0.1:9999 0.0.0.0:* users:(("python",pid=444,fd=10))
    """

    assert parse_ss_pids(output, [8011, 8012, 8013]) == {111, 333}
