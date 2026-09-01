from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import scip_validation
from scip_validation import ScipError

SOURCE_A = b"from b import shared\n\n\ndef shared() -> int:\n    return 1\n"
SOURCE_B = b"def caller() -> int:\n    return shared()\n"
SYMBOL = "scip-python python noodles af95f1321a9b a/shared()."
PAYLOAD = {
    "metadata": {"tool_info": {"name": "scip-python", "version": "0.6.6"}, "project_root": "file:///tmp/x"},
    "documents": [
        {
            "relative_path": "a.py",
            "occurrences": [
                {"range": [3, 4, 10], "symbol": SYMBOL, "symbol_roles": 1},
                {"range": [0, 14, 20], "symbol": SYMBOL, "symbol_roles": 8},
                {"range": [3, 4, 10], "symbol": "local 3", "symbol_roles": 1},
            ],
        },
        {
            "relative_path": "b.py",
            "occurrences": [{"range": [1, 11, 17], "symbol": SYMBOL, "symbol_roles": 8}],
        },
    ],
}
COMMIT = "af95f1321a9b" + "0" * 28
# constraint: ed3c/noodles#293 - the admission fixture is synthesized here rather than read from a
# constraint: committed receipt, so the admission core survives the retired migration evidence
# constraint: station and this gate keeps naming exactly what admit_evidence itself requires.
EVIDENCE = {
    "schema_version": scip_validation.SCHEMA_VERSION,
    "capability": scip_validation.CAPABILITY,
    "indexer": dict(scip_validation.INDEXER_PIN),
    "reader": dict(scip_validation.READER_PIN),
    "repository": {"repo": "ed3c/noodles", "commit": COMMIT, "tree": "b" * 40},
    "index": {
        "project_root": "file:///tmp/x",
        "tool_info": dict(PAYLOAD["metadata"]["tool_info"]),
        "sha256": "c" * 64,
        "bytes": 4096,
    },
    "lookups": {
        "symbol": SYMBOL,
        "definition": {"path": "a.py", "range": [3, 4, 10], "text": "shared"},
        "reference_count": 2,
        "cross_file_reference": {"path": "b.py", "range": [1, 11, 17], "text": "shared"},
        "source_readback": "shared",
    },
    "controls": [
        {
            "control": scip_validation.CONTROL_UNCOVERED,
            "description": "a tracked non-Python file is outside the indexer's language coverage",
            "rejected": True,
            "diagnostic": "uncovered: run.sh has no SCIP document",
        },
        {
            "control": scip_validation.CONTROL_STALE,
            "description": "the definition is renamed in place, so every byte offset still matches",
            "rejected": True,
            "diagnostic": "stale index: a.py[3, 4, 10] reads 'xxxxxx', recorded 'shared'",
        },
    ],
    "metrics": {
        "build_seconds": 1.5,
        "index_read_seconds": 0.25,
        "query_seconds": 0.01,
        "index_bytes": 4096,
        "indexed_documents": 2,
        "tracked_files": 2,
        "tracked_python_files": 2,
        "python_coverage": 1.0,
        "tracked_coverage": 1.0,
        "residue": [],
    },
    "non_claims": ["one past physical run at the recorded commit, never a Golden Path dependency"],
}


class ScipLookupCoreTests(unittest.TestCase):
    """The lookup core is the part trusted CI can re-run; the external indexer is not installed here."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "a.py").write_bytes(SOURCE_A)
        (self.root / "b.py").write_bytes(SOURCE_B)

    def test_definition_reference_cross_file_and_direct_source_readback(self) -> None:
        definition_path, definition_range = scip_validation.definition_of(PAYLOAD, SYMBOL)
        self.assertEqual((definition_path, definition_range), ("a.py", [3, 4, 10]))
        self.assertEqual(len(scip_validation.references_of(PAYLOAD, SYMBOL)), 2)
        cross_path, cross_range = scip_validation.cross_file_reference(PAYLOAD, SYMBOL, definition_path)
        self.assertEqual((cross_path, cross_range), ("b.py", [1, 11, 17]))
        self.assertEqual(scip_validation.verify_readback(self.root, definition_path, definition_range, "shared"), "shared")
        self.assertEqual(scip_validation.verify_readback(self.root, cross_path, cross_range, "shared"), "shared")

    def test_planted_unsupported_coverage_control_refuses_instead_of_reading_empty(self) -> None:
        scip_validation.require_covered(PAYLOAD, "a.py")
        with self.assertRaises(ScipError) as refusal:
            scip_validation.require_covered(PAYLOAD, "run.sh")
        self.assertIn("uncovered", str(refusal.exception))

    def test_planted_stale_index_control_survives_an_offset_preserving_rename(self) -> None:
        (self.root / "a.py").write_bytes(scip_validation.rename_in_place(SOURCE_A, [3, 4, 10]))
        self.assertEqual(len((self.root / "a.py").read_bytes()), len(SOURCE_A))
        with self.assertRaises(ScipError) as refusal:
            scip_validation.verify_readback(self.root, "a.py", [3, 4, 10], "shared")
        self.assertIn("stale index", str(refusal.exception))

    def test_per_document_local_symbols_and_malformed_payloads_fail_closed(self) -> None:
        for symbol in ("local 3", "shared", ""):
            with self.assertRaises(ScipError):
                scip_validation.definition_of(PAYLOAD, symbol)
        with self.assertRaises(ScipError):
            scip_validation.documents({"documents": [{"occurrences": []}]})
        with self.assertRaises(ScipError):
            scip_validation.definition_of({"documents": []}, SYMBOL)


class ScipEvidenceAdmissionTests(unittest.TestCase):
    """A receipt is admitted only when it names the exact pins and records both controls as proven failures."""

    def setUp(self) -> None:
        self.evidence = copy.deepcopy(EVIDENCE)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "a.py").write_bytes(SOURCE_A)
        (self.root / "b.py").write_bytes(SOURCE_B)

    def test_recorded_run_admits_and_the_index_names_its_own_pinned_producer(self) -> None:
        self.assertEqual(scip_validation.admit_evidence(self.evidence, root=self.root), self.evidence)
        self.assertEqual(
            self.evidence["index"]["tool_info"],
            {"name": scip_validation.INDEXER_PIN["tool"], "version": scip_validation.INDEXER_PIN["version"]},
        )
        for pin in (scip_validation.INDEXER_PIN, scip_validation.READER_PIN):
            self.assertRegex(pin["commit"], r"^[0-9a-f]{40}$")

    def test_source_readback_refuses_a_receipt_whose_range_no_longer_spells_the_definition(self) -> None:
        (self.root / "a.py").write_bytes(scip_validation.rename_in_place(SOURCE_A, [3, 4, 10]))
        with self.assertRaises(ScipError) as refusal:
            scip_validation.admit_evidence(self.evidence, root=self.root)
        self.assertIn("stale index", str(refusal.exception))

    def test_planted_evidence_mutations_are_all_rejected(self) -> None:
        # constraint: each mutation removes exactly one physical property the receipt claims to have proven.
        mutations = {
            "unpinned indexer": lambda item: item["indexer"].update({"commit": "0" * 40}),
            "forged commit": lambda item: item["repository"].update({"commit": "not-a-commit"}),
            "no built index": lambda item: item["index"].update({"bytes": 0}),
            "index disowns its pinned producer": lambda item: item["index"]["tool_info"].update({"version": "0.6.5"}),
            "same-file relation": lambda item: item["lookups"]["cross_file_reference"].update(
                {"path": item["lookups"]["definition"]["path"]}
            ),
            "no references": lambda item: item["lookups"].update({"reference_count": 0}),
            "readback text drift": lambda item: item["lookups"]["definition"].update({"text": "other"}),
            "symbol from another commit": lambda item: item["lookups"].update(
                {"symbol": item["lookups"]["symbol"].replace(item["repository"]["commit"][:12], "000000000000")}
            ),
            "control silently passed": lambda item: item["controls"][0].update({"rejected": False}),
            "control without diagnostic": lambda item: item["controls"][1].update({"diagnostic": "  "}),
            "one control dropped": lambda item: item["controls"].pop(),
            "residue left behind": lambda item: item["metrics"].update({"residue": ["?? index.scip"]}),
            "no non-claims": lambda item: item.update({"non_claims": []}),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                planted = copy.deepcopy(self.evidence)
                mutate(planted)
                with self.assertRaises(ScipError):
                    scip_validation.admit_evidence(planted)

        for field in scip_validation.EVIDENCE_FIELDS:
            with self.subTest(missing=field):
                planted = copy.deepcopy(self.evidence)
                planted.pop(field)
                with self.assertRaises(ScipError):
                    scip_validation.admit_evidence(planted)


if __name__ == "__main__":
    unittest.main()
