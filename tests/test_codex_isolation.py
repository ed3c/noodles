from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import codex_isolation
import noodles
from tests.support import CANDIDATE_ROOT, copy_tracked, write_fake_codex_stub


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
        temp = tempfile.TemporaryDirectory(prefix="noodles-codex-isolation-")
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


if __name__ == "__main__":
    unittest.main()
