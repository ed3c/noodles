from __future__ import annotations

import json
import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import codex_isolation
import noodles
import runtime_contract
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
    'permissions.noodles-cook.workspace_roots={"/Users/neon/noodles/.git"=true,"/Users/neon/noodles/.noodle/sessions"=true}',
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
        '"-c", "permissions.noodles-cook.workspace_roots={\\"/Users/neon/noodles/.git\\"=true,\\"/Users/neon/noodles/.noodle/sessions\\"=true}", '
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

    def test_codex_agent_config_rejects_broader_noodle_root(self) -> None:
        args = [value.replace("/.noodle/sessions", "/.noodle") for value in PERMISSION_PROFILE_ARGS]
        config = {"agents": {"codex": {"path": ".agents/bin", "args": args}}}
        self.assertIn(
            codex_isolation.WORKSPACE_ROOTS_ERROR,
            codex_isolation.validate_codex_agent_config(CANDIDATE_ROOT, config),
        )

    WRITE_PROBE_STUB = (
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, os.environ['NOODLES_PROBE_REPO'])\n"
        "import codex_isolation\n"
        "target = Path(os.environ['NOODLES_PROBE_TARGET'])\n"
        "allowed = codex_isolation.profile_write_allowed(sys.argv[1:], target)\n"
        "if allowed:\n"
        "    with target.open('a', encoding='utf-8') as handle:\n"
        "        handle.write(os.environ['NOODLES_PROBE_PAYLOAD'] + '\\n')\n"
        "Path(os.environ['NOODLES_PROBE_RECEIPT']).write_text(\n"
        "    json.dumps({\n"
        "        'allowed': allowed,\n"
        "        'forwarded_argv': sys.argv[1:],\n"
        "        'target': str(target),\n"
        "        'rejection': None if allowed else 'patch rejected: writing outside of the project',\n"
        "    }),\n"
        "    encoding='utf-8',\n"
        ")\n"
    )

    def run_write_probe(self, base: Path, root: Path, args: list[str], target: Path, payload: str) -> dict[str, object]:
        """Drive one planted cook write through the tracked wrapper, so the grant under test is the one that survives forwarding."""
        fake_bin = base / "probe-bin"
        fake_bin.mkdir(exist_ok=True)
        stub = fake_bin / "codex"
        stub.write_text(self.WRITE_PROBE_STUB, encoding="utf-8")
        stub.chmod(0o755)
        receipt = base / "probe-receipt.json"
        env = os.environ.copy()
        env["HOME"] = str(base / "user-home")
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["NOODLES_PROBE_REPO"] = str(root)
        env["NOODLES_PROBE_TARGET"] = str(target)
        env["NOODLES_PROBE_PAYLOAD"] = payload
        env["NOODLES_PROBE_RECEIPT"] = str(receipt)
        env.pop("NOODLES_CODEX_TRACE_FILE", None)
        subprocess.run(
            [str(root / codex_isolation.CODEX_WRAPPER), "debug", "probe-write", *args],
            cwd=root,
            env=env,
            text=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(receipt.read_text(encoding="utf-8"))

    def test_planted_cook_session_event_arrives_and_other_noodle_paths_stay_walled(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        # constraint: the tracked profile pins grants under the real checkout; relocating the pin onto this
        # constraint: copy keeps the shape honest while letting the planted append be real bytes, not a claim.
        tracked = tomllib.loads((root / ".noodle.toml").read_text(encoding="utf-8"))["agents"]["codex"]["args"]
        args = [str(value).replace("/Users/neon/noodles", str(root)) for value in tracked]
        events = root / ".noodle" / "sessions" / "session-170" / "events.ndjson"
        events.parent.mkdir(parents=True)
        events.write_text("", encoding="utf-8")
        walled = [root / ".noodle" / "providers" / "pinned.json", root / ".noodle" / "status.json"]
        for path in walled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        stage_message = json.dumps(
            {"type": "stage_message", "payload": {"message": "[order:ed3c/noodles#170] planted handoff"}},
            separators=(",", ":"),
        )

        arrived = self.run_write_probe(base, root, args, events, stage_message)
        self.assertTrue(arrived["allowed"], arrived)
        self.assertIn(f'{root}/.noodle/sessions"=true', " ".join(str(item) for item in arrived["forwarded_argv"]))
        self.assertEqual(
            [item["type"] for item in runtime_contract.read_session_events(events, error_cls=RuntimeError)],
            ["stage_message"],
        )

        for path in walled:
            rejected = self.run_write_probe(base, root, args, path, stage_message)
            self.assertFalse(rejected["allowed"], rejected)
            self.assertEqual(rejected["rejection"], "patch rejected: writing outside of the project")
            self.assertEqual(path.read_text(encoding="utf-8"), "{}\n")

        # constraint: falsifiability - drop the session grant and the same append must stop arriving,
        # constraint: otherwise the positive control was measuring the worktree, not the new root.
        without_grant = [value.replace(f',"{root}/.noodle/sessions"=true', "") for value in args]
        self.assertNotEqual(without_grant, args)
        denied = self.run_write_probe(base, root, without_grant, events, stage_message)
        self.assertFalse(denied["allowed"], denied)
        self.assertEqual(len(runtime_contract.read_session_events(events, error_cls=RuntimeError)), 1)

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
