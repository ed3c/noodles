"""One canary journey across the landed code-intelligence band, and its planted faults.

The chain under test is `intent query -> candidate paths -> structural/source readback -> one
exact-subject evidence row`: the GrepAI candidate generator (#7), the pinned tree-sitter structural
readback cross-checked against CPython (#6), and the SQLite evidence ledger (#5).

The consumer controls run everywhere, including hosted CI with no parser and no retrieval tool
installed, because they only need CPython's own parser to locate a definition. The journey itself
runs wherever the pinned tree-sitter wheels are present, driven by a stub search so that a missing
grepai index cannot silently turn the gate green.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import evidence_ledger
import noodles
import retrieval_contract
import structural_contract
from tests.support import CANDIDATE_ROOT

PARSER_INSTALLED = all(
    importlib.util.find_spec(module) is not None for module in ("tree_sitter", "tree_sitter_python")
)
SUBJECT = "ed3c/noodles#900009"
SAMPLE_PATH = "sample.py"
SAMPLE = (
    "import json\n"
    "\n"
    "\n"
    "def admitted(value):\n"
    "    return json.dumps(value)\n"
).encode("utf-8")


def sample_claim() -> dict[str, object]:
    """Locate the definition with CPython's own parser, so the fixture needs no tree-sitter."""
    (span, name), = structural_contract.expected_definitions(SAMPLE).items()
    name_start = SAMPLE.index(name.encode("utf-8"))
    return {
        "path": SAMPLE_PATH,
        "definition": name,
        "range": [span[0], span[1]],
        "name_range": [name_start, name_start + len(name)],
    }


class AdmitCanaryRowTests(unittest.TestCase):
    """Five boundaries, five planted faults, five refusals: subject, digest, adapter, path, range."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="noodles-canary-consumer-")
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.claim = sample_claim()
        self.connection = self.ledger("real", self.claim)

    def ledger(self, name: str, observation: object) -> object:
        connection = retrieval_contract._planted_ledger(
            self.directory,
            name,
            SUBJECT,
            SAMPLE,
            observation if isinstance(observation, str) else json.dumps(observation, sort_keys=True),
            error_cls=noodles.GateError,
        )
        self.addCleanup(connection.close)
        return connection

    def admit(
        self,
        connection: object | None = None,
        subject: str = SUBJECT,
        source: bytes = SAMPLE,
        adapter: str = retrieval_contract.CANARY_ADAPTER,
        path: str = SAMPLE_PATH,
    ) -> dict[str, object]:
        return retrieval_contract.admit_canary_row(
            self.connection if connection is None else connection,
            subject,
            source,
            adapter=adapter,
            path=path,
            error_cls=noodles.GateError,
        )

    def test_positive_control_serves_the_exact_row(self) -> None:
        admitted = self.admit()
        self.assertEqual(admitted["subject"], SUBJECT)
        self.assertEqual(admitted["adapter"], retrieval_contract.CANARY_ADAPTER)
        self.assertEqual(admitted["definition"], "admitted")
        self.assertEqual(admitted["source_sha256"], hashlib.sha256(SAMPLE).hexdigest())
        start, end = admitted["range"]
        self.assertTrue(SAMPLE[start:end].startswith(b"def admitted"))

    def test_a_different_exact_subject_finds_no_row(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "no evidence row for exact subject"):
            self.admit(subject=retrieval_contract.CONTROL_FOREIGN_SUBJECT)

    def test_renamed_in_place_source_is_refused_as_stale(self) -> None:
        name_start, name_end = self.claim["name_range"]
        renamed = SAMPLE[:name_start] + b"x" * (name_end - name_start) + SAMPLE[name_end:]
        self.assertEqual(len(renamed), len(SAMPLE))
        with self.assertRaisesRegex(noodles.GateError, "stale evidence"):
            self.admit(source=renamed)

    def test_foreign_adapter_identity_is_refused(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "not the expected 'not-the-canary'"):
            self.admit(adapter=retrieval_contract.CONTROL_FOREIGN_ADAPTER)

    def test_row_naming_another_path_is_refused(self) -> None:
        connection = self.ledger("path", {**self.claim, "path": retrieval_contract.CONTROL_FOREIGN_PATH})
        with self.assertRaisesRegex(noodles.GateError, "not the requested 'sample.py'"):
            self.admit(connection=connection)

    def test_shifted_and_out_of_bounds_ranges_are_refused(self) -> None:
        start, end = self.claim["range"]
        name_start, name_end = self.claim["name_range"]
        plants = {
            "shifted by one": (
                {"range": [start + 1, end], "name_range": [name_start + 1, name_end + 1]},
                "which read back",
            ),
            "past the source bytes": ({"range": [start, len(SAMPLE) + 1]}, "not inside the"),
            "name outside the definition": ({"name_range": [end + 1, end + 3]}, "not inside the"),
        }
        for label, (override, fragment) in plants.items():
            with self.subTest(plant=label):
                connection = self.ledger(f"range-{label.replace(' ', '-')}", {**self.claim, **override})
                with self.assertRaisesRegex(noodles.GateError, fragment):
                    self.admit(connection=connection)

    def test_unreadable_observation_is_refused_instead_of_parsed_loosely(self) -> None:
        connection = self.ledger("prose", "the definition is somewhere in sample.py")
        with self.assertRaisesRegex(noodles.GateError, "is not one structural claim"):
            self.admit(connection=connection)

    def test_every_planted_control_is_recorded_as_a_proven_refusal(self) -> None:
        controls = retrieval_contract.canary_controls(
            self.directory, self.connection, SUBJECT, SAMPLE, SAMPLE_PATH, self.claim, error_cls=noodles.GateError
        )
        self.assertEqual(
            [control["control"] for control in controls],
            ["wrong_subject", "stale_source", "wrong_adapter", "wrong_path", "wrong_range"],
        )
        for control in controls:
            with self.subTest(control=control["control"]):
                self.assertTrue(control["rejected"])
                self.assertTrue(control["diagnostic"].strip())

    def test_a_control_whose_consumer_stays_blind_fails_the_run(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "planted control blind did not fail"):
            retrieval_contract._canary_control("blind", "a consumer that admits anything", lambda: None, error_cls=noodles.GateError)


class CanaryCommandSurfaceTests(unittest.TestCase):
    def test_cli_accepts_the_canary_action_against_an_index_root(self) -> None:
        arguments = noodles.build_parser().parse_args(["retrieval", "canary", "--index-root", "/elsewhere"])
        self.assertEqual((arguments.command, arguments.action), ("retrieval", "canary"))

    def test_canary_subject_and_evidence_path_are_exact(self) -> None:
        self.assertRegex(retrieval_contract.CANARY_SUBJECT, r"^ed3c/noodles#\d+$")
        self.assertTrue(retrieval_contract.CANARY_EVIDENCE_PATH.startswith(".noodle/"))


@unittest.skipUnless(
    PARSER_INSTALLED,
    "the pinned tree-sitter wheels are intentionally absent in hosted/offline CI; the live canary "
    "journey runs wherever the band's parser is actually installed",
)
class LiveCanaryJourneyTests(unittest.TestCase):
    """The real repository is the fixture. Retrieval is stubbed so a stale index cannot fake a pass."""

    def definition_line(self, relative: str, declaration: str) -> int:
        lines = (CANDIDATE_ROOT / relative).read_text(encoding="utf-8").splitlines()
        return next(index + 1 for index, line in enumerate(lines) if line.startswith(declaration))

    def search(self, candidates: list[dict[str, object]]):
        return lambda _query: json.dumps(candidates)

    def candidate(self, path: str, start: int, end: int, score: float = 0.5) -> dict[str, object]:
        return {"file_path": path, "start_line": start, "end_line": end, "score": score}

    def test_journey_resolves_a_python_candidate_to_one_exact_subject_evidence_row(self) -> None:
        line = self.definition_line("evidence_ledger.py", "def source_digest(")
        receipt = retrieval_contract.code_intel_journey(
            CANDIDATE_ROOT,
            self.search([self.candidate("AGENTS.md", 1, 4, 0.9), self.candidate("evidence_ledger.py", line, line + 1)]),
            SUBJECT,
            error_cls=noodles.GateError,
        )
        claim = receipt["chain"]["structural"]["claim"]
        self.assertEqual(claim["path"], "evidence_ledger.py")
        self.assertEqual(claim["definition"], "source_digest")
        self.assertEqual(receipt["chain"]["candidate"]["path"], "evidence_ledger.py")
        self.assertEqual(receipt["chain"]["evidence_row"]["subject"], SUBJECT)
        self.assertEqual(receipt["chain"]["evidence_row"]["adapter"], retrieval_contract.CANARY_ADAPTER)
        self.assertEqual(
            receipt["chain"]["evidence_row"]["source_sha256"],
            hashlib.sha256((CANDIDATE_ROOT / "evidence_ledger.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(receipt["chain"]["structural"]["parser"]["grammar"]["semantic_version"], [0, 25, 0])
        self.assertEqual(receipt["subject"], SUBJECT)
        self.assertEqual(receipt["authority"], "P")

    def test_journey_records_latency_context_bytes_evidence_digest_and_residue(self) -> None:
        line = self.definition_line("evidence_ledger.py", "def source_digest(")
        receipt = retrieval_contract.code_intel_journey(
            CANDIDATE_ROOT, self.search([self.candidate("evidence_ledger.py", line, line + 1)]), SUBJECT, error_cls=noodles.GateError
        )
        metrics = receipt["metrics"]
        for field in ("retrieval_ms", "structural_ms", "ledger_ms", "context_bytes", "evidence_sha256"):
            with self.subTest(metric=field):
                self.assertIn(field, metrics)
        self.assertGreater(metrics["context_bytes"], 0)
        self.assertEqual(metrics["context_bytes"], metrics["candidate_context_bytes"] + metrics["definition_bytes"])
        self.assertRegex(metrics["evidence_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["residue"]["tree_sha256"], retrieval_contract._tree_digest(CANDIDATE_ROOT)[0])
        self.assertTrue(receipt["residue"]["ledger_outside_candidate_tree"])
        self.assertTrue(receipt["non_claims"])

    def test_every_boundary_control_stays_red_inside_the_journey(self) -> None:
        line = self.definition_line("evidence_ledger.py", "def source_digest(")
        receipt = retrieval_contract.code_intel_journey(
            CANDIDATE_ROOT, self.search([self.candidate("evidence_ledger.py", line, line + 1)]), SUBJECT, error_cls=noodles.GateError
        )
        self.assertEqual(
            [control["control"] for control in receipt["controls"]],
            ["wrong_subject", "stale_source", "wrong_adapter", "wrong_path", "wrong_range"],
        )
        for control in receipt["controls"]:
            with self.subTest(control=control["control"]):
                self.assertTrue(control["rejected"], control)

    def test_a_candidate_set_the_grammar_cannot_cover_fails_closed_without_claiming_absence(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "a candidate miss is never absence proof"):
            retrieval_contract.code_intel_journey(
                CANDIDATE_ROOT, self.search([self.candidate("AGENTS.md", 1, 4)]), SUBJECT, error_cls=noodles.GateError
            )

    def test_a_python_candidate_carrying_no_definition_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "a candidate miss is never absence proof"):
            retrieval_contract.code_intel_journey(
                CANDIDATE_ROOT, self.search([self.candidate("evidence_ledger.py", 1, 2)]), SUBJECT, error_cls=noodles.GateError
            )

    def test_a_stale_candidate_line_range_fails_closed_before_any_evidence_row(self) -> None:
        lines = len((CANDIDATE_ROOT / "evidence_ledger.py").read_bytes().splitlines())
        with self.assertRaisesRegex(noodles.GateError, "stale retrieval index"):
            retrieval_contract.code_intel_journey(
                CANDIDATE_ROOT, self.search([self.candidate("evidence_ledger.py", lines, lines + 50)]), SUBJECT, error_cls=noodles.GateError
            )


if __name__ == "__main__":
    unittest.main()
