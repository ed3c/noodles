"""The code-intel runtime surface: the pin gate, the two ceremony verbs, and their receipt states.

Every check below except `LiveCodeIntelCeremonyTests` runs with neither pinned binary installed, so
hosted CI proves the oracle can go red without the indexer. The live class is the one that needs the
real tools and skips with an explicit line when they are absent.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
import scip_validation
from scip_validation import ScipError
from tests.support import CANDIDATE_ROOT, ENGINE_ROOT, cmd, copy_tracked

PINS = json.loads((CANDIDATE_ROOT / scip_validation.LOCK_PATH).read_text(encoding="utf-8"))[
    scip_validation.CODE_INTEL_KEY
]
COMMIT = "be5b809277c249468d5e40d084fb604d71a79534"
TREE = "1d88fda09d4a71e1307c566fc2300ce7c7d77070"
SYMBOL = scip_validation.symbol_for("noodles", COMMIT, "feature_contract", "verify_feature")


def tools_installed() -> bool:
    """The live path runs only where both pinned binaries resolve at their pinned digests."""
    try:
        for role in scip_validation.PIN_ROLES:
            scip_validation.resolve_pinned_tool(PINS[role])
    except ScipError:
        return False
    return True


TOOLS_INSTALLED = tools_installed()


def checkout_receipt(**overrides: object) -> dict:
    receipt = {
        "schema_version": scip_validation.SCHEMA_VERSION,
        "capability": scip_validation.CAPABILITY,
        "verb": "checkout",
        "authority": scip_validation.AUTHORITY,
        "state": scip_validation.CHECKOUT_INDEXED,
        "repository": "ed3c/noodles",
        "source": "https://github.com/ed3c/noodles.git",
        "commit": COMMIT,
        "tree": TREE,
        "clone_path": "/nowhere/clone",
        "indexer": {
            "tool": PINS["indexer"]["tool"],
            "version": PINS["indexer"]["version"],
            "commit": PINS["indexer"]["commit"],
            "path": "/nowhere/scip-python",
            "sha256": PINS["indexer"]["binary_sha256"],
        },
        "index": {"path": "/nowhere/index.scip", "sha256": "a" * 64, "bytes": 4096, "build_seconds": 1.0},
        "non_claims": list(scip_validation.CHECKOUT_NON_CLAIMS),
    }
    receipt.update(overrides)
    return receipt


def lookup_receipt(**overrides: object) -> dict:
    receipt = {
        "schema_version": scip_validation.SCHEMA_VERSION,
        "capability": scip_validation.CAPABILITY,
        "verb": "lookup",
        "authority": scip_validation.AUTHORITY,
        "state": scip_validation.LOOKUP_RESOLVED,
        "checkout_receipt": "/nowhere/checkout.json",
        "clone_path": "/nowhere/clone",
        "repository": "ed3c/noodles",
        "commit": COMMIT,
        "reader": {
            "tool": PINS["reader"]["tool"],
            "version": PINS["reader"]["version"],
            "commit": PINS["reader"]["commit"],
            "path": "/nowhere/scip",
            "sha256": PINS["reader"]["binary_sha256"],
        },
        "symbol": SYMBOL,
        "definition": {
            "path": "feature_contract.py",
            "range": [349, 4, 18],
            "line": 350,
            "name": "verify_feature",
            "text": "verify_feature",
        },
        "controls": [
            {"control": scip_validation.CONTROL_UNCOVERED, "rejected": True, "diagnostic": "uncovered: x"},
            {"control": scip_validation.CONTROL_STALE, "rejected": True, "diagnostic": "stale index: x"},
        ],
        "non_claims": list(scip_validation.LOOKUP_NON_CLAIMS),
    }
    receipt.update(overrides)
    return receipt


class CodeIntelLockTests(unittest.TestCase):
    """The pins live in the lock and nowhere else, so the module's mirroring claim cannot be false."""

    def lock_errors(self, mutate) -> list[str]:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            (root / "policy").mkdir()
            payload = json.loads((CANDIDATE_ROOT / scip_validation.LOCK_PATH).read_text(encoding="utf-8"))
            mutate(payload[scip_validation.CODE_INTEL_KEY])
            (root / scip_validation.LOCK_PATH).write_text(json.dumps(payload), encoding="utf-8")
            return scip_validation.validate_code_intel_lock(root)

    def test_the_tracked_lock_passes_and_the_module_restates_no_pin(self) -> None:
        self.assertEqual(scip_validation.validate_code_intel_lock(CANDIDATE_ROOT), [])
        source = (CANDIDATE_ROOT / "scip_validation.py").read_text(encoding="utf-8")
        for role in scip_validation.PIN_ROLES:
            for field in ("commit", "binary_sha256"):
                self.assertNotIn(PINS[role][field], source, f"{role} {field} is restated in the module")

    def test_verify_consumes_the_pin_gate(self) -> None:
        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        self.assertIn("scip_validation.validate_code_intel_lock(root)", source)

    def test_planted_lock_mutations_are_all_rejected(self) -> None:
        mutations = {
            "absent version": (lambda pins: pins["indexer"].update(version="  "), "version is required"),
            "short commit": (lambda pins: pins["reader"].update(commit="deadbeef"), "40-hex"),
            "no digest": (lambda pins: pins["indexer"].update(binary_sha256=""), "ambient PATH"),
            "foreign source": (lambda pins: pins["reader"].update(source="http://elsewhere"), "GitHub HTTPS"),
            "argv drift": (lambda pins: pins["indexer"].update(version_argv=["other", "--version"]), "version_argv"),
            "authority claim": (lambda pins: pins.update(authority="L"), "authority"),
            "missing role": (lambda pins: pins.pop("reader"), "reader pin"),
        }
        for name, (mutate, phrase) in mutations.items():
            with self.subTest(mutation=name):
                errors = self.lock_errors(mutate)
                self.assertTrue(any(phrase in error for error in errors), errors)


class PinnedToolResolutionTests(unittest.TestCase):
    """PATH proposes; the pinned digest decides. Both refusals name the pin, because 'absent' and
    'a different binary answered to the same name' are different repairs."""

    def stub_path(self, temp: Path, name: str, body: str) -> Path:
        script = temp / name
        script.write_text(body, encoding="utf-8")
        script.chmod(0o755)
        return script

    def test_absent_binary_fails_closed_naming_the_pin(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp, mock.patch.dict(os.environ, {"PATH": temp}, clear=False):
            with self.assertRaises(ScipError) as refusal:
                scip_validation.resolve_pinned_tool(PINS["indexer"])
        message = str(refusal.exception)
        self.assertIn("is not installed on this host", message)
        self.assertIn(PINS["indexer"]["commit"], message)

    def test_ambient_binary_with_a_different_digest_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as name:
            temp = Path(name)
            self.stub_path(temp, PINS["indexer"]["tool"], "#!/bin/sh\necho 0.6.6\n")
            with mock.patch.dict(os.environ, {"PATH": str(temp)}, clear=False):
                with self.assertRaises(ScipError) as refusal:
                    scip_validation.resolve_pinned_tool(PINS["indexer"])
        message = str(refusal.exception)
        self.assertIn("not the pinned", message)
        self.assertIn(PINS["indexer"]["binary_sha256"], message)

    def test_a_binary_that_does_not_report_the_pinned_version_is_refused(self) -> None:
        """ed3c/noodles#294 monitor reconcile: `validate_code_intel_lock` no longer enumerates
        floating names like "latest". This is where a version that does not describe the running
        binary is actually caught - against the tool's own report, not against a denylist that fails
        open on every name nobody enumerated."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as name:
            temp = Path(name)
            stub = self.stub_path(temp, PINS["indexer"]["tool"], "#!/bin/sh\necho 0.6.6\n")
            pin = {**PINS["indexer"], "binary_sha256": hashlib.sha256(stub.read_bytes()).hexdigest(), "version": "latest"}
            with mock.patch.dict(os.environ, {"PATH": str(temp)}, clear=False):
                with self.assertRaises(ScipError) as refusal:
                    scip_validation.resolve_pinned_tool(pin)
        message = str(refusal.exception)
        self.assertIn("not the pinned version", message)
        self.assertIn("0.6.6", message)


class CheckoutStateTests(unittest.TestCase):
    """An index-build failure is its own declared state on the receipt, never a silent absence."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="noodles-code-intel-", ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = self.root / "session"
        self.session.mkdir()
        self.target = self.root / "target"
        self.target.mkdir()
        (self.target / "module.py").write_text("def thing() -> int:\n    return 1\n", encoding="utf-8")
        cmd(["git", "init", "-q", "-b", "main"], self.target)
        cmd(["git", "add", "-A"], self.target)
        cmd(["git", "commit", "-q", "-m", "target"], self.target)
        self.commit = cmd(["git", "rev-parse", "HEAD"], self.target)

    def stub_pins(self, body: str) -> dict:
        stub = self.root / "bin"
        stub.mkdir(exist_ok=True)
        script = stub / "stub-indexer"
        script.write_text(body, encoding="utf-8")
        script.chmod(0o755)
        digest = hashlib.sha256(script.read_bytes()).hexdigest()
        return {
            "indexer": {
                "tool": "stub-indexer",
                "version": "0.6.6",
                "commit": "0" * 40,
                "source": "https://github.com/sourcegraph/scip-python.git",
                "binary_sha256": digest,
                "version_argv": ["stub-indexer", "--version"],
            },
            "reader": PINS["reader"],
            "bin": str(stub),
        }

    def test_index_build_failure_is_a_declared_state_carrying_its_diagnostic(self) -> None:
        pins = self.stub_pins('#!/bin/sh\nif [ "$1" = "--version" ]; then echo 0.6.6; exit 0; fi\necho "boom" >&2\nexit 1\n')
        # constraint: the stub leads PATH rather than replacing it; git still has to resolve, and only
        # constraint: the indexer is the planted one.
        with mock.patch.dict(os.environ, {"PATH": f"{pins.pop('bin')}{os.pathsep}{os.environ['PATH']}"}, clear=False):
            receipt = scip_validation.code_intel_checkout(
                self.session, "ed3c/target", str(self.target), self.commit, pins=pins
            )
        self.assertEqual(receipt["state"], scip_validation.CHECKOUT_INDEX_FAILED)
        self.assertIn("boom", receipt["index"]["diagnostic"])
        self.assertEqual(json.loads(Path(receipt["receipt_path"]).read_text(encoding="utf-8"))["state"], receipt["state"])
        with self.assertRaises(ScipError) as refusal:
            scip_validation.admit_checkout_receipt(receipt, pins)
        self.assertIn(scip_validation.CHECKOUT_INDEX_FAILED, str(refusal.exception))

    def test_absent_indexer_is_a_distinct_state_from_a_failed_build(self) -> None:
        # constraint: git must still resolve; only the pinned indexer is removed from the search path.
        git_dir = str(Path(shutil.which("git") or "/usr/bin/git").parent)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as empty, mock.patch.dict(
            os.environ, {"PATH": f"{empty}{os.pathsep}{git_dir}"}, clear=False
        ):
            receipt = scip_validation.code_intel_checkout(
                self.session, "ed3c/target", str(self.target), self.commit, pins=PINS
            )
        self.assertEqual(receipt["state"], scip_validation.CHECKOUT_INDEXER_MISSING)
        self.assertIn(PINS["indexer"]["commit"], receipt["indexer"]["diagnostic"])
        self.assertNotEqual(scip_validation.CHECKOUT_INDEXER_MISSING, scip_validation.CHECKOUT_INDEX_FAILED)

    def test_a_commit_the_target_does_not_carry_fails_closed(self) -> None:
        with self.assertRaises(ScipError):
            scip_validation.code_intel_checkout(
                self.session, "ed3c/target", str(self.target), "f" * 40, pins=PINS
            )

    def test_a_non_exact_commit_is_refused_before_any_clone(self) -> None:
        with self.assertRaisesRegex(ScipError, "exact 40-hex commit"):
            scip_validation.code_intel_checkout(self.session, "ed3c/target", str(self.target), "main", pins=PINS)


class IndexCurrencyTests(unittest.TestCase):
    """A corrupted or commit-mismatched index is refused before any reader runs, with no tool installed."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="noodles-code-intel-", ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clone = self.root / "clone"
        self.clone.mkdir()
        (self.clone / "module.py").write_text("def thing() -> int:\n    return 1\n", encoding="utf-8")
        cmd(["git", "init", "-q", "-b", "main"], self.clone)
        cmd(["git", "add", "-A"], self.clone)
        cmd(["git", "commit", "-q", "-m", "one"], self.clone)
        self.commit = cmd(["git", "rev-parse", "HEAD"], self.clone)
        self.index = self.root / "index.scip"
        self.index.write_bytes(b"pretend-index-bytes")
        self.checkout = checkout_receipt(
            commit=self.commit,
            clone_path=str(self.clone),
            index={
                "path": str(self.index),
                "sha256": hashlib.sha256(self.index.read_bytes()).hexdigest(),
                "bytes": self.index.stat().st_size,
                "build_seconds": 0.1,
            },
        )

    def test_the_current_index_is_admitted(self) -> None:
        self.assertEqual(scip_validation.require_current_index(self.checkout), self.index)

    def test_corrupted_index_bytes_are_refused(self) -> None:
        self.index.write_bytes(b"pretend-index-byteS")
        with self.assertRaisesRegex(ScipError, "index-mismatch"):
            scip_validation.require_current_index(self.checkout)

    def test_a_clone_moved_off_the_indexed_commit_is_refused(self) -> None:
        (self.clone / "module.py").write_text("def thing() -> int:\n    return 2\n", encoding="utf-8")
        cmd(["git", "add", "-A"], self.clone)
        cmd(["git", "commit", "-q", "-m", "two"], self.clone)
        with self.assertRaisesRegex(ScipError, "index-mismatch"):
            scip_validation.require_current_index(self.checkout)

    def test_an_absent_index_is_refused_rather_than_read_as_empty(self) -> None:
        self.index.unlink()
        with self.assertRaisesRegex(ScipError, "index-mismatch"):
            scip_validation.require_current_index(self.checkout)


class ReceiptAdmissionTests(unittest.TestCase):
    """Each planted mutation removes exactly one physical property the receipt claims to have proven."""

    def test_the_synthesized_receipts_admit(self) -> None:
        self.assertEqual(scip_validation.admit_checkout_receipt(checkout_receipt(), PINS)["state"], "indexed")
        self.assertEqual(scip_validation.admit_lookup_receipt(lookup_receipt(), PINS)["state"], "resolved")

    def test_planted_checkout_mutations_are_all_rejected(self) -> None:
        mutations = {
            "unpinned indexer": lambda item: item["indexer"].update(commit="0" * 40),
            "ambient indexer digest": lambda item: item["indexer"].update(sha256="b" * 64),
            "forged commit": lambda item: item.update(commit="not-a-commit"),
            "no built index": lambda item: item["index"].update(bytes=0),
            "index digest is not a digest": lambda item: item["index"].update(sha256="short"),
            "undefined state": lambda item: item.update(state="fine"),
            "authority laundering": lambda item: item.update(authority="L"),
            "no non-claims": lambda item: item.update(non_claims=[]),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                planted = copy.deepcopy(checkout_receipt())
                mutate(planted)
                with self.assertRaises(ScipError):
                    scip_validation.admit_checkout_receipt(planted, PINS)
        for field in scip_validation.CHECKOUT_FIELDS:
            with self.subTest(missing=field):
                planted = copy.deepcopy(checkout_receipt())
                planted.pop(field)
                with self.assertRaises(ScipError):
                    scip_validation.admit_checkout_receipt(planted, PINS)

    def test_planted_lookup_mutations_are_all_rejected(self) -> None:
        mutations = {
            "unpinned reader": lambda item: item["reader"].update(version="v0.8.0"),
            "ambient reader digest": lambda item: item["reader"].update(sha256="b" * 64),
            "symbol from another commit": lambda item: item.update(
                symbol=item["symbol"].replace(COMMIT[:12], "000000000000")
            ),
            "symbol names another definition": lambda item: item["definition"].update(name="other"),
            "readback text drift": lambda item: item["definition"].update(text="other"),
            "no file and line": lambda item: item["definition"].update(line=0),
            "local symbol": lambda item: item.update(symbol="local 3"),
            "control silently passed": lambda item: item["controls"][0].update(rejected=False),
            "control without diagnostic": lambda item: item["controls"][1].update(diagnostic="  "),
            "one control dropped": lambda item: item["controls"].pop(),
            "no checkout receipt named": lambda item: item.update(checkout_receipt="  "),
            "undefined state": lambda item: item.update(state="fine"),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                planted = copy.deepcopy(lookup_receipt())
                mutate(planted)
                with self.assertRaises(ScipError):
                    scip_validation.admit_lookup_receipt(planted, PINS)
        for field in scip_validation.LOOKUP_FIELDS:
            with self.subTest(missing=field):
                planted = copy.deepcopy(lookup_receipt())
                planted.pop(field)
                with self.assertRaises(ScipError):
                    scip_validation.admit_lookup_receipt(planted, PINS)

    def test_a_missing_tool_and_a_missing_symbol_never_share_a_representation(self) -> None:
        states = {
            scip_validation.LOOKUP_READER_MISSING,
            scip_validation.LOOKUP_SYMBOL_NOT_FOUND,
            scip_validation.LOOKUP_INDEX_MISMATCH,
            scip_validation.LOOKUP_RESOLVED,
        }
        self.assertEqual(len(states), 4)
        for state in states - {scip_validation.LOOKUP_RESOLVED}:
            with self.subTest(state=state):
                planted = lookup_receipt(state=state, diagnostic=f"declared {state}")
                with self.assertRaises(ScipError) as refusal:
                    scip_validation.admit_lookup_receipt(planted, PINS)
                self.assertIn(state, str(refusal.exception))


class CrossRepositoryReceiptTests(unittest.TestCase):
    """Work done outside the ceremony surface is inadmissible, not merely discouraged."""

    def receipt(self, subject: str, **extra: object) -> dict:
        return {"claims": [{"subject": subject, "status": "claimed", "meaning": "x"}], **extra}

    def test_a_same_repository_cycle_needs_no_checkout_receipt(self) -> None:
        self.assertEqual(
            noodles.cross_repository_receipt_errors(self.receipt("ed3c/noodles#1"), "ed3c/noodles"), []
        )

    def test_a_cross_repository_cycle_naming_no_checkout_receipt_is_refused(self) -> None:
        errors = noodles.cross_repository_receipt_errors(self.receipt("ed3c/elsewhere#1"), "ed3c/noodles")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("ed3c/elsewhere", errors[0])
        self.assertIn(noodles.CODE_INTEL_CHECKOUT_FIELD, errors[0])
        self.assertIn("./noodles ceremony checkout", errors[0])

    def test_a_cross_repository_cycle_that_names_its_checkout_receipt_is_admitted(self) -> None:
        named = self.receipt("ed3c/elsewhere#1", **{noodles.CODE_INTEL_CHECKOUT_FIELD: "/session/checkout.json"})
        self.assertEqual(noodles.cross_repository_receipt_errors(named, "ed3c/noodles"), [])

    def test_an_empty_checkout_reference_is_not_a_reference(self) -> None:
        named = self.receipt("ed3c/elsewhere#1", **{noodles.CODE_INTEL_CHECKOUT_FIELD: "   "})
        self.assertEqual(len(noodles.cross_repository_receipt_errors(named, "ed3c/noodles")), 1)

    def test_verify_reds_on_a_planted_cross_repository_cycle_receipt(self) -> None:
        """The rule is only a rule where a machine surface executes it, so this plants the receipt in a
        real candidate tree and requires `verify_repository` itself to refuse."""
        with tempfile.TemporaryDirectory(prefix="noodles-code-intel-", ignore_cleanup_errors=True) as temp:
            root = Path(temp) / "repo"
            copy_tracked(CANDIDATE_ROOT, root)
            receipt = {
                "frontier": [],
                "winners": [],
                "max_useful_workers": 1,
                "claims": [
                    {
                        "subject": "ed3c/elsewhere#1",
                        "status": "claimed",
                        "meaning": noodles.skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["claimed"],
                    }
                ],
            }
            (root / ".noodle").mkdir(parents=True, exist_ok=True)
            (root / ".noodle/schedule-cycle.json").write_text(json.dumps(receipt), encoding="utf-8")
            result = noodles.verify_repository(root, ENGINE_ROOT)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any(noodles.CODE_INTEL_CHECKOUT_FIELD in error for error in result["errors"]), result["errors"]
        )


class CeremonySurfaceTests(unittest.TestCase):
    def test_the_cli_exposes_both_code_intel_verbs(self) -> None:
        checkout = noodles.build_parser().parse_args(
            ["ceremony", "checkout", "--repository", "a/b", "--source", "https://x", "--commit", COMMIT]
        )
        self.assertEqual((checkout.command, checkout.ceremony_verb, checkout.commit), ("ceremony", "checkout", COMMIT))
        lookup = noodles.build_parser().parse_args(
            ["ceremony", "lookup", "--checkout-receipt", "/r.json", "--module", "m", "--name", "n"]
        )
        self.assertEqual((lookup.ceremony_verb, lookup.module, lookup.name), ("lookup", "m", "n"))

    def test_the_session_directory_is_derived_not_supplied(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": ""}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "NOODLE_SESSION_ID"):
                noodles.code_intel_session_dir(CANDIDATE_ROOT)
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": "../escape"}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "NOODLE_SESSION_ID"):
                noodles.code_intel_session_dir(CANDIDATE_ROOT)

    def test_the_execute_skill_names_the_admitted_navigation_surface(self) -> None:
        skill = (CANDIDATE_ROOT / ".agents/skills/execute/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("./noodles ceremony checkout", skill)
        self.assertIn("./noodles ceremony lookup", skill)


@unittest.skipUnless(
    TOOLS_INSTALLED,
    "the pinned scip-python indexer and scip reader are intentionally absent in hosted/offline CI; "
    "the live checkout-and-lookup round trip runs wherever both pinned binaries are installed at "
    "their pinned digests",
)
class LiveCodeIntelCeremonyTests(unittest.TestCase):
    """The real repository is the target. One verb materializes and indexes it; the other answers."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="noodles-code-intel-live-", ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.session = Path(self.temp.name)
        self.commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(CANDIDATE_ROOT), text=True, capture_output=True, check=True
        ).stdout.strip()

    def test_checkout_indexes_at_the_exact_commit_and_lookup_resolves_a_known_symbol(self) -> None:
        checkout = scip_validation.code_intel_checkout(
            self.session, "ed3c/noodles", str(CANDIDATE_ROOT), self.commit, pins=PINS
        )
        scip_validation.admit_checkout_receipt(checkout, PINS)
        written = json.loads(Path(checkout["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(written["commit"], self.commit)
        self.assertEqual(written["index"]["sha256"], hashlib.sha256(Path(written["index"]["path"]).read_bytes()).hexdigest())

        receipt = scip_validation.code_intel_lookup(
            Path(checkout["receipt_path"]), "feature_contract", "verify_feature", pins=PINS
        )
        clone = Path(receipt["clone_path"])
        scip_validation.admit_lookup_receipt(receipt, PINS, root=clone)
        recorded = json.loads(Path(receipt["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(recorded["state"], scip_validation.LOOKUP_RESOLVED)
        self.assertEqual(recorded["definition"]["path"], "feature_contract.py")
        line = (clone / "feature_contract.py").read_text(encoding="utf-8").splitlines()[recorded["definition"]["line"] - 1]
        self.assertTrue(line.startswith("def verify_feature("), line)

    def test_a_symbol_the_index_does_not_carry_is_its_own_state(self) -> None:
        checkout = scip_validation.code_intel_checkout(
            self.session, "ed3c/noodles", str(CANDIDATE_ROOT), self.commit, pins=PINS
        )
        receipt = scip_validation.code_intel_lookup(
            Path(checkout["receipt_path"]), "feature_contract", "no_such_definition", pins=PINS
        )
        self.assertEqual(receipt["state"], scip_validation.LOOKUP_SYMBOL_NOT_FOUND)
        self.assertTrue(receipt["diagnostic"])

    def test_a_corrupted_index_is_refused_instead_of_answered(self) -> None:
        checkout = scip_validation.code_intel_checkout(
            self.session, "ed3c/noodles", str(CANDIDATE_ROOT), self.commit, pins=PINS
        )
        index = Path(checkout["index"]["path"])
        index.write_bytes(index.read_bytes() + b"corrupt")
        receipt = scip_validation.code_intel_lookup(
            Path(checkout["receipt_path"]), "feature_contract", "verify_feature", pins=PINS
        )
        self.assertEqual(receipt["state"], scip_validation.LOOKUP_INDEX_MISMATCH)

    def tearDown(self) -> None:
        shutil.rmtree(self.session / "code-intel", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
