"""Findings register: the durable home a disclosed-not-fixed finding gets when intake refuses it
an Issue. The register itself is N - an entry gates nothing. What is L is its shape: a malformed
entry and a silently removed entry both fail the recomputation, and the gate is wired into
`verify_repository` so the trusted verify path reads it too."""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT


def candidate_register() -> dict:
    return json.loads((CANDIDATE_ROOT / noodles.FINDINGS_REGISTER_PATH).read_text(encoding="utf-8"))


class PlantedRegister:
    """A tree carrying only the two files the gate reads, so a planted defect is the only variable."""

    def __init__(self, case: unittest.TestCase) -> None:
        temp = tempfile.TemporaryDirectory(prefix="noodles-findings-register-", ignore_cleanup_errors=True)
        case.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "policy").mkdir()
        shutil.copy2(CANDIDATE_ROOT / noodles.COMPONENT_MAP_PATH, self.root / noodles.COMPONENT_MAP_PATH)
        (self.root / "docs" / "findings").mkdir(parents=True)

    def write(self, payload: object) -> Path:
        path = self.root / noodles.FINDINGS_REGISTER_PATH
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.root

    def errors(self, payload: object) -> list[str]:
        return noodles.findings_register_errors(self.write(payload))


class FindingsRegisterShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planted = PlantedRegister(self)
        self.register = candidate_register()

    def test_positive_control_candidate_register_validates_clean(self) -> None:
        self.assertEqual(noodles.findings_register_errors(CANDIDATE_ROOT), [])
        self.assertEqual(self.planted.errors(self.register), [])

    def test_planted_negative_removed_entry_breaks_the_append_only_check(self) -> None:
        register = copy.deepcopy(self.register)
        del register["entries"][1]
        errors = self.planted.errors(register)
        self.assertEqual(len(errors), 1)
        self.assertIn("an entry was removed or reordered", errors[0])

    def test_planted_negative_removed_entry_with_renumbered_ids_still_breaks_the_chain(self) -> None:
        register = copy.deepcopy(self.register)
        del register["entries"][1]
        for position, entry in enumerate(register["entries"], start=1):
            entry["id"] = position
        errors = self.planted.errors(register)
        self.assertEqual(len(errors), 1)
        self.assertIn("the register was mutated, not appended", errors[0])

    def test_planted_negative_edited_entry_text_breaks_the_chain(self) -> None:
        register = copy.deepcopy(self.register)
        register["entries"][0]["finding"] = "A softer statement of the same finding."
        errors = self.planted.errors(register)
        self.assertEqual(len(errors), 1)
        self.assertIn("the register was mutated, not appended", errors[0])

    def test_planted_negative_reordered_entries_are_refused(self) -> None:
        register = copy.deepcopy(self.register)
        register["entries"][0], register["entries"][1] = register["entries"][1], register["entries"][0]
        errors = self.planted.errors(register)
        self.assertEqual(len(errors), 1)
        self.assertIn("an entry was removed or reordered", errors[0])

    def test_planted_negative_appending_without_recomputing_the_chain_is_refused(self) -> None:
        register = copy.deepcopy(self.register)
        appended = copy.deepcopy(register["entries"][-1])
        appended["id"] = len(register["entries"]) + 1
        appended.pop("promoted_to", None)
        appended["status"] = "open"
        register["entries"].append(appended)
        errors = self.planted.errors(register)
        self.assertEqual(len(errors), 1)
        self.assertIn("the register was mutated, not appended", errors[0])

    def test_planted_negative_malformed_entries_each_name_their_own_defect(self) -> None:
        cases = {
            "severity": ("severity", "S9", "is not one of S1, S2, S3"),
            "date": ("date", "2026-9-1", "is not an exact YYYY-MM-DD day"),
            "owner_component": ("owner_component", "kitchen", f"is not in {noodles.COMPONENT_MAP_PATH}"),
            "finding": ("finding", "   ", "must be one non-empty statement"),
            "receipts": ("receipts", [], "non-empty list of non-empty receipt strings"),
            "blank receipt": ("receipts", ["  "], "non-empty list of non-empty receipt strings"),
            # constraint: ed3c/noodles#263 - `status` carries the promoted_to field rule with it, so
            # constraint: the unknown-status case is planted on an entry that declares no promoted_to.
            "status": ("status", "acknowledged", "is not one of open, promoted, retired"),
        }
        for name, (field, value, diagnostic) in cases.items():
            with self.subTest(defect=name):
                register = copy.deepcopy(self.register)
                position = len(register["entries"]) - 1 if field == "status" else 0
                entry = register["entries"][position]
                entry[field] = value
                entry["chain"] = noodles.finding_chain(entry, register["entries"][position - 1]["chain"] if position else "")
                errors = self.planted.errors(register)
                self.assertEqual(len(errors), 1)
                self.assertIn(diagnostic, errors[0])

    def test_planted_negative_unknown_and_missing_fields_are_refused(self) -> None:
        extra = copy.deepcopy(self.register)
        extra["entries"][0]["owner"] = "someone"
        self.assertIn("unexpected ['owner']", self.planted.errors(extra)[0])
        missing = copy.deepcopy(self.register)
        del missing["entries"][0]["receipts"]
        self.assertIn("missing ['receipts']", self.planted.errors(missing)[0])

    def test_planted_negative_promoted_entry_without_an_exact_subject_is_refused(self) -> None:
        register = copy.deepcopy(self.register)
        entry = next(item for item in register["entries"] if item["status"] == "promoted")
        entry["promoted_to"] = "#263"
        entry["chain"] = noodles.finding_chain(entry, "" if entry["id"] == 1 else register["entries"][entry["id"] - 2]["chain"])
        errors = self.planted.errors(register)
        self.assertEqual(len(errors), 1)
        self.assertIn("is not an exact owner/repo#N subject", errors[0])

    def test_planted_negative_open_entry_carrying_promoted_to_is_refused(self) -> None:
        register = copy.deepcopy(self.register)
        entry = next(item for item in register["entries"] if item["status"] == "open")
        entry["promoted_to"] = "ed3c/noodles#274"
        errors = self.planted.errors(register)
        self.assertEqual(len(errors), 1)
        self.assertIn("unexpected ['promoted_to']", errors[0])

    def test_planted_negative_wrong_envelope_and_missing_file_are_refused(self) -> None:
        self.assertIn("schema_version 1", self.planted.errors({"schema_version": 2, "entries": []})[0])
        self.assertIn("non-empty array", self.planted.errors({"schema_version": 1, "entries": []})[0])
        # constraint: ed3c/noodles#319 - one constructor for temporary trees under tests/, and it
        # constraint: tolerates a failed cleanup, so no fixture can red a run from its teardown.
        temp = tempfile.TemporaryDirectory(prefix="noodles-findings-absent-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        empty = Path(temp.name)
        self.assertIn("missing findings register", noodles.findings_register_errors(empty)[0])


class FindingsRegisterSeedTests(unittest.TestCase):
    """The three wave-9 orphaned findings are the first entries, and one carries a live promotion."""

    def setUp(self) -> None:
        self.entries = candidate_register()["entries"]

    def test_the_first_three_entries_are_the_wave_nine_orphans_with_receipts(self) -> None:
        self.assertGreaterEqual(len(self.entries), 3)
        for entry in self.entries[:3]:
            with self.subTest(entry=entry["id"]):
                self.assertEqual(entry["status"], "promoted")
                self.assertTrue(noodles.SUBJECT_RE.fullmatch(entry["promoted_to"]))
                self.assertGreaterEqual(len(entry["receipts"]), 2)
        seeded = "\n".join(json.dumps(entry) for entry in self.entries[:3])
        self.assertIn("intake_normalize", seeded)
        self.assertIn("33366751879", seeded)
        self.assertIn("compile_handoff_feature_map", seeded)

    def test_the_escalation_hole_and_the_handoff_observation_name_their_own_issues(self) -> None:
        promoted = {entry["promoted_to"] for entry in self.entries if entry["status"] == "promoted"}
        self.assertLessEqual({"ed3c/noodles#263", "ed3c/noodles#264"}, promoted)

    def test_the_register_carries_at_least_one_open_finding_for_the_reader(self) -> None:
        self.assertTrue(noodles.open_findings(CANDIDATE_ROOT))


class FindingsRegisterReaderTests(unittest.TestCase):
    def test_open_entries_surface_as_read_only_backlog_lines(self) -> None:
        items = noodles.findings_backlog_items(CANDIDATE_ROOT)
        self.assertTrue(items)
        for item in items:
            with self.subTest(item=item["id"]):
                self.assertEqual(item["kind"], "finding")
                self.assertEqual(item["status"], "open")
                self.assertIsNone(noodles.SUBJECT_RE.fullmatch(item["id"]))
                self.assertTrue(item["receipts"])

    def test_promoted_and_retired_entries_never_reach_the_backlog_surface(self) -> None:
        surfaced = {item["id"] for item in noodles.findings_backlog_items(CANDIDATE_ROOT)}
        promoted = {
            f"finding-{entry['id']}"
            for entry in candidate_register()["entries"]
            if entry["status"] != "open"
        }
        self.assertTrue(promoted)
        self.assertEqual(surfaced & promoted, set())


class FindingsRegisterGateWiringTests(unittest.TestCase):
    def test_planted_register_defect_reaches_the_repository_verification_errors(self) -> None:
        with mock.patch.object(noodles, "findings_register_errors", return_value=["planted register defect"]) as gate:
            result = noodles.verify_repository(CANDIDATE_ROOT)
        self.assertIn("planted register defect", result["errors"])
        self.assertFalse(result["ok"])
        self.assertEqual(gate.call_args, mock.call(CANDIDATE_ROOT, CANDIDATE_ROOT))


if __name__ == "__main__":
    unittest.main()
