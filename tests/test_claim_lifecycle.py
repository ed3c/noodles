"""Planted fixtures for the dead-claim lifecycle: detect, adopt, release, re-admit (ed3c/noodles#181)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import claim_contract
import issue_contract
import noodles
import skill_contract
from tests.support import (
    CANDIDATE_ROOT,
    ISSUE_DEPENDS_ON_MARKER,
    ISSUE_FEATURE_MARKER,
    ISSUE_REQUIREMENT_MARKER,
    cmd,
    complete_issue_sections,
    copy_tracked,
    handoff_fixture,
)

REPOSITORY = "ed3c/noodles"
SUBJECT = "ed3c/noodles#33"
BRANCH = "ed3c-noodles-33-0-execute"
FIXED_NOW = datetime(2026, 8, 30, tzinfo=timezone.utc).timestamp()
LIVE_TIMESTAMP = "2026-08-29T23:30:00Z"
MAIN_HEAD = "b" * 40
EXECUTE_MODEL = skill_contract.task_profiles(CANDIDATE_ROOT)["execute"]["model"]


def issue_body(state: str, *, local: bool = False) -> str:
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {REPOSITORY} -->\n"
        f"<!-- noodles-subject: {SUBJECT} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        f"{ISSUE_FEATURE_MARKER}\n"
        f"{ISSUE_DEPENDS_ON_MARKER}\n"
        "<!-- noodles-write-boundary: none -->\n"
        f"<!-- noodles-executor: {'local-noodle' if local else 'gha-runtime'} -->\n"
        f"<!-- noodles-runtime: {'python' if local else 'shell'} -->\n"
        "<!-- noodles-evidence: github-only-v1 -->\n"
        f"{ISSUE_REQUIREMENT_MARKER}\n\n"
        + complete_issue_sections("One exact claimed atom.", "- Nothing adjacent.")
    )


class ClaimProvider:
    """Stateful provider double for issue/PR/refs/workflow readbacks and claim mutations."""

    def __init__(self, head: str, *, issue_state: str = "open", contract_state: str = "awaiting_land", failed: bool = True, local: bool = False) -> None:
        self.head = head
        self.failed = failed
        self.pr_open = True
        self.refs: dict[str, str] = {f"refs/heads/{BRANCH}": head}
        self.issue = {
            "number": 33,
            "state": issue_state,
            "title": "[PARALLEL-P0] claimed atom 33",
            "html_url": f"https://github.test/{REPOSITORY}/issues/33",
            "body": issue_body(contract_state, local=local),
        }
        self.ref_posts: list[str] = []
        self.ref_deletes: list[str] = []
        self.body_patches = 0
        self.comments: list[dict] = []

    def pr(self) -> dict:
        return {
            "number": 44,
            "state": "open",
            "merged": False,
            "draft": False,
            "body": f"Refs {SUBJECT}",
            "head": {"sha": self.head, "ref": BRANCH},
            "base": {"ref": "main"},
        }

    def run(self) -> dict:
        return {
            "id": 777,
            "name": "verify",
            "path": ".github/workflows/verify.yml",
            "event": "pull_request_target",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": self.head,
            "html_url": "https://example.invalid/runs/777",
            "workflow_id": 11,
            "run_attempt": 1,
            "pull_requests": [{"number": 44}],
        }

    def api(self, endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
        # constraint: ed3c/noodles#272 - both callers now hit the one paginated shape, because
        # constraint: repair_contract.find_open_pr_for_subject reads through the same shared exit
        # constraint: (noodles.matching_open_pull_requests) schedule_publish's refusal already
        # constraint: used; an unpaginated second correlation no longer exists to answer for.
        if endpoint == f"repos/{REPOSITORY}/pulls?state=open&per_page=100&page=1":
            return [self.pr()] if self.pr_open else []
        if endpoint == f"repos/{REPOSITORY}/issues/33":
            if method == "PATCH":
                assert isinstance(payload, dict)
                self.body_patches += 1
                self.issue["body"] = str(payload["body"])
            return self.issue
        if endpoint == f"repos/{REPOSITORY}/issues/33/comments?per_page=100":
            return list(self.comments)
        if endpoint == f"repos/{REPOSITORY}/issues/33/comments" and method == "POST":
            assert isinstance(payload, dict)
            self.comments.append({"id": len(self.comments) + 1, "body": payload["body"]})
            return self.comments[-1]
        if endpoint.startswith(f"repos/{REPOSITORY}/issues?state=open"):
            return [self.issue] if self.issue["state"] == "open" else []
        if endpoint == f"repos/{REPOSITORY}/git/ref/heads/main":
            return {"ref": "refs/heads/main", "object": {"sha": MAIN_HEAD}}
        if endpoint.startswith(f"repos/{REPOSITORY}/git/matching-refs/heads/"):
            prefix = endpoint.partition("/git/matching-refs/heads/")[2]
            return [
                {"ref": ref, "object": {"sha": sha}}
                for ref, sha in sorted(self.refs.items())
                if ref.removeprefix("refs/heads/").startswith(prefix)
            ]
        if endpoint == f"repos/{REPOSITORY}/git/refs" and method == "POST":
            assert isinstance(payload, dict)
            ref, sha = str(payload["ref"]), str(payload["sha"])
            if ref in self.refs:
                raise noodles.GateError("provider rejected duplicate ref")
            self.refs[ref] = sha
            self.ref_posts.append(ref)
            return {"ref": ref, "object": {"sha": sha}}
        if endpoint.startswith(f"repos/{REPOSITORY}/git/refs/heads/") and method == "DELETE":
            ref = "refs/heads/" + endpoint.partition("/git/refs/heads/")[2]
            if ref not in self.refs:
                raise noodles.GateError(f"provider has no ref {ref}")
            del self.refs[ref]
            self.ref_deletes.append(ref)
            if ref == f"refs/heads/{BRANCH}":
                self.pr_open = False
            return None
        if endpoint == f"repos/{REPOSITORY}/actions/runs?head_sha={self.head}&per_page=100":
            return {"workflow_runs": [self.run()] if self.failed else []}
        if endpoint == f"repos/{REPOSITORY}/actions/runs/777":
            return self.run()
        if endpoint == f"repos/{REPOSITORY}":
            return {"full_name": REPOSITORY, "default_branch": "main"}
        if endpoint == f"repos/{REPOSITORY}/actions/workflows/verify.yml":
            return {"id": 11, "name": "verify", "path": ".github/workflows/verify.yml", "state": "active"}
        if endpoint == f"repos/{REPOSITORY}/actions/runs/777/jobs?per_page=100":
            return {"jobs": [{
                "id": 99073595935,
                "name": "candidate-self-tests",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://example.invalid/jobs/99073595935",
            }]}
        raise AssertionError(f"unexpected provider call: {method} {endpoint}")


class ClaimLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp, self.root, self.binary, self.session_id = handoff_fixture(
            CANDIDATE_ROOT,
            subject=SUBJECT,
            worktree_name=BRANCH,
        )
        self.addCleanup(self.temp.cleanup)
        self.head = cmd(["git", "rev-parse", "HEAD"], self.root)
        self.events_path = self.root / ".noodle" / "sessions" / self.session_id / "events.ndjson"

    def sweep(self, provider: ClaimProvider) -> list[dict]:
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            return claim_contract.sweep_dead_claims(self.root, now=FIXED_NOW)

    def snapshot(self, provider: ClaimProvider) -> list[dict]:
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            return claim_contract.dead_claim_snapshot(self.root, REPOSITORY, now=FIXED_NOW)

    def append_event(self, timestamp: str, event_type: str = "action", payload: dict | None = None) -> None:
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "type": event_type,
                "payload": payload if payload is not None else {"message": f"[order:{SUBJECT}] heartbeat"},
                "timestamp": timestamp,
                "session_id": self.session_id,
            }) + "\n")

    def drop_session(self) -> None:
        shutil.rmtree(self.root / ".noodle" / "sessions" / self.session_id)

    def assert_untouched(self, provider: ClaimProvider) -> None:
        self.assertEqual(provider.ref_posts, [])
        self.assertEqual(provider.ref_deletes, [])
        self.assertEqual(provider.body_patches, 0)
        self.assertEqual(noodles.parse_issue_contract(self.issue_state_body(provider))["state"], "awaiting_land")

    def issue_state_body(self, provider: ClaimProvider) -> str:
        return str(provider.issue["body"])

    def test_detector_classifies_planted_dead_claim_deterministically(self) -> None:
        provider = ClaimProvider(self.head)
        records = self.snapshot(provider)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["class"], "dead_claim")
        self.assertEqual(record["subject"], SUBJECT)
        self.assertEqual(record["branch"], BRANCH)
        self.assertEqual(record["head"], self.head)
        self.assertEqual(record["pr_number"], 44)
        self.assertEqual(record["session_ids"], [self.session_id])

    def test_fresh_ledger_session_is_live_and_sweep_mutates_nothing(self) -> None:
        provider = ClaimProvider(self.head)
        self.append_event(LIVE_TIMESTAMP)
        outcomes = self.sweep(provider)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["class"], "live_session")
        self.assertEqual(outcomes[0]["action"], "skipped")
        self.assert_untouched(provider)

    def test_non_awaiting_land_claim_is_planted_negative_control(self) -> None:
        provider = ClaimProvider(self.head, contract_state="in_progress")
        outcomes = self.sweep(provider)
        self.assertEqual(outcomes[0]["class"], "not_awaiting_land")
        self.assertEqual(outcomes[0]["action"], "skipped")
        self.assertEqual(provider.ref_posts, [])
        self.assertEqual(provider.ref_deletes, [])
        self.assertEqual(provider.body_patches, 0)

    def test_missing_open_pr_is_planted_negative_control(self) -> None:
        provider = ClaimProvider(self.head)
        provider.pr_open = False
        outcomes = self.sweep(provider)
        self.assertEqual(outcomes[0]["class"], "no_single_open_pr")
        self.assertEqual(outcomes[0]["action"], "skipped")
        self.assert_untouched(provider)

    def test_pre_pr_orphan_binds_exact_registered_worktree_and_preserves_dirty_bytes(self) -> None:
        self.drop_session()
        dirty = self.root / "orphan-dirty.txt"
        dirty.write_bytes(b"preserve this exact byte string\n")
        provider = ClaimProvider(self.head, contract_state="ready", local=True)
        provider.pr_open = False
        record = self.snapshot(provider)[0]
        self.assertEqual(record["class"], "pre_pr_orphan")
        self.assertEqual(record["repository"], REPOSITORY)
        self.assertEqual(record["subject"], SUBJECT)
        self.assertEqual(record["provider_head"], self.head)
        self.assertEqual(record["local_branch"], BRANCH)
        self.assertEqual(record["local_head"], self.head)
        self.assertEqual(record["worktree_path"], str(self.root.resolve()))
        self.assertIn("orphan-dirty.txt", record["dirty_paths"])
        self.assertEqual(dirty.read_bytes(), b"preserve this exact byte string\n")

    def test_pre_pr_orphan_without_exact_registered_worktree_is_held(self) -> None:
        self.drop_session()
        provider = ClaimProvider(self.head, contract_state="ready", local=True)
        provider.pr_open = False
        with mock.patch.object(noodles, "registered_worktrees", return_value={}):
            record = self.snapshot(provider)[0]
        self.assertEqual(record["class"], "held")
        self.assertIn(f"exactly one registered worktree on refs/heads/{BRANCH}", record["reason"])
        self.assertIn(SUBJECT, record["reason"])

    def test_pre_pr_claim_with_live_session_is_held_live(self) -> None:
        provider = ClaimProvider(self.head, contract_state="ready", local=True)
        provider.pr_open = False
        self.append_event(LIVE_TIMESTAMP)
        record = self.snapshot(provider)[0]
        self.assertEqual(record["class"], "held_live")
        self.assertEqual(record["live_session_ids"], [self.session_id])
        self.assertIn(self.session_id, record["reason"])

    def test_pre_pr_quiet_worker_must_exit_before_adoption(self) -> None:
        provider = ClaimProvider(self.head, contract_state="ready", local=True)
        provider.pr_open = False
        worker = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.read()"],
            cwd=self.root, stdin=subprocess.PIPE,
        )
        process_path = self.events_path.with_name("process.json")
        process_path.write_text(json.dumps({
            "pid": worker.pid, "session_id": self.session_id,
            "started_at": "2026-08-29T00:00:00Z",
        }))
        try:
            self.assertIsNone(worker.poll())
            record = self.snapshot(provider)[0]
            self.assertEqual(record["class"], "held_live")
            self.assertIn(str(worker.pid), record["reason"])
            self.events_path.unlink()
            self.assertEqual(self.snapshot(provider)[0]["class"], "held_live")
        finally:
            worker.stdin.close()
            worker.wait(timeout=5)
        record = self.snapshot(provider)[0]
        self.assertEqual(record["class"], "pre_pr_orphan")
        self.assertEqual(provider.ref_posts, [])
        self.assertEqual(provider.ref_deletes, [])
        self.assertEqual(provider.body_patches, 0)

    def test_pre_pr_unknown_process_record_is_held(self) -> None:
        provider = ClaimProvider(self.head, contract_state="ready", local=True)
        provider.pr_open = False
        process_path = self.events_path.with_name("process.json")
        for payload in (None, "not json", {"pid": 0, "session_id": self.session_id},
                        {"pid": os.getpid(), "session_id": "foreign-session"}):
            with self.subTest(payload=payload):
                if payload is not None:
                    process_path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
                record = self.snapshot(provider)[0]
                self.assertEqual(record["class"], "held")
                self.assertIn("process", record["reason"])
        self.assertEqual(provider.ref_posts, [])
        self.assertEqual(provider.ref_deletes, [])

    def test_pre_pr_provider_local_head_drift_is_held(self) -> None:
        self.drop_session()
        provider = ClaimProvider("c" * 40, contract_state="ready", local=True)
        provider.pr_open = False
        record = self.snapshot(provider)[0]
        self.assertEqual(record["class"], "held")
        self.assertEqual(record["provider_head"], "c" * 40)
        self.assertEqual(record["local_head"], self.head)
        self.assertIn("registered/local heads", record["reason"])

    def test_pre_pr_ambiguous_registered_worktrees_are_held(self) -> None:
        self.drop_session()
        provider = ClaimProvider(self.head, contract_state="ready", local=True)
        provider.pr_open = False
        registry = noodles.registered_worktrees(self.root)
        registry[(self.root.parent / "duplicate").resolve()] = dict(registry[self.root.resolve()])
        with mock.patch.object(noodles, "registered_worktrees", return_value=registry):
            record = self.snapshot(provider)[0]
        self.assertEqual(record["class"], "held")
        self.assertIn("found 2", record["reason"])
        self.assertIn("duplicate", record["reason"])

    def test_pre_pr_unreadable_issue_is_held_before_worktree_adoption(self) -> None:
        self.drop_session()
        provider = ClaimProvider(self.head, contract_state="ready", local=True)
        provider.pr_open = False
        provider.issue["body"] = "not an issue contract"
        record = self.snapshot(provider)[0]
        self.assertEqual(record["class"], "unreadable_issue")
        self.assertIn("missing noodles-role marker", record["reason"])

    def test_schedule_reuses_pre_pr_provider_ref_worktree_and_dirty_bytes_once(self) -> None:
        self.drop_session()
        dirty = self.root / "orphan-dirty.txt"
        dirty.write_bytes(b"never reset or clean me\n")
        provider = ClaimProvider(self.head, contract_state="ready", local=True)
        provider.pr_open = False
        candidate = self.root / ".noodle" / "orders-next.candidate.json"
        candidate.write_text(json.dumps({
            "orders": [{
                "id": SUBJECT,
                "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "resume exact orphan"}],
            }]
        }))
        before_path = str(self.root.resolve())
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            first = noodles.schedule_publish(self.root, candidate)
            candidate.write_text(json.dumps({"orders": [{
                "id": SUBJECT,
                "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "resume exact orphan"}],
            }]}))
            second = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(first["claims"][0]["status"], "claimed")
        self.assertEqual(first["claims"][0]["adoption"]["status"], "adopted")
        self.assertEqual(first["claims"][0]["adoption"]["worktree_path"], before_path)
        self.assertEqual(second["claims"][0]["status"], "claimed_elsewhere")
        self.assertEqual(second["claims"][0]["adoption"]["status"], "already_published")
        self.assertEqual(json.loads((self.root / ".noodle" / "orders-next.json").read_text())["orders"], [{
            "id": SUBJECT,
            "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "resume exact orphan"}],
        }])
        self.assertEqual(provider.ref_posts, [])
        self.assertEqual(provider.ref_deletes, [])
        self.assertEqual(dirty.read_bytes(), b"never reset or clean me\n")
        self.assertEqual(len(provider.comments), 1)

    @unittest.skipIf(
        os.getenv("NOODLES_OFFLINE_TESTS") == "1" or os.getenv("GITHUB_ACTIONS") == "true",
        "pinned Noodle runtime is intentionally unavailable in hosted/offline CI; live control runs before handoff",
    )
    def test_pinned_noodle_reuses_the_exact_dirty_pre_pr_worktree(self) -> None:
        binary = noodles.resolve_locked_runtime_binary(CANDIDATE_ROOT, error_cls=AssertionError)
        with tempfile.TemporaryDirectory(prefix="noodles-pre-pr-adoption-", ignore_cleanup_errors=True) as temp_name:
            project = Path(temp_name) / "repo"
            copy_tracked(CANDIDATE_ROOT, project)

            worktree = project / ".worktrees" / BRANCH
            worktree.parent.mkdir()
            cmd(["git", "worktree", "add", "-q", "-b", BRANCH, str(worktree), "HEAD"], project)
            dirty = worktree / "README.md"
            dirty.write_bytes(dirty.read_bytes() + b"\npre-pr adoption must preserve this byte\n")
            before = cmd(["git", "diff", "--binary"], worktree)

            fake_bin = Path(temp_name) / "bin"
            fake_bin.mkdir()
            fake_codex = fake_bin / "codex"
            fake_codex.write_text(
                f"#!{sys.executable}\n"
                "import json\n"
                "import sys\n"
                "sys.stdin.read()\n"
                "print(json.dumps({'type': 'thread.started', 'thread_id': 'fixture'}))\n"
                "print(json.dumps({'type': 'turn.completed', 'usage': {}}))\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            (project / ".noodle.toml").write_text(
                "mode = \"supervised\"\n"
                "[routing.defaults]\nprovider = \"codex\"\nmodel = \"fixture\"\n"
                "[concurrency]\nmax_concurrency = 1\n"
                "[runtime.process]\nmax_concurrent = 1\n"
                "[server]\nenabled = false\n"
                "[skills]\npaths = [\".agents/skills\"]\n"
                f"[agents.codex]\npath = {json.dumps(str(fake_bin))}\nargs = []\n",
                encoding="utf-8",
            )
            runtime = project / ".noodle"
            runtime.mkdir(exist_ok=True)
            provider = ClaimProvider(cmd(["git", "rev-parse", "HEAD"], worktree), contract_state="ready", local=True)
            provider.pr_open = False
            candidate = runtime / "orders-next.candidate.json"
            candidate.write_text(json.dumps({
                "orders": [{
                    "id": SUBJECT,
                    "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "resume exact orphan"}],
                }]
            }))
            with mock.patch.dict(os.environ, {"NOODLE_PROJECT_DIR": str(project)}), \
                 mock.patch.object(noodles, "gh_api", side_effect=provider.api):
                brief = noodles.schedule_publish(project, candidate)

            result = subprocess.run(
                [str(binary), "--project-dir", str(project), "start", "--once"],
                cwd=project,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            sessions = sorted(runtime.glob(f"sessions/{BRANCH}-*"))
            self.assertEqual(len(sessions), 1, result.stderr or result.stdout)
            spawn = json.loads((sessions[0] / "spawn.json").read_text())
            self.assertEqual(Path(spawn["worktree_path"]).resolve(), worktree.resolve())
            self.assertEqual(cmd(["git", "diff", "--binary"], worktree), before)
            self.assertEqual(brief["claims"][0]["adoption"]["status"], "adopted")
            self.assertEqual(provider.ref_posts, [])
            self.assertEqual(provider.ref_deletes, [])

    def test_pr_branch_head_drift_is_planted_negative_control(self) -> None:
        provider = ClaimProvider(self.head)
        provider.refs[f"refs/heads/{BRANCH}"] = "c" * 40
        outcomes = self.sweep(provider)
        self.assertEqual(outcomes[0]["class"], "head_drift")
        self.assertEqual(outcomes[0]["action"], "skipped")
        self.assert_untouched(provider)

    def test_dead_claim_is_adopted_onto_existing_branch_and_pr_via_repair_ceremony(self) -> None:
        provider = ClaimProvider(self.head)
        outcomes = self.sweep(provider)
        self.assertEqual(len(outcomes), 1)
        outcome = outcomes[0]
        self.assertEqual(outcome["action"], "adopted")
        self.assertEqual(outcome["session_id"], self.session_id)
        self.assertEqual(outcome["attempt"], 1)
        receipt = json.loads(Path(outcome["repair_receipt_path"]).read_text())
        self.assertEqual(receipt["issue_subject"], SUBJECT)
        self.assertEqual(receipt["pr_number"], 44)
        self.assertEqual(receipt["head_sha"], self.head)
        self.assertEqual(receipt["failed_workflow_run"]["id"], 777)
        events = [json.loads(line) for line in self.events_path.read_text().splitlines()]
        self.assertEqual(len([item for item in events if item["type"] == "repair_receipt"]), 1)
        self.assertIn(f"refs/heads/{BRANCH}", provider.refs)
        self.assertEqual(provider.ref_deletes, [])
        self.assertEqual(provider.body_patches, 0)
        self.assertEqual(noodles.parse_issue_contract(self.issue_state_body(provider))["state"], "awaiting_land")

    def test_exhausted_adoption_fails_back_to_release_terminal_state(self) -> None:
        for index in range(noodles.REPAIR_MAX_ATTEMPTS):
            self.append_event(
                "2026-08-29T00:00:01Z",
                event_type="repair_receipt",
                payload={"issue_subject": SUBJECT, "pr_number": 44, "head_sha": f"{index + 1:040x}"},
            )
        provider = ClaimProvider(self.head)
        outcomes = self.sweep(provider)
        self.assertEqual(len(outcomes), 1)
        outcome = outcomes[0]
        self.assertEqual(outcome["action"], "released")
        self.assertIn("attempts exhausted", outcome["adoption_blocker"])
        preserved = f"progress-33-{self.head[:12]}"
        self.assertEqual(outcome["preserved_branch"], preserved)
        self.assertEqual(provider.refs, {f"refs/heads/{preserved}": self.head})
        self.assertEqual(provider.ref_deletes, [f"refs/heads/{BRANCH}"])
        self.assertEqual(noodles.parse_issue_contract(self.issue_state_body(provider))["state"], "ready")
        self.assertEqual(outcome["required_check"], "verify")
        self.assertEqual(outcome["failed_workflow_run"]["id"], 777)
        self.assertEqual(outcome["failed_job"]["name"], "candidate-self-tests")
        written = json.loads(Path(outcome["release_receipt_path"]).read_text())
        self.assertEqual(written["preserved_branch"], preserved)
        self.assertEqual(written["required_check"], "verify")

    def test_release_without_session_readmits_through_the_normal_ceremony(self) -> None:
        self.drop_session()
        provider = ClaimProvider(self.head)
        outcomes = self.sweep(provider)
        self.assertEqual(outcomes[0]["action"], "released")
        self.assertIn("no session ledger entry", outcomes[0]["adoption_blocker"])
        self.assertNotIn(f"refs/heads/{BRANCH}", provider.refs)
        candidate = self.root / ".noodle" / "orders-next.candidate.json"
        candidate.write_text(json.dumps({
            "orders": [{
                "id": SUBJECT,
                "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next"}],
            }]
        }))
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(brief["claims"], [{
            "subject": SUBJECT,
            "status": "claimed",
            "meaning": skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["claimed"],
            "branch": BRANCH,
            "head": MAIN_HEAD,
            "lane": "gha-runtime",
            "checkout": issue_contract.EPHEMERAL_CHECKOUT,
            "target": REPOSITORY,
            "base_sha": MAIN_HEAD,
            "runtime": "shell",
            "evidence": "github-only-v1",
            "write_boundary": [],
        }])
        published = json.loads((self.root / ".noodle" / "orders-next.json").read_text())["orders"]
        self.assertEqual([item["id"] for item in published], [SUBJECT])
        self.assertEqual(provider.refs[f"refs/heads/{BRANCH}"], MAIN_HEAD)

    def test_green_pr_dead_claim_is_held_with_no_provider_mutation(self) -> None:
        self.drop_session()
        provider = ClaimProvider(self.head, failed=False)
        outcomes = self.sweep(provider)
        self.assertEqual(outcomes[0]["action"], "held")
        self.assertIn("no completed failed workflow run", outcomes[0]["reason"])
        self.assert_untouched(provider)

    def test_salvage_collision_at_foreign_head_fails_closed(self) -> None:
        self.drop_session()
        provider = ClaimProvider(self.head)
        preserved = f"progress-33-{self.head[:12]}"
        provider.refs[f"refs/heads/{preserved}"] = "d" * 40
        outcomes = self.sweep(provider)
        self.assertEqual(outcomes[0]["action"], "held")
        self.assertIn(preserved, outcomes[0]["reason"])
        self.assertIn(f"refs/heads/{BRANCH}", provider.refs)
        self.assertEqual(provider.ref_deletes, [])
        self.assertEqual(provider.body_patches, 0)
        self.assertEqual(noodles.parse_issue_contract(self.issue_state_body(provider))["state"], "awaiting_land")

    def test_in_flight_release_residue_is_resumed_to_completion(self) -> None:
        self.drop_session()
        provider = ClaimProvider(self.head, contract_state="ready")
        preserved = f"progress-33-{self.head[:12]}"
        provider.refs[f"refs/heads/{preserved}"] = self.head
        records = self.snapshot(provider)
        self.assertEqual(records[0]["class"], "released_residue")
        outcomes = self.sweep(provider)
        self.assertEqual(outcomes[0]["action"], "released")
        self.assertEqual(provider.refs, {f"refs/heads/{preserved}": self.head})
        self.assertEqual(noodles.parse_issue_contract(self.issue_state_body(provider))["state"], "ready")

    def test_ready_claim_without_salvage_receipt_is_never_released(self) -> None:
        self.drop_session()
        provider = ClaimProvider(self.head, contract_state="ready")
        outcomes = self.sweep(provider)
        self.assertEqual(outcomes[0]["class"], "not_awaiting_land")
        self.assertEqual(outcomes[0]["action"], "skipped")
        self.assertIn(f"refs/heads/{BRANCH}", provider.refs)
        self.assertEqual(provider.ref_deletes, [])
        self.assertEqual(provider.body_patches, 0)


if __name__ == "__main__":
    unittest.main()
