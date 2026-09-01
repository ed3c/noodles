from __future__ import annotations

import dataclasses
import sqlite3
import tempfile
import unittest
from pathlib import Path

import evidence_ledger
import noodles

OBSERVATIONS = (
    evidence_ledger.SourceObservation(
        subject="ed3c/noodles#5",
        observation="state=in_progress",
        source=b"<!-- noodles-state: in_progress -->\n",
        adapter="github",
    ),
    evidence_ledger.SourceObservation(
        subject="ed3c/noodles#4",
        observation="state=landed",
        source=b"<!-- noodles-state: landed -->\n",
        adapter="github",
    ),
    evidence_ledger.SourceObservation(
        subject="ed3c/noodles#20",
        observation="feature=verification-skill-oracle",
        source=b"<!-- noodles-feature: verification-skill-oracle -->\n",
        adapter="feature-map",
    ),
)


class EvidenceLedgerTests(unittest.TestCase):
    def ledger_dir(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        # constraint: a real on-disk SQLite database, never :memory:, so residue is observable.
        temp = tempfile.TemporaryDirectory(prefix="noodles-evidence-ledger-", ignore_cleanup_errors=True)
        return temp, Path(temp.name)

    def test_insert_exact_readback_and_order_independent_rebuild(self) -> None:
        temp, root = self.ledger_dir()
        with temp:
            forward = evidence_ledger.rebuild(root / "forward.sqlite3", OBSERVATIONS, error_cls=noodles.GateError)
            self.addCleanup(forward.close)

            for observation in OBSERVATIONS:
                row = evidence_ledger.read_back(
                    forward, observation.subject, observation.source, error_cls=noodles.GateError
                )
                self.assertEqual(
                    dataclasses.astuple(row),
                    (
                        observation.subject,
                        observation.observation,
                        evidence_ledger.source_digest(observation.source),
                        observation.adapter,
                    ),
                )
                self.assertNotIn(observation.source.decode(), evidence_ledger.canonical_export(forward))

            reverse = evidence_ledger.rebuild(
                root / "reverse.sqlite3", tuple(reversed(OBSERVATIONS)), error_cls=noodles.GateError
            )
            self.addCleanup(reverse.close)
            export = evidence_ledger.canonical_export(forward)
            self.assertEqual(export, evidence_ledger.canonical_export(reverse))
            self.assertEqual(export.count('"subject"'), len(OBSERVATIONS))

            # constraint: planted negatives prove the export is not blind to the fields it exports;
            # constraint: an export that ignored adapter identity or source bytes would stay green here.
            for index, field, value in (
                (0, "adapter", "impostor"),
                (0, "observation", "state=landed"),
                (0, "source", b"<!-- noodles-state: landed -->\n"),
            ):
                planted = list(OBSERVATIONS)
                planted[index] = dataclasses.replace(planted[index], **{field: value})
                drifted = evidence_ledger.rebuild(
                    root / f"planted-{field}.sqlite3", planted, error_cls=noodles.GateError
                )
                self.addCleanup(drifted.close)
                self.assertNotEqual(export, evidence_ledger.canonical_export(drifted), field)

    def test_duplicate_exact_subject_and_stale_source_are_refused(self) -> None:
        temp, root = self.ledger_dir()
        with temp:
            original = OBSERVATIONS[0]
            ledger = evidence_ledger.rebuild(root / "ledger.sqlite3", (original,), error_cls=noodles.GateError)
            self.addCleanup(ledger.close)
            before = evidence_ledger.canonical_export(ledger)

            duplicate = dataclasses.replace(
                original, observation="state=landed", source=b"other", adapter="impostor"
            )
            with self.assertRaises(noodles.GateError) as duplicate_error:
                evidence_ledger.record(ledger, duplicate, error_cls=noodles.GateError)
            self.assertIn("duplicate exact subject rejected", str(duplicate_error.exception))
            self.assertEqual(before, evidence_ledger.canonical_export(ledger))

            with self.assertRaises(noodles.GateError) as stale_error:
                evidence_ledger.read_back(ledger, original.subject, b"drifted source", error_cls=noodles.GateError)
            self.assertIn("stale evidence", str(stale_error.exception))
            # constraint: refusing a stale read is not deletion - the exact source still reads back.
            self.assertEqual(
                evidence_ledger.read_back(
                    ledger, original.subject, original.source, error_cls=noodles.GateError
                ).observation,
                original.observation,
            )

            with self.assertRaises(noodles.GateError):
                evidence_ledger.read_back(ledger, "ed3c/noodles#999", b"missing", error_cls=noodles.GateError)

            # constraint: each malformed case gets its own unused subject, so the guard under test is
            # constraint: the only thing that can reject it - a subject collision would mask a
            # constraint: deleted guard behind the duplicate refusal and report a false green.
            malformed_cases = (
                ("subject", "ed3c/noodles"),
                ("subject", "#5"),
                ("subject", "other/repo#5 "),
                ("adapter", ""),
                ("adapter", "GitHub"),
                ("observation", "   "),
                ("source", "<!-- noodles-state: in_progress -->\n"),
            )
            for index, (field, value) in enumerate(malformed_cases):
                fresh = dataclasses.replace(original, subject=f"ed3c/noodles#{100 + index}")
                malformed = dataclasses.replace(fresh, **{field: value})
                with self.assertRaises(noodles.GateError, msg=f"{field}={value!r}"):
                    evidence_ledger.record(ledger, malformed, error_cls=noodles.GateError)
            self.assertEqual(before, evidence_ledger.canonical_export(ledger))

    def test_ledger_leaves_one_file_and_explicit_cleanup_reads_back_empty(self) -> None:
        temp, root = self.ledger_dir()
        with temp:
            path = root / "ledger.sqlite3"
            ledger = evidence_ledger.rebuild(path, OBSERVATIONS, error_cls=noodles.GateError)
            ledger.close()
            # constraint: no -wal / -shm / -journal residue survives close, so cleanup is one unlink.
            self.assertEqual(sorted(entry.name for entry in root.iterdir()), [path.name])

            reopened = evidence_ledger.open_ledger(path)
            self.addCleanup(reopened.close)
            self.assertEqual(
                evidence_ledger.canonical_export(reopened),
                evidence_ledger.canonical_export(
                    evidence_ledger.rebuild(root / "control.sqlite3", OBSERVATIONS, error_cls=noodles.GateError)
                ),
            )
            reopened.close()

            for entry in sorted(root.iterdir()):
                entry.unlink()
            self.assertEqual(list(root.iterdir()), [])

    def test_schema_refuses_a_direct_duplicate_write(self) -> None:
        temp, root = self.ledger_dir()
        with temp:
            ledger = evidence_ledger.open_ledger(root / "schema.sqlite3")
            self.addCleanup(ledger.close)
            columns = ", ".join(evidence_ledger.LEDGER_COLUMNS)
            row = ("ed3c/noodles#5", "state=in_progress", evidence_ledger.source_digest(b""), "github")
            ledger.execute(f"INSERT INTO evidence ({columns}) VALUES (?, ?, ?, ?)", row)
            # constraint: the refusal lives in the database, not in record(), so a writer that
            # constraint: bypasses this module is still refused.
            with self.assertRaises(sqlite3.IntegrityError):
                ledger.execute(f"INSERT INTO evidence ({columns}) VALUES (?, ?, ?, ?)", row)


if __name__ == "__main__":
    unittest.main()
