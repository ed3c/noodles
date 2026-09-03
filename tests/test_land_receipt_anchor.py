"""Land-time physical-receipt anchor: one idempotent N-class comment per merged PR.

The anchor's load-bearing values (merge commit SHA, merged-at, and since ed3c/noodles#375 the sha256
of the PR body as merged) are provider truth the land path has already read back, so the machine emits
them one-per-land instead of a manual bulk backfill that trips GitHub's secondary content-creation
limit. These controls pin that the anchor is posted exactly once, never duplicated, never emitted when
the merge was refused, never read by an admission path, and that its body digest is recomputable from
the provider-read body by the one-line check documented beside the anchor format."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT

ENGINE_ROOT = Path(noodles.__file__).resolve().parent
ANCHOR_MARKER = "physical-receipt-anchor"
REPOSITORY = "ed3c/noodles"
PR_NUMBER = 4242
ISSUE_NUMBER = 900246
SUBJECT = f"{REPOSITORY}#{ISSUE_NUMBER}"
HEAD_SHA = "a" * 40
TREE_SHA = "b" * 40
MERGE_SHA = "c" * 40
MERGED_AT = "2026-08-31T04:05:06Z"
# constraint: ed3c/noodles#375 - the tightest body a NORMALISING digest disagrees with while still
# constraint: being a legal PR body (parse_pr_reference admits exactly one `Refs owner/repo#N` line):
# constraint: a CRLF terminator. strip(), a splitlines()-rejoin, and an LF rewrite each move this
# constraint: value, so the fixture is a live control on "raw bytes, UTF-8, no normalisation" rather
# constraint: than a restatement of it.
MERGED_BODY = f"Refs {SUBJECT}\r\n"


def issue_body(state: str = "awaiting_land") -> str:
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {REPOSITORY} -->\n"
        f"<!-- noodles-subject: {SUBJECT} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        "<!-- noodles-depends-on: none -->\n"
    )


class LandApi:
    """The provider surface land_pull_request actually calls, with the merge as real mutable state."""

    def __init__(
        self,
        *,
        merge_allowed: bool = True,
        merged_at: str | None = MERGED_AT,
        comments: list | None = None,
        fail_anchor_comments: bool = False,
        body: str = MERGED_BODY,
    ) -> None:
        self.merge_allowed = merge_allowed
        self.merged_at = merged_at
        self.body = body
        self.comments = list(comments or [])
        self.fail_anchor_comments = fail_anchor_comments
        self.posts: list[tuple[str, object]] = []
        self.merged = False
        self.issue = {"state": "open", "body": issue_body()}

    def pull(self) -> dict:
        return {
            "number": PR_NUMBER,
            "state": "closed" if self.merged else "open",
            "draft": False,
            "merged": self.merged,
            "merge_commit_sha": MERGE_SHA if self.merged else None,
            "merged_at": self.merged_at if self.merged else None,
            "body": self.body,
            "head": {"sha": HEAD_SHA},
            "base": {"ref": "main"},
        }

    def __call__(self, endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
        if endpoint == f"repos/{REPOSITORY}/pulls/{PR_NUMBER}/merge" and method == "PUT":
            if not self.merge_allowed:
                return {"merged": False, "message": "Head branch was modified. Review and try the merge again."}
            self.merged = True
            return {"merged": True, "sha": MERGE_SHA}
        if endpoint == f"repos/{REPOSITORY}/pulls/{PR_NUMBER}":
            return self.pull()
        if endpoint == f"repos/{REPOSITORY}/git/commits/{HEAD_SHA}":
            return {"tree": {"sha": TREE_SHA}}
        if endpoint == f"repos/{REPOSITORY}/git/commits/{MERGE_SHA}":
            return {"parents": [{"sha": HEAD_SHA}, {"sha": "d" * 40}]}
        if endpoint == f"repos/{REPOSITORY}/branches/main":
            return {"commit": {"sha": MERGE_SHA}}
        if endpoint == f"repos/{REPOSITORY}/issues/{PR_NUMBER}/comments?per_page=100":
            if self.fail_anchor_comments:
                raise noodles.GateError("simulated provider failure reading anchor comments")
            return list(self.comments)
        if endpoint == f"repos/{REPOSITORY}/issues/{PR_NUMBER}/comments" and method == "POST":
            self.posts.append((endpoint, payload))
            self.comments.append({"body": (payload or {}).get("body", "")})
            return {"id": 1}
        if endpoint == f"repos/{REPOSITORY}/issues/{ISSUE_NUMBER}":
            if method == "PATCH":
                self.issue.update(payload or {})
                return dict(self.issue)
            return dict(self.issue)
        raise AssertionError(f"unexpected gh api call: {method} {endpoint}")

    def anchors(self) -> list[str]:
        return [str((payload or {}).get("body", "")) for _endpoint, payload in self.posts]


def engine_head() -> str:
    """The revision this engine tree is checked out at - what the shim would have pinned to reach it."""
    return noodles.git(ENGINE_ROOT, "rev-parse", "HEAD")


def land(api: LandApi, *, lander_pin: str | None = None) -> dict:
    """The land ceremony against that provider surface. Module-level since ed3c/noodles#375 so the
    digest controls drive the same ceremony without borrowing another TestCase's bound method.

    `lander_pin` is what ed3c/noodles#433's entry exports into `$GITHUB_ENV` before the pinned tree
    takes over: `None` means "this engine tree, correctly pinned", `""` means the entry never ran,
    and an explicit sha plants a disagreement between the declared pin and the landing bytes."""
    with tempfile.TemporaryDirectory(prefix="noodles-land-anchor-", ignore_cleanup_errors=True) as name:
        work = Path(name)
        event_path = work / "event.json"
        receipt_path = work / "receipt.json"
        event_path.write_text(json.dumps({
            "repository": {"full_name": REPOSITORY},
            "workflow_run": {
                "name": "verify",
                "conclusion": "success",
                "id": 777,
                "head_sha": HEAD_SHA,
                "pull_requests": [{"number": PR_NUMBER}],
            },
        }), encoding="utf-8")
        receipt_path.write_text(json.dumps({
            "repository": REPOSITORY,
            "pr_number": PR_NUMBER,
            "head_sha": HEAD_SHA,
            "tree_sha": TREE_SHA,
            "issue_subject": SUBJECT,
        }), encoding="utf-8")
        trusted = {"run": {"id": 777}, "workflow": {"path": ".github/workflows/verify.yml"}, "provider_default_branch": "main"}
        declared = engine_head() if lander_pin is None else lander_pin
        with (
            mock.patch.dict(os.environ, {noodles.LANDER_PIN_ENV: declared}, clear=False),
            mock.patch.object(noodles, "gh_api", side_effect=api),
            mock.patch.object(noodles.github_protection, "trusted_workflow_run_readback", return_value=trusted),
            mock.patch.object(noodles.github_protection, "protection_audit", return_value={"required_check": "verify"}),
        ):
            return noodles.land_pull_request(ENGINE_ROOT, event_path, receipt_path)


class LandReceiptAnchorTests(unittest.TestCase):
    def test_land_posts_one_anchor_carrying_the_merge_readback_values(self) -> None:
        api = LandApi()
        result = land(api)
        self.assertEqual(result["merge_sha"], MERGE_SHA)
        self.assertTrue(result["issue_closed"])
        self.assertEqual(result["receipt_anchor"], "posted")
        digest = hashlib.sha256(MERGED_BODY.encode("utf-8")).hexdigest()
        self.assertEqual(
            api.anchors(),
            [
                f"physical-receipt-anchor: pr={PR_NUMBER} merge-commit={MERGE_SHA} "
                f"merged-at={MERGED_AT} body-sha256={digest}"
            ],
        )

    def test_planted_pre_existing_anchor_produces_no_duplicate(self) -> None:
        # constraint: the backfill overlap and the workflow re-run look identical from here - an anchor
        # constraint: already on the PR, whatever posted it, must make the step a no-op.
        backfilled = f"physical-receipt-anchor: pr={PR_NUMBER} merge-commit={MERGE_SHA} merged-at={MERGED_AT} drive-index=https://example.invalid/index"
        api = LandApi(comments=[{"body": "unrelated review chatter"}, {"body": backfilled}])
        result = land(api)
        self.assertEqual(result["receipt_anchor"], "existing")
        self.assertEqual(api.anchors(), [])
        self.assertEqual([c["body"] for c in api.comments].count(backfilled), 1)

    def test_planted_negative_refused_merge_posts_no_anchor(self) -> None:
        api = LandApi(merge_allowed=False)
        with self.assertRaisesRegex(noodles.GateError, "GitHub merge failed"):
            land(api)
        self.assertEqual(api.anchors(), [])
        self.assertFalse(api.merged)
        self.assertEqual(api.issue["state"], "open")
        self.assertIn("<!-- noodles-state: awaiting_land -->", api.issue["body"])

    def test_planted_negative_merge_readback_without_a_timestamp_degrades_the_anchor_only(self) -> None:
        # constraint: merged_at only feeds the decorative anchor comment - it must never turn an
        # constraint: already-succeeded merge+closure into a reported land failure.
        api = LandApi(merged_at=None)
        result = land(api)
        self.assertTrue(api.merged)
        self.assertTrue(result["issue_closed"])
        self.assertEqual(result["receipt_anchor"], "failed")
        self.assertEqual(api.anchors(), [])

    def test_planted_negative_anchor_post_failure_never_gates_an_already_succeeded_land(self) -> None:
        # constraint: the anchor exists specifically to dodge GitHub's secondary content-creation limit -
        # constraint: a provider failure posting it must degrade to receipt_anchor="failed", not raise
        # constraint: after the merge and issue closure it is reporting on already happened.
        api = LandApi(fail_anchor_comments=True)
        result = land(api)
        self.assertTrue(api.merged)
        self.assertTrue(result["issue_closed"])
        self.assertEqual(result["receipt_anchor"], "failed")
        self.assertEqual(api.anchors(), [])

    def test_anchor_is_n_class_no_admission_path_reads_it(self) -> None:
        """Mechanical N-class proof, read off the exact candidate tree rather than the engine import."""
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=str(CANDIDATE_ROOT), text=True, capture_output=True, check=False
        )
        self.assertEqual(tracked.returncode, 0, tracked.stderr)
        executable_hits = set()
        for relative in [entry for entry in tracked.stdout.split("\0") if entry]:
            if not (relative.endswith((".py", ".yml", ".yaml")) or relative == "noodles"):
                continue
            if ANCHOR_MARKER in (CANDIDATE_ROOT / relative).read_text(encoding="utf-8", errors="ignore"):
                executable_hits.add(relative)
        self.assertEqual(executable_hits, {"noodles.py", "tests/test_land_receipt_anchor.py"})

        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        self.assertEqual(source.count(ANCHOR_MARKER), 1, "the marker literal must live in exactly one constant")
        readers = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and "RECEIPT_ANCHOR_PREFIX" in (ast.get_source_segment(source, node) or "")
        }
        self.assertEqual(readers, {"post_receipt_anchor"})


class AnchorBodyDigestTests(unittest.TestCase):
    """ed3c/noodles#375 - the anchor named the merge but not the bytes.

    Every body-digest claim about a landed atom here was self-report: nothing provider-side existed to
    check it against, which leaves the cheapest lie open - quoting someone else's digest as your own
    "independently reproduced" value, the exact composed-truth instance a sibling repository caught
    live. The field costs one hash of a string the lander already holds.

    Non-claim, so the green here is not read wider than it is: these controls prove the anchor CARRIES
    a recomputable digest of the body the provider returned. They do not police lane reports, and they
    do not re-anchor anything that landed before this field existed - an old anchor without the field
    is old, not forged."""

    def check(self, anchor: str, body: bytes) -> int:
        """Run the exact one-liner `noodles.py` documents beside the anchor format, and return its
        real exit code.

        Executed rather than described: if the documentation drifts from what actually refuses, this
        control drifts with it and the planted negatives below stop being detectable."""
        with tempfile.TemporaryDirectory(prefix="noodles-anchor-digest-", ignore_cleanup_errors=True) as name:
            work = Path(name)
            (work / "anchor.txt").write_text(anchor, encoding="utf-8")
            (work / "body.bin").write_bytes(body)
            completed = subprocess.run(
                ["sh", "-c", noodles.ANCHOR_BODY_DIGEST_CHECK, "sh", str(work / "anchor.txt"), str(work / "body.bin")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.stderr, "", completed.stderr)
            return completed.returncode

    def anchor(self, api: LandApi) -> str:
        anchors = api.anchors()
        self.assertEqual(len(anchors), 1, anchors)
        return anchors[0]

    def test_the_landed_anchor_digest_is_recomputable_from_the_provider_read_body(self) -> None:
        api = LandApi()
        land(api)
        anchor = self.anchor(api)
        field = re.search(r"body-sha256=([0-9a-f]+)", anchor)
        self.assertIsNotNone(field, anchor)
        self.assertEqual(len(field.group(1)), 64, "truncation is impossible by construction; assert it anyway")
        self.assertEqual(field.group(1), hashlib.sha256(MERGED_BODY.encode("utf-8")).hexdigest())
        self.assertEqual(self.check(anchor, MERGED_BODY.encode("utf-8")), 0)

    def test_the_digest_is_over_raw_bytes_so_every_normalisation_of_the_same_body_is_refused(self) -> None:
        """The preimage is the provider's RAW body bytes, UTF-8, no normalisation. A digest that
        agreed with a stripped or LF-rewritten body would agree with bytes nobody merged."""
        api = LandApi()
        land(api)
        anchor = self.anchor(api)
        self.assertEqual(self.check(anchor, MERGED_BODY.encode("utf-8")), 0)
        for label, variant in {
            "stripped": MERGED_BODY.strip(),
            "lf-rewritten": MERGED_BODY.replace("\r\n", "\n"),
            "newline-dropped": "\n".join(MERGED_BODY.splitlines()),
        }.items():
            with self.subTest(normalisation=label):
                self.assertNotEqual(variant.encode("utf-8"), MERGED_BODY.encode("utf-8"))
                self.assertEqual(self.check(anchor, variant.encode("utf-8")), 1)

    def test_planted_negative_an_anchor_missing_the_field_is_refused_by_the_documented_check(self) -> None:
        without = f"physical-receipt-anchor: pr={PR_NUMBER} merge-commit={MERGE_SHA} merged-at={MERGED_AT}"
        self.assertEqual(self.check(without, MERGED_BODY.encode("utf-8")), 1)

    def test_planted_negative_a_digest_quoted_from_another_body_is_refused(self) -> None:
        """The composed-truth shape this field exists for: an anchor whose digest is real, 64 hex, and
        someone else's."""
        api = LandApi()
        land(api)
        stolen = hashlib.sha256(f"Refs {REPOSITORY}#111111\r\n".encode("utf-8")).hexdigest()
        forged = re.sub(r"body-sha256=[0-9a-f]{64}", f"body-sha256={stolen}", self.anchor(api))
        self.assertIn(stolen, forged)
        self.assertEqual(self.check(forged, MERGED_BODY.encode("utf-8")), 1)

    def test_planted_negative_a_truncated_digest_is_refused_rather_than_prefix_matched(self) -> None:
        api = LandApi()
        land(api)
        anchor = self.anchor(api)
        truncated = re.sub(r"(body-sha256=[0-9a-f]{40})[0-9a-f]{24}", r"\1", anchor)
        self.assertNotEqual(truncated, anchor)
        self.assertEqual(self.check(truncated, MERGED_BODY.encode("utf-8")), 1)


class LanderProvenanceTests(unittest.TestCase):
    """ed3c/noodles#433 - every land receipt names the lander revision that produced it.

    `workflow_run` runs the default branch's entry file, so before this atom the answer to "which
    lander landed this" was "whatever `main` happened to carry at trigger time" and no record said
    so. The entry now checks the pinned revision out over itself and exports the pin; these controls
    hold the lander to reading that pin back against the bytes it is actually running, and to
    refusing BEFORE the merge when the two disagree or the handoff never happened."""

    def test_the_land_receipt_records_the_pinned_lander_revision(self) -> None:
        api = LandApi()
        result = land(api)
        self.assertEqual(result["lander"], {"sha": engine_head(), "pin": engine_head(), "pinned": True})
        self.assertTrue(api.merged)

    def test_planted_negative_a_pin_disagreeing_with_the_landing_bytes_refuses_before_the_merge(self) -> None:
        api = LandApi()
        with self.assertRaisesRegex(noodles.GateError, "lander pin readback failed"):
            land(api, lander_pin="0" * 40)
        self.assertFalse(api.merged)
        self.assertEqual(api.anchors(), [])
        self.assertEqual(api.issue["state"], "open")

    def test_planted_negative_an_entry_that_never_handed_off_refuses_before_the_merge(self) -> None:
        api = LandApi()
        with self.assertRaisesRegex(noodles.GateError, f"{noodles.LANDER_PIN_ENV} is absent"):
            land(api, lander_pin="")
        self.assertFalse(api.merged)
        self.assertEqual(api.anchors(), [])
        self.assertEqual(api.issue["state"], "open")


if __name__ == "__main__":
    unittest.main()
