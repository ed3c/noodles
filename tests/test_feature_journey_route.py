"""Route truth for the journey-compilation gate (ed3c/noodles#264).

`ed3c/noodles#242` put the gate inside `./noodles issue handoff`, a route the lanes that actually
land cannot take: `execute_provenance_admission` admits only a registered Noodle worktree on the
exact `execute_branch(subject)`, while wave-9 atoms landed from ordinary clones on their own
branches and reached `awaiting_land` by writing the marker directly. The gate existed and was
bypassable, and both routes ended green.

These controls hold the gate at the confluence instead: a candidate whose issue reached
`awaiting_land` by a direct marker flip is refused with its own diagnostic when the declared
feature's code surface is absent from the exact base..head diff, and the same candidate passes
once that surface is really changed.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import feature_contract
import noodles
from tests.support import CANDIDATE_ROOT, cmd, initialize_repo

HEAD_SHA = "c" * 40
SUBJECT = "ed3c/noodles#900264"
FEATURE = feature_contract.VERIFICATION_SKILL_FEATURE


def issue_body(*, feature: str | None = FEATURE.feature_id, state: str = "awaiting_land") -> str:
    """A body whose `awaiting_land` marker was written directly - no handoff produced it."""
    feature_marker = f"<!-- noodles-feature: {feature} -->\n" if feature is not None else ""
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        "<!-- noodles-target: ed3c/noodles -->\n"
        f"<!-- noodles-subject: {SUBJECT} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        "<!-- noodles-component: schedule -->\n"
        f"{feature_marker}"
        "<!-- noodles-depends-on: none -->\n\n"
        "## Goal\n\nCompile the declared journey where landing flows.\n\n"
        "## Physical acceptance\n\n- Planted controls fail closed.\n\n"
        "## Non-claims\n\n- The marker flip itself is never authorized by this gate.\n"
    )


class FeatureJourneyRouteGateTests(unittest.TestCase):
    def run_verify(self, body: str, changed_files: list[str]) -> tuple[object, mock.MagicMock]:
        temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        event_path = base / "event.json"
        event_path.write_text(
            json.dumps(
                {
                    "pull_request": {
                        "number": 11,
                        "head": {"sha": HEAD_SHA},
                        "base": {"ref": "main"},
                        "draft": False,
                        "body": f"Refs {SUBJECT}",
                    },
                    "repository": {"full_name": "ed3c/noodles"},
                }
            ),
            encoding="utf-8",
        )

        def fake_git(root: Path, *args: str, check: bool = True) -> str:
            if args == ("rev-parse", "HEAD"):
                return HEAD_SHA
            if args == ("rev-parse", "HEAD^{tree}"):
                return "d" * 40
            if args == ("log", "-1", "--format=%B", "HEAD"):
                return f"compile the declared journey\n\nRefs {SUBJECT}\n"
            raise AssertionError(f"unexpected git call: {args}")

        with mock.patch.object(noodles, "issue_read", return_value={"state": "open", "body": body}), \
                mock.patch.object(noodles, "merge_base_changed_files", return_value=changed_files), \
                mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": [], "metrics": {}}) as repository, \
                mock.patch.object(noodles, "git", side_effect=fake_git):
            receipt = noodles.verify_pull_request(CANDIDATE_ROOT, event_path, base, base / "receipt.json")
        return receipt, repository

    def test_positive_control_changed_feature_surface_compiles_into_the_landing_receipt(self) -> None:
        receipt, _ = self.run_verify(issue_body(), [FEATURE.code_surface])
        self.assertIn("feature-journey", receipt["gates"])
        self.assertEqual(receipt["feature"], FEATURE.feature_id)
        self.assertEqual(receipt["feature_changed_node"], FEATURE.code_surface)
        self.assertEqual(receipt["feature_journeys"], list(FEATURE.journeys))
        self.assertEqual(receipt["feature_transitions"], list(FEATURE.transitions))

    def test_planted_negative_direct_marker_flip_with_an_unmapped_journey_is_refused(self) -> None:
        with self.assertRaises(noodles.GateError) as raised:
            self.run_verify(issue_body(), ["AGENTS.md"])
        diagnostic = str(raised.exception)
        self.assertIn("candidate feature-journey gate failed", diagnostic)
        self.assertIn("unmapped journey", diagnostic)
        self.assertIn(FEATURE.code_surface, diagnostic)
        self.assertIn("Supported path", diagnostic)
        self.assertIn(SUBJECT, diagnostic)

    def test_planted_negative_fails_closed_before_the_repository_gate_runs(self) -> None:
        with mock.patch.object(noodles, "verify_repository") as repository:
            with self.assertRaises(noodles.GateError):
                self.run_verify(issue_body(), ["AGENTS.md"])
        repository.assert_not_called()

    def test_planted_negative_unadmitted_feature_id_is_refused_naming_the_supported_path(self) -> None:
        with self.assertRaises(noodles.GateError) as raised:
            self.run_verify(issue_body(feature="handoff-route-truth"), ["AGENTS.md"])
        diagnostic = str(raised.exception)
        self.assertIn("candidate feature-journey gate failed", diagnostic)
        self.assertIn("unadmitted noodles-feature", diagnostic)
        self.assertIn("drop the noodles-feature marker", diagnostic)

    def test_the_landing_receipt_reads_the_one_owned_gate_inventory(self) -> None:
        # constraint: ed3c/noodles#302 - the preview enumerates its coverage against this same tuple,
        # constraint: so a gate re-inlined here as a literal would be a surface the preview never
        # constraint: learns it misses. One owner is what makes the coverage list unable to rot.
        receipt, _ = self.run_verify(issue_body(), [FEATURE.code_surface])

        self.assertEqual(receipt["gates"], list(feature_contract.VERIFY_PR_GATES))

    def test_positive_control_marker_free_issue_carries_the_gate_with_no_compiled_map(self) -> None:
        receipt, repository = self.run_verify(issue_body(feature=None), ["AGENTS.md"])
        self.assertIn("feature-journey", receipt["gates"])
        self.assertIsNone(receipt["feature"])
        self.assertIsNone(receipt["feature_changed_node"])
        repository.assert_called_once()


class HandoffRouteIsNotTheLandingRouteTests(unittest.TestCase):
    """The evidence the arm choice rests on. `landed` below is a transcribed historical fact (which
    branch each wave-9 PR merged from), not a live readback - candidate-root-differs replay copies
    tracked files with no `.git` directory, so this file cannot read git history at test time and
    still run there. The transcription is checked against the real, live `noodles.execute_branch`.
    To re-verify the transcription itself now, from the merged tree:
      for n in 256 270 273; do gh pr view "$n" --json number,headRefName,mergedAt; done
    """

    def test_the_wave_nine_lane_branches_are_not_admissible_execute_branches(self) -> None:
        landed = ("fix-46-worktree-admission", "fix-99-exclusive-admission", "fix-100-concurrency-invariants")
        for branch in landed:
            with self.subTest(branch=branch):
                self.assertNotEqual(branch, noodles.execute_branch("ed3c/noodles#46"))
                self.assertNotEqual(branch, noodles.execute_branch("ed3c/noodles#99"))
                self.assertNotEqual(branch, noodles.execute_branch("ed3c/noodles#100"))

    def test_the_marker_writer_is_unconstrained_by_any_route_identity(self) -> None:
        # constraint: ed3c/noodles#264 - issue_set_state admits awaiting_land from any state and the
        # constraint: backlog adapter exposes it as a verb, which is why the gate cannot sit behind it.
        # constraint: this test proves only the premise (any edit actor can set the marker); the
        # constraint: class's other tests supply the "grants nothing" half by running that exact
        # constraint: direct-flip body through run_verify, showing the gate never reads how or by
        # constraint: whom awaiting_land was reached.
        self.assertIn("awaiting_land", noodles.ALLOWED_ISSUE_STATES)
        self.assertIn("edit = \".noodle/adapters/github edit\"", (CANDIDATE_ROOT / ".noodle.toml").read_text(encoding="utf-8"))
        self.assertIn("    issue_set_state(item_id, new_status)", (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8"))

    def test_the_journey_gate_has_exactly_one_home_and_it_is_the_landing_route(self) -> None:
        # constraint: ed3c/noodles#264 - the declaration anchors are composed at runtime; writing
        # constraint: `def <symbol>(` literally here would make this file a second declaration site
        # constraint: for the retrieval ground truth in tests/test_lancedb_ab.py.
        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("compile_handoff_feature_map("), 1)
        handoff = source.split(f"def {'execute_handoff'}(", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("compile_handoff_feature_map", handoff)
        verify = source.split(f"def {'verify_pull_request'}(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("compile_handoff_feature_map", verify)


# constraint: ed3c/noodles#275 - the disposition of `./noodles issue handoff`, and the reason it is a
# constraint: gate rather than a sentence. ed3c/noodles#264 moved the journey-compilation gate off
# constraint: this route, which left the verb looking free to delete. It is not free: the route is the
# constraint: only entrypoint to the only production caller of the admission carrying invariant I2.
# constraint: What reds here is exactly the shape that made #264 land as a half - a declared route
# constraint: whose live caller chain has quietly gone missing, with no recorded owner.
HANDOFF_ROUTE = "./noodles issue handoff"
HANDOFF_CUSTODY_KEYS = (
    "recorded_by", "disposition", "route", "admission", "live_caller", "module", "declared_at", "held_by",
)


def top_level_definitions(source: str) -> set[str]:
    return {
        node.name
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def handoff_custody_errors(proof: dict, source: str, readme: str) -> list[str]:
    """One predicate for both controls: the recorded custody, the live caller chain it names, and the
    declaring line, judged against the candidate's own bytes.

    Three separate readers would each pass over a shape the others never exercise, which is how a
    route ends up declared with no live caller in the first place."""
    invariants = {entry.get("id"): entry for entry in proof.get("invariants", []) if isinstance(entry, dict)}
    custody = (invariants.get("I2") or {}).get("custody")
    if not isinstance(custody, dict):
        return ["policy/concurrency-proof.json invariant I2 records no custody for its admission"]
    errors = [f"I2 custody names no {key}" for key in HANDOFF_CUSTODY_KEYS if not str(custody.get(key) or "").strip()]
    if errors:
        return errors
    definitions = top_level_definitions(source)
    admission = str(custody["admission"])
    caller = str(custody["live_caller"])
    for role, name in (("admission", admission), ("live_caller", caller)):
        if name not in definitions:
            errors.append(f"I2 custody {role} {name!r} is not a top-level definition of {custody['module']}")
    if errors:
        return errors
    if admission not in source.split(f"def {caller}(", 1)[1].split("\ndef ", 1)[0]:
        errors.append(f"I2 custody live_caller {caller!r} does not reach {admission!r}")
    dispatch = f'args.issue_action == "{str(custody["route"]).split()[-1]}"'
    if dispatch not in source:
        errors.append(f"I2 custody route {custody['route']!r} has no CLI dispatch ({dispatch})")
    elif caller not in source.split(dispatch, 1)[1].split("\n            if ", 1)[0]:
        errors.append(f"I2 custody route {custody['route']!r} does not dispatch to {caller!r}")
    declaring = [line for line in readme.splitlines() if line.startswith(HANDOFF_ROUTE)]
    if len(declaring) != 1:
        errors.append(
            f"{custody['declared_at']} carries {len(declaring)} declaring lines for {HANDOFF_ROUTE!r}; expected 1"
        )
    elif "Noodle-cook route" not in declaring[0]:
        errors.append(
            f"{custody['declared_at']} declaring line does not name the route that owns the verb: {declaring[0]!r}"
        )
    return errors


class HandoffVerbCustodyTests(unittest.TestCase):
    def setUp(self) -> None:
        # constraint: ed3c/noodles#275 - the lock's path is read through the module that already
        # constraint: imports it rather than by importing skill_contract here or restating the
        # constraint: literal. A direct import adds one standing cross-surface edge to `carrier` and
        # constraint: `docs`, and those counts are the ratchet ed3c/noodles#276 filed: the honest
        # constraint: response to a ratchet is not to add the edge, not to raise the number.
        proof_path = noodles.skill_contract.CONCURRENCY_PROOF_PATH
        self.proof = json.loads((CANDIDATE_ROOT / proof_path).read_text(encoding="utf-8"))
        self.source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        self.readme = (CANDIDATE_ROOT / "README.md").read_text(encoding="utf-8")

    def custody(self, proof: dict) -> dict:
        return next(entry for entry in proof["invariants"] if entry["id"] == "I2")["custody"]

    def test_positive_control_the_route_is_kept_with_a_recorded_live_caller(self) -> None:
        self.assertEqual(handoff_custody_errors(self.proof, self.source, self.readme), [])

    def test_planted_negative_the_pre_atom_state_no_recorded_custody_is_refused(self) -> None:
        # constraint: ed3c/noodles#275 - the exact shape this atom disposes of: I2 recorded, its
        # constraint: controls named, and nothing saying which live caller carries it.
        planted = json.loads(json.dumps(self.proof))
        del next(entry for entry in planted["invariants"] if entry["id"] == "I2")["custody"]
        self.assertEqual(
            handoff_custody_errors(planted, self.source, self.readme),
            ["policy/concurrency-proof.json invariant I2 records no custody for its admission"],
        )

    def test_planted_negative_custody_naming_an_absent_caller_is_refused(self) -> None:
        planted = json.loads(json.dumps(self.proof))
        self.custody(planted)["live_caller"] = "execute_handoff_retired"
        errors = handoff_custody_errors(planted, self.source, self.readme)
        self.assertTrue(any("is not a top-level definition" in error for error in errors), errors)

    def test_planted_negative_a_caller_that_no_longer_reaches_the_admission_is_refused(self) -> None:
        admission = self.custody(self.proof)["admission"]
        gutted = self.source.replace(f"    provenance = {admission}(", "    provenance = dict(", 1)
        self.assertNotEqual(gutted, self.source)
        errors = handoff_custody_errors(self.proof, gutted, self.readme)
        self.assertTrue(any("does not reach" in error for error in errors), errors)

    def test_planted_negative_a_retired_cli_dispatch_is_refused(self) -> None:
        retired = self.source.replace('args.issue_action == "handoff"', 'args.issue_action == "retired"', 1)
        self.assertNotEqual(retired, self.source)
        errors = handoff_custody_errors(self.proof, retired, self.readme)
        self.assertTrue(any("has no CLI dispatch" in error for error in errors), errors)

    def test_planted_negative_a_dispatch_that_stops_calling_the_caller_is_refused(self) -> None:
        caller = self.custody(self.proof)["live_caller"]
        detached = self.source.replace(f"print(json.dumps({caller}(root, args.subject", "print(json.dumps(dict(root, args.subject", 1)
        self.assertNotEqual(detached, self.source)
        errors = handoff_custody_errors(self.proof, detached, self.readme)
        self.assertTrue(any("does not dispatch to" in error for error in errors), errors)

    def test_planted_negative_a_dropped_declaring_line_is_refused(self) -> None:
        declaring = next(line for line in self.readme.splitlines() if line.startswith(HANDOFF_ROUTE))
        errors = handoff_custody_errors(self.proof, self.source, self.readme.replace(declaring + "\n", "", 1))
        self.assertTrue(any("declaring lines" in error for error in errors), errors)

    def test_planted_negative_the_stale_declaring_line_is_refused(self) -> None:
        # constraint: ed3c/noodles#275 - the exact line this atom replaced. It described the verb as
        # constraint: if it were the awaiting_land writer, which is the stale reading #264 disclosed.
        declaring = next(line for line in self.readme.splitlines() if line.startswith(HANDOFF_ROUTE))
        stale = f"{HANDOFF_ROUTE} REPO#N --pr N  # exact head/body + awaiting_land + blocking current-session handoff"
        errors = handoff_custody_errors(self.proof, self.source, self.readme.replace(declaring, stale, 1))
        self.assertTrue(any("does not name the route that owns the verb" in error for error in errors), errors)

    def test_i2_still_names_the_planted_negatives_keeping_the_verb_keeps(self) -> None:
        # constraint: ed3c/noodles#275 - that each named control really exists in the suite is already
        # constraint: gated by skill_contract.validate_concurrency_proof under `./noodles verify`;
        # constraint: re-resolving them here would be a second reader of the same fact. What this
        # constraint: adds is only the count, so retiring the verb cannot quietly thin I2's controls
        # constraint: on the way past. Ceiling inherited from the lock: existence, never assertion.
        entry = next(item for item in self.proof["invariants"] if item["id"] == "I2")
        self.assertEqual(len(entry["planted_negatives"]), 5)
        self.assertTrue(all(name.startswith("tests.test_execute_provenance.") for name in entry["planted_negatives"]))


class JourneyGatePreviewTests(unittest.TestCase):
    """ed3c/noodles#302 - the local preview covers the journey gate CI runs, or names that it does not.

    The trusted tree here is a real git repository carrying the trusted `feature_contract` module, so
    the compiler these controls exercise is the one CI would run over the candidate as data. Nothing
    in this class touches the provider: a stale marker reds before any push exists."""

    def preview_repo(self, *, changed: str = feature_contract.VERIFICATION_SKILL_FEATURE.code_surface, widen_candidate: bool = False) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-journey-preview-test-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        root.mkdir(parents=True)
        for module in ("feature_contract.py", "skill_contract.py"):
            shutil.copy2(CANDIDATE_ROOT / module, root / module)
        initialize_repo(root)
        cmd(["git", "checkout", "-q", "-b", "candidate"], root)
        surface = root / changed
        surface.parent.mkdir(parents=True, exist_ok=True)
        surface.write_text("candidate change\n", encoding="utf-8")
        if widen_candidate:
            planted = (root / "feature_contract.py").read_text(encoding="utf-8") + (
                "\n\nADMITTED_FEATURES['candidate-invented-feature'] = FeatureContract(\n"
                "    feature_id='candidate-invented-feature',\n"
                f"    code_surface={changed!r},\n"
                "    operation=('./noodles', 'verify'),\n"
                "    oracle_phrases=('x',),\n"
                "    oracle='planted',\n"
                "    transitions=('t',),\n"
                "    journeys=('j',),\n"
                ")\n"
            )
            (root / "feature_contract.py").write_text(planted, encoding="utf-8")
        cmd(["git", "add", "-A"], root)
        cmd(["git", "commit", "-q", "-m", "candidate"], root)
        return root

    def preview(self, root: Path, declared_feature: str | None) -> dict:
        return feature_contract.preview_journey_gate(root, trusted_ref="main", declared_feature=declared_feature, error_cls=AssertionError)

    def test_planted_control_stale_unadmitted_marker_reds_locally_naming_the_journey_gate(self) -> None:
        receipt = self.preview(self.preview_repo(), "component-surface-existing-edges")

        self.assertFalse(receipt["ok"], receipt)
        self.assertTrue(receipt["simulated"])
        self.assertIn("journey-compilation gate would red at CI", receipt["diagnostic"])
        self.assertIn("verify_pull_request feature-journey gate", receipt["diagnostic"])
        self.assertIn("unadmitted noodles-feature", receipt["diagnostic"])
        self.assertIn("drop the noodles-feature marker", receipt["diagnostic"])
        self.assertIsNone(receipt["feature_map"])

    def test_planted_control_admitted_marker_whose_code_surface_is_absent_reds_locally(self) -> None:
        receipt = self.preview(self.preview_repo(changed="AGENTS.md"), FEATURE.feature_id)

        self.assertFalse(receipt["ok"], receipt)
        self.assertIn("unmapped journey", receipt["diagnostic"])
        self.assertIn(FEATURE.code_surface, receipt["diagnostic"])
        self.assertEqual(receipt["changed_files"], ["AGENTS.md"])

    def test_planted_negative_control_a_correct_marker_stays_green_and_compiles_the_journey(self) -> None:
        receipt = self.preview(self.preview_repo(), FEATURE.feature_id)

        self.assertTrue(receipt["ok"], receipt)
        self.assertEqual(receipt["feature_map"]["feature_id"], FEATURE.feature_id)
        self.assertEqual(receipt["feature_map"]["journeys"], list(FEATURE.journeys))
        self.assertEqual(receipt["feature_map"]["transitions"], list(FEATURE.transitions))
        self.assertEqual(receipt["changed_files"], [FEATURE.code_surface])
        self.assertIn("feature-journey", receipt["coverage"]["covered"])

    def test_planted_negative_the_compiler_is_the_trusted_trees_not_the_candidates(self) -> None:
        """A candidate that invents its own admitted feature cannot preview itself green."""
        receipt = self.preview(self.preview_repo(widen_candidate=True), "candidate-invented-feature")

        self.assertFalse(receipt["ok"], receipt)
        self.assertIn("unadmitted noodles-feature", receipt["diagnostic"])

    def test_marker_free_issue_is_simulated_and_green_exactly_as_ci_compiles_nothing(self) -> None:
        receipt = self.preview(self.preview_repo(changed="AGENTS.md"), "")

        self.assertTrue(receipt["ok"], receipt)
        self.assertTrue(receipt["simulated"])
        self.assertIsNone(receipt["feature_map"])
        self.assertIn("feature-journey", receipt["coverage"]["covered"])

    def test_an_undeclared_feature_is_reported_as_an_uncovered_surface_never_as_a_pass(self) -> None:
        receipt = self.preview(self.preview_repo(), None)

        self.assertTrue(receipt["ok"], receipt)
        self.assertFalse(receipt["simulated"])
        self.assertEqual(receipt["coverage"]["covered"], [])
        gap = next(item for item in receipt["coverage"]["uncovered"] if item["gate"] == "feature-journey")
        self.assertEqual(gap["reason"], feature_contract.JOURNEY_PREVIEW_UNDECLARED)

    def test_every_verify_pr_gate_is_previewed_or_carries_a_printed_reason(self) -> None:
        receipt = self.preview(self.preview_repo(), FEATURE.feature_id)
        enumerated = set(receipt["coverage"]["covered"]) | {item["gate"] for item in receipt["coverage"]["uncovered"]}

        self.assertEqual(enumerated, set(feature_contract.VERIFY_PR_GATES))
        self.assertEqual(feature_contract.preview_coverage_errors(feature_contract.VERIFY_PR_GATES), [])
        for item in receipt["coverage"]["uncovered"]:
            self.assertTrue(item["reason"].strip(), item)

    def test_planted_negative_a_new_ci_gate_with_no_disposition_is_named_not_silently_skipped(self) -> None:
        errors = feature_contract.preview_coverage_errors([*feature_contract.VERIFY_PR_GATES, "provider-quota"])

        self.assertEqual(len(errors), 1)
        self.assertIn("provider-quota", errors[0])
        self.assertIn("neither previewed nor named", errors[0])

    def test_the_gate_inventory_is_not_re_inlined_in_the_landing_route(self) -> None:
        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        self.assertIn("feature_contract.VERIFY_PR_GATES", source)
        self.assertNotIn('"evidence-publication"', source)

    def test_the_cli_prints_the_journey_verdict_and_every_uncovered_surface(self) -> None:
        root = self.preview_repo()
        stub = {"ok": True, "trusted_ref": "main", "trusted_sha": "a" * 40, "fetch": "skipped", "would_red": [], "diagnostic": None}
        buffer = io.StringIO()
        with mock.patch.object(noodles.trusted_preview, "preview_trusted_verify", return_value=stub), \
                mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": [], "metrics": {}, "warnings": [], "warning_readback": []}), \
                contextlib.redirect_stdout(buffer):
            code = noodles.main(["--root", str(root), "verify", "--trusted-preview", "--trusted-ref", "main", "--feature", FEATURE.feature_id])
        printed = buffer.getvalue()

        self.assertEqual(code, 0, printed)
        self.assertIn("journey-preview main@", printed)
        self.assertIn(f"feature={FEATURE.feature_id!r}: PASS", printed)
        for gate in feature_contract.VERIFY_PR_GATES:
            if gate not in feature_contract.PREVIEW_COVERED_GATES:
                self.assertIn(f"  not previewed: {gate} - ", printed)

    def test_the_cli_reds_and_names_the_journey_gate_on_a_stale_marker(self) -> None:
        root = self.preview_repo()
        stub = {"ok": True, "trusted_ref": "main", "trusted_sha": "a" * 40, "fetch": "skipped", "would_red": [], "diagnostic": None}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(noodles.trusted_preview, "preview_trusted_verify", return_value=stub), \
                mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": [], "metrics": {}, "warnings": [], "warning_readback": []}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = noodles.main(["--root", str(root), "verify", "--trusted-preview", "--trusted-ref", "main", "--feature", "component-surface-existing-edges"])

        self.assertEqual(code, 1)
        self.assertIn("journey-preview main@", out.getvalue())
        self.assertIn(": FAIL", out.getvalue())
        self.assertIn("journey-compilation gate would red at CI", err.getvalue())


if __name__ == "__main__":
    unittest.main()
