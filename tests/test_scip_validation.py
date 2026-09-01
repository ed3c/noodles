from __future__ import annotations

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


class ScipLookupCoreTests(unittest.TestCase):
    """The lookup core is the part trusted CI can re-run; the external indexer is not installed here."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
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


if __name__ == "__main__":
    unittest.main()
