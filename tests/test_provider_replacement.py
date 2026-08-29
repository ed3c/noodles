from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
import runtime_contract
from tests.support import (
    CANDIDATE_ROOT,
    ENGINE_ROOT,
    cmd,
    copy_tracked,
    provider_fixture,
    write_noodle_stub,
    write_skill_discovery_fixture,
)


class ProviderReplacementTests(unittest.TestCase):
    def mutated_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-provider-replacement-")
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return temp, root

    def commit(self, root: Path) -> None:
        cmd(["git", "add", "-A"], root)
        cmd(["git", "commit", "-q", "-m", "provider replacement negative"], root)

    def runtime_candidate(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-provider-discovery-")
        candidate = Path(temp.name) / "candidate"
        copy_tracked(CANDIDATE_ROOT, candidate)
        binary = Path(temp.name) / "bin/noodle"
        binary.parent.mkdir()
        write_noodle_stub(binary, "v9.9.9")
        return temp, candidate, binary

    def assert_provider_sync_rejected(self, field: str, value: str, pattern: str) -> None:
        temp, candidate = provider_fixture()
        self.addCleanup(temp.cleanup)
        path = candidate / "policy/providers.lock.json"
        payload = json.loads(path.read_text())
        payload["providers"][0]["admission"][field] = value
        path.write_text(json.dumps(payload))
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, pattern):
                noodles.provider_sync(candidate)

    def test_retired_matt_provider_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "policy/providers.lock.json"
        payload = json.loads(path.read_text())
        payload["providers"][1]["name"] = runtime_contract.RETIRED_PROVIDER
        payload["providers"][1]["destination"] = runtime_contract.RETIRED_PROVIDER_DESTINATION
        path.write_text(json.dumps(payload))
        self.commit(root)
        result = noodles.verify_repository(root, ENGINE_ROOT)
        self.assertFalse(result["ok"])
        self.assertTrue(any("retired and must not remain" in item for item in result["errors"]))

    def test_control_noodle_discovery_path_is_required(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".noodle.toml"
        config = path.read_text()
        required = '  ".noodle/providers/skill-concerns/skills/control-noodle"\n'
        self.assertIn(required, config)
        path.write_text(config.replace(required, "", 1))
        self.commit(root)
        result = noodles.verify_repository(root, ENGINE_ROOT)
        self.assertFalse(result["ok"])
        self.assertTrue(any("skills.paths must include" in item for item in result["errors"]))

    def test_wrong_locked_admission_digest_is_rejected(self) -> None:
        self.assert_provider_sync_rejected("sha256", "0" * 64, "admission digest")

    def test_wrong_locked_skill_tree_digest_is_rejected(self) -> None:
        self.assert_provider_sync_rejected("skill_tree_sha256", "1" * 64, "admission skill-tree digest")

    def test_retired_matt_checkout_residue_is_rejected(self) -> None:
        temp, candidate = provider_fixture()
        self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            noodles.provider_sync(candidate)
            (candidate / runtime_contract.RETIRED_PROVIDER_DESTINATION).mkdir(parents=True)
            with self.assertRaisesRegex(noodles.GateError, "retired provider checkout still present"):
                noodles.provider_check(candidate)

    def test_missing_control_noodle_discovery_is_rejected(self) -> None:
        temp, candidate, binary = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        output = write_skill_discovery_fixture(candidate)
        control_root = (candidate / runtime_contract.PROJECT_SKILLS_ROOT / runtime_contract.CONTROL_NOODLE_SKILL).resolve()
        lines = [
            f"not-control-noodle\t{control_root.parent}\ttrue\t{control_root}" if line.startswith("control-noodle\t") else line
            for line in output.splitlines()
        ]
        with mock.patch.dict(os.environ, {"NOODLES_TEST_SKILLS_OUTPUT": "\n".join(lines) + "\n"}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "missing required external skill 'control-noodle' from"):
                runtime_contract.skill_discovery_check(candidate, binary, error_cls=noodles.GateError)

    def test_retired_matt_discovery_is_rejected(self) -> None:
        temp, candidate, binary = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        matt_skill = (candidate / runtime_contract.RETIRED_PROVIDER_DISCOVERY_ROOT / "ask-matt").resolve()
        matt_skill.mkdir(parents=True)
        (matt_skill / "SKILL.md").write_text("# Ask Matt\n")
        output = write_skill_discovery_fixture(candidate) + f"ask-matt\t{matt_skill.parent}\ttrue\t{matt_skill}\n"
        with mock.patch.dict(os.environ, {"NOODLES_TEST_SKILLS_OUTPUT": output}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "must not expose retired matt-engineering skills"):
                runtime_contract.skill_discovery_check(candidate, binary, error_cls=noodles.GateError)
