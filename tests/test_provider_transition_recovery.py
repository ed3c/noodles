from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.support import (
    CANDIDATE_ROOT,
    cmd,
    copy_tracked,
    current_provider_lock,
    current_skill_paths,
    exact_provider_transition_state,
    recovery_provider_lock,
    recovery_skill_paths,
)


class ProviderTransitionRecoveryTests(unittest.TestCase):
    def mutated_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-provider-transition-")
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return temp, root

    def write_provider_lock(self, root: Path, providers: list[dict[str, object]]) -> None:
        path = root / "policy/providers.lock.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["providers"] = providers
        path.write_text(json.dumps(payload), encoding="utf-8")

    def set_external_skill_path(self, root: Path, external_path: str) -> None:
        path = root / ".noodle.toml"
        config = path.read_text(encoding="utf-8")
        for candidate in (current_skill_paths()[2], recovery_skill_paths()[2]):
            needle = f'  "{candidate}"\n'
            if needle in config:
                path.write_text(config.replace(needle, f'  "{external_path}"\n', 1), encoding="utf-8")
                return
        self.fail("trusted test fixture missing external provider skill path")

    def test_provider_transition_oracle_rejects_mixed_or_third_states(self) -> None:
        cases = (
            (
                "new lock plus old path",
                lambda root: (
                    self.write_provider_lock(root, recovery_provider_lock()),
                    self.set_external_skill_path(root, current_skill_paths()[2]),
                ),
            ),
            (
                "old lock plus new path",
                lambda root: (
                    self.write_provider_lock(root, current_provider_lock()),
                    self.set_external_skill_path(root, recovery_skill_paths()[2]),
                ),
            ),
            (
                "retained Matt plus skill-concerns",
                lambda root: self.write_provider_lock(
                    root,
                    [
                        current_provider_lock()[0],
                        current_provider_lock()[1],
                        recovery_provider_lock()[1],
                        current_provider_lock()[2],
                    ],
                ),
            ),
            (
                "third enabled provider",
                lambda root: self.write_provider_lock(
                    root,
                    [
                        current_provider_lock()[0],
                        current_provider_lock()[1],
                        {**current_provider_lock()[2], "enabled": True},
                    ],
                ),
            ),
            (
                "wrong replacement commit",
                lambda root: self.write_provider_lock(
                    root,
                    [
                        recovery_provider_lock()[0],
                        {**recovery_provider_lock()[1], "commit": "0" * 40},
                        recovery_provider_lock()[2],
                    ],
                ),
            ),
            (
                "wrong replacement digest",
                lambda root: self.write_provider_lock(
                    root,
                    [
                        recovery_provider_lock()[0],
                        {
                            **recovery_provider_lock()[1],
                            "admission": {
                                **dict(recovery_provider_lock()[1]["admission"]),
                                "sha256": "1" * 64,
                            },
                        },
                        recovery_provider_lock()[2],
                    ],
                ),
            ),
        )
        for label, mutate in cases:
            with self.subTest(case=label):
                temp, root = self.mutated_copy()
                self.addCleanup(temp.cleanup)
                mutate(root)
                with self.assertRaisesRegex(AssertionError, "exact #49 control-noodle state"):
                    exact_provider_transition_state(root)


if __name__ == "__main__":
    unittest.main()
