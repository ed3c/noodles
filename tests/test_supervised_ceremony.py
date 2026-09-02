"""Physical controls for the repository-owned supervised runner and ceremony entrypoints (ed3c/noodles#141).

No live provider call happens here: every provider readback is a planted fake, every daemon
generation is a stub child, and every heal runs against a real local git pair. The planted
negatives are a salvage push that must fail before any reset, a lease held by a live pid, a
dirty control checkout, a rejected commit whose staged paths must disappear, a conflicting
rebase that must leave no in-progress state, and a run whose head is not the branch tip.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

import daemon_lease
import noodles
from tests.support import CANDIDATE_ROOT, cmd, control_checkout_fixture

DEAD_PID = 4194304
IDENTITY = ("ed3c", "ed3c@users.noreply.github.com")
TIP_SHA = "a" * 40
STALE_SHA = "b" * 40


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def head(root: Path) -> str:
    return cmd(["git", "rev-parse", "HEAD"], root)


def fake_gh_api(refs: dict[str, str], runs: list[dict[str, object]], single: dict[str, object] | None = None):
    def call(endpoint: str, **_kwargs: object) -> object:
        for branch, sha in refs.items():
            if endpoint.endswith(f"git/ref/heads/{branch}"):
                return {"object": {"sha": sha}}
        if "/actions/runs?" in endpoint:
            return {"workflow_runs": runs}
        if "/actions/runs/" in endpoint:
            return single
        raise AssertionError(f"unexpected endpoint {endpoint}")

    return call


def workflow_run(run_id: int, head_sha: str, attempt: int = 1, name: str = "verify") -> dict[str, object]:
    return {
        "id": run_id,
        "name": name,
        "path": ".github/workflows/verify.yml",
        "event": "pull_request_target",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "topic",
        "head_sha": head_sha,
        "html_url": f"https://example.invalid/{run_id}",
        "workflow_id": 1,
        "run_attempt": attempt,
        "pull_requests": [],
    }


class ControlCheckoutFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp, self.control, self.provider = control_checkout_fixture()
        self.addCleanup(self.temp.cleanup)

    def heal(self, **kwargs: object) -> dict[str, object]:
        return noodles.heal_control_checkout(self.control, "main", **kwargs)

    def provider_head(self) -> str:
        return cmd(["git", "rev-parse", "main"], self.provider)

    def commit_on_control(self, name: str, message: str) -> str:
        write(self.control / name, message + "\n")
        cmd(["git", "add", name], self.control)
        cmd(["git", "commit", "-q", "-m", message], self.control)
        return head(self.control)

    def plant_pre_receive_failure(self) -> None:
        hook = self.provider / ".git" / "hooks" / "pre-receive"
        write(hook, "#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)


class HealControlCheckoutTests(ControlCheckoutFixture):
    def test_merge_only_divergence_resets_losslessly(self) -> None:
        """A daemon-made merge over an already-pushed branch carries no unique content, so the reset is lossless."""
        cmd(["git", "checkout", "-q", "-b", "feat"], self.control)
        content_sha = self.commit_on_control("feature.txt", "feature")
        cmd(["git", "push", "-q", "origin", "feat"], self.control)
        cmd(["git", "checkout", "-q", "main"], self.control)
        cmd(["git", "merge", "-q", "--no-ff", "-m", "daemon merge", "feat"], self.control)
        self.assertNotEqual(head(self.control), self.provider_head())

        receipt = self.heal()

        self.assertIn("lossless_reset", receipt["actions"])
        self.assertEqual(receipt["salvage_ref"], "")
        self.assertEqual(head(self.control), self.provider_head())
        self.assertIn("origin/feat", cmd(["git", "branch", "-r", "--contains", content_sha], self.control))

    def test_unsaved_content_is_salvage_pushed_before_reset(self) -> None:
        local_tip = self.commit_on_control("unsaved.txt", "unlanded work")

        receipt = self.heal()

        self.assertEqual(receipt["actions"][:2], ["salvage_push", "lossless_reset"])
        self.assertTrue(str(receipt["salvage_ref"]).startswith("salvage-main-"))
        self.assertEqual(cmd(["git", "rev-parse", str(receipt["salvage_ref"])], self.provider), local_tip)
        self.assertEqual(head(self.control), self.provider_head())

    def test_failed_salvage_push_refuses_the_reset(self) -> None:
        """Planted negative: when the lineage cannot be made safe remotely, the bytes must survive locally."""
        local_tip = self.commit_on_control("unsaved.txt", "unlanded work")
        self.plant_pre_receive_failure()

        with self.assertRaises(noodles.GateError):
            self.heal()

        self.assertEqual(head(self.control), local_tip)

    def test_refusing_salvage_never_resets(self) -> None:
        local_tip = self.commit_on_control("unsaved.txt", "unlanded work")

        with self.assertRaisesRegex(noodles.GateError, "unsaved content commits"):
            self.heal(salvage_push=False)

        self.assertEqual(head(self.control), local_tip)

    def test_behind_control_checkout_fast_forwards(self) -> None:
        cmd(["git", "commit", "-q", "--allow-empty", "-m", "landed elsewhere"], self.provider)

        receipt = self.heal()

        self.assertIn("fast_forward", receipt["actions"])
        self.assertEqual(head(self.control), self.provider_head())

    def test_dirty_control_checkout_fails_closed(self) -> None:
        write(self.control / "scratch.txt", "residue\n")

        with self.assertRaisesRegex(noodles.GateError, "dirty control checkout"):
            self.heal()

    def test_live_pid_lease_fails_closed(self) -> None:
        write(self.control / daemon_lease.LOCK_RELATIVE, f"{os.getpid()}\n")

        with self.assertRaisesRegex(noodles.GateError, "is alive"):
            self.heal()

    def test_stale_lease_clearing_cures_the_matching_status_ghost(self) -> None:
        write(self.control / daemon_lease.LOCK_RELATIVE, f"{DEAD_PID}\n")
        write(self.control / daemon_lease.STATUS_RELATIVE, json.dumps({"loop_state": "running", "cycles": 7}))

        receipt = self.heal()

        self.assertEqual(receipt["actions"], ["cleared_stale_lease", "cured_status_ghost"])
        self.assertFalse((self.control / daemon_lease.LOCK_RELATIVE).exists())
        status = json.loads((self.control / daemon_lease.STATUS_RELATIVE).read_text(encoding="utf-8"))
        self.assertEqual(status, {"loop_state": "idle", "cycles": 7})

    def test_idle_status_without_lease_is_left_alone(self) -> None:
        write(self.control / daemon_lease.STATUS_RELATIVE, json.dumps({"loop_state": "idle"}))

        self.assertEqual(self.heal()["actions"], [])


class RateLimitCooldownTests(unittest.TestCase):
    def test_full_primary_bucket_classifies_as_a_secondary_burst(self) -> None:
        payload = {"resources": {"core": {"remaining": 4000, "reset": 10_000_000}}}

        self.assertEqual(noodles.rate_limit_cooldown(payload, 0.0), noodles.SECONDARY_BURST_COOLDOWN_SECONDS)

    def test_exhausted_bucket_waits_past_reset(self) -> None:
        payload = {"resources": {"core": {"remaining": 0, "reset": 1_000_300}}}

        self.assertEqual(noodles.rate_limit_cooldown(payload, 1_000_000.0), 360.0)

    def test_absurd_reset_falls_back_to_a_bounded_wait(self) -> None:
        payload = {"resources": {"core": {"remaining": 0, "reset": 0}}}

        self.assertEqual(noodles.rate_limit_cooldown(payload, 1_000_000.0), noodles.RATE_LIMIT_COOLDOWN_FALLBACK_SECONDS)

    def test_malformed_readback_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "resources.core"):
            noodles.rate_limit_cooldown({"resources": {}}, 0.0)


class SupervisedGenerationTests(ControlCheckoutFixture):
    def child(self, source: str) -> list[str]:
        return [sys.executable, "-c", source]

    def test_generation_that_exits_on_its_own_is_reported_as_exited(self) -> None:
        outcome = noodles.run_supervised_generation(
            self.control,
            self.child("print('daemon died: rate limit', flush=True)\nraise SystemExit(1)"),
            wedge_seconds=30.0,
            rotate_after_seconds=30.0,
        )

        self.assertEqual((outcome["reason"], outcome["returncode"]), ("exited", 1))
        self.assertIn("rate limit", outcome["tail"])

    def test_silent_generation_is_terminated_at_the_wedge_deadline(self) -> None:
        """Planted wedge: a live process that stops writing must not hold the fleet forever."""
        outcome = noodles.run_supervised_generation(
            self.control,
            self.child("import time\nprint('up', flush=True)\ntime.sleep(120)"),
            wedge_seconds=2.0,
            rotate_after_seconds=120.0,
        )

        self.assertEqual(outcome["reason"], "wedge")
        self.assertLess(outcome["seconds"], 30.0)

    def test_declared_quota_wait_survives_the_ordinary_wedge_deadline_but_silence_alone_never_does(self) -> None:
        """ed3c/noodles#291 - both directions: the 13:20 generation died with no stderr because a
        provider-ordered sleep was indistinguishable from a hang. Declaring the wait is the whole
        difference, so a child that declares nothing must still be killed on the same clock."""
        declared = self.child(
            "import time\n"
            "print('NOODLES_GH_QUOTA_WAIT: gh api issues deferred before issuing; core remaining=0 "
            "floor=25; recoverable-wait 8s until 2026-09-01T09:00:00Z', flush=True)\n"
            "time.sleep(6)\n"
        )
        silent = self.child("import time\nprint('up', flush=True)\ntime.sleep(6)")

        waited = noodles.run_supervised_generation(self.control, declared, wedge_seconds=2.0, rotate_after_seconds=120.0)
        killed = noodles.run_supervised_generation(self.control, silent, wedge_seconds=2.0, rotate_after_seconds=120.0)

        self.assertEqual(waited["reason"], "exited")
        self.assertEqual(waited["declared_quota_wait"], 8.0)
        self.assertGreater(waited["seconds"], 4.0)
        self.assertEqual(killed["reason"], "wedge")
        self.assertEqual(killed["declared_quota_wait"], 0.0)
        self.assertLess(killed["seconds"], waited["seconds"])

    def test_cycle_status_separates_a_quota_wait_from_a_failure_and_from_a_clean_exit(self) -> None:
        def refuse() -> object:
            self.fail("a declared quota wait carries its own reset; no live bucket read is admitted")

        declared = {"returncode": 1, "reason": "exited", "tail": "", "declared_quota_wait": 240.0}
        legacy = {"returncode": 1, "reason": "exited", "tail": "daemon died: primary rate limit", "declared_quota_wait": 0.0}
        broken = {"returncode": 2, "reason": "exited", "tail": "traceback", "declared_quota_wait": 0.0}
        clean = {"returncode": 0, "reason": "exited", "tail": "clean stop", "declared_quota_wait": 0.0}

        self.assertEqual(noodles.cycle_status(declared, refuse, 180.0), ("quota_wait", 240.0))
        self.assertEqual(
            noodles.cycle_status(legacy, lambda: {"resources": {"core": {"remaining": 0, "reset": 1_000_300}}}, 180.0)[0],
            "quota_wait",
        )
        self.assertEqual(noodles.cycle_status(broken, refuse, 180.0), ("failed", 180.0))
        self.assertEqual(noodles.cycle_status(clean, refuse, 180.0), ("ok", 0.0))
        # constraint: ed3c/noodles#323 - stays a strict equality, and this is the measured reason
        # constraint: rather than the assumed one. It looks like the ed3c/noodles#285 trusted-transition
        # constraint: deadlock (main's copy of this module judging a candidate that adds a status), but
        # constraint: `.github/workflows/verify.yml` sets PYTHONPATH to `.trusted`, so a trusted module
        # constraint: imports the TRUSTED engine and reads the candidate only as data through
        # constraint: CANDIDATE_ROOT. This line therefore judges main's own vocabulary against main's
        # constraint: own literal and can never deadlock a candidate. Physically confirmed:
        # constraint: `./noodles verify --trusted-preview` on the candidate that added
        # constraint: `struggle_detected` reported would_red=[]. Keep it exact - a floor here would
        # constraint: stop catching an accidentally added status and buy nothing.
        self.assertEqual(sorted(noodles.CYCLE_STATUS_MEANINGS), ["failed", "ok", "quota_wait", "struggle_detected"])

    def test_supervise_receipt_records_the_quota_wait_status_and_backs_off_until_reset(self) -> None:
        slept: list[float] = []
        receipts = noodles.supervise(
            self.control,
            "http://127.0.0.1:3210",
            generations=1,
            child_argv=self.child(
                "print('NOODLES_GH_QUOTA_WAIT: gh api issues deferred before issuing; core remaining=0 "
                "floor=25; recoverable-wait 240s until 2026-09-01T09:00:00Z', flush=True)\n"
                "raise SystemExit(75)\n"
            ),
            sleep_fn=slept.append,
            rate_limit_fn=lambda: self.fail("a declared quota wait must not spend a call reading the bucket"),
        )

        self.assertEqual((receipts[0]["status"], receipts[0]["cooldown"]), ("quota_wait", 240.0))
        self.assertEqual(receipts[0]["meaning"], noodles.CYCLE_STATUS_MEANINGS["quota_wait"])
        self.assertEqual(slept, [240.0])
        ledger = (self.control / noodles.SUPERVISE_LOG_RELATIVE).read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(ledger[-1])["status"], "quota_wait")

    STRUGGLE_SIGNATURE = "controls=[verify] diagnostics=[repository verification failed]"

    def declaring_child(self, *, subject: str, tail: str = "raise SystemExit(0)\n") -> list[str]:
        line = (
            f"NOODLES_STRUGGLE_DETECTED: subject {subject} attempts 3 reason same_signature "
            f"signature {self.STRUGGLE_SIGNATURE}"
        )
        return self.child(f"print({line!r}, flush=True)\n{tail}")

    def test_cycle_status_separates_a_declared_struggle_from_a_failure_a_wait_and_a_clean_exit(self) -> None:
        """ed3c/noodles#323 - the status is a sibling of quota_wait, never a shade of `failed`, and
        never collapsed into `ok`: a generation that stopped a struggling subject cleanly exits zero,
        which is exactly how nineteen no-evidence cycles read as progress."""
        def refuse() -> object:
            self.fail("a declared struggle carries no provider wait; no live bucket read is admitted")

        struggle = [{"subject": "ed3c/noodles#900", "attempts": 3, "reason": "same_signature", "signature": self.STRUGGLE_SIGNATURE}]
        clean_hold = {"returncode": 0, "reason": "exited", "tail": "", "declared_quota_wait": 0.0, "declared_struggles": struggle}
        failed_hold = {"returncode": 1, "reason": "exited", "tail": "", "declared_quota_wait": 0.0, "declared_struggles": struggle}
        no_hold = {"returncode": 1, "reason": "exited", "tail": "", "declared_quota_wait": 0.0, "declared_struggles": []}

        self.assertEqual(noodles.cycle_status(clean_hold, refuse, 180.0), ("struggle_detected", 180.0))
        self.assertEqual(noodles.cycle_status(failed_hold, refuse, 180.0), ("struggle_detected", 180.0))
        self.assertEqual(noodles.cycle_status(no_hold, refuse, 180.0), ("failed", 180.0))
        self.assertIn("struggle_detected", noodles.CYCLE_STATUS_MEANINGS)
        self.assertNotEqual(
            noodles.CYCLE_STATUS_MEANINGS["struggle_detected"], noodles.CYCLE_STATUS_MEANINGS["failed"]
        )

    def test_supervise_receipt_records_the_struggle_status_and_names_the_repeated_signature(self) -> None:
        slept: list[float] = []
        receipts = noodles.supervise(
            self.control,
            "http://127.0.0.1:3210",
            generations=1,
            child_argv=self.declaring_child(subject="ed3c/noodles#900"),
            backoff_seconds=90.0,
            sleep_fn=slept.append,
            rate_limit_fn=lambda: self.fail("a declared struggle must not spend a call reading the bucket"),
        )

        self.assertEqual((receipts[0]["status"], receipts[0]["cooldown"]), ("struggle_detected", 90.0))
        self.assertEqual(receipts[0]["meaning"], noodles.CYCLE_STATUS_MEANINGS["struggle_detected"])
        self.assertEqual(receipts[0]["declared_struggles"], [{
            "subject": "ed3c/noodles#900",
            "attempts": 3,
            "reason": "same_signature",
            "signature": self.STRUGGLE_SIGNATURE,
        }])
        ledger = json.loads((self.control / noodles.SUPERVISE_LOG_RELATIVE).read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(ledger["status"], "struggle_detected")
        self.assertEqual(ledger["declared_struggles"][0]["signature"], self.STRUGGLE_SIGNATURE)

    def test_a_generation_that_never_declares_carries_no_struggle_and_keeps_its_ordinary_status(self) -> None:
        """Planted negative control - the seam must stay silent unless a struggle was declared, or
        every ordinary failure would arrive dressed as an exhausted lane."""
        outcome = noodles.run_supervised_generation(
            self.control,
            self.child("print('repair: attempt 1 of 3 failed', flush=True)\nraise SystemExit(1)"),
            wedge_seconds=30.0,
            rotate_after_seconds=30.0,
        )

        self.assertEqual(outcome["declared_struggles"], [])
        self.assertEqual(noodles.cycle_status(outcome, lambda: self.fail("no bucket read"), 180.0), ("failed", 180.0))

    def test_a_declared_hold_lets_other_subjects_finish_but_never_licenses_silence(self) -> None:
        """Both directions, mirroring ed3c/noodles#291 by contrast. A quota wait is provider-ordered
        SILENCE and earns a reprieve from the wedge deadline. A struggle hold is not silence: the
        generation drops one subject and keeps working the others, so it must reach its own exit
        untouched - and a generation that declares a hold and then goes quiet is still killed on the
        ordinary clock, because the hold was never a licence to stop producing output."""
        continuing = noodles.run_supervised_generation(
            self.control,
            self.declaring_child(
                subject="ed3c/noodles#900",
                tail="import time\nfor _ in range(4):\n    print('subject ed3c/noodles#901 progressing', flush=True)\n    time.sleep(0.5)\nraise SystemExit(0)\n",
            ),
            wedge_seconds=2.0,
            rotate_after_seconds=120.0,
        )
        silent = noodles.run_supervised_generation(
            self.control,
            self.declaring_child(subject="ed3c/noodles#900", tail="import time\ntime.sleep(6)\n"),
            wedge_seconds=2.0,
            rotate_after_seconds=120.0,
        )

        self.assertEqual(continuing["reason"], "exited")
        self.assertEqual(continuing["returncode"], 0)
        self.assertIn("ed3c/noodles#901 progressing", continuing["tail"])
        self.assertEqual(len(continuing["declared_struggles"]), 1)
        self.assertEqual(silent["reason"], "wedge")
        self.assertEqual(len(silent["declared_struggles"]), 1)
        self.assertLess(silent["seconds"], continuing["seconds"] + 4.0)

    def test_chatty_generation_is_bounded_by_the_rotation_deadline(self) -> None:
        outcome = noodles.run_supervised_generation(
            self.control,
            self.child("import time\nwhile True:\n    print('tick', flush=True)\n    time.sleep(0.2)"),
            wedge_seconds=120.0,
            rotate_after_seconds=2.0,
        )

        self.assertEqual(outcome["reason"], "rotation")
        self.assertLess(outcome["seconds"], 30.0)

    def test_rotation_env_refuses_a_credential_that_is_not_a_single_token(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "single-token"):
            noodles.rotation_env({}, "printf 'two tokens'")

    def test_rotation_env_exports_the_machine_local_token(self) -> None:
        env = noodles.rotation_env({}, "printf 'ghs_planted'")

        self.assertEqual((env["GH_TOKEN"], env["GITHUB_TOKEN"], env["NOODLE_NO_BROWSER"]), ("ghs_planted", "ghs_planted", "1"))

    def test_rate_limited_generation_cools_down_from_the_live_bucket(self) -> None:
        slept: list[float] = []
        receipts = noodles.supervise(
            self.control,
            "http://127.0.0.1:3210",
            generations=1,
            child_argv=self.child("print('daemon died: primary rate limit', flush=True)\nraise SystemExit(1)"),
            sleep_fn=slept.append,
            rate_limit_fn=lambda: {"resources": {"core": {"remaining": 0, "reset": time.time() + 240}}},
        )

        self.assertEqual(len(receipts), 1)
        self.assertGreater(receipts[0]["cooldown"], 250.0)
        self.assertEqual(slept, [receipts[0]["cooldown"]])
        self.assertEqual(receipts[0]["heal"]["local_head_after"], self.provider_head())
        ledger = (self.control / noodles.SUPERVISE_LOG_RELATIVE).read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(ledger[-1])["generation"], 1)

    def test_healthy_generation_is_restarted_without_a_cooldown(self) -> None:
        slept: list[float] = []
        receipts = noodles.supervise(
            self.control,
            "http://127.0.0.1:3210",
            generations=2,
            child_argv=self.child("print('clean stop', flush=True)"),
            sleep_fn=slept.append,
            rate_limit_fn=lambda: self.fail("a clean exit must not read the rate limit bucket"),
        )

        self.assertEqual([receipt["cooldown"] for receipt in receipts], [0.0, 0.0])
        self.assertEqual(slept, [])

    def test_heal_failure_backs_off_instead_of_spawning(self) -> None:
        write(self.control / daemon_lease.LOCK_RELATIVE, f"{os.getpid()}\n")
        slept: list[float] = []

        receipts = noodles.supervise(
            self.control,
            "http://127.0.0.1:3210",
            generations=1,
            child_argv=self.child("raise AssertionError('daemon must not be spawned over a live lease')"),
            sleep_fn=slept.append,
            backoff_seconds=7.0,
        )

        self.assertIn("is alive", receipts[0]["error"])
        self.assertEqual(slept, [7.0])


class CeremonyGitTests(ControlCheckoutFixture):
    def identity_of_head(self) -> tuple[str, str, str, str]:
        return tuple(cmd(["git", "log", "-1", "--format=%an%n%ae%n%cn%n%ce"], self.control).splitlines())

    def test_commit_applies_the_repository_identity_over_a_planted_foreign_config(self) -> None:
        cmd(["git", "config", "user.name", "planted-foreign"], self.control)
        cmd(["git", "config", "user.email", "planted@example.invalid"], self.control)
        write(self.control / "atom.txt", "work\n")

        receipt = noodles.ceremony_commit(self.control, "why this atom exists", ["atom.txt"])

        self.assertEqual(receipt["head"], head(self.control))
        self.assertEqual(self.identity_of_head(), IDENTITY + IDENTITY)

    def test_rejected_commit_unstages_exactly_the_paths_it_staged(self) -> None:
        """Planted negative: a rejected commit must not leave its paths in the shared index."""
        write(self.control / "other.txt", "someone else\n")
        cmd(["git", "add", "other.txt"], self.control)
        hook = self.control / ".git" / "hooks" / "pre-commit"
        write(hook, "#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        write(self.control / "atom.txt", "work\n")

        with self.assertRaisesRegex(noodles.GateError, "ceremony commit rejected"):
            noodles.ceremony_commit(self.control, "why this atom exists", ["atom.txt"])

        self.assertEqual(cmd(["git", "diff", "--cached", "--name-only"], self.control), "other.txt")

    def test_empty_message_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "non-empty message"):
            noodles.ceremony_commit(self.control, "   ", [])

    def test_rebase_applies_the_repository_identity(self) -> None:
        cmd(["git", "checkout", "-q", "-b", "topic"], self.control)
        self.commit_on_control("topic.txt", "topic work")
        cmd(["git", "checkout", "-q", "main"], self.control)
        self.commit_on_control("main.txt", "main work")
        cmd(["git", "checkout", "-q", "topic"], self.control)

        receipt = noodles.ceremony_rebase(self.control, "main")

        self.assertNotEqual(receipt["head"], receipt["before"])
        self.assertEqual(self.identity_of_head()[2:], IDENTITY)

    def test_conflicting_rebase_aborts_and_leaves_no_in_progress_state(self) -> None:
        cmd(["git", "checkout", "-q", "-b", "topic"], self.control)
        before = self.commit_on_control("clash.txt", "topic side")
        cmd(["git", "checkout", "-q", "main"], self.control)
        self.commit_on_control("clash.txt", "main side")
        cmd(["git", "checkout", "-q", "topic"], self.control)

        with self.assertRaisesRegex(noodles.GateError, "aborted"):
            noodles.ceremony_rebase(self.control, "main")

        self.assertEqual(head(self.control), before)
        self.assertFalse(Path(cmd(["git", "rev-parse", "--git-path", "rebase-merge"], self.control)).exists())


class CeremonyProviderTests(ControlCheckoutFixture):
    def test_run_selects_the_newest_attempt_for_the_named_workflow(self) -> None:
        call = fake_gh_api(
            {"topic": TIP_SHA},
            [workflow_run(1, TIP_SHA, attempt=1), workflow_run(2, TIP_SHA, attempt=2), workflow_run(3, TIP_SHA, name="land")],
        )

        receipt = noodles.ceremony_run(call, "ed3c/noodles", "topic", "verify")

        self.assertEqual((receipt["branch_tip"], receipt["run"]["id"]), (TIP_SHA, 2))

    def test_missing_workflow_run_fails_closed(self) -> None:
        call = fake_gh_api({"topic": TIP_SHA}, [workflow_run(3, TIP_SHA, name="land")])

        with self.assertRaisesRegex(noodles.GateError, "no 'verify' workflow run"):
            noodles.ceremony_run(call, "ed3c/noodles", "topic", "verify")

    def test_rerun_refuses_a_run_whose_head_is_not_the_branch_tip(self) -> None:
        """Planted negative: rerunning a stale head cancels the live head's run under the per-PR concurrency group."""
        call = fake_gh_api({"topic": TIP_SHA}, [], single={"id": 9, "name": "verify", "head_sha": STALE_SHA, "head_branch": "topic"})

        with self.assertRaisesRegex(noodles.GateError, "rerun refused"):
            noodles.ceremony_rerun(self.control, call, "ed3c/noodles", "topic", run_id=9)

    def test_rerun_dry_run_admits_the_live_head_without_spending_the_rerun(self) -> None:
        call = fake_gh_api({"topic": TIP_SHA}, [], single={"id": 9, "name": "verify", "head_sha": TIP_SHA, "head_branch": "topic"})

        receipt = noodles.ceremony_rerun(self.control, call, "ed3c/noodles", "topic", run_id=9, dry_run=True)

        self.assertEqual((receipt["run"]["id"], receipt["dry_run"]), (9, True))

    def test_rerun_without_a_selector_fails_closed(self) -> None:
        call = fake_gh_api({"topic": TIP_SHA}, [])

        with self.assertRaisesRegex(noodles.GateError, "--workflow or --run-id"):
            noodles.ceremony_rerun(self.control, call, "ed3c/noodles", "topic")

    def test_paced_gh_routes_through_the_tracked_carrier(self) -> None:
        recorder = self.control / "fake-gh-bin" / "gh"
        write(recorder, "#!/usr/bin/env python3\nimport os, sys\nopen(os.environ['FAKE_GH_LOG'], 'w').write(' '.join(sys.argv[1:]))\n")
        recorder.chmod(0o755)
        log = self.control / "fake-gh.log"
        environment = dict(os.environ, NOODLES_GH_REAL_BIN=str(recorder), FAKE_GH_LOG=str(log))

        result = subprocess.run(
            [sys.executable, str(noodles.__file__), "--root", str(self.control), "ceremony", "gh", "--", "run", "rerun", "9"],
            cwd=str(self.control), env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.read_text(encoding="utf-8"), "run rerun 9")

    def test_missing_carrier_fails_closed(self) -> None:
        (self.control / noodles.GH_CARRIER_RELATIVE).unlink()

        with self.assertRaisesRegex(noodles.GateError, "carrier is missing"):
            noodles.paced_gh(self.control, ["api", "rate_limit"])


COMMITTED_FIXTURE = """def double(value):
    return value * 2


PAD_A = 1
PAD_B = 2
PAD_C = 3
PAD_D = 4
PAD_E = 5


def unrelated(value):
    return value
"""
PLANTED_FIXTURE = COMMITTED_FIXTURE.replace("return value * 2", "return value * 3")
UNRELATED_EDIT = "    return value + 1\n"


class CeremonyPlantTests(ControlCheckoutFixture):
    """ed3c/noodles#269 - the plant/unplant ritual on a file that also carries uncommitted work.

    This is the exact shape the incident had: the ritual every load-bearing control requires runs
    while the working tree already carries the atom's own edits to the same file, and the full-file
    revert takes both. The controls below prove the carrier moves only the plant's own hunk in both
    directions, by direct byte comparison rather than by reading a diff.
    """

    def setUp(self) -> None:
        super().setUp()
        self.fixture = self.control / "fixture.py"
        write(self.fixture, COMMITTED_FIXTURE)
        cmd(["git", "add", "fixture.py"], self.control)
        cmd(["git", "commit", "-q", "-m", "control fixture"], self.control)
        write(self.fixture, PLANTED_FIXTURE)
        self.patch = Path(self.temp.name) / "plant.patch"
        self.patch.write_text(
            subprocess.run(
                ["git", "diff", "--", "fixture.py"],
                cwd=self.control,
                capture_output=True,
                text=True,
                check=True,
            ).stdout,
            encoding="utf-8",
        )
        write(self.fixture, COMMITTED_FIXTURE)

    def add_unrelated_uncommitted_work(self) -> None:
        write(self.fixture, COMMITTED_FIXTURE.replace("    return value\n", UNRELATED_EDIT))

    def control_is_green(self) -> bool:
        """The control this ritual reds and greens: `double(2) == 4` against the live file.

        `-B` is load-bearing, not tidiness: the plant is a same-length edit applied within the same
        second, so a written `__pycache__` entry would be reused and the control would stay green
        against bytes that no longer exist. It also leaves no residue in the checkout.
        """
        return subprocess.run(
            [sys.executable, "-B", "-c", "import fixture; assert fixture.double(2) == 4"],
            cwd=self.control,
            capture_output=True,
            text=True,
        ).returncode == 0

    def test_round_trip_reds_and_greens_the_control_and_never_touches_co_resident_work(self) -> None:
        self.add_unrelated_uncommitted_work()
        before = self.fixture.read_bytes()
        self.assertTrue(self.control_is_green())

        planted = noodles.ceremony_plant(self.control, self.patch, reverse=False)

        self.assertEqual(planted["verb"], "plant")
        self.assertEqual(planted["paths"], ["fixture.py"])
        self.assertFalse(self.control_is_green())
        # constraint: ed3c/noodles#269 - direct byte comparison of the region the plant does not
        # constraint: name, not an inspection of a diff: the uncommitted edit must survive.
        self.assertIn(UNRELATED_EDIT, self.fixture.read_text(encoding="utf-8"))
        self.assertNotEqual(self.fixture.read_bytes(), before)

        reversed_receipt = noodles.ceremony_plant(self.control, self.patch, reverse=True)

        self.assertEqual(reversed_receipt["verb"], "unplant")
        self.assertTrue(self.control_is_green())
        self.assertEqual(self.fixture.read_bytes(), before)

    def test_planted_negative_a_reversal_whose_hunk_no_longer_applies_touches_nothing(self) -> None:
        self.add_unrelated_uncommitted_work()
        before = self.fixture.read_bytes()

        with self.assertRaisesRegex(noodles.GateError, "does not apply cleanly to this tree and nothing was touched"):
            noodles.ceremony_plant(self.control, self.patch, reverse=True)

        self.assertEqual(self.fixture.read_bytes(), before)
        self.assertTrue(self.control_is_green())

    def test_planted_negative_a_second_plant_over_an_applied_plant_is_refused(self) -> None:
        noodles.ceremony_plant(self.control, self.patch, reverse=False)
        before = self.fixture.read_bytes()

        with self.assertRaisesRegex(noodles.GateError, "does not apply cleanly"):
            noodles.ceremony_plant(self.control, self.patch, reverse=False)

        self.assertEqual(self.fixture.read_bytes(), before)

    def test_missing_patch_file_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "needs an existing patch file"):
            noodles.ceremony_plant(self.control, Path(self.temp.name) / "absent.patch", reverse=False)

    def test_the_full_file_revert_this_carrier_replaces_really_does_discard_co_resident_work(self) -> None:
        """The incident itself, reproduced: `git checkout --` is the failure mode the carrier exists for.

        Without this, "the carrier is safer" would be a claim about a failure nothing here observes.
        """
        self.add_unrelated_uncommitted_work()
        noodles.ceremony_plant(self.control, self.patch, reverse=False)
        self.assertIn(UNRELATED_EDIT, self.fixture.read_text(encoding="utf-8"))

        cmd(["git", "checkout", "--", "fixture.py"], self.control)

        self.assertEqual(self.fixture.read_text(encoding="utf-8"), COMMITTED_FIXTURE)
        self.assertNotIn(UNRELATED_EDIT, self.fixture.read_text(encoding="utf-8"))

    def test_the_ritual_step_names_the_carrier_as_the_admitted_path(self) -> None:
        # constraint: ed3c/noodles#269 - the executable existing is not the cure; the cure is that
        # constraint: the ritual's own documented step points at it, so the reversible form is the
        # constraint: one an agent reaches for first.
        skill = (CANDIDATE_ROOT / ".agents/skills/execute/SKILL.md").read_text(encoding="utf-8")
        step = next(line for line in skill.splitlines() if line.startswith("8. "))
        self.assertIn("./noodles ceremony plant --patch", step)
        self.assertIn("./noodles ceremony unplant --patch", step)
        self.assertIn("git checkout -- <file>", step)


if __name__ == "__main__":
    unittest.main()
