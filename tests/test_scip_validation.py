from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import scip_validation
from scip_validation import ScipError
from tests.support import CANDIDATE_ROOT

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
    """The committed receipt must name the exact pins and record both controls as proven failures."""

    def setUp(self) -> None:
        self.evidence = json.loads((CANDIDATE_ROOT / scip_validation.EVIDENCE_PATH).read_text(encoding="utf-8"))

    def test_recorded_run_admits_and_the_index_names_its_own_pinned_producer(self) -> None:
        self.assertEqual(scip_validation.admit_evidence(self.evidence), self.evidence)
        self.assertEqual(
            self.evidence["index"]["tool_info"],
            {"name": scip_validation.INDEXER_PIN["tool"], "version": scip_validation.INDEXER_PIN["version"]},
        )
        for pin in (scip_validation.INDEXER_PIN, scip_validation.READER_PIN):
            self.assertRegex(pin["commit"], r"^[0-9a-f]{40}$")

    def test_the_ledger_routes_to_the_machine_receipt_without_promoting_itself(self) -> None:
        # constraint: the receipt is a pointer, not a promotion; capabilities[6] stays the evidence-free MIGRATE negative fixture.
        ledger = json.loads((CANDIDATE_ROOT / "migrations/skills-shared/ledger.json").read_text(encoding="utf-8"))
        entry = next(item for item in ledger["capabilities"] if item["id"] == scip_validation.LEDGER_CAPABILITY)
        self.assertEqual(entry["validation_receipt"], scip_validation.EVIDENCE_PATH)
        self.assertEqual(entry["physical_evidence"], [])

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
