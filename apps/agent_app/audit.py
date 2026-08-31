import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from shared.datetime import now_utc


class AgentAuditLog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def setup(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(
                """
                create table if not exists agent_runs (
                    run_id text primary key,
                    thread_id text not null,
                    user_input text not null,
                    status text not null,
                    started_at text not null,
                    finished_at text
                );

                create table if not exists agent_events (
                    id integer primary key autoincrement,
                    run_id text not null,
                    thread_id text not null,
                    event_type text not null,
                    node_name text,
                    payload_json text not null,
                    created_at text not null
                );

                create table if not exists tool_calls (
                    id integer primary key autoincrement,
                    run_id text not null,
                    thread_id text not null,
                    tool_name text not null,
                    args_json text not null,
                    result_json text,
                    error text,
                    duration_ms integer not null,
                    created_at text not null
                );

                create table if not exists human_interrupts (
                    id integer primary key autoincrement,
                    run_id text not null,
                    thread_id text not null,
                    question_json text not null,
                    answer_json text,
                    created_at text not null,
                    resumed_at text
                );

                create table if not exists state_snapshots (
                    id integer primary key autoincrement,
                    run_id text not null,
                    thread_id text not null,
                    node_name text not null,
                    state_json text not null,
                    created_at text not null
                );
                """
            )

    def start_run(self, run_id: str, thread_id: str, user_input: str) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                insert or replace into agent_runs
                    (run_id, thread_id, user_input, status, started_at, finished_at)
                values (?, ?, ?, ?, ?, null)
                """,
                (run_id, thread_id, user_input, "running", now_utc().isoformat()),
            )

    def ensure_run(self, run_id: str, thread_id: str, user_input: str) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                insert or ignore into agent_runs
                    (run_id, thread_id, user_input, status, started_at, finished_at)
                values (?, ?, ?, ?, ?, null)
                """,
                (run_id, thread_id, user_input, "running", now_utc().isoformat()),
            )

    def finish_run(self, run_id: str, status: str) -> None:
        self.update_run_status(run_id, status, finished=True)

    def fail_run(
        self,
        run_id: str,
        thread_id: str,
        exc: Exception,
        *,
        node_name: str | None = None,
    ) -> None:
        self.event(
            run_id,
            thread_id,
            "run_failed",
            node_name=node_name,
            payload={"error_type": type(exc).__name__, "error": str(exc)},
        )
        self.finish_run(run_id, "failed")

    def update_run_status(self, run_id: str, status: str, *, finished: bool = False) -> None:
        finished_at = now_utc().isoformat() if finished else None
        with self.connection() as connection:
            connection.execute(
                """
                update agent_runs
                set status = ?, finished_at = ?
                where run_id = ?
                """,
                (status, finished_at, run_id),
            )

    def event(
        self,
        run_id: str,
        thread_id: str,
        event_type: str,
        *,
        node_name: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                insert into agent_events
                    (run_id, thread_id, event_type, node_name, payload_json, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    thread_id,
                    event_type,
                    node_name,
                    encode_json(payload or {}),
                    now_utc().isoformat(),
                ),
            )

    def tool_call(
        self,
        run_id: str,
        thread_id: str,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
        duration_ms: int,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                insert into tool_calls
                    (
                        run_id,
                        thread_id,
                        tool_name,
                        args_json,
                        result_json,
                        error,
                        duration_ms,
                        created_at
                    )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    thread_id,
                    tool_name,
                    encode_json(args),
                    encode_json(result),
                    result.get("error"),
                    duration_ms,
                    now_utc().isoformat(),
                ),
            )

    def interrupt(self, run_id: str, thread_id: str, question: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                "update agent_runs set status = ? where run_id = ?",
                ("waiting_for_human", run_id),
            )
            existing = connection.execute(
                """
                select id from human_interrupts
                where run_id = ? and thread_id = ? and resumed_at is null
                order by id desc
                limit 1
                """,
                (run_id, thread_id),
            ).fetchone()
            if existing is not None:
                return
            connection.execute(
                """
                insert into human_interrupts
                    (run_id, thread_id, question_json, answer_json, created_at, resumed_at)
                values (?, ?, ?, null, ?, null)
                """,
                (run_id, thread_id, encode_json(question), now_utc().isoformat()),
            )

    def resume(self, run_id: str, thread_id: str, answer: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                "update agent_runs set status = ? where run_id = ?",
                ("running", run_id),
            )
            connection.execute(
                """
                update human_interrupts
                set answer_json = ?, resumed_at = ?
                where id = (
                    select id from human_interrupts
                    where run_id = ? and thread_id = ? and resumed_at is null
                    order by id desc
                    limit 1
                )
                """,
                (encode_json(answer), now_utc().isoformat(), run_id, thread_id),
            )

    def snapshot(self, run_id: str, thread_id: str, node_name: str, state: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                insert into state_snapshots
                    (run_id, thread_id, node_name, state_json, created_at)
                values (?, ?, ?, ?, ?)
                """,
                (run_id, thread_id, node_name, encode_json(state), now_utc().isoformat()),
            )

    @contextmanager
    def timed_tool_call(
        self,
        run_id: str,
        thread_id: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000)
            self.event(
                run_id,
                thread_id,
                "tool_duration",
                payload={"tool_name": tool_name, "args": args, "duration_ms": duration_ms},
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


def encode_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, default=str)
