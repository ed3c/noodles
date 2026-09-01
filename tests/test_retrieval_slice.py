"""The retrieval slice of the code-intel surface: intent queries, hypothesis receipts, and metering.

Every check here runs with the pinned retrieval binary absent, which is the point: backend-missing,
index-absent, index-mismatch, and a real miss have to be four distinguishable outcomes before the
surface is allowed to answer anything. The live query is one skipped-when-absent class.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
import retrieval_contract
import scip_validation
from tests.support import CANDIDATE_ROOT, cmd

PIN = json.loads((CANDIDATE_ROOT / retrieval_contract.LOCK_PATH).read_text(encoding="utf-8"))["retrieval"]
CODE_INTEL_PINS = json.loads((CANDIDATE_ROOT / scip_validation.LOCK_PATH).read_text(encoding="utf-8"))[
    scip_validation.CODE_INTEL_KEY
]


def backend_installed() -> bool:
    try:
        retrieval_contract.verify_pinned_executable(PIN, error_cls=noodles.GateError)
    except noodles.GateError:
        return False
    return True


BACKEND_INSTALLED = backend_installed()


def intent_receipt(**overrides: object) -> dict:
    receipt = {
        "schema_version": noodles.SCHEMA_VERSION,
        "capability": noodles.RETRIEVAL_CAPABILITY,
        "verb": "intent",
        "authority": retrieval_contract.AUTHORITY,
        "state": noodles.RETRIEVAL_CANDIDATES,
        "checkout_receipt": "/session/checkout.json",
        "clone_path": "/session/clone",
        "repository": "ed3c/noodles",
        "commit": "b" * 40,
        "query": "where is the code that validates provider pins",
        "embedder": {
            "provider": PIN["embedder"]["provider"],
            "model": PIN["embedder"]["model"],
            "digest": PIN["embedder"]["digest"],
            "dimensions": PIN["embedder"]["dimensions"],
            "external": False,
            "external_calls": 0,
            "spend": 0.0,
            "metered_carrier": None,
            "reason": "pinned local embedding model; index construction opens no external channel",
        },
        "backend": {"path": "/usr/local/bin/grepai", "sha256": PIN["binary_sha256"], "version_stdout": PIN["version"]},
        "index": {"index_root": "/session", "index_bytes": 4096, "index_sha256": "c" * 64},
        "candidates": [
            {
                "path": "noodles.py",
                "start_line": 10,
                "end_line": 20,
                "score": 0.42,
                "source_bytes": 100,
                "source_sha256": "d" * 64,
                "confirmed": False,
            }
        ],
        "non_claims": list(noodles.RETRIEVAL_NON_CLAIMS),
    }
    receipt.update(overrides)
    return receipt


class RetrievalMeteringTests(unittest.TestCase):
    """Index construction is never an unmetered consumption channel."""

    def test_the_pinned_local_embedder_is_admitted_and_named_in_the_receipt(self) -> None:
        spend = noodles.retrieval_spend_admission(PIN)
        self.assertEqual(spend["provider"], PIN["embedder"]["provider"])
        self.assertEqual(spend["digest"], PIN["embedder"]["digest"])
        self.assertIs(spend["external"], False)
        self.assertEqual(spend["external_calls"], 0)

    def test_an_external_embedder_is_refused_naming_the_absent_metered_carrier(self) -> None:
        planted = copy.deepcopy(PIN)
        planted["embedder"]["provider"] = "openai"
        with self.assertRaises(noodles.GateError) as refusal:
            noodles.retrieval_spend_admission(planted)
        message = str(refusal.exception)
        self.assertIn("unmetered consumption channel", message)
        self.assertIn(noodles.GH_CARRIER_RELATIVE, message)

    def test_the_lazy_initialisation_argv_is_pinned_and_stays_one_shot(self) -> None:
        self.assertEqual(noodles.retrieval_init_argv_errors(PIN), [])
        cases = {
            "foreign command": (lambda pin: pin.update(init_argv=["other", "init"]), "pinned command"),
            "daemon verb": (
                lambda pin: pin.update(init_argv=[PIN["command"], noodles.RETRIEVAL_INDEX_DAEMON_VERB]),
                "one-shot",
            ),
            "query placeholder": (
                lambda pin: pin.update(init_argv=[PIN["command"], "init", retrieval_contract.QUERY_PLACEHOLDER]),
                retrieval_contract.QUERY_PLACEHOLDER,
            ),
            "unowned index": (lambda pin: pin.update(index_owner="  "), "index_owner"),
        }
        for name, (mutate, phrase) in cases.items():
            with self.subTest(mutation=name):
                planted = copy.deepcopy(PIN)
                mutate(planted)
                errors = noodles.retrieval_init_argv_errors(planted)
                self.assertTrue(any(phrase in error for error in errors), errors)

    def test_verify_consumes_the_retrieval_initialisation_gate(self) -> None:
        self.assertIn(
            "retrieval_init_argv_errors(", (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        )


class RetrievalIndexCurrencyTests(unittest.TestCase):
    """A corrupted or commit-mismatched retrieval index is refused with the binary absent."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="noodles-retrieval-", ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clone = self.root / "clone"
        self.clone.mkdir()
        (self.clone / "module.py").write_text("def thing() -> int:\n    return 1\n", encoding="utf-8")
        cmd(["git", "init", "-q", "-b", "main"], self.clone)
        cmd(["git", "add", "-A"], self.clone)
        cmd(["git", "commit", "-q", "-m", "one"], self.clone)
        self.commit = cmd(["git", "rev-parse", "HEAD"], self.clone)
        self.index = self.root / retrieval_contract.INDEX_DIRNAME / retrieval_contract.INDEX_FILENAME
        self.index.parent.mkdir()
        self.index.write_bytes(b"pretend-vectors")

    def test_a_populated_index_at_the_checked_out_commit_is_admitted(self) -> None:
        admitted = noodles.retrieval_index_admission(self.root, self.clone, self.commit)
        self.assertEqual(admitted["index_bytes"], len(b"pretend-vectors"))
        self.assertEqual(admitted["index_sha256"], hashlib.sha256(b"pretend-vectors").hexdigest())

    def test_a_truncated_index_is_refused_rather_than_read_as_a_miss(self) -> None:
        self.index.write_bytes(b"")
        with self.assertRaisesRegex(noodles.GateError, "index-absent"):
            noodles.retrieval_index_admission(self.root, self.clone, self.commit)

    def test_a_clone_moved_off_the_indexed_commit_is_refused(self) -> None:
        (self.clone / "module.py").write_text("def thing() -> int:\n    return 2\n", encoding="utf-8")
        cmd(["git", "add", "-A"], self.clone)
        cmd(["git", "commit", "-q", "-m", "two"], self.clone)
        with self.assertRaisesRegex(noodles.GateError, "index-mismatch"):
            noodles.retrieval_index_admission(self.root, self.clone, self.commit)


class IntentReceiptAdmissionTests(unittest.TestCase):
    """Candidates are hypotheses; the receipt has to say so, and every state has to be distinguishable."""

    def test_the_synthesized_receipt_admits(self) -> None:
        self.assertEqual(noodles.admit_intent_receipt(intent_receipt(), PIN)["state"], noodles.RETRIEVAL_CANDIDATES)

    def test_backend_missing_and_no_match_never_share_a_representation(self) -> None:
        self.assertNotEqual(noodles.RETRIEVAL_BACKEND_UNAVAILABLE, noodles.RETRIEVAL_NO_MATCH)
        self.assertEqual(len(set(noodles.RETRIEVAL_STATES)), 5)
        for state in set(noodles.RETRIEVAL_STATES) - {noodles.RETRIEVAL_CANDIDATES}:
            with self.subTest(state=state):
                planted = intent_receipt(state=state, candidates=[], diagnostic=f"declared {state}")
                with self.assertRaises(noodles.GateError) as refusal:
                    noodles.admit_intent_receipt(planted, PIN)
                self.assertIn(state, str(refusal.exception))

    def test_planted_intent_mutations_are_all_rejected(self) -> None:
        mutations = {
            "confirmed candidate": lambda item: item["candidates"][0].update(confirmed=True),
            "candidate without a line": lambda item: item["candidates"][0].update(start_line=0),
            "empty candidate list in the candidates state": lambda item: item.update(candidates=[]),
            "unpinned backend digest": lambda item: item["backend"].update(sha256="e" * 64),
            "foreign embedder": lambda item: item["embedder"].update(provider="openai"),
            "unmetered external channel": lambda item: item["embedder"].update(external=True, external_calls=3),
            "authority laundering": lambda item: item.update(authority="L"),
            "no query": lambda item: item.update(query="   "),
            "no checkout receipt": lambda item: item.update(checkout_receipt=""),
            "no non-claims": lambda item: item.update(non_claims=[]),
            "undefined state": lambda item: item.update(state="fine"),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                planted = copy.deepcopy(intent_receipt())
                mutate(planted)
                with self.assertRaises(noodles.GateError):
                    noodles.admit_intent_receipt(planted, PIN)
        for field in noodles.RETRIEVAL_FIELDS:
            with self.subTest(missing=field):
                planted = copy.deepcopy(intent_receipt())
                planted.pop(field)
                with self.assertRaises(noodles.GateError):
                    noodles.admit_intent_receipt(planted, PIN)

    def test_the_emitter_admits_before_it_writes_so_no_caller_can_forget(self) -> None:
        """ed3c/noodles#295 monitor reconcile: the admitter used to have zero production call sites,
        so a candidates receipt no reader would accept could still be emitted and left on disk. Every
        emission path goes through `write_intent_receipt`, so the binding lives there."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as name:
            path = Path(name) / "intent.json"
            written = noodles.write_intent_receipt(path, copy.deepcopy(intent_receipt()), PIN)
            self.assertEqual(written["receipt_path"], str(path))
            self.assertTrue(path.exists())

            path = Path(name) / "planted.json"
            planted = copy.deepcopy(intent_receipt())
            planted["candidates"][0].update(confirmed=True)
            with self.assertRaises(noodles.GateError):
                noodles.write_intent_receipt(path, planted, PIN)
            self.assertFalse(path.exists(), "an inadmissible candidates receipt must not reach disk")

    def test_a_refusal_state_is_written_with_its_diagnostic_rather_than_admitted(self) -> None:
        """The four non-candidates states are refusals, not answers: they carry a diagnostic instead
        of candidates, and the emitter must still record them."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as name:
            path = Path(name) / "absent.json"
            receipt = intent_receipt(state=noodles.RETRIEVAL_INDEX_ABSENT, candidates=[], diagnostic="no index")
            written = noodles.write_intent_receipt(path, receipt, PIN)
            self.assertEqual(written["state"], noodles.RETRIEVAL_INDEX_ABSENT)
            self.assertTrue(path.exists())


class IntentSurfaceTests(unittest.TestCase):
    def test_the_cli_exposes_the_intent_verb(self) -> None:
        parsed = noodles.build_parser().parse_args(
            ["ceremony", "intent", "--checkout-receipt", "/r.json", "--query", "where is X"]
        )
        self.assertEqual((parsed.ceremony_verb, parsed.query), ("intent", "where is X"))

    def test_the_execute_skill_routes_question_shapes_as_pointers(self) -> None:
        skill = (CANDIDATE_ROOT / ".agents/skills/execute/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("./noodles ceremony intent", skill)
        self.assertIn("./noodles ceremony lookup", skill)

    def test_an_empty_query_is_refused_before_any_backend_call(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "non-empty query"):
            noodles.code_intel_intent(CANDIDATE_ROOT, "/nowhere/checkout.json", "   ")

    def test_an_absent_backend_is_its_own_state_naming_the_pin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-retrieval-", ignore_cleanup_errors=True) as temp:
            session = Path(temp)
            clone = session / "clone"
            clone.mkdir()
            (clone / "module.py").write_text("def thing() -> int:\n    return 1\n", encoding="utf-8")
            cmd(["git", "init", "-q", "-b", "main"], clone)
            cmd(["git", "add", "-A"], clone)
            cmd(["git", "commit", "-q", "-m", "one"], clone)
            commit = cmd(["git", "rev-parse", "HEAD"], clone)
            receipt_path = session / "checkout.json"
            checkout = {
                "schema_version": scip_validation.SCHEMA_VERSION,
                "capability": scip_validation.CAPABILITY,
                "verb": "checkout",
                "authority": scip_validation.AUTHORITY,
                "state": scip_validation.CHECKOUT_INDEXED,
                "repository": "ed3c/target",
                "source": "https://github.com/ed3c/target.git",
                "commit": commit,
                "tree": cmd(["git", "rev-parse", "HEAD^{tree}"], clone),
                "clone_path": str(clone),
                "indexer": {
                    "tool": CODE_INTEL_PINS["indexer"]["tool"],
                    "version": CODE_INTEL_PINS["indexer"]["version"],
                    "commit": CODE_INTEL_PINS["indexer"]["commit"],
                    "path": "/nowhere/scip-python",
                    "sha256": CODE_INTEL_PINS["indexer"]["binary_sha256"],
                },
                "index": {"path": "/nowhere/index.scip", "sha256": "a" * 64, "bytes": 1},
                "non_claims": list(scip_validation.CHECKOUT_NON_CLAIMS),
            }
            receipt_path.write_text(json.dumps(checkout), encoding="utf-8")
            git_dir = str(Path(shutil.which("git") or "/usr/bin/git").parent)
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as empty, mock.patch.dict(
                os.environ, {"PATH": f"{empty}{os.pathsep}{git_dir}"}, clear=False
            ):
                receipt = noodles.code_intel_intent(CANDIDATE_ROOT, str(receipt_path), "where is the thing")
            self.assertEqual(receipt["state"], noodles.RETRIEVAL_BACKEND_UNAVAILABLE)
            self.assertIn(PIN["command"], receipt["diagnostic"])
            self.assertEqual(receipt["candidates"], [])
            written = json.loads(Path(receipt["receipt_path"]).read_text(encoding="utf-8"))
            self.assertEqual(written["state"], noodles.RETRIEVAL_BACKEND_UNAVAILABLE)


@unittest.skipUnless(
    BACKEND_INSTALLED,
    "the pinned grepai retrieval binary is intentionally absent in hosted/offline CI; the live intent "
    "query runs wherever the pinned binary is installed at its pinned digest",
)
class LiveRetrievalTests(unittest.TestCase):
    """The lazy backend initialisation is one-shot and daemon-free; vector population has its own owner."""

    def test_lazy_initialisation_materializes_the_file_backed_backend_without_a_daemon(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-retrieval-live-", ignore_cleanup_errors=True) as temp:
            workspace = Path(temp)
            first = noodles.ensure_retrieval_backend(workspace, PIN)
            self.assertTrue(first["initialized"])
            self.assertTrue(Path(first["config"]).is_file())
            second = noodles.ensure_retrieval_backend(workspace, PIN)
            self.assertFalse(second["initialized"])
            self.assertFalse(
                (workspace / retrieval_contract.INDEX_DIRNAME / retrieval_contract.INDEX_FILENAME).exists(),
                "initialisation must not populate vectors; that owner is the watcher",
            )


if __name__ == "__main__":
    unittest.main()
