"""Physical controls for the migrated claim: source bytes -> pinned parser/query -> structural
ranges -> direct source-byte readback.

The pin-shape gate and the readback comparator run everywhere, including hosted CI with no parser
installed. The live parse runs wherever the pinned wheels are actually present; the same gate is
what `./noodles structural verify` executes before handoff.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import noodles
import structural_contract
from tests.support import CANDIDATE_ROOT, cmd, copy_tracked

PARSER_INSTALLED = all(
    importlib.util.find_spec(module) is not None for module in ("tree_sitter", "tree_sitter_python")
)
SAMPLE = (
    "import functools\n"
    "\n"
    "\n"
    "class Outer:\n"
    "    @functools.cache\n"
    "    def método(self, x):\n"
    "        def inner():\n"
    "            return x\n"
    "        return inner\n"
    "\n"
    "\n"
    "async def top(y):\n"
    "    return y\n"
).encode("utf-8")


def candidate_copy(case: unittest.TestCase) -> Path:
    temp = tempfile.TemporaryDirectory(prefix="noodles-structural-test-", ignore_cleanup_errors=True)
    case.addCleanup(temp.cleanup)
    root = Path(temp.name) / "repo"
    copy_tracked(CANDIDATE_ROOT, root)
    return root


class ParserPinTests(unittest.TestCase):
    """The pin is the first gate: a floating or absent parser pin fails with no parser installed."""

    def test_repository_lock_is_pinned(self) -> None:
        self.assertEqual(structural_contract.validate_parser_lock(CANDIDATE_ROOT), [])

    def test_missing_lock_fails_closed_in_repository_verify(self) -> None:
        root = candidate_copy(self)
        (root / structural_contract.PARSER_LOCK_PATH).unlink()
        cmd(["git", "add", "-A"], root)
        cmd(["git", "commit", "-q", "-m", "planted missing parser lock"], root)
        result = noodles.verify_repository(root)
        self.assertFalse(result["ok"])
        self.assertIn(f"missing {structural_contract.PARSER_LOCK_PATH}", result["errors"])

    def test_planted_lock_defects_fail_closed(self) -> None:
        root = candidate_copy(self)
        path = root / structural_contract.PARSER_LOCK_PATH
        original = json.loads(path.read_text(encoding="utf-8"))
        cases = {
            "exact version": ("library", "version", "0.26", "not pinned to an exact version"),
            "exact commit": ("library", "commit", "a9e753e", "not pinned to an exact 40-hex commit"),
            "github source": ("grammar", "source", "https://pypi.org/project/tree-sitter-python/", "must be a GitHub HTTPS URL"),
            "grammar abi": ("grammar", "abi_version", "15", "abi_version must be an integer"),
            "grammar semver": ("grammar", "semantic_version", [0, 24, 0], "must restate the pinned version"),
            "grammar suffixes": ("grammar", "suffixes", ["py"], "must be a non-empty list of file suffixes"),
        }
        for label, (section, field, value, fragment) in cases.items():
            with self.subTest(case=label):
                planted = json.loads(json.dumps(original))
                planted["parser"][section][field] = value
                path.write_text(json.dumps(planted), encoding="utf-8")
                errors = structural_contract.validate_parser_lock(root)
                self.assertTrue(any(fragment in error for error in errors), errors)
        path.write_text(json.dumps({"schema_version": 2, "parser": original["parser"]}), encoding="utf-8")
        self.assertIn("unsupported parser lock schema: 2", structural_contract.validate_parser_lock(root))
        path.write_text("{not json", encoding="utf-8")
        self.assertTrue(structural_contract.validate_parser_lock(root)[0].startswith("invalid parser lock:"))


class ReadbackComparatorTests(unittest.TestCase):
    """CPython's parser supplies the expectation, so the comparator is independent of tree-sitter."""

    def expected(self) -> dict[tuple[int, int], str]:
        return structural_contract.expected_definitions(SAMPLE)

    def test_independent_expectation_slices_the_real_source_bytes(self) -> None:
        expected = self.expected()
        self.assertEqual(sorted(expected.values()), ["Outer", "inner", "método", "top"])
        for (start, end), name in expected.items():
            with self.subTest(name=name):
                self.assertTrue(SAMPLE[start:end].startswith((b"def ", b"async def ", b"class ")))
                self.assertIn(name.encode("utf-8"), SAMPLE[start:end])

    def observed_from_expectation(self) -> list[tuple[int, int, int, int]]:
        observed = []
        for (start, end), name in self.expected().items():
            header = SAMPLE.index(name.encode("utf-8"), start, end)
            observed.append((start, end, header, header + len(name.encode("utf-8"))))
        return sorted(observed)

    def test_matching_ranges_read_back_clean(self) -> None:
        self.assertEqual(
            structural_contract.readback_errors("sample.py", SAMPLE, self.observed_from_expectation(), self.expected()),
            [],
        )

    def test_planted_wrong_range_and_name_are_rejected(self) -> None:
        expected = self.expected()
        observed = self.observed_from_expectation()
        start, end, name_start, name_end = observed[0]
        cases = {
            "shifted end byte": ([(start, end - 1, name_start, name_end), *observed[1:]], "does not: bytes"),
            "missing definition": (observed[1:], "missed the structural range"),
            "shifted name range": ([(start, end, name_start + 1, name_end), *observed[1:]], "read back"),
            "range outside source": ([(start, len(SAMPLE) + 1, name_start, name_end), *observed[1:]], "does not: bytes"),
        }
        for label, (planted, fragment) in cases.items():
            with self.subTest(case=label):
                errors = structural_contract.readback_errors("sample.py", SAMPLE, planted, expected)
                self.assertTrue(any(fragment in error for error in errors), errors)


@unittest.skipUnless(
    PARSER_INSTALLED,
    "the pinned tree-sitter wheels are intentionally absent in hosted/offline CI; the live "
    "structural gate runs before handoff",
)
class LiveStructuralReadbackTests(unittest.TestCase):
    """The real repository is the fixture; the gate must go green here and red on every plant."""

    def language(self) -> tuple[object, object, tuple[str, ...]]:
        lock = structural_contract.load_parser_lock(CANDIDATE_ROOT, error_cls=noodles.GateError)
        module, language, _pins = structural_contract.load_language(lock, error_cls=noodles.GateError)
        return module, language, tuple(lock["grammar"]["suffixes"])

    def test_cli_parses_the_real_repository_and_every_control_stays_red(self) -> None:
        result = subprocess.run(
            [str(CANDIDATE_ROOT / "noodles"), "structural", "verify", "--json"],
            cwd=CANDIDATE_ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"], payload["errors"])
        self.assertGreater(payload["coverage"]["definitions"], 0)
        self.assertGreater(payload["coverage"]["unsupported_paths"], 0)
        self.assertEqual(payload["parser"]["grammar"]["semantic_version"], [0, 25, 0])
        for name, control in payload["controls"].items():
            with self.subTest(control=name):
                self.assertTrue(control["rejected"], control)
        self.assertEqual(payload["residue"]["before"], payload["residue"]["after"])

    def test_live_ranges_agree_with_cpython_on_a_real_repository_file(self) -> None:
        module, language, suffixes = self.language()
        relative = "structural_contract.py"
        source, observed, parse_error = structural_contract.definitions_for_path(
            CANDIDATE_ROOT, relative, module, language, suffixes, error_cls=noodles.GateError
        )
        self.assertIsNone(parse_error)
        expected = structural_contract.expected_definitions(source)
        self.assertGreater(len(observed), 0)
        self.assertEqual(structural_contract.readback_errors(relative, source, observed, expected), [])

    def test_malformed_input_reports_one_bounded_parse_error(self) -> None:
        module, language, _suffixes = self.language()
        observed, parse_error = structural_contract.observed_definitions(
            module, language, structural_contract.MALFORMED_SOURCE, structural_contract.DEFINITION_QUERY
        )
        self.assertIsNone(observed)
        self.assertIsNotNone(parse_error)
        self.assertLessEqual(parse_error["end_byte"], len(structural_contract.MALFORMED_SOURCE))
        self.assertLess(parse_error["start_byte"], parse_error["end_byte"])

    def test_unsupported_language_is_refused_not_silently_skipped(self) -> None:
        module, language, suffixes = self.language()
        with self.assertRaisesRegex(noodles.GateError, "unsupported language for AGENTS.md"):
            structural_contract.definitions_for_path(
                CANDIDATE_ROOT, "AGENTS.md", module, language, suffixes, error_cls=noodles.GateError
            )

    def test_unpinned_installed_parser_is_refused(self) -> None:
        lock = structural_contract.load_parser_lock(CANDIDATE_ROOT, error_cls=noodles.GateError)
        cases = {
            "library version": ("library", "version", "0.0.1", "is not the pinned 0.0.1"),
            "grammar version": ("grammar", "version", "0.0.1", "is not the pinned 0.0.1"),
            "grammar language": ("grammar", "language", "rust", "not the pinned 'rust'"),
            "grammar abi": ("grammar", "abi_version", 1, "is not the pinned 1"),
            "grammar semver": ("grammar", "semantic_version", [9, 9, 9], r"is not the pinned \[9, 9, 9\]"),
        }
        for label, (section, field, value, fragment) in cases.items():
            with self.subTest(case=label):
                planted = json.loads(json.dumps(lock))
                planted[section][field] = value
                with self.assertRaisesRegex(noodles.GateError, fragment):
                    structural_contract.load_language(planted, error_cls=noodles.GateError)


if __name__ == "__main__":
    unittest.main()
