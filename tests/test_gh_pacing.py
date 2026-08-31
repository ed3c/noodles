"""Physical controls for the repository-owned gh pacing carrier (ed3c/noodles#169).

Every assertion drives the tracked `.agents/bin/gh` with a fake gh binary: no live API call
happens here. The planted negatives are a decoy `gh` earlier on the parent PATH, a zero-gap
burst whose total wall time is measurably not spread, an untracked carrier that fails `./noodles verify`, and a
mutation whose secondary-limit 403 must never be auto-retried.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import noodles
from tests.support import CANDIDATE_ROOT, cmd, copy_tracked

CARRIER_BIN = CANDIDATE_ROOT / ".agents" / "bin"
GH_CARRIER = CARRIER_BIN / "gh"

RECORDER_GH = (
    "import os, time\n"
    "with open(os.environ['FAKE_GH_LOG'], 'a', encoding='utf-8') as handle:\n"
    "    handle.write(f'{time.time():.6f}\\n')\n"
)
PASSTHROUGH_GH = (
    "import json, sys\n"
    "sys.stdout.buffer.write(b'\\x00binary\\xffbody')\n"
    "sys.stderr.write(json.dumps(sys.argv[1:]))\n"
    "raise SystemExit(7)\n"
)
STDIN_ECHO_GH = "import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n"
SECONDARY_LIMIT_GH = (
    "import os, sys\n"
    "log = os.environ['FAKE_GH_LOG']\n"
    "attempts = len(open(log, encoding='utf-8').read()) if os.path.exists(log) else 0\n"
    "open(log, 'a', encoding='utf-8').write('x')\n"
    "if attempts == 0:\n"
    "    sys.stderr.write('gh: secondary rate limit (HTTP 403)\\nRetry-After: 1\\n')\n"
    "    raise SystemExit(1)\n"
    "sys.stdout.write('ok\\n')\n"
)
PATH_PROBE_CODEX = (
    "import json, os, shutil\n"
    "json.dump({'path': os.environ.get('PATH', ''), 'which_gh': shutil.which('gh')},\n"
    "          open(os.environ['FAKE_CODEX_PROBE'], 'w', encoding='utf-8'))\n"
)
BURST_CALLS = 3
BURST_INTERVAL = 1.5
# constraint: total burst wall time is monotone in pacing - spawn jitter can only lengthen it, never
# constraint: shorten it below (calls - 1) * interval, so a loaded machine cannot fake a paced verdict.
BURST_FLOOR = (BURST_CALLS - 1) * BURST_INTERVAL * 0.95


def leading_path(directory: Path) -> str:
    # constraint: the fake binary must win PATH order while `#!/usr/bin/env python3` still resolves.
    return os.pathsep.join(entry for entry in (str(directory), os.environ.get("PATH", "")) if entry)


def write_fake(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)


def load_carrier_module():
    loader = importlib.machinery.SourceFileLoader("noodles_gh_carrier", str(GH_CARRIER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class GhPacingCarrierTests(unittest.TestCase):
    def scratch(self) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-gh-pacing-")
        self.addCleanup(temp.cleanup)
        return Path(temp.name)

    def carrier_env(self, base: Path, fake_body: str) -> dict[str, str]:
        fake_bin = base / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        write_fake(fake_bin / "gh", fake_body)
        env = os.environ.copy()
        env["PATH"] = leading_path(fake_bin)
        env["FAKE_GH_LOG"] = str(base / "gh-calls.log")
        env["NOODLES_GH_PACE_STATE"] = str(base / "pace.state")
        env["NOODLES_GH_MIN_INTERVAL"] = "0"
        return env

    def test_carrier_passes_argv_stdout_stderr_and_exit_code_byte_faithfully(self) -> None:
        base = self.scratch()
        env = self.carrier_env(base, PASSTHROUGH_GH)
        argv = ["api", "repos/ed3c/noodles", "--jq", ".full_name"]
        result = subprocess.run([str(GH_CARRIER), *argv], env=env, capture_output=True, check=False)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, b"\x00binary\xffbody")
        self.assertEqual(json.loads(result.stderr.decode("utf-8")), argv)

    def test_carrier_passes_stdin_through_to_the_real_binary(self) -> None:
        base = self.scratch()
        env = self.carrier_env(base, STDIN_ECHO_GH)
        result = subprocess.run(
            [str(GH_CARRIER), "api", "--method", "PATCH", "repos/ed3c/noodles", "--input", "-"],
            env=env,
            input=b'{"body":"\xf0\x9f\x8d\x9c"}',
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'{"body":"\xf0\x9f\x8d\x9c"}')

    def burst(self, root: Path, base: Path, interval: str) -> tuple[float, int]:
        fake_bin = base / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        write_fake(fake_bin / "gh", RECORDER_GH)
        log = base / f"burst-{interval}.log"
        env = os.environ.copy()
        env["PATH"] = leading_path(fake_bin)
        env["FAKE_GH_LOG"] = str(log)
        env["NOODLES_GH_MIN_INTERVAL"] = interval
        env.pop("NOODLES_GH_PACE_STATE", None)
        # constraint: no state override, so the default .noodle/ state file is the surface under test.
        started = time.monotonic()
        processes = [
            subprocess.Popen([str(root / ".agents/bin/gh"), "api", "rate_limit"], env=env, cwd=root)
            for _ in range(BURST_CALLS)
        ]
        for process in processes:
            self.assertEqual(process.wait(timeout=60), 0)
        return time.monotonic() - started, len(log.read_text(encoding="utf-8").split())

    def test_concurrent_burst_is_serialized_and_spread_but_a_zero_gap_control_is_not(self) -> None:
        base = self.scratch()
        root = base / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        paced, calls = self.burst(root, base, str(BURST_INTERVAL))
        self.assertEqual(calls, BURST_CALLS)
        self.assertTrue((root / ".noodle/gh-pace.state").is_file())
        self.assertGreaterEqual(paced, BURST_FLOOR)
        (root / ".noodle/gh-pace.state").unlink()
        control, control_calls = self.burst(root, base, "0")
        self.assertEqual(control_calls, BURST_CALLS)
        self.assertLess(control, BURST_FLOOR)

    def test_read_only_secondary_limit_403_retries_once_after_retry_after(self) -> None:
        base = self.scratch()
        env = self.carrier_env(base, SECONDARY_LIMIT_GH)
        started = time.monotonic()
        result = subprocess.run(
            [str(GH_CARRIER), "api", "repos/ed3c/noodles"], env=env, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"ok\n")
        self.assertEqual(Path(env["FAKE_GH_LOG"]).read_text(encoding="utf-8"), "xx")
        self.assertGreaterEqual(time.monotonic() - started, 1.0)

    def test_mutation_secondary_limit_403_never_auto_retries(self) -> None:
        base = self.scratch()
        env = self.carrier_env(base, SECONDARY_LIMIT_GH)
        result = subprocess.run(
            [str(GH_CARRIER), "api", "--method", "POST", "repos/ed3c/noodles/issues"],
            env=env,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"HTTP 403", result.stderr)
        self.assertEqual(Path(env["FAKE_GH_LOG"]).read_text(encoding="utf-8"), "x")

    def test_unclassifiable_and_writing_shapes_fail_closed_to_no_retry(self) -> None:
        carrier = load_carrier_module()
        for argv in (["api", "repos/ed3c/noodles"], ["issue", "view", "169"], ["pr", "list"], ["api", "-XGET", "x"]):
            self.assertTrue(carrier.is_read_only(argv), argv)
        for argv in (
            ["api", "graphql", "-f", "query=x"],
            ["api", "repos/x", "-f", "state=closed"],
            ["api", "--method", "POST", "repos/x"],
            ["api", "repos/x", "--input", "-"],
            ["pr", "merge", "1"],
            ["issue", "close", "169"],
            [],
        ):
            self.assertFalse(carrier.is_read_only(argv), argv)

    def test_cook_path_ordering_puts_the_carrier_ahead_of_a_planted_decoy_gh(self) -> None:
        base = self.scratch()
        root = base / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        root = root.resolve()
        fake_bin = base / "cook-bin"
        fake_bin.mkdir()
        write_fake(fake_bin / "codex", PATH_PROBE_CODEX)
        decoy = fake_bin / "gh"
        write_fake(decoy, "raise SystemExit('decoy gh must never be reached from a cook')\n")
        probe = base / "cook-probe.json"
        trace = base / "cook-trace.json"
        env = os.environ.copy()
        env["HOME"] = str(base / "user-home")
        env["PATH"] = leading_path(fake_bin)
        env["FAKE_CODEX_PROBE"] = str(probe)
        env["NOODLES_CODEX_TRACE_FILE"] = str(trace)
        self.assertEqual(shutil.which("gh", path=env["PATH"]), str(decoy))
        subprocess.run(
            [str(root / ".agents/bin/codex"), "debug", "prompt-input", "probe"],
            cwd=root,
            env=env,
            capture_output=True,
            check=True,
        )
        child_path = json.loads(trace.read_text(encoding="utf-8"))["child_path"]
        self.assertEqual(child_path.split(os.pathsep)[0], str(root / ".agents/bin"))
        self.assertEqual(
            json.loads(probe.read_text(encoding="utf-8"))["which_gh"], str(root / ".agents/bin/gh")
        )

    def test_verify_repository_requires_the_tracked_gh_carrier(self) -> None:
        base = self.scratch()
        root = base / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        self.assertTrue(noodles.verify_repository(root, CANDIDATE_ROOT)["ok"])
        cmd(["git", "rm", "-q", "--cached", ".agents/bin/gh"], root)
        result = noodles.verify_repository(root, CANDIDATE_ROOT)
        self.assertFalse(result["ok"])
        self.assertIn("missing required tracked path: .agents/bin/gh", result["errors"])


if __name__ == "__main__":
    unittest.main()
