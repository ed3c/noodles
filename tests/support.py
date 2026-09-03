from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import daemon_lease
import feature_contract
import noodles
import runtime_contract

ENGINE_ROOT = Path(noodles.__file__).resolve().parent
CANDIDATE_ROOT = Path(os.getenv("NOODLES_CANDIDATE_ROOT", ENGINE_ROOT)).resolve()
FEATURE = feature_contract.VERIFICATION_SKILL_FEATURE
ISSUE_FEATURE_MARKER = f"<!-- noodles-feature: {FEATURE.feature_id} -->"
ISSUE_DEPENDS_ON_MARKER = "<!-- noodles-depends-on: none -->"
# constraint: ed3c/noodles#120 - one stable requirement heading that really exists in
# constraint: contracts/system-v1.md, so fixtures resolve through the production read path.
ISSUE_REQUIREMENT_MARKER = "<!-- noodles-requirement: SYSTEM.PURPOSE.001 -->"
# constraint: ed3c/noodles#317 - one owner for the two evidence markers every complete fixture body
# constraint: carries, so the next tightening of this pair migrates the fixtures in one edit.
ISSUE_EVIDENCE_MARKERS = "<!-- noodles-observer: none -->\n<!-- noodles-capability-probe: none -->\n"
READY_BACKLOG_FIXTURE = Path("tests/fixtures/issue-contract-ready-backlog.json")
MIGRATION_DIAGNOSTIC = (
    "migration obligation: update the durable ready-backlog fixture in this same atom; "
    "mechanically derivable live intake repair belongs at intake-normalizer seam ed3c/noodles#157"
)


@dataclass(frozen=True)
class ReadyBacklogFixture:
    id: str
    subject: str
    body: str


@dataclass(frozen=True)
class CandidateParse:
    id: str
    subject: str
    accepted: bool
    error_type: str | None
    error: str | None
    state: str | None


_CANDIDATE_ISSUE_CONTRACT_PROBE = r"""
import json
import pathlib
import sys

candidate_root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(candidate_root))
import noodles

request = json.load(sys.stdin)
results = []
for item in request["fixtures"]:
    try:
        contract = noodles.parse_issue_contract(item["body"], item["subject"])
    except Exception as exc:
        results.append({
            "id": item["id"],
            "subject": item["subject"],
            "accepted": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "state": None,
        })
    else:
        results.append({
            "id": item["id"],
            "subject": contract.get("subject"),
            "accepted": True,
            "error_type": None,
            "error": None,
            "state": contract.get("state"),
        })
print(json.dumps({"module_file": noodles.__file__, "results": results}, sort_keys=True))
"""


def load_ready_backlog_fixtures(root: Path) -> tuple[ReadyBacklogFixture, ...]:
    path = root / READY_BACKLOG_FIXTURE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; fixture corpus unreadable: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "fixtures"}:
        raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; fixture corpus must contain schema_version and fixtures")
    if payload["schema_version"] != 1 or isinstance(payload["schema_version"], bool):
        raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; fixture corpus schema_version must be 1")
    raw_fixtures = payload["fixtures"]
    if not isinstance(raw_fixtures, list) or not raw_fixtures:
        raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; fixture corpus fixtures must be a non-empty list")
    fixtures: list[ReadyBacklogFixture] = []
    ids: set[str] = set()
    subjects: set[str] = set()
    for raw in raw_fixtures:
        if not isinstance(raw, dict) or set(raw) != {"id", "subject", "body"}:
            raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; every fixture must contain only id, subject, and body")
        if not all(isinstance(raw[field], str) and raw[field] for field in ("id", "subject", "body")):
            raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; fixture id, subject, and body must be non-empty strings")
        fixture = ReadyBacklogFixture(raw["id"], raw["subject"], raw["body"])
        if fixture.id in ids or fixture.subject in subjects:
            raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; duplicate fixture id or subject: {fixture.id}")
        if fixture.body.count(f"<!-- noodles-subject: {fixture.subject} -->") != 1:
            raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; fixture {fixture.id} body does not bind {fixture.subject}")
        ids.add(fixture.id)
        subjects.add(fixture.subject)
        fixtures.append(fixture)
    return tuple(fixtures)


def candidate_parse(
    candidate_root: Path, fixtures: tuple[ReadyBacklogFixture, ...]
) -> dict[str, CandidateParse]:
    request = {
        "fixtures": [
            {"id": fixture.id, "subject": fixture.subject, "body": fixture.body}
            for fixture in fixtures
        ]
    }
    env = {"NOODLES_OFFLINE_TESTS": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _CANDIDATE_ISSUE_CONTRACT_PROBE, str(candidate_root.resolve())],
            cwd=candidate_root,
            env=env,
            input=json.dumps(request),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; candidate parser probe failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise AssertionError(
            f"{MIGRATION_DIAGNOSTIC}; candidate parser probe exited {completed.returncode}: {detail}"
        )
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; candidate parser probe emitted malformed JSON: {exc}") from exc
    if not isinstance(response, dict) or set(response) != {"module_file", "results"}:
        raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; candidate parser probe response shape is invalid")
    try:
        module_file = Path(response["module_file"]).resolve()
    except (TypeError, ValueError, OSError):
        module_file = None
    expected_module = (candidate_root / "noodles.py").resolve()
    if module_file != expected_module:
        raise AssertionError(
            f"{MIGRATION_DIAGNOSTIC}; candidate parser provenance {response.get('module_file')!r} "
            f"is not the exact candidate parser {expected_module}"
        ) from None
    raw_results = response["results"]
    if not isinstance(raw_results, list):
        raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; candidate parser results must be a list")
    expected_ids = {fixture.id for fixture in fixtures}
    results: dict[str, CandidateParse] = {}
    for raw in raw_results:
        if not isinstance(raw, dict) or set(raw) != {
            "id", "subject", "accepted", "error_type", "error", "state"
        }:
            raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; candidate parser result shape is invalid")
        if raw["id"] in results:
            raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; duplicate candidate parser result id {raw['id']!r}")
        results[raw["id"]] = CandidateParse(
            id=raw["id"],
            subject=raw["subject"],
            accepted=raw["accepted"],
            error_type=raw["error_type"],
            error=raw["error"],
            state=raw["state"],
        )
    if set(results) != expected_ids:
        raise AssertionError(
            f"{MIGRATION_DIAGNOSTIC}; candidate parser result ids differ: "
            f"expected {sorted(expected_ids)}, observed {sorted(results)}"
        )
    return results


def assert_tightening_migrates_fixture_set(
    trusted: tuple[ReadyBacklogFixture, ...],
    candidate: tuple[ReadyBacklogFixture, ...],
    baseline: dict[str, CandidateParse],
    migrated: dict[str, CandidateParse],
) -> None:
    trusted_by_id = {fixture.id: fixture for fixture in trusted}
    candidate_by_id = {fixture.id: fixture for fixture in candidate}
    for fixture in trusted:
        try:
            parsed = noodles.parse_issue_contract(fixture.body, fixture.subject)
        except Exception as exc:
            raise AssertionError(
                f"{MIGRATION_DIAGNOSTIC}; trusted fixture {fixture.id} is invalid: {type(exc).__name__}: {exc}"
            ) from exc
        if parsed.get("state") != "ready" or parsed.get("subject") != fixture.subject:
            raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; trusted fixture {fixture.id} is not ready")
    for fixture_id, trusted_fixture in trusted_by_id.items():
        candidate_fixture = candidate_by_id.get(fixture_id)
        if candidate_fixture is None:
            raise AssertionError(f"{MIGRATION_DIAGNOSTIC}; fixture {fixture_id} disappeared")
        if candidate_fixture.subject != trusted_fixture.subject:
            raise AssertionError(
                f"{MIGRATION_DIAGNOSTIC}; fixture {fixture_id} rebound subject "
                f"from {trusted_fixture.subject} to {candidate_fixture.subject}"
            )
        baseline_result = baseline[fixture_id]
        migrated_result = migrated[fixture_id]
        if baseline_result.accepted:
            if candidate_fixture.body != trusted_fixture.body:
                raise AssertionError(
                    f"{MIGRATION_DIAGNOSTIC}; fixture {fixture_id} changed although the candidate parser accepts its baseline"
                )
        elif candidate_fixture.body == trusted_fixture.body:
            raise AssertionError(
                f"{MIGRATION_DIAGNOSTIC}; fixture {fixture_id} newly rejected by candidate parser: "
                f"{baseline_result.error_type}: {baseline_result.error}"
            )
        elif not migrated_result.accepted or migrated_result.state != "ready" or migrated_result.subject != trusted_fixture.subject:
            raise AssertionError(
                f"{MIGRATION_DIAGNOSTIC}; fixture {fixture_id} migration is not accepted as ready: "
                f"{migrated_result.error_type}: {migrated_result.error}"
            )
    for fixture_id, candidate_fixture in candidate_by_id.items():
        result = migrated[fixture_id]
        if not result.accepted or result.state != "ready" or result.subject != candidate_fixture.subject:
            raise AssertionError(
                f"{MIGRATION_DIAGNOSTIC}; fixture {fixture_id} candidate body is not accepted as ready: "
                f"{result.error_type}: {result.error}"
            )


def assert_candidate_preserves_or_migrates_ready_backlog(trusted_root: Path, candidate_root: Path) -> None:
    trusted = load_ready_backlog_fixtures(trusted_root)
    candidate = load_ready_backlog_fixtures(candidate_root)
    baseline = candidate_parse(candidate_root, trusted)
    migrated = candidate_parse(candidate_root, candidate)
    assert_tightening_migrates_fixture_set(trusted, candidate, baseline, migrated)


def complete_issue_sections(goal: str, non_claims: str, *, claim: str | None = None) -> str:
    """ed3c/noodles#120 - the deterministic section shape a schedulable repository-mutating Issue
    must carry, with one owner so a fixture cannot drift from the contract it represents.

    ed3c/noodles#317 - the two evidence markers ride here rather than in each caller's own header
    block: they are read by a whole-body scan, this text is always prepended by the caller's markers
    and precedes the first `##`, and one owner is what let the tightening migrate every caller at
    once. `none` is the honest value for these fixtures, whose triggers claim no observation."""
    return (
        f"{ISSUE_EVIDENCE_MARKERS}\n"
        "## Physical trigger\n\nA syntactically valid ready subject can still be unimplementable.\n\n"
        f"## Goal\n\n{goal}\n\n"
        f"## Claim\n\n{claim or goal}\n\n"
        "## Physical acceptance\n\n"
        "- Positive control and planted-negative control pass.\n"
        "- Direct source readback proves the claim.\n"
        "- Zero residue after the run.\n\n"
        "## Non-case\n\nnone\n\n"
        f"## Non-claims\n\n{non_claims}\n"
    )


def code_surface_digest(root: Path, feature: feature_contract.FeatureContract = FEATURE) -> str:
    return hashlib.sha256((root / feature.code_surface).read_bytes()).hexdigest()


def write_feature_evidence(
    root: Path, head: str, feature: feature_contract.FeatureContract = FEATURE, **overrides: object
) -> Path:
    """Write an evidence packet shaped exactly like the verifier's own output, then apply planted drift."""
    evidence: dict[str, object] = {
        "feature_id": feature.feature_id,
        "head": head,
        "code_surface": feature.code_surface,
        "code_surface_sha256": code_surface_digest(root, feature),
        "operation": list(feature.operation),
        "oracle": feature.oracle,
        "observed": {"returncode": 0, "ok": True, "errors": []},
    }
    evidence.update(overrides)
    for field in [key for key, value in overrides.items() if value is None]:
        evidence.pop(field, None)
    path = root / feature_contract.EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


def acceptance_evidence(
    root: Path, head: str, feature: feature_contract.FeatureContract | None = None, **overrides: object
) -> dict[str, object]:
    specialized: dict[str, object] | None = None
    if feature is not None:
        specialized = {
            "feature_id": feature.feature_id,
            "head": head,
            "code_surface": feature.code_surface,
            "code_surface_sha256": code_surface_digest(root, feature),
            "operation": list(feature.operation),
            "oracle": feature.oracle,
            "observed": {"returncode": 0, "ok": True, "errors": []},
        }
    evidence: dict[str, object] = {
        "schema_version": 1,
        "head": head,
        "tree": cmd(["git", "rev-parse", "HEAD^{tree}"], root),
        "baseline": {
            "contract_id": feature_contract.BASELINE_CONTRACT_ID,
            "operations": [
                list(feature_contract.BASELINE_TEST_OPERATION),
                list(feature_contract.BASELINE_VERIFY_OPERATION),
            ],
            "observed": {
                "tests": {"returncode": 0},
                "verify": {"returncode": 0, "ok": True, "errors": []},
            },
        },
        "specialized": specialized,
    }
    evidence.update(overrides)
    return evidence


def write_acceptance_evidence(
    root: Path, head: str, feature: feature_contract.FeatureContract | None = None, **overrides: object
) -> Path:
    evidence = acceptance_evidence(root, head, feature, **overrides)
    path = root / feature_contract.ACCEPTANCE_EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


def cmd(argv: list[str], cwd: Path) -> str:
    result = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise AssertionError(f"command failed {argv}: {result.stderr or result.stdout}")
    return result.stdout.strip()


def initialize_repo(root: Path) -> None:
    cmd(["git", "init", "-q", "-b", "main"], root)
    cmd(["git", "config", "user.name", "tests"], root)
    cmd(["git", "config", "user.email", "tests@example.invalid"], root)
    cmd(["git", "add", "-A"], root)
    cmd(["git", "commit", "-q", "--allow-empty", "-m", "fixture"], root)


def copy_tracked(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    tracked = cmd(["git", "ls-files"], source).splitlines()
    for relative in tracked:
        src = source / relative
        dst = destination / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)
    initialize_repo(destination)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            digest.update(f"L {relative} {os.readlink(path)}\n".encode("utf-8"))
            continue
        if path.is_dir():
            digest.update(f"D {relative}\n".encode("utf-8"))
            continue
        digest.update(f"F {relative}\n".encode("utf-8"))
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def write_noodle_stub(
    path: Path, version: str, *, start_delay: float | None = None, emit_admission_receipt: bool = False
) -> None:
    start_clause = ""
    if start_delay is not None:
        admission_clause = (
            "    print('{\"admitted\": true}', file=sys.stderr, flush=True)\n" if emit_admission_receipt else ""
        )
        start_clause = (
            "elif args == ['start']:\n"
            "    import http.server\n"
            "    import json\n"
            "    import pathlib\n"
            "    import select\n"
            "    import signal\n"
            "    import threading\n"
            "    project = pathlib.Path(os.environ['NOODLES_TEST_START_PROJECT'])\n"
            "    (project / '.noodle').mkdir(parents=True, exist_ok=True)\n"
            "    (project / '.noodle' / 'noodle.lock').write_text(str(os.getpid()))\n"
            f"    time.sleep({start_delay!r})\n"
            "    (project / '.noodle' / 'status.json').write_text(\n"
            "        json.dumps({'loop_state': 'running', 'mode': 'supervised', 'max_concurrency': 4})\n"
            "    )\n"
            f"{admission_clause}"
            "    if os.environ.get('NOODLES_TEST_START_SERVE') == '1':\n"
            "        class Handler(http.server.BaseHTTPRequestHandler):\n"
            "            def do_GET(self):\n"
            "                if self.path != '/api/snapshot':\n"
            "                    self.send_response(404)\n"
            "                    self.end_headers()\n"
            "                    return\n"
            "                body = json.dumps({'pending_reviews': [], 'unclaimed_orders': []}).encode('utf-8')\n"
            "                self.send_response(200)\n"
            "                self.send_header('Content-Type', 'application/json')\n"
            "                self.send_header('Content-Length', str(len(body)))\n"
            "                self.end_headers()\n"
            "                self.wfile.write(body)\n"
            "            def log_message(self, *ignored):\n"
            "                return\n"
            "        server = http.server.HTTPServer(\n"
            "            ('127.0.0.1', int(os.environ['NOODLES_TEST_START_PORT'])), Handler\n"
            "        )\n"
            "        server.timeout = 0.05\n"
            "        stop_requested = threading.Event()\n"
            "        signal.signal(signal.SIGTERM, lambda *_ignored: stop_requested.set())\n"
            "        while not stop_requested.is_set():\n"
            "            server.handle_request()\n"
            "        drain_budget = 8\n"
            "        while drain_budget > 0 and select.select([server.fileno()], [], [], 0.02)[0]:\n"
            "            server.handle_request()\n"
            "            drain_budget -= 1\n"
            "        server.server_close()\n"
        )
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        "import time\n"
        "args = sys.argv[1:]\n"
        f"if args == ['--version']:\n    print({version!r})\n"
        "elif len(args) >= 4 and args[0] == '--project-dir' and args[2:] == ['skills', 'list']:\n"
        "    print(os.environ.get('NOODLES_TEST_SKILLS_OUTPUT', ''), end='')\n"
        f"{start_clause}"
        "else:\n"
        "    raise SystemExit(f'unexpected args: {args}')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_handoff_noodle_stub(path: Path, version: str, blocking: bool = True) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import pathlib\n"
        "import subprocess\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        f"if args == ['--version']:\n    print({version!r})\n"
        "elif len(args) >= 5 and args[0] == '--project-dir' and args[2:4] == ['event', 'emit']:\n"
        "    root = pathlib.Path(args[1])\n"
        "    event_type = args[4]\n"
        "    session = ''\n"
        "    payload = {}\n"
        "    index = 5\n"
        "    while index < len(args):\n"
        "        if args[index] == '--session':\n"
        "            session = args[index + 1]\n"
        "            index += 2\n"
        "            continue\n"
        "        if args[index] == '--payload':\n"
        "            payload = json.loads(args[index + 1])\n"
        "            index += 2\n"
        "            continue\n"
        "        raise SystemExit(f'unexpected args: {args}')\n"
        "    if event_type == 'stage_message':\n"
        f"        payload['blocking'] = {blocking!r}\n"
        "    event = {'type': event_type, 'payload': payload, 'timestamp': '2026-08-29T00:00:00Z', 'session_id': session}\n"
        "    target = root / '.noodle' / 'sessions' / session / 'events.ndjson'\n"
        "    with target.open('a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps(event) + '\\n')\n"
        "elif len(args) >= 4 and args[:2] == ['worktree', 'exec']:\n"
        "    root = pathlib.Path(os.getcwd()).resolve()\n"
        "    worktree_name = args[2]\n"
        "    command = args[3:]\n"
        "    if not (root / '.noodle').is_dir():\n"
        "        raise SystemExit(f'cwd is not a Noodle project root: {root}')\n"
        "    worktree_path = None\n"
        "    sessions = root / '.noodle' / 'sessions'\n"
        "    for spawn in sessions.glob('*/spawn.json'):\n"
        "        payload = json.loads(spawn.read_text())\n"
        "        candidate_path = pathlib.Path(str(payload.get('worktree_path') or '')).expanduser()\n"
        "        candidate_name = str(payload.get('worktree_name') or candidate_path.name)\n"
        "        if candidate_name == worktree_name:\n"
        "            worktree_path = candidate_path\n"
        "            break\n"
        "    if worktree_path is None:\n"
        "        raise SystemExit(f'unknown worktree: {worktree_name}')\n"
        "    completed = subprocess.run(command, cwd=str(worktree_path), text=True, check=False)\n"
        "    raise SystemExit(completed.returncode)\n"
        "else:\n"
        "    raise SystemExit(f'unexpected args: {args}')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def execute_branch_name(subject: str) -> str:
    return noodles.execute_branch(subject)


def handoff_fixture(
    source: Path,
    subject: str = "ed3c/noodles#33",
    *,
    blocking: bool = True,
    worktree_name: str | None = None,
) -> tuple[tempfile.TemporaryDirectory[str], Path, Path, str]:
    worktree_name = worktree_name or execute_branch_name(subject)
    temp = tempfile.TemporaryDirectory(prefix="noodles-handoff-test-", ignore_cleanup_errors=True)
    root = Path(temp.name) / "repo"
    copy_tracked(source, root)
    cmd(["git", "remote", "add", "origin", "git@github.com:ed3c/noodles.git"], root)
    binary = Path(temp.name) / "noodle"
    write_handoff_noodle_stub(binary, "v0.1.5", blocking)
    lock_path = root / "policy/runtime.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["runtime"]["command"] = str(binary)
    lock["runtime"]["platforms"]["darwin_arm64"]["binary_sha256"] = runtime_contract.sha256_file(binary)
    lock_path.write_text(json.dumps(lock))
    cmd(["git", "add", "policy/runtime.lock.json"], root)
    cmd(["git", "commit", "-q", "-m", "lock handoff runtime"], root)
    cmd(["git", "checkout", "-q", "-b", worktree_name], root)
    cmd(["git", "commit", "-q", "--allow-empty", "-m", f"execute {subject}"], root)
    session_id = "ed3c-noodles-33-0-execute-fixture"
    session = root / ".noodle" / "sessions" / session_id
    session.mkdir(parents=True)
    (session / "spawn.json").write_text(json.dumps({"worktree_path": str(root), "worktree_name": worktree_name}))
    (session / "events.ndjson").write_text(json.dumps({
        "type": "action",
        "payload": {"message": f"[order:{subject}] fixture"},
        "timestamp": "2026-08-29T00:00:00Z",
        "session_id": session_id,
    }) + "\n")
    return temp, root, binary, session_id


def provider_fixture(subpath: str = "skills/control-noodle", license_path: str = "LICENSE") -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-provider-test-", ignore_cleanup_errors=True)
    base = Path(temp.name)
    candidate = base / "candidate"
    copy_tracked(CANDIDATE_ROOT, candidate)
    source = base / "source"
    source.mkdir()
    initialize_repo(source)
    (source / "LICENSE").write_text("MIT\n")
    skill_root = source / "skills/control-noodle"
    skill_root.mkdir(parents=True)
    skill_file = skill_root / "SKILL.md"
    skill_file.write_text("# Control Noodle\n")
    skill_tree_sha256 = tree_digest(skill_root)
    admission_path = source / "admissions/control-noodle.json"
    admission_path.parent.mkdir(parents=True, exist_ok=True)
    admission_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skill": "control-noodle",
                "status": "ADMITTED",
                "subject_files": [
                    {
                        "path": "skills/control-noodle/SKILL.md",
                        "sha256": runtime_contract.sha256_file(skill_file),
                    }
                ],
                "skill_tree_sha256": skill_tree_sha256,
            }
        )
    )
    cmd(["git", "add", "-A"], source)
    cmd(["git", "commit", "-q", "-m", "provider"], source)
    commit = cmd(["git", "rev-parse", "HEAD"], source)
    lock_path = candidate / "policy/providers.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["providers"] = [
        {
            "name": "fixture",
            "source": str(source),
            "commit": commit,
            "subpath": subpath,
            "destination": ".noodle/providers/fixture",
            "license_path": license_path,
            "admission": {
                "path": "admissions/control-noodle.json",
                "sha256": runtime_contract.sha256_file(admission_path),
                "skill": "control-noodle",
                "skill_tree_sha256": skill_tree_sha256,
                "subject_files": {
                    "skills/control-noodle/SKILL.md": runtime_contract.sha256_file(skill_file),
                },
            },
            "enabled": True,
            "authority": "P",
        }
    ]
    lock_path.write_text(json.dumps(lock))
    cmd(["git", "add", "-A"], candidate)
    cmd(["git", "commit", "-q", "-m", "lock fixture"], candidate)
    return temp, candidate


def cursor_pstack_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-cursor-provider-test-", ignore_cleanup_errors=True)
    base = Path(temp.name)
    candidate = base / "candidate"
    copy_tracked(CANDIDATE_ROOT, candidate)
    source = base / "source"
    source.mkdir()
    initialize_repo(source)
    (source / "pstack/LICENSE").parent.mkdir(parents=True, exist_ok=True)
    (source / "pstack/LICENSE").write_text("MIT\n")
    (source / "cursor-team-kit/LICENSE").parent.mkdir(parents=True, exist_ok=True)
    (source / "cursor-team-kit/LICENSE").write_text("MIT\n")
    for skill in runtime_contract.CURSOR_PSTACK_REQUIRED_NATIVE_SKILLS:
        skill_dir = source / "pstack/skills" / skill
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {skill}\n")
    poteto_playbooks = source / "pstack/skills/poteto-mode/playbooks"
    poteto_playbooks.mkdir(parents=True, exist_ok=True)
    for name in ("investigation.md", "feature.md", "multi-phase-plan.md"):
        (poteto_playbooks / name).write_text(f"# {name}\n")
    for skill in ("control-cli", "deslop", "control-ui"):
        skill_dir = source / "cursor-team-kit/skills" / skill
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {skill}\n")
    extra = source / "cursor-team-kit/skills/review-and-ship"
    extra.mkdir(parents=True)
    (extra / "SKILL.md").write_text("# review-and-ship\n")
    cmd(["git", "add", "-A"], source)
    cmd(["git", "commit", "-q", "-m", "provider"], source)
    commit = cmd(["git", "rev-parse", "HEAD"], source)
    lock_path = candidate / "policy/providers.lock.json"
    lock = json.loads(lock_path.read_text())
    providers = lock["providers"]
    providers[0]["source"] = str(source)
    providers[0]["commit"] = commit
    providers[0]["destination"] = runtime_contract.CURSOR_PSTACK_DESTINATION
    lock_path.write_text(json.dumps(lock))
    cmd(["git", "add", "-A"], candidate)
    cmd(["git", "commit", "-q", "-m", "lock fixture"], candidate)
    return temp, candidate


# constraint: ed3c/noodles#359 - three attempts, because the observed rate is a low-single-digit
# constraint: percentage per clone (see clone_fixture) and a fixture that burns a whole hosted job on
# constraint: a 1-in-a-million triple is not cheaper than one that retries twice.
FIXTURE_CLONE_ATTEMPTS = 3


def clone_fixture(source: Path, destination: Path, cwd: Path) -> None:
    """Clone a fixture repository in a form a concurrent write into `source`'s git dir cannot red.

    ed3c/noodles#359 - the setup-side sibling of the ed3c/noodles#319 teardown race. The wave-18 tail
    lost a `candidate-self-tests` run at SETUP to `git clone ... fatal: hardlink different from
    source`; the teardown cure is scoped to cleanup and explicitly does not reach here.

    The reproduction the issue's Goal asks for was run - 150 clones of a locally-written repo against
    a thread committing, repacking and pruning it, per form - and it kills the obvious cure. The
    default hardlinking form failed 4/150, three of them the exact recorded `fatal: hardlink
    different from source` (on a `.pack`, an `.idx` and `objects/info/commit-graph`). `--no-hardlinks`
    failed 3/150, with `failed to copy file to '...': No such file or directory` and one
    `update_ref failed ... nonexistent object`. Disabling hardlinks MOVES the failure, it does not
    remove it, so shipping that flag would have been a cure carrying a receipt for another mechanism.
    `--no-local` is no better: it hands the same racing object store to `upload-pack`.

    What every observed form has in common is that the failure is in ACQUIRING the source's objects,
    not in what the clone means, and setup is not part of what any control asserts - the same reason
    ed3c/noodles#319 gives for teardown. So the disposition, not the mechanism, is fixed: a clone that
    lost the race leaves nothing behind and is taken again. A source that is genuinely broken still
    fails, `FIXTURE_CLONE_ATTEMPTS` times, and `cmd` raises with git's own diagnostic.

    Ceiling, stated rather than implied: this makes the fixture race-immune, not git. A production
    clone racing a writer is a different problem with a different owner."""
    for attempt in range(FIXTURE_CLONE_ATTEMPTS):
        try:
            cmd(["git", "clone", "-q", str(source), str(destination)], cwd)
            return
        except AssertionError:
            if attempt == FIXTURE_CLONE_ATTEMPTS - 1:
                raise
            shutil.rmtree(destination, ignore_errors=True)


def control_checkout_fixture(source: Path = CANDIDATE_ROOT) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-control-checkout-test-", ignore_cleanup_errors=True)
    base = Path(temp.name)
    provider = base / "provider"
    copy_tracked(source, provider)
    control = base / "control"
    clone_fixture(provider, control, base)
    cmd(["git", "config", "user.name", "tests"], control)
    cmd(["git", "config", "user.email", "tests@example.invalid"], control)
    return temp, control, provider


def write_skill_discovery_fixture(
    candidate: Path,
    *,
    compat_skills: tuple[str, ...] = runtime_contract.CURSOR_PSTACK_COMPAT_SKILLS,
    playbooks: tuple[str, ...] = ("investigation.md", "feature.md", "multi-phase-plan.md"),
) -> str:
    project_root = (candidate / runtime_contract.PROJECT_SKILLS_ROOT).resolve()
    cursor_root = (candidate / runtime_contract.CURSOR_PSTACK_NATIVE_ROOT).resolve()
    compat_source_root = (
        candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT
    ).resolve()
    control_noodle_source_root = (candidate / runtime_contract.CONTROL_NOODLE_DISCOVERY_ROOT).resolve()

    poteto_skill = cursor_root / "poteto-mode"
    poteto_skill.mkdir(parents=True, exist_ok=True)
    (poteto_skill / "SKILL.md").write_text("# Poteto Mode\n")
    playbook_root = poteto_skill / "playbooks"
    playbook_root.mkdir(exist_ok=True)
    for name in playbooks:
        (playbook_root / name).write_text(f"# {name}\n")

    output_lines = []
    for skill in runtime_contract.PROJECT_REQUIRED_SKILLS:
        project_skill = (candidate / runtime_contract.PROJECT_SKILLS_ROOT / skill).resolve()
        output_lines.append(f"{skill}\t{project_root}\ttrue\t{project_skill}")
    for skill in runtime_contract.CURSOR_PSTACK_REQUIRED_NATIVE_SKILLS:
        skill_dir = cursor_root / skill
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            skill_file.write_text(f"# {skill}\n")
        output_lines.append(f"{skill}\t{cursor_root}\ttrue\t{skill_dir}")

    for skill in compat_skills:
        source_dir = compat_source_root / skill
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "SKILL.md").write_text(f"# {skill}\n")
        mapped_dir = project_root / skill
        mapped_dir.mkdir(exist_ok=True)
        target = source_dir / "SKILL.md"
        os.symlink(os.path.relpath(target, start=mapped_dir), mapped_dir / "SKILL.md")
        output_lines.append(f"{skill}\t{project_root}\ttrue\t{mapped_dir}")

    control_noodle_source_root.mkdir(parents=True, exist_ok=True)
    (control_noodle_source_root / "SKILL.md").write_text("# Control Noodle\n")
    control_noodle_root = project_root / runtime_contract.CONTROL_NOODLE_SKILL
    control_noodle_root.mkdir(exist_ok=True)
    os.symlink(os.path.relpath(control_noodle_source_root / "SKILL.md", start=control_noodle_root), control_noodle_root / "SKILL.md")
    output_lines.append(f"{runtime_contract.CONTROL_NOODLE_SKILL}\t{project_root}\ttrue\t{control_noodle_root}")
    return "\n".join(output_lines) + "\n"


RUNTIME_LOCK_FIELDS = {"repository", "release", "commit", "command", "platforms"}
RUNTIME_PLATFORM_FIELDS = {"asset_name", "asset_sha256", "binary_sha256"}


def runtime_lock_shape_errors(root: Path) -> list[str]:
    """ed3c/noodles#315 - judge `root`'s runtime pin by shape, derivation and internal consistency.

    This replaced a strict-equal literal of the whole `runtime` object in
    `tests/test_noodles.py::test_runtime_lock_pins_expected_release`. That literal lived in a module
    `pull_request_target` supplies from the DEFAULT BRANCH while the value it compared came from the
    candidate, so a candidate that legitimately bumped the Noodle release computed new bytes, was
    compared against a dict only `main` could hold, and could never merge to update it.

    Trusted authority is kept, not weakened: `runtime_contract.validate_runtime_lock` is the shipped
    judge of repository identity, v-semver release, 40-hex commit and 64-hex digests, so it is
    delegated to rather than restated. Added here is only what the literal was carrying that the
    production judge does not - the exact field sets, and the derivation that ties each platform's
    asset name to its own platform key, which is the internal consistency a copy-pasted platform
    block breaks and a whole-object literal could only catch by memorizing the answer."""
    errors = list(runtime_contract.validate_runtime_lock(root))
    try:
        runtime = json.loads((root / "policy/runtime.lock.json").read_text(encoding="utf-8"))["runtime"]
        platforms = runtime["platforms"]
        items = sorted(platforms.items())
    except (OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        return [*errors, f"runtime lock is unreadable as a runtime object: {exc}"]
    if set(runtime) != RUNTIME_LOCK_FIELDS:
        errors.append(f"runtime field set is {sorted(runtime)}, expected exactly {sorted(RUNTIME_LOCK_FIELDS)}")
    for platform_key, item in items:
        if not isinstance(item, dict) or set(item) != RUNTIME_PLATFORM_FIELDS:
            errors.append(f"runtime platform {platform_key} field set is wrong, expected exactly {sorted(RUNTIME_PLATFORM_FIELDS)}")
            continue
        expected_asset = f"noodle_{platform_key}.tar.gz"
        if item["asset_name"] != expected_asset:
            errors.append(
                f"runtime platform {platform_key} asset_name {item['asset_name']!r} is not derived "
                f"from its own key: expected {expected_asset!r}"
            )
    return errors


def runtime_release_reader(release: str, commit: str, asset_name: str, asset_sha256: str):
    def read(endpoint: str) -> dict:
        if endpoint == f"repos/poteto/noodle/releases/tags/{release}":
            return {
                "tag_name": release,
                "assets": [{"name": asset_name, "digest": f"sha256:{asset_sha256}"}],
            }
        if endpoint == f"repos/poteto/noodle/git/ref/tags/{release}":
            return {"object": {"type": "commit", "sha": commit}}
        raise AssertionError(f"unexpected endpoint {endpoint}")

    return read


def script_mode_gateerror_identity(root: Path = CANDIDATE_ROOT) -> dict[str, object]:
    script = (
        "import importlib.util, json, sys\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[1]).resolve()\n"
        "sys.modules.pop('noodles', None)\n"
        "sys.modules.pop('repair_contract', None)\n"
        "spec = importlib.util.spec_from_file_location('__main__', root / 'noodles.py')\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['__main__'] = module\n"
        "sys.argv = ['noodles.py', '--root', str(root), 'verify']\n"
        "try:\n"
        "    spec.loader.exec_module(module)\n"
        "except SystemExit:\n"
        "    pass\n"
        "import repair_contract\n"
        "import noodles\n"
        "engine = repair_contract._engine()\n"
        "print(json.dumps({'main_module': module.__name__, 'engine_module': engine.__name__, 'same_gate_error_identity': module.GateError is engine.GateError, 'split_gate_error_identity': module.GateError is noodles.GateError}))\n"
    )
    result = subprocess.run(
        ["python3", "-c", script, str(root)],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"script mode GateError readback failed: {result.stderr or result.stdout}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def validate_script_mode_gateerror_identity(readback: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if (readback.get("main_module"), readback.get("engine_module")) != ("__main__", "__main__"):
        errors.append(f"repair path resolved wrong module identity: {readback}")
    if readback.get("same_gate_error_identity") is not True:
        errors.append("repair path did not preserve one GateError identity")
    if readback.get("split_gate_error_identity") is not False:
        errors.append("legacy split GateError identity remains observable in script mode")
    return errors


def _write_fake_gh_stub(path: Path, *, release: str, commit: str, asset_name: str, asset_sha256: str) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if not args or args[0] != 'api':\n    raise SystemExit(f'unexpected args: {args}')\n"
        "rest = args[1:]\n"
        "include = False\n"
        "if rest and rest[0] == '--include':\n    include = True\n    rest = rest[1:]\n"
        "if rest[:2] != ['--method', 'GET']:\n    raise SystemExit(f'unexpected args: {args}')\n"
        "endpoint = rest[2]\n"
        f"release = {release!r}\ncommit = {commit!r}\nasset_name = {asset_name!r}\nasset_sha256 = {asset_sha256!r}\n"
        "if endpoint == f'repos/poteto/noodle/releases/tags/{release}':\n"
        "    body = {'tag_name': release, 'assets': [{'name': asset_name, 'digest': f'sha256:{asset_sha256}'}]}\n"
        "elif endpoint == f'repos/poteto/noodle/git/ref/tags/{release}':\n"
        "    body = {'object': {'type': 'commit', 'sha': commit}}\n"
        "elif endpoint == 'repos/ed3c/noodles/branches/main/protection':\n"
        "    body = {'required_status_checks': {'strict': True, 'contexts': ['verify', 'candidate-self-tests']}, 'enforce_admins': {'enabled': True}, 'required_pull_request_reviews': {'required_approving_review_count': 0}, 'allow_force_pushes': {'enabled': False}, 'allow_deletions': {'enabled': False}}\n"
        "else:\n    raise SystemExit(f'unexpected endpoint: {endpoint}')\n"
        "if include:\n    sys.stdout.write('HTTP/1.1 200 OK\\nETag: test\\nX-GitHub-Request-Id: test\\n\\n')\n"
        "sys.stdout.write(json.dumps(body))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _lock_start_runtime(root: Path, binary: Path, *, release: str, commit: str, asset_sha256: str) -> None:
    platform_key = runtime_contract.resolve_platform_key(error_cls=AssertionError)
    asset_name = f"noodle_{platform_key}.tar.gz"
    lock_path = root / "policy/runtime.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["runtime"] = {
        "repository": "poteto/noodle",
        "release": release,
        "commit": commit,
        "command": "noodle",
        "platforms": {
            platform_key: {
                "asset_name": asset_name,
                "asset_sha256": asset_sha256,
                "binary_sha256": runtime_contract.sha256_file(binary),
            }
        },
    }
    lock_path.write_text(json.dumps(lock), encoding="utf-8")


def write_fake_codex_stub(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "cwd = Path.cwd().resolve()\n"
        "home = Path(os.environ.get('HOME', '~')).expanduser().resolve()\n"
        "codex_home = Path(os.environ.get('CODEX_HOME', str(home))).resolve()\n"
        "skill_rows = []\n"
        "roots = []\n"
        "for idx, root in enumerate([codex_home / 'skills', home / '.agents' / 'skills', cwd / '.agents' / 'skills']):\n"
        "    roots.append((f'r{idx}', str(root.resolve())))\n"
        "    if not root.is_dir():\n"
        "        continue\n"
        "    for skill in sorted(root.iterdir()):\n"
        "        if (skill / 'SKILL.md').is_file():\n"
        "            skill_rows.append((skill.name, f'r{idx}/{skill.name}/SKILL.md'))\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['debug', 'prompt-input']:\n"
        "    skills_block = '\\n'.join(f'- {name}: planted (file: {raw})' for name, raw in skill_rows)\n"
        "    roots_block = '\\n'.join(f'- `{name}` = `{root}`' for name, root in roots)\n"
        "    text = '### Skill roots\\n' + roots_block + '\\n### Available skills\\n' + skills_block + '\\n</skills_instructions>'\n"
        "    print(json.dumps([{'role': 'developer', 'content': [{'type': 'input_text', 'text': text}]}]))\n"
        "elif args == ['plugin', 'list', '--json']:\n"
        "    print(json.dumps({'installed': [], 'available': []}))\n"
        "else:\n"
        "    raise SystemExit(f'unexpected args: {args}')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_codex_real_bin_probe(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "self_path = Path(__file__).resolve()\n"
        "override = os.environ.get('NOODLES_CODEX_REAL_BIN', '').strip()\n"
        "if override:\n"
        "    print(override)\n"
        "    raise SystemExit(0)\n"
        "for entry in os.environ.get('PATH', '').split(os.pathsep):\n"
        "    candidate = Path(entry or '.') / 'codex'\n"
        "    try:\n"
        "        resolved = candidate.resolve()\n"
        "    except OSError:\n"
        "        continue\n"
        "    if resolved == self_path:\n"
        "        continue\n"
        "    if candidate.is_file() and os.access(candidate, os.X_OK):\n"
        "        print(str(candidate))\n"
        "        raise SystemExit(0)\n"
        "raise SystemExit('NOODLES_CODEX_WRAPPER_FAIL: cannot resolve real codex binary')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def codex_real_bin_export(base: Path) -> str | None:
    if os.getenv("NOODLES_OFFLINE_TESTS") != "1":
        return None
    fake_codex = base / "codex-real-fixture"
    write_fake_codex_stub(fake_codex)
    return str(fake_codex)


def codex_real_bin_resolution(*, override: Path | None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="noodles-codex-real-bin-probe-", ignore_cleanup_errors=True) as temp_name:
        base = Path(temp_name)
        probe = base / "resolve_codex.py"
        write_codex_real_bin_probe(probe)
        env = os.environ.copy()
        env["PATH"] = str(base)
        if override is not None:
            env["NOODLES_CODEX_REAL_BIN"] = str(override)
        else:
            env.pop("NOODLES_CODEX_REAL_BIN", None)
        result = subprocess.run(
            [sys.executable, str(probe)],
            cwd=base,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _free_tcp_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


# constraint: 3s grace bounds the wait for the entrypoint's own admission receipt line after the harness poller already saw a served readback - long enough for a genuinely admitting entrypoint's line to land, short enough to keep the suite fast when it never does
ADMISSION_RECEIPT_GRACE_SECONDS = 3.0


def start_entrypoint_with_delayed_listener(
    delay: float = 0.25,
    interval: float = 0.05,
    *,
    start_listener: bool = True,
    runtime_start_delay: float = 0.7,
    emit_admission_receipt: bool = False,
) -> dict[str, object]:
    temp, candidate = cursor_pstack_fixture()
    with temp:
        base = Path(temp.name)
        release = "v9.9.9"
        commit = "1" * 40
        asset_sha256 = "2" * 64
        bin_dir = base / "bin"
        bin_dir.mkdir()
        runtime = bin_dir / "noodle"
        write_noodle_stub(
            runtime, release, start_delay=runtime_start_delay, emit_admission_receipt=emit_admission_receipt
        )
        _lock_start_runtime(candidate, runtime, release=release, commit=commit, asset_sha256=asset_sha256)
        cmd(["git", "add", "policy/runtime.lock.json"], candidate)
        cmd(["git", "commit", "-q", "-m", "runtime fixture"], candidate)
        temp_control, control, provider = control_checkout_fixture(candidate)
        try:
            fake_gh = bin_dir / "gh"
            platform_key = runtime_contract.resolve_platform_key(error_cls=AssertionError)
            _write_fake_gh_stub(
                fake_gh,
                release=release,
                commit=commit,
                asset_name=f"noodle_{platform_key}.tar.gz",
                asset_sha256=asset_sha256,
            )
            output = write_skill_discovery_fixture(control)
            port = _free_tcp_port()
            control_url = f"http://127.0.0.1:{port}"
            listener_ready = threading.Event()
            listener_served = threading.Event()
            listener_stop = threading.Event()
            listener_state: dict[str, object] = {
                "listener_ready": False,
                "listener_served": False,
                "listener_request_count": 0,
                "listener_thread_alive": False,
                "listener_error": None,
                "listener_bound_port": port,
                "listener_response": None,
                "entrypoint_path": str(control / "noodles"),
                "entrypoint_exists": (control / "noodles").exists(),
            }

            def poll_listener() -> None:
                import urllib.error
                import urllib.request

                if not start_listener:
                    return
                try:
                    while not listener_stop.is_set():
                        try:
                            with urllib.request.urlopen(f"{control_url}/api/snapshot", timeout=0.05) as response:
                                listener_state["listener_ready"] = True
                                listener_ready.set()
                                body = json.loads(response.read().decode("utf-8"))
                                listener_state["listener_request_count"] = (
                                    int(listener_state["listener_request_count"]) + 1
                                )
                                listener_state["listener_response"] = body
                                listener_state["listener_served"] = True
                                listener_served.set()
                                return
                        except (urllib.error.URLError, OSError):
                            pass
                        listener_stop.wait(0.02)
                except Exception as exc:
                    listener_state["listener_error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    listener_stop.set()

            terminator_stop = threading.Event()
            admission_timeout = max(5.0, delay * 8)
            stderr_path = base / "start-entrypoint.stderr"
            stderr_path.write_text("", encoding="utf-8")
            listener_state["admission_receipt_seen"] = False
            listener_state["admission_wait_seconds"] = None

            def terminate_runtime_when_ready() -> None:
                # constraint: 15s ceiling only guards a genuinely broken (never-serving) listener from hanging the suite; happy path returns in well under a second
                deadline = time.monotonic() + 15
                while (
                    not listener_served.is_set()
                    and not terminator_stop.is_set()
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)
                if terminator_stop.is_set():
                    return
                # constraint: see ADMISSION_RECEIPT_GRACE_SECONDS above for the grace ceiling rationale
                grace_start = time.monotonic()
                grace_deadline = grace_start + ADMISSION_RECEIPT_GRACE_SECONDS
                while not terminator_stop.is_set() and time.monotonic() < grace_deadline:
                    stderr_so_far = stderr_path.read_text(encoding="utf-8", errors="replace").replace(" ", "")
                    if '"admitted":true' in stderr_so_far:
                        listener_state["admission_receipt_seen"] = True
                        break
                    time.sleep(0.02)
                listener_state["admission_wait_seconds"] = time.monotonic() - grace_start
                if terminator_stop.is_set():
                    return
                lock_path = control / ".noodle" / "noodle.lock"
                if not lock_path.exists():
                    return
                try:
                    pid = int(lock_path.read_text().strip())
                except (OSError, ValueError):
                    return
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

            listener_thread = threading.Thread(target=poll_listener, name="start-entrypoint-listener")
            listener_thread.start()
            terminator_thread = threading.Thread(
                target=terminate_runtime_when_ready, name="start-entrypoint-terminator", daemon=True
            )
            terminator_thread.start()
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            env["PYTHONPATH"] = str(CANDIDATE_ROOT)
            env["NOODLES_TEST_ALLOW_LOCAL_PROVIDER"] = "1"
            env["NOODLES_TEST_SKILLS_OUTPUT"] = output
            env["NOODLES_TEST_START_PROJECT"] = str(control)
            env["NOODLES_TEST_START_PORT"] = str(port)
            env["NOODLES_TEST_START_SERVE"] = "1" if start_listener else "0"
            codex_real_bin = codex_real_bin_export(base)
            if codex_real_bin is not None:
                env["NOODLES_CODEX_REAL_BIN"] = codex_real_bin
            with stderr_path.open("w", encoding="utf-8") as stderr_sink:
                result = subprocess.run(
                    [
                        str(control / "noodles"),
                        "start",
                        "--control-url",
                        control_url,
                        "--interval",
                        str(interval),
                        "--admission-timeout",
                        str(admission_timeout),
                    ],
                    cwd=control,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=stderr_sink,
                    check=False,
                )
            listener_stop.set()
            terminator_stop.set()
            listener_thread.join(timeout=2)
            terminator_thread.join(timeout=2)
            listener_state["listener_thread_alive"] = listener_thread.is_alive()
            lock_path = control / ".noodle" / "noodle.lock"
            status_path = control / ".noodle" / "status.json"
            runtime_lock_pid = lock_path.read_text().strip() if lock_path.exists() else None
            runtime_status = json.loads(status_path.read_text()) if status_path.exists() else None
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": stderr_path.read_text(encoding="utf-8", errors="replace"),
                "runtime_lock_pid": runtime_lock_pid,
                "runtime_status": runtime_status,
                "control_port": port,
                "listener_after_exit": daemon_lease.listener_pids("127.0.0.1", port),
                "lease_after_exit": daemon_lease.read_lease(control)[1],
                **listener_state,
            }
        finally:
            temp_control.cleanup()


def validate_start_entrypoint_receipt(receipt: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if receipt.get("returncode") != 0:
        errors.append(f"entrypoint returned {receipt.get('returncode')!r}: {receipt.get('stderr', '')}")
    stderr = str(receipt.get("stderr") or "")
    connection_refusal_diagnosed = (
        "repair: Noodle control request failed" in stderr
        or '"admitted":' in stderr
        or "noodles-start" in stderr
    )
    if not connection_refusal_diagnosed:
        errors.append("wrapper never diagnosed startup connection refusal on repair path")
    if '"admitted":true' not in stderr.replace(" ", ""):
        errors.append("wrapper never admitted a truthful Noodle daemon lease")
    if f'"listener_pids":[' not in stderr.replace(" ", ""):
        errors.append("listener ownership readback missing from the admission receipt")
    if "listener-absent" in stderr or "admission-timeout" in stderr:
        errors.append("listener never became reachable within bounded admission")
    if '"loop_state":"running"' not in stderr.replace(" ", ""):
        errors.append("listener never served snapshot readback with a live runtime status")
    if "Traceback" in stderr:
        errors.append("wrapper terminated with traceback instead of failing closed")
    if receipt.get("entrypoint_exists") is not True:
        errors.append(f"documented entrypoint missing at {receipt.get('entrypoint_path')}")
    if receipt.get("listener_after_exit") != []:
        errors.append(f"listener residue remained after subprocess exit: {receipt.get('listener_after_exit')}")
    if not str(receipt.get("lease_after_exit") or ""):
        errors.append("failed startup did not preserve the runtime lease evidence")
    return errors


def assert_valid_start_entrypoint_receipt(receipt: dict[str, object]) -> None:
    errors = validate_start_entrypoint_receipt(receipt)
    if errors:
        raise AssertionError("; ".join(errors))


def graphql_backlog_payload(issues: list[dict], pulls: list[dict] | tuple = ()) -> dict:
    """One GraphQL bulk-sync response in the exact shape `noodles.backlog_graphql_snapshot` reads.

    ed3c/noodles#292 - fixtures state the backlog once, in REST-ish shape, and this projects it into
    the single query that replaced the per-issue REST fan-out.
    """
    return {
        "data": {
            "repository": {
                "issues": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "number": issue["number"],
                            "title": issue.get("title") or "",
                            "body": issue.get("body") or "",
                            "url": issue.get("html_url") or "",
                            "state": str(issue.get("state") or "open").upper(),
                        }
                        for issue in issues
                    ],
                },
                "pullRequests": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": list(pulls)},
            }
        }
    }


@contextlib.contextmanager
def backlog_project():
    """A throwaway Noodle project, so a sync's cycle record never lands in the real checkout."""
    with tempfile.TemporaryDirectory(prefix="noodles-backlog-project-", ignore_cleanup_errors=True) as name:
        project = Path(name)
        (project / ".noodle").mkdir()
        with mock.patch.dict(os.environ, {"NOODLE_PROJECT_DIR": str(project)}, clear=False):
            yield project
