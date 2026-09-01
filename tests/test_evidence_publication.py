"""GitHub Actions evidence publication: package, scrub, digest-bind and read back one run's bytes.

Durable Drive custody is not correctness and never merge authority, so what is proven here is the
half that is physical today: the custody key is exact, the manifest describes exactly the bytes it
was built from, and a wrong-head folder, a missing or extra member, a truncation, a tampered digest,
an empty denominator, or a credential that reached the archive each fails closed. Transport itself
is reported as `custody_unadmitted` rather than assumed, because no Google credential path exists
inside Actions; the controls below pin that no admission path reads any of it.
"""
from __future__ import annotations

import ast
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT

REPOSITORY = "ed3c/noodles"
SUBJECT = f"{REPOSITORY}#900188"
ISSUE_NUMBER = 900188
PR_NUMBER = 188
HEAD_SHA = "a" * 40
RUN_ID = 42
RUN_ATTEMPT = 2
FOLDER = f"GitHub-Actions-Evidence/v1/{REPOSITORY}/issue-{ISSUE_NUMBER}/pr-{PR_NUMBER}/{HEAD_SHA}/run-{RUN_ID}-attempt-{RUN_ATTEMPT}"
MEMBERS = {"runtime/runner.json": b'{"runner_os": "Linux"}\n', "verification/receipt.json": b'{"head_sha": "a"}\n'}
RUN_ENV = {"GITHUB_RUN_ID": str(RUN_ID), "GITHUB_RUN_ATTEMPT": str(RUN_ATTEMPT)}
# constraint: ed3c/noodles#188 - planted credentials are assembled at runtime, never written as a
# constraint: literal, so this control file cannot itself trip provider push protection or seed a
# constraint: real-looking token into the tree it is protecting.
PLANTED = {
    "github-token": b"gh" + b"p_" + b"A" * 36,
    "github-pat": b"github" + b"_pat_" + b"B" * 40,
    "google-api-key": b"AI" + b"za" + b"C" * 35,
    "google-service-account-key": b'{"private' + b'_key_id": "x"}',
    "openai-key": b"sk" + b"-" + b"D" * 40,
    "private-key-block": b"-----BEGIN " + b"RSA PRIVATE KEY" + b"-----",
    "authorization-header": b"Authorization" + b": Bearer " + b"E" * 20,
}


def issue_body(state: str = "awaiting_land") -> str:
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {REPOSITORY} -->\n"
        f"<!-- noodles-subject: {SUBJECT} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        "<!-- noodles-component: verify -->\n"
        "<!-- noodles-depends-on: none -->\n\n"
        "## Goal\n\nPublish complete runtime receipts.\n\n"
        "## Physical acceptance\n\n- Planted controls fail closed.\n\n"
        "## Non-claims\n\n- Custody never proves correctness.\n"
    )


class CustodyKeyTests(unittest.TestCase):
    def test_positive_control_builds_the_one_deterministic_custody_path(self) -> None:
        self.assertEqual(
            noodles.evidence_custody_folder(REPOSITORY, ISSUE_NUMBER, PR_NUMBER, HEAD_SHA, RUN_ID, RUN_ATTEMPT), FOLDER
        )

    def test_same_attempt_recomputes_the_same_folder_so_a_retry_grows_no_second_tree(self) -> None:
        again = noodles.evidence_custody_folder(REPOSITORY, ISSUE_NUMBER, PR_NUMBER, HEAD_SHA, RUN_ID, RUN_ATTEMPT)
        other = noodles.evidence_custody_folder(REPOSITORY, ISSUE_NUMBER, PR_NUMBER, HEAD_SHA, RUN_ID, RUN_ATTEMPT + 1)
        self.assertEqual(again, FOLDER)
        self.assertNotEqual(other, FOLDER)

    def test_planted_negative_inexact_head_is_refused(self) -> None:
        for head in ("", "a" * 39, "A" * 40, "z" * 40, f"{HEAD_SHA}\n"):
            with self.subTest(head=head), self.assertRaisesRegex(noodles.GateError, "exact 40-hex candidate head"):
                noodles.evidence_custody_folder(REPOSITORY, ISSUE_NUMBER, PR_NUMBER, head, RUN_ID, RUN_ATTEMPT)

    def test_planted_negative_inexact_repository_is_refused(self) -> None:
        for repository in ("", "noodles", "ed3c/noodles/extra", "ed3c noodles"):
            with self.subTest(repository=repository), self.assertRaisesRegex(noodles.GateError, "exact owner/repo"):
                noodles.evidence_custody_folder(repository, ISSUE_NUMBER, PR_NUMBER, HEAD_SHA, RUN_ID, RUN_ATTEMPT)

    def test_planted_negative_absent_run_identity_never_defaults_into_a_path(self) -> None:
        for index, name in enumerate(("issue", "pr", "run id", "run attempt")):
            for bad in (0, -1, True, "1", None):
                arguments = [ISSUE_NUMBER, PR_NUMBER, RUN_ID, RUN_ATTEMPT]
                arguments[index] = bad
                with self.subTest(field=name, value=bad), self.assertRaisesRegex(noodles.GateError, f"custody {name} "):
                    noodles.evidence_custody_folder(REPOSITORY, arguments[0], arguments[1], HEAD_SHA, arguments[2], arguments[3])

    def test_blob_path_is_content_addressed_and_refuses_a_non_digest(self) -> None:
        digest = "0" * 64
        self.assertEqual(noodles.evidence_blob_path(digest), f"GitHub-Actions-Evidence/v1/blobs/sha256/{digest}")
        for bad in ("", "0" * 63, "g" * 64, HEAD_SHA):
            with self.subTest(digest=bad), self.assertRaisesRegex(noodles.GateError, "sha256 hex digest"):
                noodles.evidence_blob_path(bad)


class ScrubTests(unittest.TestCase):
    def test_planted_negative_every_bounded_credential_shape_is_found_without_its_value(self) -> None:
        for pattern_id, secret in PLANTED.items():
            with self.subTest(pattern=pattern_id):
                findings = noodles.evidence_scrub_findings("runtime/log.txt", b"prefix\n" + secret + b"\nsuffix\n")
                self.assertEqual(len(findings), 1, findings)
                self.assertIn(pattern_id, findings[0])
                self.assertNotIn(secret.decode(), findings[0])

    def test_planted_negative_generated_credential_file_is_refused_by_name_alone(self) -> None:
        self.assertEqual(noodles.evidence_scrub_findings("runtime/gha-creds-1a2b.json", b"{}"), ["runtime/gha-creds-1a2b.json: generated-credential-file"])

    def test_positive_control_a_secret_reference_is_not_a_secret_value(self) -> None:
        referencing = b"private-key: ${{ secrets.NOODLES_APP_PRIVATE_KEY }}\ngithub-token: ${{ github.token }}\n"
        self.assertEqual(noodles.evidence_scrub_findings("candidate/workflows/land.yml", referencing), [])

    def test_positive_control_the_real_candidate_member_set_carries_no_credential(self) -> None:
        members = noodles.evidence_publication_members(CANDIDATE_ROOT, {"head_sha": HEAD_SHA})
        self.assertTrue(any(name.startswith("candidate/policy/") for name in members), sorted(members))
        self.assertTrue(any(name.startswith("candidate/workflows/") for name in members), sorted(members))
        findings = [finding for name, data in members.items() for finding in noodles.evidence_scrub_findings(name, data)]
        self.assertEqual(findings, [])


class PublicationBuildTests(unittest.TestCase):
    def build(self, members: dict[str, bytes] | None = None, folder: str = FOLDER) -> dict:
        return noodles.build_evidence_publication(folder, dict(MEMBERS if members is None else members))

    def test_positive_control_manifest_binds_every_member_to_its_digest_and_blob(self) -> None:
        publication = self.build()
        self.assertEqual(publication["folder"], FOLDER)
        self.assertEqual(publication["manifest"]["schema_version"], noodles.EVIDENCE_SCHEMA_VERSION)
        names = [entry["name"] for entry in publication["manifest"]["members"]]
        self.assertEqual(names, sorted(MEMBERS))
        for entry in publication["manifest"]["members"]:
            self.assertEqual(entry["bytes"], len(MEMBERS[entry["name"]]))
            self.assertTrue(entry["blob"].endswith(entry["sha256"]))

    def test_a_repeated_publication_of_the_same_bytes_is_byte_identical(self) -> None:
        self.assertEqual(self.build()["manifest_sha256"], self.build()["manifest_sha256"])
        self.assertNotEqual(
            self.build()["manifest_sha256"],
            self.build({**MEMBERS, "runtime/runner.json": b"{}\n"})["manifest_sha256"],
        )

    def test_planted_negative_empty_denominator_is_refused(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "empty member denominator"):
            self.build({})

    def test_planted_negative_a_credential_in_the_archive_refuses_the_whole_publication(self) -> None:
        with self.assertRaises(noodles.GateError) as raised:
            self.build({**MEMBERS, "runtime/transcript.txt": b"token=" + PLANTED["github-token"]})
        diagnostic = str(raised.exception)
        self.assertIn("scrub refused", diagnostic)
        self.assertIn("github-token", diagnostic)
        self.assertNotIn(PLANTED["github-token"].decode(), diagnostic)

    def test_planted_negative_non_byte_member_and_inexact_member_name_are_refused(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "must be exact bytes"):
            self.build({"runtime/runner.json": "text"})
        for name in ("/absolute", "../escape", "Runtime/Runner.json", ""):
            with self.subTest(name=name), self.assertRaisesRegex(noodles.GateError, "exact relative archive path"):
                self.build({name: b"{}"})


class PublicationReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.publication = noodles.build_evidence_publication(FOLDER, dict(MEMBERS))

    def readback(self, publication: dict | None = None, folder: str = FOLDER, members: dict[str, bytes] | None = None) -> dict:
        return noodles.evidence_publication_readback(
            self.publication if publication is None else publication, folder, dict(MEMBERS if members is None else members)
        )

    def test_positive_control_readback_accepts_the_exact_bytes_it_was_built_from(self) -> None:
        self.assertEqual(self.readback(), {"folder": FOLDER, "members": 2, "bytes": sum(len(v) for v in MEMBERS.values())})

    def test_planted_negative_wrong_head_manifest_is_refused_at_the_custody_key(self) -> None:
        wrong = noodles.evidence_custody_folder(REPOSITORY, ISSUE_NUMBER, PR_NUMBER, "b" * 40, RUN_ID, RUN_ATTEMPT)
        with self.assertRaisesRegex(noodles.GateError, "!= expected custody folder"):
            self.readback(folder=wrong)

    def test_planted_negative_missing_and_extra_members_are_refused(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "absent from the readback source"):
            self.readback(members={"runtime/runner.json": MEMBERS["runtime/runner.json"]})
        with self.assertRaisesRegex(noodles.GateError, "absent from the manifest"):
            self.readback(members={**MEMBERS, "runtime/extra.json": b"{}\n"})

    def test_planted_negative_truncated_member_is_refused_on_byte_count_and_digest(self) -> None:
        with self.assertRaises(noodles.GateError) as raised:
            self.readback(members={**MEMBERS, "runtime/runner.json": MEMBERS["runtime/runner.json"][:-1]})
        self.assertIn("byte count", str(raised.exception))
        self.assertIn("sha256", str(raised.exception))

    def test_planted_negative_tampered_recorded_digest_is_refused(self) -> None:
        tampered = copy.deepcopy(self.publication)
        tampered["manifest"]["members"][0]["sha256"] = "0" * 64
        tampered.update(noodles.evidence_manifest_digest(tampered["manifest"]))
        with self.assertRaisesRegex(noodles.GateError, "manifest sha256"):
            self.readback(tampered)

    def test_planted_negative_manifest_edited_under_a_published_digest_is_refused(self) -> None:
        tampered = copy.deepcopy(self.publication)
        tampered["manifest"]["folder"] = FOLDER
        tampered["manifest"]["members"][0]["bytes"] = 0
        with self.assertRaisesRegex(noodles.GateError, "does not describe the manifest"):
            self.readback(tampered)


class PublicationProducerTests(unittest.TestCase):
    """The one production caller: the trusted verify path, on the candidate tree as untrusted data."""

    def receipt(self) -> dict:
        return {"repository": REPOSITORY, "issue_subject": SUBJECT, "pr_number": PR_NUMBER, "head_sha": HEAD_SHA}

    def test_absent_run_identity_is_its_own_reported_state_not_a_publication(self) -> None:
        with mock.patch.dict(noodles.os.environ, {"GITHUB_RUN_ID": "", "GITHUB_RUN_ATTEMPT": ""}, clear=False):
            published = noodles.evidence_publication(CANDIDATE_ROOT, self.receipt())
        self.assertEqual(published["status"], "run_identity_absent")
        self.assertIsNone(published["folder"])
        self.assertIsNone(published["manifest_sha256"])

    def test_positive_control_a_real_run_identity_packages_and_reads_back_the_candidate(self) -> None:
        with mock.patch.dict(noodles.os.environ, RUN_ENV, clear=False):
            published = noodles.evidence_publication(CANDIDATE_ROOT, self.receipt())
        self.assertEqual(published["status"], "custody_unadmitted")
        self.assertEqual(published["folder"], FOLDER)
        self.assertGreaterEqual(published["members"], 3)
        self.assertEqual(len(published["manifest_sha256"]), 64)
        self.assertIn("no admitted Google Drive destination credential", published["reason"])

    def test_planted_negative_a_credential_in_a_candidate_lock_fails_the_trusted_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-evidence-", ignore_cleanup_errors=True) as name:
            candidate = Path(name) / "candidate"
            shutil.copytree(CANDIDATE_ROOT / "policy", candidate / "policy")
            leaked = candidate / "policy/leaked.lock.json"
            leaked.write_bytes(b'{"token": "' + PLANTED["github-token"] + b'"}\n')
            with mock.patch.dict(noodles.os.environ, RUN_ENV, clear=False), self.assertRaises(noodles.GateError) as raised:
                noodles.evidence_publication(candidate, self.receipt())
        self.assertIn("candidate/policy/leaked.lock.json: github-token", str(raised.exception))
        self.assertNotIn(PLANTED["github-token"].decode(), str(raised.exception))


class VerifyPullRequestEvidenceGateTests(unittest.TestCase):
    def run_verify(self, candidate: Path) -> dict:
        temp = tempfile.TemporaryDirectory(prefix="noodles-evidence-verify-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        (base / "event.json").write_text(json.dumps({
            "pull_request": {"number": PR_NUMBER, "head": {"sha": HEAD_SHA}, "base": {"ref": "main"}, "draft": False, "body": f"Refs {SUBJECT}"},
            "repository": {"full_name": REPOSITORY},
        }), encoding="utf-8")

        def fake_git(root: Path, *args: str, check: bool = True) -> str:
            return HEAD_SHA if args == ("rev-parse", "HEAD") else "b" * 40

        with mock.patch.object(noodles, "issue_read", return_value={"state": "open", "body": issue_body()}), \
                mock.patch.object(noodles, "merge_base_changed_files", return_value=["noodles.py"]), \
                mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": [], "metrics": {}}), \
                mock.patch.object(noodles, "git", side_effect=fake_git), \
                mock.patch.dict(noodles.os.environ, RUN_ENV, clear=False):
            return noodles.verify_pull_request(CANDIDATE_ROOT, base / "event.json", candidate, base / "receipt.json")

    def test_positive_control_receipt_carries_the_publication_bound_to_the_exact_head(self) -> None:
        receipt = self.run_verify(CANDIDATE_ROOT)
        self.assertIn("evidence-publication", receipt["gates"])
        published = receipt["evidence_publication"]
        self.assertEqual(published["status"], "custody_unadmitted")
        self.assertEqual(published["folder"], FOLDER)
        self.assertIn(receipt["head_sha"], published["folder"])
        recorded = {entry["name"] for entry in published["manifest"]["members"]}
        self.assertIn("verification/receipt.json", recorded)
        self.assertIn("candidate/workflows/verify.yml", recorded)

    def test_planted_negative_a_leaking_candidate_never_receives_a_landing_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-evidence-leak-", ignore_cleanup_errors=True) as name:
            candidate = Path(name) / "candidate"
            shutil.copytree(CANDIDATE_ROOT / "policy", candidate / "policy")
            (candidate / "policy/leaked.lock.json").write_bytes(b'{"key": "' + PLANTED["private-key-block"] + b'"}\n')
            with self.assertRaisesRegex(noodles.GateError, "scrub refused"):
                self.run_verify(candidate)


class PublicationAuthorityTests(unittest.TestCase):
    """Custody is evidence, never correctness: no admission path may read the publication."""

    def test_only_the_trusted_verify_path_calls_the_publisher(self) -> None:
        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        callers = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef)
            and any(
                isinstance(call.func, ast.Name) and call.func.id == "evidence_publication"
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
            )
        }
        self.assertEqual(callers, {"verify_pull_request"})

    def test_no_merge_or_closure_path_reads_the_publication(self) -> None:
        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        admission = {"land_pull_request", "post_receipt_anchor", "execute_handoff", "landing_train", "train_select"}
        bodies = {
            node.name: ast.get_source_segment(source, node) or ""
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name in admission
        }
        self.assertEqual(set(bodies), admission)
        self.assertEqual([name for name, body in bodies.items() if "evidence_publication" in body or "custody" in body], [])

    def test_the_custody_root_literal_lives_in_exactly_one_executable_constant(self) -> None:
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=str(CANDIDATE_ROOT), text=True, capture_output=True, check=False)
        self.assertEqual(tracked.returncode, 0, tracked.stderr)
        hits = {
            relative
            for relative in (entry for entry in tracked.stdout.split("\0") if entry)
            if relative.endswith((".py", ".yml", ".yaml")) and "GitHub-Actions-Evidence" in (CANDIDATE_ROOT / relative).read_text(encoding="utf-8", errors="ignore")
        }
        self.assertEqual(hits, {"noodles.py", "tests/test_evidence_publication.py"})
        self.assertEqual((CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8").count("GitHub-Actions-Evidence"), 1)


if __name__ == "__main__":
    unittest.main()
