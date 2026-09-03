from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import codex_isolation
import noodles
from tests.support import CANDIDATE_ROOT, copy_tracked, write_fake_codex_stub

FIXTURES = Path(__file__).resolve().parent / "fixtures"
# constraint: ed3c/noodles#260 - the exact rule this atom deletes, kept HERE and nowhere in
# constraint: production so both directions of its mis-match can be shown against recorded provider
# constraint: bytes. The two planted negatives below are the verbatim failing inputs the acceptance
# constraint: asks for, and a candidate that reintroduces the pattern in production reds them.
DELETED_TRUNCATION_RE = re.compile(r"truncat|skill-context-budget", re.I)


PERMISSION_PROFILE_ARGS = [
    "--ignore-user-config",
    "-c",
    'approval_policy="never"',
    "-c",
    'default_permissions="noodles-cook"',
    "-c",
    'permissions.noodles-cook.extends=":workspace"',
    "-c",
    'permissions.noodles-cook.workspace_roots={"/Users/neon/noodles/.git"=true}',
    "-c",
    'permissions.noodles-cook.filesystem={":workspace_roots"={".agents/skills"="write"}}',
    "-c",
    "permissions.noodles-cook.network.enabled=true",
]


class CodexIsolationTests(unittest.TestCase):
    def mutated_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-codex-isolation-", ignore_cleanup_errors=True)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return temp, root

    def test_verify_repository_requires_isolated_codex_wrapper(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".noodle.toml"
        path.write_text(path.read_text(encoding="utf-8").replace('path = ".agents/bin"', 'path = "~/.codex"', 1), encoding="utf-8")
        result = noodles.verify_repository(root, CANDIDATE_ROOT)
        self.assertFalse(result["ok"])
        self.assertIn(".noodle.toml agents.codex.path must be '.agents/bin'", result["errors"])

    def test_verify_repository_requires_ignore_user_config_flag(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".noodle.toml"
        path.write_text(path.read_text(encoding="utf-8").replace('"--ignore-user-config", ', "", 1), encoding="utf-8")
        result = noodles.verify_repository(root, CANDIDATE_ROOT)
        self.assertFalse(result["ok"])
        self.assertIn(".noodle.toml agents.codex.args must include '--ignore-user-config'", result["errors"])

    SANDBOX_SHAPE_ARGS = (
        '["--ignore-user-config", "--sandbox", "workspace-write", "-c", "approval_policy=\\"never\\"", '
        '"-c", "sandbox_workspace_write.network_access=true", '
        '"-c", "sandbox_workspace_write.writable_roots=[\\"/Users/neon/noodles/.git\\"]"]'
    )
    PROFILE_SHAPE_ARGS = (
        '["--ignore-user-config", "-c", "approval_policy=\\"never\\"", '
        '"-c", "default_permissions=\\"noodles-cook\\"", '
        '"-c", "permissions.noodles-cook.extends=\\":workspace\\"", '
        '"-c", "permissions.noodles-cook.workspace_roots={\\"/Users/neon/noodles/.git\\"=true}", '
        '"-c", "permissions.noodles-cook.filesystem={\\":workspace_roots\\"={\\".agents/skills\\"=\\"write\\"}}", '
        '"-c", "permissions.noodles-cook.network.enabled=true"]'
    )

    def rewrite_args(self, root: Path, new_args: str) -> None:
        # constraint: shape-agnostic fixture (ed3c/noodles#193) - the staged
        # constraint: tests must hold on both sides of the #180/#172 flip, so
        # constraint: this replaces whatever args line the tracked file carries.
        import re as _re

        path = root / ".noodle.toml"
        text = path.read_text(encoding="utf-8")
        rewritten, count = _re.subn(r"(?m)^args = \[.*\]$", f"args = {new_args}", text, count=1)
        self.assertEqual(count, 1)
        path.write_text(rewritten, encoding="utf-8")

    def test_permissions_profile_shape_is_accepted_during_staging_window(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        self.rewrite_args(root, self.PROFILE_SHAPE_ARGS)
        result = noodles.verify_repository(root, CANDIDATE_ROOT)
        self.assertTrue(result["ok"], result["errors"])

    def test_neither_sandbox_shape_fails_closed(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        self.rewrite_args(root, '["--ignore-user-config", "-c", "approval_policy=\\"never\\""]')
        result = noodles.verify_repository(root, CANDIDATE_ROOT)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("noodles-cook" in error and "profile" in error for error in result["errors"]),
            result["errors"],
        )

    def test_partial_permissions_profile_fails_closed(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        partial = self.PROFILE_SHAPE_ARGS.replace(
            '"-c", "permissions.noodles-cook.filesystem={\\":workspace_roots\\"={\\".agents/skills\\"=\\"write\\"}}", ',
            "",
            1,
        )
        self.assertNotEqual(partial, self.PROFILE_SHAPE_ARGS)
        self.rewrite_args(root, partial)
        result = noodles.verify_repository(root, CANDIDATE_ROOT)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any(".agents/skills" in error or "profile" in error for error in result["errors"]),
            result["errors"],
        )

    def test_codex_agent_config_accepts_narrow_skill_permission_profile(self) -> None:
        config = {"agents": {"codex": {"path": ".agents/bin", "args": PERMISSION_PROFILE_ARGS}}}
        self.assertEqual(codex_isolation.validate_codex_agent_config(CANDIDATE_ROOT, config), [])

    def test_codex_agent_config_rejects_broader_agents_write(self) -> None:
        args = [value.replace('".agents/skills"="write"', '".agents"="write"') for value in PERMISSION_PROFILE_ARGS]
        config = {"agents": {"codex": {"path": ".agents/bin", "args": args}}}
        self.assertIn(
            ".noodle.toml agents.codex.args must grant write only to '.agents/skills' inside workspace roots",
            codex_isolation.validate_codex_agent_config(CANDIDATE_ROOT, config),
        )

    def test_codex_agent_config_rejects_legacy_sandbox_with_permission_profile(self) -> None:
        args = [*PERMISSION_PROFILE_ARGS, "--sandbox", "workspace-write"]
        config = {"agents": {"codex": {"path": ".agents/bin", "args": args}}}
        self.assertIn(
            ".noodle.toml agents.codex.args must not combine the permission profile with legacy sandbox settings",
            codex_isolation.validate_codex_agent_config(CANDIDATE_ROOT, config),
        )

    def test_wrapper_isolates_home_and_strips_forbidden_flag(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        fake_bin = Path(temp.name) / "fake-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        write_fake_codex_stub(fake_codex)
        user_home = Path(temp.name) / "user-home"
        (user_home / ".codex").mkdir(parents=True)
        (user_home / ".codex" / "auth.json").write_text('{"token":"fixture"}\n', encoding="utf-8")
        trace = Path(temp.name) / "trace.json"
        env = os.environ.copy()
        env["HOME"] = str(user_home)
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["NOODLES_CODEX_TRACE_FILE"] = str(trace)
        subprocess.run(
            [
                str(root / codex_isolation.CODEX_WRAPPER),
                "debug",
                "prompt-input",
                "use execute skill",
                codex_isolation.FORBIDDEN_FORWARD_ARG,
                "--ignore-user-config",
                *PERMISSION_PROFILE_ARGS[1:],
            ],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        receipt = json.loads(trace.read_text(encoding="utf-8"))
        self.assertNotIn(codex_isolation.FORBIDDEN_FORWARD_ARG, receipt["forwarded_argv"])
        self.assertEqual(receipt["forwarded_argv"][-len(PERMISSION_PROFILE_ARGS):], PERMISSION_PROFILE_ARGS)
        self.assertEqual(receipt["incoming_argv"][0:3], ["debug", "prompt-input", "use execute skill"])
        self.assertEqual(Path(receipt["isolated_home"]).resolve(), (root / codex_isolation.ISOLATED_HOME).resolve())
        self.assertEqual(Path(receipt["isolated_codex_home"]).resolve(), (root / codex_isolation.ISOLATED_CODEX_HOME).resolve())
        self.assertEqual(Path(receipt["auth_source"]).resolve(), (user_home / ".codex" / "auth.json").resolve())
        self.assertEqual(Path(receipt["auth_target"]).resolve(), (root / codex_isolation.ISOLATED_CODEX_HOME / "auth.json").resolve())

    def test_codex_surface_canary_rejects_injected_isolated_skill(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        for skill in ("control-cli", "control-noodle"):
            skill_root = root / ".agents" / "skills" / skill
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
        fake_bin = Path(temp.name) / "fake-bin"
        fake_bin.mkdir()
        write_fake_codex_stub(fake_bin / "codex")
        user_home = Path(temp.name) / "user-home"
        (user_home / ".codex").mkdir(parents=True)
        (user_home / ".codex" / "auth.json").write_text('{"token":"fixture"}\n', encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(user_home), "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}, clear=False):
            receipt = codex_isolation.codex_surface_canary(root, error_cls=RuntimeError)
            self.assertIn("schedule", receipt["schedule"]["skills"])
            planted = root / codex_isolation.ISOLATED_CODEX_HOME / "skills" / "user-only"
            planted.mkdir(parents=True)
            (planted / "SKILL.md").write_text("# user-only\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "isolated user-only skills"):
                codex_isolation.codex_surface_canary(root, error_cls=RuntimeError)


class NoodleResidueObserverTests(unittest.TestCase):
    """ed3c/noodles#313 - the zero-residue clause has never been evaluated, because the observer
    every lane runs (`git status --porcelain --untracked-files=all`) cannot see a `.noodle/` path at
    all: `.gitignore` carries `.noodle/*`. Both directions are asserted here - the blind observer
    stays silent on a planted residue that this one names, and this one stays silent on the ignored
    paths that are not runtime state, so it is neither `git status` under another name nor a check
    that reds on everything and gets turned off."""

    def tracked_copy(self) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-residue-observer-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return root

    def git_status_porcelain(self, root: Path) -> str:
        return subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root, text=True, stdout=subprocess.PIPE, check=True,
        ).stdout

    def test_a_planted_isolation_home_is_named_by_the_observer_and_invisible_to_git_status(self) -> None:
        root = self.tracked_copy()
        self.assertEqual(codex_isolation.noodle_runtime_residue(root, error_cls=RuntimeError), [])
        (root / codex_isolation.ISOLATED_HOME).mkdir(parents=True)
        self.assertEqual(self.git_status_porcelain(root), "")
        self.assertIn(codex_isolation.ISOLATED_HOME, codex_isolation.noodle_runtime_residue(root, error_cls=RuntimeError))

    def test_the_observer_names_a_written_file_under_an_ignored_directory(self) -> None:
        root = self.tracked_copy()
        auth = root / codex_isolation.ISOLATED_CODEX_HOME / "auth.json"
        auth.parent.mkdir(parents=True)
        auth.write_text("{}\n", encoding="utf-8")
        self.assertEqual(self.git_status_porcelain(root), "")
        self.assertIn(
            f"{codex_isolation.ISOLATED_CODEX_HOME}/auth.json",
            codex_isolation.noodle_runtime_residue(root, error_cls=RuntimeError),
        )

    def test_ignored_paths_outside_the_runtime_root_are_not_residue(self) -> None:
        root = self.tracked_copy()
        cache = root / "__pycache__"
        cache.mkdir()
        (cache / "noodles.cpython-314.pyc").write_bytes(b"\x00")
        self.assertEqual(self.git_status_porcelain(root), "")
        self.assertEqual(codex_isolation.noodle_runtime_residue(root, error_cls=RuntimeError), [])

    def test_the_observer_fails_closed_where_there_is_no_repository_to_observe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-residue-nonrepo-", ignore_cleanup_errors=True) as temp:
            with self.assertRaisesRegex(RuntimeError, "residue observer could not read git status"):
                codex_isolation.noodle_runtime_residue(Path(temp), error_cls=RuntimeError)

    def test_the_tracked_wrapper_writes_its_isolation_state_into_its_own_root_not_the_cwd(self) -> None:
        """The root cause, asserted directly: `.agents/bin/codex` resolves its repository root from
        its own `__file__`, so the wrapper a test invokes - not the cwd it is given - decides which
        tree gains `.noodle/codex-isolation/`. That is why `run_carrier`'s old `root=CANDIDATE_ROOT`
        default wrote into the live checkout while pointing its cwd wherever it liked."""
        root = self.tracked_copy()
        fake_bin = root.parent / "fake-bin"
        fake_bin.mkdir()
        write_fake_codex_stub(fake_bin / "codex")
        elsewhere = root.parent / "elsewhere"
        elsewhere.mkdir()
        before = codex_isolation.noodle_runtime_residue(CANDIDATE_ROOT, error_cls=RuntimeError)
        env = os.environ.copy()
        env["HOME"] = str(root.parent / "user-home")
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        subprocess.run(
            [str(root / codex_isolation.CODEX_WRAPPER), "debug", "prompt-input", "probe"],
            cwd=elsewhere, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        self.assertIn(codex_isolation.ISOLATED_HOME, codex_isolation.noodle_runtime_residue(root, error_cls=RuntimeError))
        self.assertEqual(codex_isolation.noodle_runtime_residue(CANDIDATE_ROOT, error_cls=RuntimeError), before)


class TypedTerminalStateTests(unittest.TestCase):
    """ed3c/noodles#260 - terminal state may be decided ONLY by the process exit status and the typed
    Codex lifecycle events; a substring of output text is payload and never a control signal.

    The fixtures are wire bytes, not shapes this suite invented. `codex-exec-turn-completed.jsonl` is
    a verbatim recording of one real `codex exec --json --sandbox read-only` run on codex-cli 0.149.0
    (recorded 2026-09-03 for this atom, prompt "Reply with exactly: ok", process exit status 0). The
    two `turn.failed` / stream-`error` fixtures are HAND-WRITTEN AND SYNTHETIC - the recorded run
    succeeded, and buying a real failure would have cost a second provider run - so they are marked
    synthetic in their own thread_ids and are used only for the transitions whose event NAMES the
    recorded run already proves the provider emits."""

    def events(self, name: str) -> list[dict]:
        return codex_isolation.parse_codex_events(
            (FIXTURES / name).read_text(encoding="utf-8"), error_cls=RuntimeError
        )

    def test_the_recorded_successful_run_carries_error_items_that_are_not_terminal(self) -> None:
        """The receipt at the centre of the atom: a turn that COMPLETED, carrying `error` items.

        This is why "an error appeared in the output" was never a terminal signal - the provider
        reports advisory notices through the same word. Only the typed terminal event decides."""
        events = self.events("codex-exec-turn-completed.jsonl")
        terminal = codex_isolation.codex_terminal_state(0, events)
        self.assertEqual(terminal["state"], "completed")
        self.assertEqual(terminal["source"], codex_isolation.CODEX_TURN_COMPLETED)
        notices = codex_isolation.codex_context_notices(events)
        self.assertTrue(notices, "the recorded run carries advisory notices")
        self.assertTrue(
            any("skills context budget" in notice["message"] for notice in notices),
            notices,
        )

    def test_planted_negative_the_deleted_rule_misses_the_real_context_budget_notice(self) -> None:
        """False-negative direction, verbatim: the pattern never matched the message it was for.

        The rule looked for `skill-context-budget`; the provider writes "skills context budget" with
        spaces. So the substring guard was silent on precisely the event it existed to catch, while
        the typed reader names it. Inverse edit that reds this: put the notice's own words into
        DELETED_TRUNCATION_RE."""
        events = self.events("codex-exec-turn-completed.jsonl")
        notice = next(
            item for item in codex_isolation.codex_context_notices(events)
            if "skills context budget" in item["message"]
        )
        self.assertEqual(DELETED_TRUNCATION_RE.findall(notice["message"]), [])
        # constraint: and the deeper half - even a HIT would not have been terminal. The stream that
        # constraint: carries this notice reads `completed`, so the guard was inferring control from
        # constraint: a message the provider emits on its way to success.
        self.assertEqual(codex_isolation.codex_terminal_state(0, events)["state"], "completed")

    def test_no_production_name_carries_the_deleted_pattern(self) -> None:
        """The acceptance clause "zero remaining bare-substring match for the same token", mechanised.

        Asserted on the module's namespace rather than by reading the diff, so a candidate that
        reintroduces the rule under any name reds here instead of passing review."""
        patterns = {
            name: value.pattern for name, value in vars(codex_isolation).items()
            if isinstance(value, re.Pattern)
        }
        self.assertNotIn("TRUNCATION_RE", vars(codex_isolation))
        offenders = {name: pattern for name, pattern in patterns.items() if DELETED_TRUNCATION_RE.search(pattern)}
        self.assertEqual(offenders, {}, offenders)

    def test_planted_negative_the_deleted_rule_fires_on_a_payload_that_only_says_truncate(self) -> None:
        """False-positive direction, verbatim: the input that hard-failed a healthy run.

        A skill whose own description contains the letters "truncat" was enough to raise. The typed
        decision reads the same stream as `completed`, because nothing in it is a terminal event."""
        payload = '{"name": "log-tools", "description": "truncate long logs"}'
        self.assertEqual(DELETED_TRUNCATION_RE.findall(payload), ["truncat"])
        events = [*self.events("codex-exec-turn-completed.jsonl")]
        events.insert(-1, {"type": "item.completed", "item": {"id": "item_planted", "type": "agent_message", "text": payload}})
        self.assertEqual(codex_isolation.codex_terminal_state(0, events)["state"], "completed")

    def test_a_typed_turn_failure_outranks_a_zero_exit_status(self) -> None:
        """The inversion a text reader gets backwards: the message says it completed; the turn failed."""
        events = self.events("codex-exec-turn-failed.jsonl")
        message = next(
            event["item"]["text"] for event in events
            if event.get("type") == "item.completed" and event["item"].get("type") == "agent_message"
        )
        self.assertEqual(DELETED_TRUNCATION_RE.findall(message), ["truncat"])
        terminal = codex_isolation.codex_terminal_state(0, events)
        self.assertEqual(terminal["state"], "failed")
        self.assertEqual(terminal["source"], codex_isolation.CODEX_TURN_FAILED)
        self.assertIn("synthetic fixture", terminal["detail"])

    def test_a_stream_level_error_is_terminal_even_with_no_turn_terminal(self) -> None:
        terminal = codex_isolation.codex_terminal_state(0, self.events("codex-exec-stream-error.jsonl"))
        self.assertEqual(terminal["state"], "failed")
        self.assertEqual(terminal["source"], codex_isolation.CODEX_STREAM_ERROR)

    def test_a_non_zero_exit_status_outranks_a_completed_turn(self) -> None:
        terminal = codex_isolation.codex_terminal_state(1, self.events("codex-exec-turn-completed.jsonl"))
        self.assertEqual(terminal["state"], "failed")
        self.assertEqual(terminal["source"], "process_exit")

    def test_a_process_that_has_not_exited_is_running_not_completed(self) -> None:
        """The absence gets its own reading rather than defaulting to success."""
        running = codex_isolation.codex_terminal_state(None, [{"type": "turn.started"}])
        self.assertEqual(running["state"], "running")
        self.assertFalse(running["terminal"])
        self.assertIsNone(running["source"])

    def test_parse_codex_events_fails_closed_on_a_line_it_cannot_type(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "invalid Codex JSONL event on line 2"):
            codex_isolation.parse_codex_events('{"type":"turn.started"}\nnot json\n', error_cls=RuntimeError)
        with self.assertRaisesRegex(RuntimeError, "expected object"):
            codex_isolation.parse_codex_events("[1, 2]\n", error_cls=RuntimeError)


class SurfaceReceiptStructuralControlTests(unittest.TestCase):
    """The control that actually held the hazard, asserted directly so the deletion is not a loss.

    The substring guard was reached for one worry: a context budget that silently drops skills. That
    worry is held STRUCTURALLY - `_surface_receipt` compares the skills the prompt really lists
    against the required set - and that control does not care what words the payload contains. These
    two cases are the positive control and its planted negative, built from synthetic prompt-input
    payloads so nothing here reads the candidate tree."""

    def receipt_input(self, *, skills: tuple[str, ...], extra_text: str = "") -> dict:
        temp = tempfile.TemporaryDirectory(prefix="noodles-surface-receipt-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        home = Path(temp.name)
        roots = f"- `r0` = `{home / 'project' / '.agents' / 'skills'}`\n"
        listed = "".join(f"- {name}: planted{extra_text} (file: r0/{name}/SKILL.md)\n" for name in skills)
        text = f"### Skill roots\n{roots}### Available skills\n{listed}</skills_instructions>"
        return {
            "argv": ["debug", "prompt-input", "use schedule skill"],
            "stdout": json.dumps([{"role": "developer", "content": [{"type": "input_text", "text": text}]}]),
            "stderr": "",
            "terminal": codex_isolation.codex_terminal_state(0),
            "trace": {
                "forwarded_argv": ["debug", "prompt-input"],
                "original_home": str(home / "user-home"),
                "isolated_home": str(home / "isolated-home"),
                "isolated_codex_home": str(home / "isolated-codex-home"),
            },
        }

    def test_a_prompt_whose_words_mention_truncation_is_admitted(self) -> None:
        receipt = codex_isolation._surface_receipt(
            self.receipt_input(skills=("schedule", "execute"), extra_text=", truncates long logs"),
            required_skills={"schedule"},
            error_cls=RuntimeError,
        )
        self.assertEqual(receipt["skills"], ["execute", "schedule"])
        self.assertEqual(receipt["terminal"]["state"], "completed")

    def test_planted_negative_a_prompt_that_really_lost_the_required_skill_still_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "missing required skills: schedule"):
            codex_isolation._surface_receipt(
                self.receipt_input(skills=("execute",)),
                required_skills={"schedule"},
                error_cls=RuntimeError,
            )


if __name__ == "__main__":
    unittest.main()
