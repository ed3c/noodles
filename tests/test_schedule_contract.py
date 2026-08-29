from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import runtime_contract
import skill_contract
from tests.support import CANDIDATE_ROOT


class ScheduleContractTests(unittest.TestCase):
    def local_publish(self, payload: dict[str, object], current: dict[str, object] | None = None) -> dict[str, object]:
        with tempfile.TemporaryDirectory(prefix="noodles-local-publish-") as temp_name:
            root = Path(temp_name)
            runtime = root / ".noodle"
            runtime.mkdir()
            if current is not None:
                (runtime / "orders.json").write_text(json.dumps(current), encoding="utf-8")
            candidate_path = runtime / "orders-next.candidate.json"
            candidate_path.write_text(json.dumps(payload), encoding="utf-8")
            try:
                destination = skill_contract.publish_schedule_output(root, candidate_path)
            except ValueError as exc:
                return {
                    "accepted": False,
                    "error": str(exc),
                    "candidate_exists": candidate_path.exists(),
                    "published_exists": (runtime / "orders-next.json").exists(),
                }
            return {
                "accepted": True,
                "destination": str(destination),
                "candidate_exists": candidate_path.exists(),
                "published_exists": (runtime / "orders-next.json").exists(),
            }

    def runtime_promote(self, payload: dict[str, object]) -> dict[str, object]:
        binary = runtime_contract.resolve_locked_runtime_binary(CANDIDATE_ROOT, error_cls=AssertionError)
        with tempfile.TemporaryDirectory(prefix="noodles-runtime-promote-") as temp_name:
            root = Path(temp_name)
            init = subprocess.run(
                [str(binary), "--project-dir", str(root), "start", "--once"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(init.returncode, 0, init.stderr or init.stdout)
            runtime = root / ".noodle"
            (runtime / "orders-next.json").write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [str(binary), "--project-dir", str(root), "start", "--once"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            bad_path = runtime / "orders-next.json.bad"
            orders_path = runtime / "orders.json"
            return {
                "accepted": not bad_path.exists(),
                "output": (result.stdout or "") + (result.stderr or ""),
                "bad_exists": bad_path.exists(),
                "orders_exists": orders_path.exists(),
            }

    def test_schedule_output_accepts_runtime_compatible_action_needed_array(self) -> None:
        proposed = {"orders": [], "action_needed": ["needs-human", ""]}
        self.assertEqual(skill_contract.validate_schedule_output({"orders": []}, proposed), [])

    def test_schedule_output_rejects_unknown_top_level_field(self) -> None:
        proposed = {"orders": [], "rationale": "top-level drift"}
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed),
            ["scheduler output has unknown field 'rationale'; allowed fields: action_needed, orders"],
        )

    def test_schedule_output_rejects_non_array_action_needed(self) -> None:
        proposed = {"orders": [], "action_needed": "ed3c/noodles#43"}
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed),
            ["scheduler output action_needed must be an array of strings"],
        )

    def test_schedule_output_rejects_unknown_order_field(self) -> None:
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#43",
                "stages": [{"do": "execute", "prompt": "next"}],
                "bogus": 1,
            }]
        }
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed),
            ["scheduler output order[0] has unknown field 'bogus'; allowed fields: id, plan, rationale, stages, title"],
        )

    def test_schedule_output_rejects_unknown_stage_field(self) -> None:
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#43",
                "stages": [{"do": "execute", "prompt": "next", "bogus": 1}],
            }]
        }
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed),
            [
                "scheduler output order 'ed3c/noodles#43' stage[0] has unknown field 'bogus'; "
                "allowed fields: do, extra, extra_prompt, group, model, prompt, runtime, with"
            ],
        )

    def test_schedule_publish_matches_runtime_promotion_path_for_compact_payloads(self) -> None:
        cases = (
            (
                "positive compact order",
                {"orders": [{"id": "ed3c/noodles#44", "stages": [{"do": "execute", "prompt": "next"}]}]},
                True,
                None,
            ),
            (
                "runtime-compatible action_needed",
                {"orders": [], "action_needed": ["needs-human"]},
                True,
                None,
            ),
            (
                "top-level rationale",
                {"orders": [], "rationale": "drift"},
                False,
                "rationale",
            ),
            (
                "misspelled top-level field",
                {"orders": [], "actionNeed": "needs-human"},
                False,
                "actionNeed",
            ),
            (
                "wrong action_needed type",
                {"orders": [], "action_needed": "ed3c/noodles#43"},
                False,
                "action_needed",
            ),
            (
                "unknown order field",
                {"orders": [{"id": "ed3c/noodles#44", "stages": [{"do": "execute", "prompt": "next"}], "bogus": 1}]},
                False,
                "bogus",
            ),
            (
                "unknown stage field",
                {"orders": [{"id": "ed3c/noodles#44", "stages": [{"do": "execute", "prompt": "next", "bogus": 1}]}]},
                False,
                "bogus",
            ),
        )
        for label, payload, accepted, fragment in cases:
            with self.subTest(case=label):
                local = self.local_publish(payload)
                runtime = self.runtime_promote(payload)
                self.assertEqual(local["accepted"], accepted)
                self.assertEqual(runtime["accepted"], accepted)
                self.assertEqual(local["accepted"], runtime["accepted"])
                if accepted:
                    self.assertFalse(local["candidate_exists"])
                    self.assertTrue(local["published_exists"])
                    self.assertFalse(runtime["bad_exists"])
                    self.assertTrue(runtime["orders_exists"])
                else:
                    self.assertTrue(local["candidate_exists"])
                    self.assertFalse(local["published_exists"])
                    self.assertTrue(runtime["bad_exists"])
                    self.assertIn(fragment, str(local["error"]))
                    self.assertIn(fragment, str(runtime["output"]))


if __name__ == "__main__":
    unittest.main()
