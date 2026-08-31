"""One SQLite evidence ledger keyed by the exact repository subject.

An observation is admitted only together with the identity of the adapter that produced it and the
sha256 of the exact source bytes it was read from. That turns three claims into physical checks
instead of assertions: the same source observations rebuild a byte-identical canonical export in any
insertion order, a second row for one exact subject is refused by the schema itself, and a row read
back against changed source bytes is refused as stale rather than served as current.

Non-claims: no scheduler state, worktree lifecycle, handoff state, closure state, task graph,
generic registry, or release ledger lives here.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from issue_contract import SUBJECT_RE

SCHEMA_VERSION = 1
ADAPTER_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
LEDGER_COLUMNS = ("subject", "observation", "source_sha256", "adapter")
SELECT_ROW = f"SELECT {', '.join(LEDGER_COLUMNS)} FROM evidence"
# constraint: PRIMARY KEY makes the duplicate exact subject a schema refusal, so no writer can forget
# constraint: the check; STRICT keeps a stored digest from silently becoming a non-text value.
SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    subject TEXT PRIMARY KEY NOT NULL,
    observation TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    adapter TEXT NOT NULL
) STRICT;
"""


@dataclass(frozen=True)
class SourceObservation:
    """What one adapter read: the exact subject, what it observed, and the exact source bytes."""

    subject: str
    observation: str
    source: bytes
    adapter: str


@dataclass(frozen=True)
class EvidenceRow:
    """What the ledger stores: the source bytes are reduced to their digest and never kept."""

    subject: str
    observation: str
    source_sha256: str
    adapter: str


def source_digest(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def open_ledger(path: Path | str) -> sqlite3.Connection:
    # constraint: autocommit, so a recorded row is durable on the real database file without a
    # constraint: separate commit call any caller could omit.
    connection = sqlite3.connect(path, isolation_level=None)
    connection.executescript(SCHEMA)
    return connection


def validated_row(observation: SourceObservation, *, error_cls: type[Exception]) -> EvidenceRow:
    if not SUBJECT_RE.fullmatch(observation.subject or ""):
        raise error_cls(f"evidence subject {observation.subject!r} is not one exact owner/repo#N subject")
    if not ADAPTER_RE.fullmatch(observation.adapter or ""):
        raise error_cls(f"evidence adapter {observation.adapter!r} is not one lowercase adapter identity")
    if not (observation.observation or "").strip():
        raise error_cls(f"evidence observation for {observation.subject} is empty")
    if not isinstance(observation.source, bytes):
        raise error_cls(
            f"evidence source for {observation.subject} must be exact bytes, "
            f"got {type(observation.source).__name__}"
        )
    return EvidenceRow(
        subject=observation.subject,
        observation=observation.observation,
        source_sha256=source_digest(observation.source),
        adapter=observation.adapter,
    )


def record(
    connection: sqlite3.Connection, observation: SourceObservation, *, error_cls: type[Exception]
) -> EvidenceRow:
    row = validated_row(observation, error_cls=error_cls)
    try:
        connection.execute(
            f"INSERT INTO evidence ({', '.join(LEDGER_COLUMNS)}) VALUES (?, ?, ?, ?)",
            (row.subject, row.observation, row.source_sha256, row.adapter),
        )
    except sqlite3.IntegrityError as exc:
        raise error_cls(f"duplicate exact subject rejected: {row.subject}") from exc
    return row


def read_back(
    connection: sqlite3.Connection, subject: str, source: bytes, *, error_cls: type[Exception]
) -> EvidenceRow:
    stored = connection.execute(f"{SELECT_ROW} WHERE subject = ?", (subject,)).fetchone()
    if stored is None:
        raise error_cls(f"no evidence row for exact subject {subject}")
    row = EvidenceRow(*stored)
    current = source_digest(source)
    if row.source_sha256 != current:
        raise error_cls(
            f"stale evidence for {subject}: the row was written against source {row.source_sha256}, "
            f"the current source is {current}"
        )
    return row


def canonical_export(connection: sqlite3.Connection) -> str:
    # constraint: ORDER BY subject, not rowid, so insertion order cannot reach the exported bytes.
    rows = connection.execute(f"{SELECT_ROW} ORDER BY subject").fetchall()
    payload = {"schema_version": SCHEMA_VERSION, "rows": [dict(zip(LEDGER_COLUMNS, row)) for row in rows]}
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def rebuild(
    path: Path | str, observations: Iterable[SourceObservation], *, error_cls: type[Exception]
) -> sqlite3.Connection:
    connection = open_ledger(path)
    for observation in observations:
        record(connection, observation, error_cls=error_cls)
    return connection
