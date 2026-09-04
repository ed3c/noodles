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
        temp = tempfile.TemporaryDirectory(prefix="noodles-preflight-test-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        cmd(["git", "remote", "add", "origin", "git@github.com:ed3c/noodles.git"], root)
        return root

    def invoke(
        self,
        root: Path,
        deprived: str | None = None,
        *,
        gh_present: bool = True,
        ambient_credential: str | None = None,
        connector_payload: object = None,
    ) -> tuple[int, str, str]:
        """ed3c/noodles#434: `gh_present` is the live physical control - an absent binary raises
        FileNotFoundError out of the process layer, which is exactly what the measured environment
        did - and `ambient_credential` is what the ambient git credential store answers with."""
        real_run = noodles.run

        def controlled_run(argv, **kwargs):
            command = list(argv)
            if command[:2] == ["git", "ls-remote"]:
                if deprived == "provider network reach":
                    return subprocess.CompletedProcess(command, 1, "", "network unavailable")
                return subprocess.CompletedProcess(command, 0, "fixture\tHEAD\n", "")
            if command[:2] == ["gh", "api"]:
                if not gh_present:
                    raise FileNotFoundError(2, "No such file or directory", "gh")
                if deprived == "credential adapter readback":
                    return subprocess.CompletedProcess(command, 1, "", "authentication required")
                return subprocess.CompletedProcess(command, 0, "ed3c/noodles\n", "")
            if command[:3] == ["git", "credential", "fill"]:
                if ambient_credential is None:
                    return subprocess.CompletedProcess(command, 1, "", "no credential store")
                filled = f"protocol=https\nhost=github.com\nusername=x-access-token\npassword={ambient_credential}\n"
                return subprocess.CompletedProcess(command, 0, filled, "")
            if command[:2] == ["git", "commit-tree"] and deprived == "git metadata write":
                return subprocess.CompletedProcess(command, 1, "", "read-only git metadata")
            if command[-3:] == ["feature", "verify", "--help"] and deprived == "feature-verify tool presence":
                return subprocess.CompletedProcess(command, 127, "", "feature verifier unavailable")
            return real_run(command, **kwargs)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(noodles, "run", side_effect=controlled_run), \
             mock.patch("urllib.request.urlopen", side_effect=self.connector_response(connector_payload)), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = noodles.main(["--root", str(root), "preflight"])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def connector_response(payload: object):
        def opened(_request, **_kwargs):
            return contextlib.closing(io.BytesIO(json.dumps(payload).encode("utf-8")))

        return opened

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
                "credential adapter readback",
                "git metadata write",
                "feature-verify tool presence",
            ],
        )
        self.assertEqual(observed["capabilities"][1]["transport"], "gh")
        self.assertEqual(observed["capabilities"][1]["transports_tried"], ["gh"])
        self.assertEqual(cmd(["git", "rev-parse", "HEAD"], root), head)
        self.assertEqual(cmd(["git", "status", "--porcelain=v1", "--untracked-files=all"], root), "")
        self.assertEqual(cmd(["git", "for-each-ref", "--format=%(refname)", "refs/noodles/preflight"], root), "")

    def test_planted_deprivations_name_the_exact_missing_capability(self) -> None:
        for capability in (
            "provider network reach",
            "credential adapter readback",
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

    def test_an_absent_gh_binary_passes_on_the_connector_transport(self) -> None:
        """ed3c/noodles#434's measured environment: no `gh`, but the ambient identity really does hold
        the access, reachable through the credential store git itself fetches with. The gate's
        question is answered, so it passes - and it passes ON the connector, not by skipping."""
        root = self.candidate_copy()

        exit_code, stdout, stderr = self.invoke(
            root,
            gh_present=False,
            ambient_credential="ambient-connector-credential",
            connector_payload={"full_name": "ed3c/noodles"},
        )

        self.assertEqual(exit_code, 0, stderr)
        readback = json.loads(stdout)["capabilities"][1]
        self.assertEqual(readback["capability"], "credential adapter readback")
        self.assertEqual(readback["transport"], "connector")
        self.assertEqual(readback["transports_tried"], ["gh", "connector"])
        self.assertEqual(readback["repository"], "ed3c/noodles")

    def test_no_present_transport_fails_closed_naming_every_transport_tried(self) -> None:
        """The other direction of the same widening: recognizing a legitimate non-`gh` arrival must
        not turn an environment that holds the access through NONE of them into a pass."""
        root = self.candidate_copy()

        exit_code, _stdout, stderr = self.invoke(root, gh_present=False, ambient_credential=None)

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "preflight missing capability: credential adapter readback: no credential transport "
            "present (tried: gh, connector)",
            stderr,
        )

    def test_a_present_connector_that_reads_back_another_repository_fails_closed(self) -> None:
        """Transport presence is not the assertion; the readback is. A connector that answers with a
        repository other than the target is refused exactly as the `gh` probe always refused it."""
        root = self.candidate_copy()

        exit_code, _stdout, stderr = self.invoke(
            root,
            gh_present=False,
            ambient_credential="ambient-connector-credential",
            connector_payload={"full_name": "someone-else/noodles"},
        )

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "credential adapter readback: connector transport: repository readback "
            "'someone-else/noodles' != 'ed3c/noodles'",
            stderr,
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
        temp = tempfile.TemporaryDirectory(prefix="noodles-preflight-bin-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        return temp.name


class CredentialAdapterSubstitutionTests(unittest.TestCase):
    """ed3c/noodles#434: widening the readback to a transport roster is honest only while every
    adapter reads the AMBIENT identity's own access. An adapter that would mint or swap a credential
    is a validator error, so the widening cannot be walked back into a bypass by a later atom."""

    PLANTS = {
        "swapped environment key": (
            "def _credential_adapter_planted(root, repository):\n"
            '    os.environ["GH_TOKEN"] = "planted"\n'
            "    return repository\n"
        ),
        "supplied transport keyword": (
            "def _credential_adapter_planted(root, repository):\n"
            '    return gh_api(f"repos/{repository}", token="planted")\n'
        ),
        "minted credential endpoint": (
            "def _credential_adapter_planted(root, repository):\n"
            '    return gh_api("app/installations/1/access_tokens", method="POST")\n'
        ),
        "credential parameter": (
            "def _credential_adapter_planted(root, repository, token=None):\n"
            "    return repository\n"
        ),
    }

    def candidate_copy(self) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-substitution-test-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return root

    @staticmethod
    def plant(root: Path, source: str) -> None:
        target = root / "noodles.py"
        target.write_text(f"{target.read_text(encoding='utf-8')}\n\n{source}", encoding="utf-8")

    def test_every_shipped_adapter_supplies_no_credential(self) -> None:
        self.assertEqual(noodles.credential_adapter_errors(CANDIDATE_ROOT), [])
        self.assertEqual([name for name, _ in noodles.CREDENTIAL_ADAPTERS], ["gh", "connector"])

    def test_each_planted_substitution_is_a_validator_error(self) -> None:
        for label, source in sorted(self.PLANTS.items()):
            with self.subTest(plant=label):
                root = self.candidate_copy()
                self.assertEqual(noodles.credential_adapter_errors(root), [])
                self.plant(root, source)
                errors = noodles.credential_adapter_errors(root)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn("noodles.py:_credential_adapter_planted", errors[0])

    def test_the_refusal_reaches_verify_repository(self) -> None:
        """The plant has to red the gate agents actually run, not only the function under it."""
        root = self.candidate_copy()
        self.assertTrue(noodles.verify_repository(root, CANDIDATE_ROOT)["ok"])

        self.plant(root, self.PLANTS["swapped environment key"])
        result = noodles.verify_repository(root, CANDIDATE_ROOT)

        self.assertFalse(result["ok"])
        self.assertIn(
            "noodles.py:_credential_adapter_planted stores into 'GH_TOKEN': an adapter may not mint "
            "or swap a credential",
            result["errors"],
        )

    def test_an_absent_source_is_inert_rather_than_red(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            self.assertEqual(noodles.credential_adapter_errors(Path(temp)), [])


if __name__ == "__main__":
    unittest.main()
