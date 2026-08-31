"""GrepAI is admitted only as `query -> candidate paths -> direct source readback`.

Every case here is a planted control derived from a physically observed grepai 0.30.0 behaviour, so the
gate is proven able to go red rather than merely observed green: an exit-zero error object, an empty
index answering like a genuine miss, a stale path or line range, a nonsense query that outranks the
real one, and a run that touches the candidate tree.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import noodles
import retrieval_contract
from tests.support import CANDIDATE_ROOT, copy_tracked

LOCK_RELATIVE = retrieval_contract.LOCK_PATH


def candidate_json(path: str, start: int, end: int, score: float) -> dict[str, object]:
    return {"file_path": path, "start_line": start, "end_line": end, "score": score}


def source_slice_sha256(root: Path, relative: str, start: int, end: int) -> tuple[int, str]:
    lines = (root / relative).read_bytes().splitlines(keepends=True)
    body = b"".join(lines[start - 1 : end])
    return len(body), hashlib.sha256(body).hexdigest()


class RetrievalPinGateTests(unittest.TestCase):
    """The pin gate must run with no grepai, no index, and no network, so a floating pin fails on
    every host including CI where the tool is absent."""

    def candidate_copy(self) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-retrieval-pin-test-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return root

    def write_lock(self, root: Path, mutate) -> None:
        payload = json.loads((root / LOCK_RELATIVE).read_text(encoding="utf-8"))
        mutate(payload["retrieval"])
        (root / LOCK_RELATIVE).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def test_positive_control_admits_the_repository_pin(self) -> None:
        self.assertEqual(retrieval_contract.validate_retrieval_lock(CANDIDATE_ROOT), [])
        pin = retrieval_contract.load_retrieval_pin(CANDIDATE_ROOT, error_cls=noodles.GateError)
        self.assertEqual(pin["authority"], retrieval_contract.AUTHORITY)
        self.assertEqual(
            retrieval_contract.pinned_argv(pin, "some query")[:3], [pin["command"], "search", "some query"]
        )

    def test_planted_floating_pins_are_rejected(self) -> None:
        plants = {
            "floating version": (lambda pin: pin.__setitem__("version", "latest"), "exact semver"),
            "floating argv token": (lambda pin: pin["argv"].append("latest"), "floating ref"),
            "no query placeholder": (lambda pin: pin.__setitem__("argv", [pin["command"], "search"]), "{query}"),
            "short binary digest": (lambda pin: pin.__setitem__("binary_sha256", "abc123"), "binary_sha256"),
            "floating embed model": (lambda pin: pin["embedder"].__setitem__("model", "latest"), "embedder model"),
            "unpinned embed digest": (lambda pin: pin["embedder"].__setitem__("digest", ""), "embedder digest"),
            "upgraded authority": (lambda pin: pin.__setitem__("authority", "L"), "authority"),
            "foreign argv command": (lambda pin: pin["argv"].__setitem__(0, "ripgrep"), "pinned command"),
            "missing nonsense control": (
                lambda pin: pin["control"].__setitem__("nonsense_query", ""),
                "nonsense_query is required",
            ),
        }
        for label, (mutate, expected) in plants.items():
            with self.subTest(plant=label):
                root = self.candidate_copy()
                self.write_lock(root, mutate)
                errors = retrieval_contract.validate_retrieval_lock(root)
                self.assertTrue(any(expected in error for error in errors), f"{label}: {errors}")

    def test_repository_verify_fails_closed_without_the_pin(self) -> None:
        root = self.candidate_copy()
        (root / LOCK_RELATIVE).unlink()
        observed = noodles.verify_repository(root)
        self.assertFalse(observed["ok"])
        self.assertIn(f"missing {LOCK_RELATIVE}", observed["errors"])

    def test_repository_verify_command_rejects_a_floating_pin(self) -> None:
        root = self.candidate_copy()
        self.write_lock(root, lambda pin: pin.__setitem__("version", "latest"))
        result = subprocess.run(["./noodles", "verify"], cwd=root, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("exact semver", result.stderr)


class RetrievalWireShapeTests(unittest.TestCase):
    """grepai signals some failures as an exit-zero JSON object, so the wire shape decides admission."""

    def test_exit_zero_error_object_is_never_read_as_candidates(self) -> None:
        observed = json.dumps({"error": 'failed to send request to Ollama: dial tcp [::1]:11434: connect refused'})
        with self.assertRaises(noodles.GateError) as raised:
            retrieval_contract.parse_candidates(observed, error_cls=noodles.GateError)
        self.assertIn("reported a failure instead of candidates", str(raised.exception))

    def test_unreadable_or_untyped_output_fails_closed(self) -> None:
        for observed in ("", "not json", "[1, 2]", json.dumps([{"file_path": "noodles.py"}])):
            with self.subTest(observed=observed[:24]):
                with self.assertRaises(noodles.GateError):
                    retrieval_contract.parse_candidates(observed, error_cls=noodles.GateError)

    def test_compact_candidate_records_parse_to_path_line_range_and_score(self) -> None:
        observed = json.dumps([candidate_json("noodles.py", 3, 9, 0.42)])
        self.assertEqual(
            retrieval_contract.parse_candidates(observed, error_cls=noodles.GateError),
            ({"path": "noodles.py", "start_line": 3, "end_line": 9, "score": 0.42},),
        )


class RetrievalReadbackTests(unittest.TestCase):
    """A candidate is a path plus a range. The bytes come from the candidate tree or the run fails."""

    def test_source_bytes_are_read_back_from_the_candidate_tree(self) -> None:
        expected_bytes, expected_sha = source_slice_sha256(CANDIDATE_ROOT, "AGENTS.md", 1, 5)
        observed = retrieval_contract.readback_candidate(
            CANDIDATE_ROOT, {"path": "AGENTS.md", "start_line": 1, "end_line": 5, "score": 0.5},
            error_cls=noodles.GateError,
        )
        self.assertEqual(observed["source_bytes"], expected_bytes)
        self.assertEqual(observed["source_sha256"], expected_sha)

    def test_stale_missing_and_escaping_candidates_fail_closed(self) -> None:
        plants = {
            "path absent from the tree": ({"path": "no_such_module.py", "start_line": 1, "end_line": 2}, "not a file"),
            "range past end of file": ({"path": "AGENTS.md", "start_line": 1, "end_line": 10_000_000}, "stale"),
            "inverted range": ({"path": "AGENTS.md", "start_line": 9, "end_line": 3}, "stale"),
            "escaping path": ({"path": "../outside.py", "start_line": 1, "end_line": 2}, "escapes"),
            "absolute path": ({"path": "/etc/hosts", "start_line": 1, "end_line": 2}, "escapes"),
        }
        for label, (candidate, expected) in plants.items():
            with self.subTest(plant=label):
                with self.assertRaises(noodles.GateError) as raised:
                    retrieval_contract.readback_candidate(
                        CANDIDATE_ROOT, {**candidate, "score": 0.1}, error_cls=noodles.GateError
                    )
                self.assertIn(expected, str(raised.exception))


class RetrievalProbeTests(unittest.TestCase):
    """The probe binds both controls, the readback, and the residue check into one receipt."""

    def candidate_copy(self) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-retrieval-probe-test-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return root

    def searcher(self, per_query: dict[str, str]):
        def search(query: str) -> str:
            return per_query[query]

        return search

    def queries(self, root: Path) -> tuple[str, str]:
        pin = retrieval_contract.load_retrieval_pin(root, error_cls=noodles.GateError)
        return pin["control"]["positive_query"], pin["control"]["nonsense_query"]

    def test_positive_and_nonsense_controls_produce_a_candidate_only_receipt(self) -> None:
        root = self.candidate_copy()
        positive, nonsense = self.queries(root)
        receipt = retrieval_contract.probe_retrieval(
            root,
            self.searcher(
                {
                    positive: json.dumps([candidate_json("noodles.py", 1, 4, 0.40)]),
                    nonsense: json.dumps([candidate_json("README.md", 1, 6, 0.53)]),
                }
            ),
            error_cls=noodles.GateError,
        )
        self.assertEqual(receipt["authority"], "P")
        self.assertIn("hit != source truth", receipt["laws"])
        self.assertIn("no absence proof", receipt["non_claims"])
        self.assertEqual(receipt["observations"]["positive"]["candidate_count"], 1)
        self.assertEqual(receipt["observations"]["nonsense"]["absence_proof"], False)
        self.assertTrue(receipt["observations"]["nonsense"]["nearest_neighbours"])
        self.assertEqual(receipt["residue"]["new_paths"], [])
        expected_bytes, expected_sha = source_slice_sha256(root, "noodles.py", 1, 4)
        candidate = receipt["observations"]["positive"]["candidates"][0]
        self.assertEqual(candidate["source_bytes"], expected_bytes)
        self.assertEqual(candidate["source_sha256"], expected_sha)
        self.assertEqual(receipt["observations"]["positive"]["context_bytes"], expected_bytes)
        self.assertGreaterEqual(receipt["observations"]["positive"]["latency_ms"], 0.0)

    def test_a_nonsense_query_outranking_the_real_one_is_still_admitted_as_a_candidate(self) -> None:
        root = self.candidate_copy()
        positive, nonsense = self.queries(root)
        receipt = retrieval_contract.probe_retrieval(
            root,
            self.searcher(
                {
                    positive: json.dumps([candidate_json("noodles.py", 1, 4, 0.402)]),
                    nonsense: json.dumps([candidate_json("schedule_domain.py", 1, 4, 0.531)]),
                }
            ),
            error_cls=noodles.GateError,
        )
        self.assertGreater(
            receipt["observations"]["nonsense"]["top_score"], receipt["observations"]["positive"]["top_score"]
        )
        self.assertFalse(receipt["observations"]["nonsense"]["absence_proof"])

    def test_empty_positive_result_is_reported_as_a_broken_index_not_as_absence(self) -> None:
        root = self.candidate_copy()
        positive, nonsense = self.queries(root)
        with self.assertRaises(noodles.GateError) as raised:
            retrieval_contract.probe_retrieval(
                root,
                self.searcher({positive: "[]", nonsense: json.dumps([candidate_json("README.md", 1, 2, 0.3)])}),
                error_cls=noodles.GateError,
            )
        self.assertIn("not absence proof", str(raised.exception))

    def test_empty_nonsense_result_refuses_to_claim_the_control_was_demonstrated(self) -> None:
        root = self.candidate_copy()
        positive, nonsense = self.queries(root)
        with self.assertRaises(noodles.GateError) as raised:
            retrieval_contract.probe_retrieval(
                root,
                self.searcher({positive: json.dumps([candidate_json("noodles.py", 1, 4, 0.4)]), nonsense: "[]"}),
                error_cls=noodles.GateError,
            )
        self.assertIn("was not demonstrated", str(raised.exception))

    def test_residue_check_goes_red_when_the_run_touches_the_candidate_tree(self) -> None:
        root = self.candidate_copy()
        positive, nonsense = self.queries(root)
        payload = {
            positive: json.dumps([candidate_json("noodles.py", 1, 4, 0.4)]),
            nonsense: json.dumps([candidate_json("README.md", 1, 2, 0.3)]),
        }

        def dirty_search(query: str) -> str:
            (root / ".grepai-planted-residue").write_text("index residue\n", encoding="utf-8")
            return payload[query]

        with self.assertRaises(noodles.GateError) as raised:
            retrieval_contract.probe_retrieval(root, dirty_search, error_cls=noodles.GateError)
        self.assertIn("mutated the candidate tree", str(raised.exception))
        self.assertIn(".grepai-planted-residue", str(raised.exception))


class RetrievalIndexAdmissionTests(unittest.TestCase):
    """`grepai init` writes `.grepai/` and appends to `.gitignore`, so the index must live outside the
    candidate tree and an absent index must never be mistaken for a searchable one."""

    def test_missing_or_empty_index_fails_closed(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="noodles-retrieval-index-test-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        with self.assertRaises(noodles.GateError) as absent:
            retrieval_contract.require_index(root, error_cls=noodles.GateError)
        self.assertIn("indistinguishable from a real miss", str(absent.exception))
        index = root / retrieval_contract.INDEX_DIRNAME / retrieval_contract.INDEX_FILENAME
        index.parent.mkdir()
        index.write_bytes(b"")
        with self.assertRaises(noodles.GateError):
            retrieval_contract.require_index(root, error_cls=noodles.GateError)
        index.write_bytes(b"gob")
        self.assertEqual(retrieval_contract.require_index(root, error_cls=noodles.GateError)["index_bytes"], 3)

    def test_index_root_inside_the_candidate_tree_is_refused(self) -> None:
        with self.assertRaises(noodles.GateError) as raised:
            retrieval_contract.retrieval_probe(CANDIDATE_ROOT, CANDIDATE_ROOT, error_cls=noodles.GateError)
        self.assertIn("outside the candidate tree", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
