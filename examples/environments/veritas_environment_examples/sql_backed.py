from __future__ import annotations

import sqlite3

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational import ActionKind, WorldDomain

from ._common import execute_episode, require_perfect


def build_environment(connection: sqlite3.Connection):
    row = connection.execute(
        "SELECT ticket_id, status, expected_status FROM tickets WHERE ticket_id = ?",
        ("T-1",),
    ).fetchone()
    if row is None:
        raise ValueError("required ticket T-1 is missing")
    ticket_id, status, expected_status = map(str, row)
    return (
        EnvironmentBuilder(
            name="sql-backed",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Resolve a SQL-backed ticket using database evidence.",
            role="database_operator",
        )
        .system("SQL")
        .action(
            "resolve_ticket",
            kind=ActionKind.WRITE,
            system="SQL",
            description="Set the ticket to its verified expected status.",
            parameters=("ticket_id", "status"),
        )
        .record(
            "sql-rec-001",
            system="SQL",
            record_type="ticket_row",
            object_id=ticket_id,
            fields={"status": status, "expected_status": expected_status},
            searchable_text=f"{ticket_id} {status} {expected_status}",
        )
        .initial_state(**{f"{ticket_id}.status": status})
        .target(ticket_id, "status", expected_status)
        .transition(
            "resolve_ticket",
            required_parameters={"ticket_id": ticket_id, "status": expected_status},
            set_state={f"{ticket_id}.status": expected_status},
            observable_result={"rows_updated": 1},
        )
        .require_action("resolve_ticket")
        .require_evidence("sql-rec-001")
        .metadata(public={"backend": "sqlite"})
        .success("The SQL-backed ticket is resolved.")
        .build()
    )


def run_demo():
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE tickets (ticket_id TEXT PRIMARY KEY, status TEXT, expected_status TEXT)"
        )
        connection.execute(
            "INSERT INTO tickets VALUES (?, ?, ?)",
            ("T-1", "open", "resolved"),
        )
        result = execute_episode(
            build_environment(connection),
            actions=(("resolve_ticket", {"ticket_id": "T-1", "status": "resolved"}),),
            evidence_ids=("sql-rec-001",),
            claimed_state={"T-1.status": "resolved"},
            conclusion="The database row supports resolving T-1.",
        )
    finally:
        connection.close()
    return require_perfect(result)
