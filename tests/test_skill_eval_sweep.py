"""skill-eval sweep: deterministic evidence custody over real execute-lane archives.

The sweep packages, it never judges. These controls pin the four properties that make the packaged
bundles usable as behavioral-judge substrate at all: selection is a pure function of the caller's
explicit inputs, every archive reference is re-verified by digest against the bytes on disk, a
missing or truncated archive is a distinct FATAL rather than a thinner bundle, and a credential in
the packaged bytes stops packaging outright. The last control proves the output is N-class: no
scheduling, verification, or landing path reads anything the sweep writes."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import noodles
import runtime_contract
from tests.support import CANDIDATE_ROOT

MARKERS = ("skill-eval", "skill_eval")
REPOSITORY = "ed3c/noodles"
LANDED_ARCHIVE = b'{"event":"tool_call","name":"read"}\n{"event":"result","ok":true}\n'
FAILED_ARCHIVE = b'{"event":"tool_call","name":"edit"}\n{"event":"result","ok":false}\n'
SKILL_DIGEST = "1" * 64


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def lane(
    number: int,
    outcome: str,
    completed_at: str,
    archive_path: str,
    archive: bytes,
    *,
    verify_receipt: str | None = None,
) -> dict:
    return {
        "subject": f"{REPOSITORY}#{number}",
        "pr": number + 1,
        "outcome": outcome,
        "completed_at": completed_at,
        "verify_receipt": verify_receipt or f"https://github.com/{REPOSITORY}/actions/runs/{number}",
        "merge_receipt": f"{number:040d}",
        "skills": {"execute": SKILL_DIGEST, "schedule": "2" * 64},
        "archives": [{"path": archive_path, "sha256": digest(archive), "bytes": len(archive)}],
    }


class SweepHarness:
    """One real filesystem: a lane index, an archive root with real bytes, and an empty out dir."""

    def __init__(self, case: unittest.TestCase, lanes: list[dict], archives: dict[str, bytes]) -> None:
        temp = tempfile.TemporaryDirectory(prefix="noodles-skill-eval-", ignore_cleanup_errors=True)
        case.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.archive_root = self.root / "archives"
        self.out = self.root / "out"
        for relative, payload in archives.items():
            path = self.archive_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        self.archive_root.mkdir(parents=True, exist_ok=True)
        self.index = self.root / "lane-index.json"
        self.index.write_text(
            json.dumps({"schema_version": 1, "lanes": lanes}, indent=2, sort_keys=True), encoding="utf-8"
        )

    def sweep(self, out: Path | None = None, **kwargs) -> dict:
        return runtime_contract.sweep_skill_eval(
            self.index, self.archive_root, out or self.out, error_cls=noodles.GateError, **kwargs
        )

    def residue(self) -> list[str]:
        return sorted(path.name for path in self.out.iterdir()) if self.out.exists() else []


def default_harness(case: unittest.TestCase, **overrides) -> SweepHarness:
    lanes = [
        lane(700, "landed", "2026-08-30T01:00:00Z", "s-700/raw.ndjson", LANDED_ARCHIVE),
        lane(701, "failed", "2026-08-30T02:00:00Z", "s-701/raw.ndjson", FAILED_ARCHIVE),
        lane(702, "anomalous", "2026-08-31T03:00:00Z", "s-702/raw.ndjson", FAILED_ARCHIVE),
        lane(703, "landed", "2026-09-01T04:00:00Z", "s-703/raw.ndjson", LANDED_ARCHIVE),
    ]
    archives = {
        "s-700/raw.ndjson": LANDED_ARCHIVE,
        "s-701/raw.ndjson": FAILED_ARCHIVE,
        "s-702/raw.ndjson": FAILED_ARCHIVE,
        "s-703/raw.ndjson": LANDED_ARCHIVE,
    }
    archives.update(overrides.pop("archives", {}))
    for relative in overrides.pop("drop_archives", ()):
        archives.pop(relative, None)
    return SweepHarness(case, overrides.pop("lanes", lanes), archives)


class SelectionTests(unittest.TestCase):
    def test_every_non_landed_lane_plus_the_explicit_sample_is_selected(self) -> None:
        manifest = default_harness(self).sweep(sample=[f"{REPOSITORY}#703"])
        self.assertEqual(
            [(entry["subject"], entry["selected_by"]) for entry in manifest["lanes"]],
            [
                (f"{REPOSITORY}#701", ["outcome:failed"]),
                (f"{REPOSITORY}#702", ["outcome:anomalous"]),
                (f"{REPOSITORY}#703", ["sample"]),
            ],
        )
        self.assertEqual(manifest["lane_count"], 3)

    def test_a_lane_selected_by_both_arms_records_both_reasons(self) -> None:
        manifest = default_harness(self).sweep(sample=[f"{REPOSITORY}#701"])
        selected = {entry["subject"]: entry["selected_by"] for entry in manifest["lanes"]}
        self.assertEqual(selected[f"{REPOSITORY}#701"], ["outcome:failed", "sample"])

    def test_caller_window_bounds_the_selection_with_no_clock_read(self) -> None:
        manifest = default_harness(self).sweep(since="2026-08-31T00:00:00Z", until="2026-08-31T23:59:59Z")
        self.assertEqual([entry["subject"] for entry in manifest["lanes"]], [f"{REPOSITORY}#702"])

    def test_selection_is_a_pure_function_of_the_declared_inputs(self) -> None:
        """The sweep source carries no clock, no randomness, and no live backlog read."""
        source = (CANDIDATE_ROOT / "runtime_contract.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        sweep_source = "\n".join(
            ast.get_source_segment(source, node) or ""
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef) and node.name.startswith(("sweep_skill_eval", "_skill_eval"))
        )
        self.assertIn("def sweep_skill_eval", sweep_source)
        for banned in ("time.time", "time.monotonic", "datetime.", "random.", "uuid.", "gh_api(", "os.getenv", "os.environ"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, sweep_source)

    def test_two_runs_with_the_same_inputs_produce_byte_identical_output(self) -> None:
        # constraint: the manifest never embeds out_dir (no field carries an out-relative or
        # constraint: out-absolute path), so this is a plain equality: nothing here needs
        # constraint: normalizing away.
        harness = default_harness(self)
        first = harness.sweep(sample=[f"{REPOSITORY}#703"])
        second_out = harness.root / "out-again"
        second = harness.sweep(out=second_out, sample=[f"{REPOSITORY}#703"])
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        for name in harness.residue():
            with self.subTest(bundle=name):
                self.assertEqual((harness.out / name).read_bytes(), (second_out / name).read_bytes())

    def test_respelling_the_same_archive_root_does_not_change_the_manifest(self) -> None:
        """archive_root is packaged evidence (manifest['archive_root']); a caller pointing at the
        identical directory through a different spelling must not fork the digest."""
        harness = default_harness(self)
        canonical = harness.sweep(sample=[f"{REPOSITORY}#703"])
        respelled_root = harness.root / "archives" / ".." / "archives" / "."
        self.assertNotEqual(str(respelled_root), str(harness.archive_root))
        respelled = runtime_contract.sweep_skill_eval(
            harness.index,
            respelled_root,
            harness.root / "out-respelled",
            sample=[f"{REPOSITORY}#703"],
            error_cls=noodles.GateError,
        )
        self.assertEqual(respelled["archive_root"], canonical["archive_root"])
        self.assertEqual(json.dumps(respelled, sort_keys=True), json.dumps(canonical, sort_keys=True))

    def test_planted_negative_sample_subject_outside_the_window_fails_closed(self) -> None:
        harness = default_harness(self)
        with self.assertRaisesRegex(noodles.GateError, "sample subjects absent from the caller's window"):
            harness.sweep(sample=[f"{REPOSITORY}#703"], until="2026-08-31T23:59:59Z")
        self.assertEqual(harness.residue(), [])

    def test_planted_negative_empty_selection_is_never_a_successful_sweep(self) -> None:
        harness = default_harness(
            self, lanes=[lane(700, "landed", "2026-08-30T01:00:00Z", "s-700/raw.ndjson", LANDED_ARCHIVE)]
        )
        with self.assertRaisesRegex(noodles.GateError, "selected no lane"):
            harness.sweep()
        self.assertEqual(harness.residue(), [])


class ArchiveCustodyTests(unittest.TestCase):
    def test_manifest_and_bundle_carry_the_declared_fields(self) -> None:
        harness = default_harness(self)
        manifest = harness.sweep()
        entry = next(item for item in manifest["lanes"] if item["subject"] == f"{REPOSITORY}#701")
        self.assertEqual(
            sorted(entry),
            ["archive_sha256", "bundle_path", "bundle_sha256", "merge_receipt", "pr", "selected_by", "skill_digests", "subject", "verify_receipt"],
        )
        self.assertEqual(entry["pr"], 702)
        self.assertEqual(entry["skill_digests"], {"execute": SKILL_DIGEST, "schedule": "2" * 64})
        self.assertEqual(entry["archive_sha256"], [digest(FAILED_ARCHIVE)])
        bundle_bytes = (harness.out / entry["bundle_path"]).read_bytes()
        self.assertEqual(digest(bundle_bytes), entry["bundle_sha256"])
        bundle = json.loads(bundle_bytes)
        self.assertEqual(bundle["subject"], f"{REPOSITORY}#701")
        self.assertEqual(bundle["archives"][0]["sha256"], digest(FAILED_ARCHIVE))
        self.assertEqual(manifest["lane_index_sha256"], digest(harness.index.read_bytes()))
        self.assertEqual(
            harness.residue(), ["ed3c-noodles-701.json", "ed3c-noodles-702.json", "skill-eval-sweep-manifest.json"]
        )

    def test_planted_negative_missing_archive_is_fatal_with_its_own_diagnostic(self) -> None:
        harness = default_harness(self, drop_archives=("s-701/raw.ndjson",))
        with self.assertRaises(noodles.GateError) as raised:
            harness.sweep()
        self.assertRegex(str(raised.exception), r"archive missing for ed3c/noodles#701: s-701/raw\.ndjson")
        self.assertNotIn("truncated", str(raised.exception))
        self.assertEqual(harness.residue(), [])

    def test_planted_negative_truncated_archive_is_fatal_with_its_own_diagnostic(self) -> None:
        harness = default_harness(self, archives={"s-701/raw.ndjson": FAILED_ARCHIVE[:10]})
        with self.assertRaises(noodles.GateError) as raised:
            harness.sweep()
        self.assertRegex(
            str(raised.exception),
            rf"archive truncated for ed3c/noodles#701: s-701/raw\.ndjson declares {len(FAILED_ARCHIVE)} bytes, read 10",
        )
        self.assertNotIn("missing", str(raised.exception))
        self.assertEqual(harness.residue(), [])

    def test_planted_negative_tampered_same_length_archive_fails_the_digest_reverification(self) -> None:
        tampered = FAILED_ARCHIVE.replace(b"false", b"true!")
        self.assertEqual(len(tampered), len(FAILED_ARCHIVE))
        harness = default_harness(self, archives={"s-701/raw.ndjson": tampered})
        with self.assertRaisesRegex(noodles.GateError, "archive digest mismatch for ed3c/noodles#701"):
            harness.sweep()
        self.assertEqual(harness.residue(), [])

    def test_planted_negative_out_of_root_archive_reference_fails_closed(self) -> None:
        harness = default_harness(
            self,
            lanes=[lane(701, "failed", "2026-08-30T02:00:00Z", "../escape.ndjson", FAILED_ARCHIVE)],
        )
        with self.assertRaisesRegex(noodles.GateError, "escapes the archive root"):
            harness.sweep()

    def test_planted_negative_non_empty_output_directory_fails_closed(self) -> None:
        harness = default_harness(self)
        harness.out.mkdir(parents=True)
        (harness.out / "stale-bundle.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "output directory is not empty"):
            harness.sweep()
        self.assertEqual(harness.residue(), ["stale-bundle.json"])


class SecretHygieneTests(unittest.TestCase):
    # constraint: assembled at runtime so the planted credential shape is never a literal in a
    # constraint: tracked file, which would make this test its own scanner's first FATAL.
    PLANTED = b"gh" + b"p_" + b"A" * 36

    def test_planted_token_in_a_packaged_archive_makes_packaging_fatal(self) -> None:
        poisoned = FAILED_ARCHIVE + b'{"event":"log","text":"' + self.PLANTED + b'"}\n'
        harness = default_harness(
            self,
            lanes=[lane(701, "failed", "2026-08-30T02:00:00Z", "s-701/raw.ndjson", poisoned)],
            archives={"s-701/raw.ndjson": poisoned},
        )
        with self.assertRaises(noodles.GateError) as raised:
            harness.sweep()
        diagnostic = str(raised.exception)
        self.assertIn("secret scan rejected archive s-701/raw.ndjson of ed3c/noodles#701", diagnostic)
        self.assertIn("ghp_ token pattern at byte offset", diagnostic)
        self.assertNotIn(self.PLANTED.decode("ascii"), diagnostic)
        self.assertEqual(harness.residue(), [])

    def test_planted_token_in_lane_metadata_makes_packaging_fatal(self) -> None:
        harness = default_harness(
            self,
            lanes=[
                lane(
                    701,
                    "failed",
                    "2026-08-30T02:00:00Z",
                    "s-701/raw.ndjson",
                    FAILED_ARCHIVE,
                    verify_receipt="https://example.invalid/?token=" + self.PLANTED.decode("ascii"),
                )
            ],
        )
        with self.assertRaisesRegex(noodles.GateError, r"secret scan rejected bundle ed3c-noodles-701\.json"):
            harness.sweep()
        self.assertEqual(harness.residue(), [])

    def test_scanner_covers_each_declared_credential_family_and_spares_a_bare_prefix(self) -> None:
        for family in ("ghs_", "ghp_", "github_pat_"):
            with self.subTest(family=family):
                with self.assertRaisesRegex(noodles.GateError, f"{family} token pattern"):
                    runtime_contract._skill_eval_secret_scan(
                        "probe", family.encode("ascii") + b"B" * 36, error_cls=noodles.GateError
                    )
        runtime_contract._skill_eval_secret_scan(
            "probe", b"the transcript mentions ghp_ and github_pat_ by name", error_cls=noodles.GateError
        )


class LaneIndexShapeTests(unittest.TestCase):
    def index_error(self, payload: object) -> str:
        temp = tempfile.TemporaryDirectory(prefix="noodles-skill-eval-index-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "lane-index.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(noodles.GateError) as raised:
            runtime_contract._skill_eval_lane_index(path, error_cls=noodles.GateError)
        return str(raised.exception)

    def test_wrong_schema_version_fails_closed(self) -> None:
        self.assertIn("schema_version 1", self.index_error({"schema_version": 2, "lanes": []}))

    def test_empty_index_fails_closed(self) -> None:
        self.assertIn("carries no lanes", self.index_error({"schema_version": 1, "lanes": []}))

    def test_non_subject_lane_id_fails_closed(self) -> None:
        broken = lane(701, "failed", "2026-08-30T02:00:00Z", "s/raw.ndjson", FAILED_ARCHIVE)
        broken["subject"] = "ed3c/noodles"
        self.assertIn("not one exact owner/repo#N subject", self.index_error({"schema_version": 1, "lanes": [broken]}))

    def test_duplicate_subject_fails_closed(self) -> None:
        entry = lane(701, "failed", "2026-08-30T02:00:00Z", "s/raw.ndjson", FAILED_ARCHIVE)
        self.assertIn("repeats subject", self.index_error({"schema_version": 1, "lanes": [entry, dict(entry)]}))

    def test_lane_without_a_session_archive_fails_closed(self) -> None:
        broken = lane(701, "failed", "2026-08-30T02:00:00Z", "s/raw.ndjson", FAILED_ARCHIVE)
        broken["archives"] = []
        self.assertIn("non-empty list of session-archive references", self.index_error({"schema_version": 1, "lanes": [broken]}))

    def test_lane_without_an_executing_skill_digest_fails_closed(self) -> None:
        broken = lane(701, "failed", "2026-08-30T02:00:00Z", "s/raw.ndjson", FAILED_ARCHIVE)
        broken["skills"] = {}
        self.assertIn("non-empty executing-skill digest map", self.index_error({"schema_version": 1, "lanes": [broken]}))


class NonClaimTests(unittest.TestCase):
    """Mechanical N-class proof, read off the exact candidate tree rather than the engine import."""

    def tracked_executables(self) -> list[str]:
        listing = subprocess.run(
            ["git", "ls-files", "-z"], cwd=str(CANDIDATE_ROOT), text=True, capture_output=True, check=False
        )
        self.assertEqual(listing.returncode, 0, listing.stderr)
        return [
            entry
            for entry in listing.stdout.split("\0")
            if entry and (entry.endswith((".py", ".yml", ".yaml", ".sh", ".toml")) or entry == "noodles")
        ]

    def test_no_executable_surface_outside_the_sweep_and_its_test_names_the_sweep(self) -> None:
        hits = {
            relative
            for relative in self.tracked_executables()
            if any(marker in (CANDIDATE_ROOT / relative).read_text(encoding="utf-8", errors="ignore") for marker in MARKERS)
        }
        self.assertEqual(hits, {"noodles.py", "runtime_contract.py", "tests/test_skill_eval_sweep.py"})

    def test_only_the_cli_entrypoint_reaches_the_sweep_no_schedule_verify_or_land_path_does(self) -> None:
        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        readers = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef)
            and any(marker in (ast.get_source_segment(source, node) or "") for marker in MARKERS)
        }
        self.assertEqual(readers, {"build_parser", "main"})

    def test_no_admission_path_reads_the_sweep_manifest_name(self) -> None:
        source = (CANDIDATE_ROOT / "runtime_contract.py").read_text(encoding="utf-8")
        readers = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef)
            and "SKILL_EVAL_MANIFEST_NAME" in (ast.get_source_segment(source, node) or "")
        }
        self.assertEqual(readers, {"sweep_skill_eval"})


if __name__ == "__main__":
    unittest.main()
