from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT, cmd, copy_tracked


class PreflightTests(unittest.TestCase):
    def candidate_copy(self) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-preflight-test-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        cmd(["git", "remote", "add", "origin", "git@github.com:ed3c/noodles.git"], root)
        return root

    def invoke(self, root: Path, deprived: str | None = None) -> tuple[int, str, str]:
        real_run = noodles.run

        def controlled_run(argv, **kwargs):
            command = list(argv)
            if command[:2] == ["git", "ls-remote"]:
                if deprived == "provider network reach":
                    return subprocess.CompletedProcess(command, 1, "", "network unavailable")
                return subprocess.CompletedProcess(command, 0, "fixture\tHEAD\n", "")
            if command[:2] == ["gh", "api"]:
                if deprived == "gh auth readback":
                    return subprocess.CompletedProcess(command, 1, "", "authentication required")
                return subprocess.CompletedProcess(command, 0, "ed3c/noodles\n", "")
            if command[:2] == ["git", "commit-tree"] and deprived == "git metadata write":
                return subprocess.CompletedProcess(command, 1, "", "read-only git metadata")
            if command[-3:] == ["feature", "verify", "--help"] and deprived == "feature-verify tool presence":
                return subprocess.CompletedProcess(command, 127, "", "feature verifier unavailable")
            return real_run(command, **kwargs)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(noodles, "run", side_effect=controlled_run), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = noodles.main(["--root", str(root), "preflight"])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_positive_control_probes_all_capabilities_and_leaves_zero_residue(self) -> None:
        root = self.candidate_copy()
        head = cmd(["git", "rev-parse", "HEAD"], root)

        exit_code, stdout, stderr = self.invoke(root)

        self.assertEqual(exit_code, 0, stderr)
        observed = json.loads(stdout)
        self.assertEqual(observed["ok"], True)
        self.assertEqual(
            [item["capability"] for item in observed["capabilities"]],
            [
                "provider network reach",
                "gh auth readback",
                "git metadata write",
                "feature-verify tool presence",
            ],
        )
        self.assertEqual(cmd(["git", "rev-parse", "HEAD"], root), head)
        self.assertEqual(cmd(["git", "status", "--porcelain=v1", "--untracked-files=all"], root), "")
        self.assertEqual(cmd(["git", "for-each-ref", "--format=%(refname)", "refs/noodles/preflight"], root), "")

    def test_planted_deprivations_name_the_exact_missing_capability(self) -> None:
        for capability in (
            "provider network reach",
            "gh auth readback",
            "git metadata write",
            "feature-verify tool presence",
        ):
            with self.subTest(capability=capability):
                root = self.candidate_copy()
                exit_code, _stdout, stderr = self.invoke(root, capability)
                self.assertEqual(exit_code, 1)
                self.assertIn(f"preflight missing capability: {capability}", stderr)
                self.assertEqual(
                    cmd(["git", "for-each-ref", "--format=%(refname)", "refs/noodles/preflight"], root),
                    "",
                )

    def test_launcher_names_missing_python_runtime_before_import(self) -> None:
        root = self.candidate_copy()
        fake_bin = Path(self._tempdir())
        fake_python = fake_bin / "python3"
        fake_python.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        fake_python.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:/bin:/usr/bin"

        result = subprocess.run(
            [str(root / "noodles"), "preflight"],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("preflight missing capability: Python 3.11+ runtime with tomllib", result.stderr)

    def _tempdir(self) -> str:
        temp = tempfile.TemporaryDirectory(prefix="noodles-preflight-bin-")
        self.addCleanup(temp.cleanup)
        return temp.name


if __name__ == "__main__":
    unittest.main()
