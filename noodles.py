#!/usr/bin/env python3
"""Small deterministic policy/evidence layer around Noodle and GitHub; requires Python, git, gh, and noodle."""
from __future__ import annotations
import argparse
import ast
import codex_isolation
import collections
import daemon_lease
import feature_contract
import fnmatch
import hashlib
import github_protection
import issue_contract
import json
import math
import os
import re
import retrieval_contract
import schedule_domain
import runtime_contract
import select
import signal
import skill_contract
import stat
import structural_contract
import subprocess
import sys
import tempfile
import time
import tokenize
import tomllib
import trusted_preview
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from claim_contract import sweep_dead_claims
from disposition_contract import sweep_closure_dispositions
from repair_contract import REPAIR_MAX_ATTEMPTS, repair_pending_reviews, repair_review
from runtime_contract import (
    blocking_handoff_readback,
    control_checkout_admission as runtime_control_checkout_admission,
    emit_blocking_handoff,
    emit_handoff_rerun_intent,
    gh_repo_from_git as runtime_gh_repo_from_git,
    handoff_rerun_intent_readback,
    provider_check as runtime_provider_check,
    provider_sync as runtime_provider_sync,
    reconcile_checkout_admission as runtime_reconcile_checkout_admission,
    resolve_locked_runtime_binary,
    runtime_check as runtime_binary_check,
    skill_discovery_check,
    validate_handoff_session,
    validate_runtime_lock,
)
from skill_contract import (
    validate_agent_document_route,
    validate_agent_guarantee_classes,
    validate_backlog_scheduler,
    validate_concurrency_proof,
    validate_execute_task,
    validate_noodle_worktree_ignore,
    validate_policy_key_consumption,
)
SCHEMA_VERSION = 1
# constraint: ed3c/noodles#99 - the exact entrypoint an open-PR refusal routes to; repair owns an
# constraint: existing PR (repair_contract.find_open_pr_for_subject), scheduling never re-attempts it.
OPEN_PR_REPAIR_OWNER = "./noodles repair"
ALLOWED_MIGRATION_STATES = {"MIGRATE", "REVALIDATE", "ADAPT_EXTERNAL", "DROP", "HOLD"}
ALLOWED_ISSUE_STATES = {"ready", "in_progress", "awaiting_land", "landed", "blocked"}
SUBJECT_RE = issue_contract.SUBJECT_RE
MARKER_PATTERNS = {
    "role": re.compile(r"<!--\s*noodles-role:\s*([^>]+?)\s*-->", re.I),
    "target": re.compile(r"<!--\s*noodles-target:\s*([^>]+?)\s*-->", re.I),
    "subject": re.compile(r"<!--\s*noodles-subject:\s*([^>]+?)\s*-->", re.I),
    "state": re.compile(r"<!--\s*noodles-state:\s*([^>]+?)\s*-->", re.I),
    "feature": re.compile(r"<!--\s*noodles-feature:\s*([^>]+?)\s*-->", re.I),
    "component": re.compile(r"<!--\s*noodles-component:\s*([^>]+?)\s*-->", re.I),
    "requirement": re.compile(r"<!--\s*noodles-requirement:\s*([^>]+?)\s*-->", re.I),
    "depends_on": re.compile(r"<!--\s*noodles-depends-on:\s*([^>]+?)\s*-->", re.I),
    "write_boundary": re.compile(r"<!--\s*noodles-write-boundary:\s*([^>]+?)\s*-->", re.I),
    "executor": re.compile(r"<!--\s*noodles-executor:\s*([^>]+?)\s*-->", re.I),
    "runtime": re.compile(r"<!--\s*noodles-runtime:\s*([^>]+?)\s*-->", re.I),
    "evidence": re.compile(r"<!--\s*noodles-evidence:\s*([^>]+?)\s*-->", re.I),
    "blocker": re.compile(r"<!--\s*noodles-blocker:\s*([^>]+?)\s*-->", re.I),
    "normalized": re.compile(r"<!--\s*noodles-normalized:\s*([0-9a-f]{64})\s*-->", re.I),
    "landed_pr": re.compile(r"<!--\s*noodles-landed-pr:\s*([^>]+?)\s*-->", re.I),
    "head": re.compile(r"<!--\s*noodles-head:\s*([0-9a-f]{40})\s*-->", re.I),
    "merge": re.compile(r"<!--\s*noodles-merge:\s*([0-9a-f]{40})\s*-->", re.I),
}
REF_RE = re.compile(r"(?m)^Refs\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*)\s*$")
COMPONENT_MAP_PATH = "policy/components.json"
COMPONENT_OWNER_MAP_PATH = "policy/component-owners.json"
SUPERVISE_LOG_RELATIVE = ".noodle/supervise.log"
SUPERVISE_TAIL_LINES = 40
SUPERVISE_POLL_SECONDS = 1.0
SUPERVISE_TERMINATE_GRACE = 10.0
DEFAULT_WEDGE_SECONDS = 1500.0
DEFAULT_ROTATE_AFTER_SECONDS = 3000.0
DEFAULT_RESTART_BACKOFF_SECONDS = 180.0
RATE_LIMIT_TAIL_RE = re.compile(r"rate limit", re.IGNORECASE)
SECONDARY_BURST_REMAINING = 500
SECONDARY_BURST_COOLDOWN_SECONDS = 180.0
RATE_LIMIT_COOLDOWN_CEILING_SECONDS = 4000.0
RATE_LIMIT_COOLDOWN_FALLBACK_SECONDS = 600.0
RATE_LIMIT_RESET_MARGIN_SECONDS = 60.0
# constraint: ed3c/noodles#291 - the carrier is the only component that sees the balance, so it
# constraint: declares the wait in one exact line and every deadline above it reads that line
# constraint: rather than re-deriving a wait nobody else can observe.
DECLARED_QUOTA_WAIT_RE = re.compile(r"NOODLES_GH_QUOTA_WAIT:[^\n]*?recoverable-wait[ \t]+(\d+)s")
CYCLE_STATUS_MEANINGS = {
    "ok": "the generation exited zero and the bucket never refused it",
    "quota_wait": "the generation stopped on a declared provider quota wait; recoverable, backoff runs until the bucket's own reset",
    "failed": "the generation exited non-zero for a reason the provider budget does not explain",
}
# constraint: ed3c/noodles#292 - one pointed query on GraphQL's separate point budget in place of
# constraint: the per-issue REST fan-out. Bodies come with the issues; the open pull requests a
# constraint: later cycle correlates against come with the same round trip.
BACKLOG_GRAPHQL_QUERY = """
query($owner: String!, $name: String!, $issues: String, $pulls: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, states: [OPEN], after: $issues, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes { number title body url state }
    }
    pullRequests(first: 100, states: [OPEN], after: $pulls) {
      pageInfo { hasNextPage endCursor }
      nodes { number body url headRefName }
    }
  }
}
"""
BACKLOG_GRAPHQL_PAGE_LIMIT = 50
BACKLOG_CYCLE_PREFIX = ".noodle/backlog-cycle-"
BACKLOG_EMPTY_BASE_SECONDS = 180.0
BACKLOG_EMPTY_CEILING_SECONDS = 3600.0
TOKEN_COMMAND_ENV = "NOODLES_TOKEN_COMMAND"
GH_CARRIER_RELATIVE = ".agents/bin/gh"
COMPONENT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
COMPARE_FILES_CEILING = 300
COMPONENT_INTRODUCTION_HEADING = "component introduction"
COMPONENT_INTRODUCTION_QUESTIONS = (
    "which invalid state does this make impossible?",
    "why can't strengthening the nearest existing contract close the same failure?",
)
# constraint: a pinned unit is any lock object carrying one of these identity keys; bumping such a key's value keeps the unit's path identical, so version bumps stay outside introduction detection.
PINNING_KEYS = frozenset({"commit", "version", "release", "digest", "binary_sha256", "asset_sha256"})
AUTO_CLOSE_RE = re.compile(r"(?im)^\s*(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#[0-9]+")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
P0_TITLE_RE = re.compile(r"^\[[A-Za-z0-9][A-Za-z0-9-]*-P0\](?:\s|$)")
N_CLASS_PREFIXES = ("docs/research/", "docs/design/")
N_CLASS_EVIDENCE_RE = re.compile(
    r"(?im)^[ \t]*(?:[-*+][ \t]+)?\*{0,2}(claim|acceptance|evidence)\*{0,2}[ \t]*:[^\n]*?"
    + r"((?:" + "|".join(prefix.rstrip("/") for prefix in N_CLASS_PREFIXES) + r")/[^\s`)\]]*)"
)
TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".toml", ".yml", ".yaml", ".txt"}
EXEC_SUFFIXES = {".py", ".sh"}
ALLOWED_COMMENT_TAGS = ("# constraint:", "# ponytail:")
# constraint: this module's own tree carries the one committed task-profile definition it verifies
# constraint: a target tree against, so a mutated copy's drifted policy still fails closed here.
ENGINE_ROOT = Path(__file__).resolve().parent
class GateError(RuntimeError):
    """A fail-closed policy or physical readback failure."""
@dataclass(frozen=True)
class Subject:
    repo: str
    number: int
    @property
    def value(self) -> str:
        return f"{self.repo}#{self.number}"
def repo_root(path: str | Path | None = None) -> Path:
    candidate = Path(path or Path(__file__).resolve().parent).resolve()
    if candidate.is_file():
        candidate = candidate.parent
    return candidate

def run(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(argv),
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        command = " ".join(argv)
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise GateError(f"command failed: {command}: {detail}")
    return result
def git(root: Path, *args: str, check: bool = True) -> str:
    return run(["git", *args], cwd=root, check=check).stdout.strip()

def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot read JSON {path}: {exc}") from exc
def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

def parse_subject(raw: str) -> Subject:
    match = SUBJECT_RE.fullmatch(raw.strip())
    if not match:
        raise GateError(f"invalid exact subject: {raw!r}")
    return Subject(match.group("repo"), int(match.group("number")))
def one_marker(body: str, name: str, required: bool = True) -> str | None:
    # constraint: ed3c/noodles#120 monitor reconcile - this stays a whole-body scan, unlike
    # constraint: declared_markers below. Audited: test_duplicate_component_markers_fail_closed and
    # constraint: test_duplicate_marker_fails_closed both plant a duplicate marker appended after the
    # constraint: body's last section and require GateError; header-only scoping (declared_markers'
    # constraint: fix for `requirement`) would silently admit that duplicate as "documentation" and
    # constraint: regress both tests. `requirement` is safe to header-scope because its own
    # constraint: multiplicity is handled by parse_requirements; the other markers here intentionally
    # constraint: catch a duplicate anywhere in the body. No live Issue body, template, or fixture in
    # constraint: this repo currently quotes one of these markers' own syntax inside a `##` section
    # constraint: the way ed3c/noodles#120's own body does for `requirement` - so the dead-example
    # constraint: failure class is a real latent risk for this shared caller, not a reproduced one.
    matches = MARKER_PATTERNS[name].findall(body or "")
    if not matches:
        if required:
            raise GateError(f"missing noodles-{name.replace('_', '-')} marker")
        return None
    if len(matches) != 1:
        raise GateError(f"expected one noodles-{name.replace('_', '-')} marker, found {len(matches)}")
    return matches[0].strip()
def declared_markers(body: str, name: str) -> list[str]:
    """Every declaration of a bounded-multiplicity marker, in authored order, read only from the
    body's marker header - the text above the first `##` section.

    A marker printed inside a section is documentation, not a declaration. ed3c/noodles#120's own
    body prints this marker's syntax in its `## Required typed surface` section, and a whole-body
    scan reads that example as a second, unresolvable binding - the same dead-example failure
    ed3c/noodles#84 removed from the document gates."""
    header = body or ""
    first_section = issue_contract.SECTION_RE.search(header)
    if first_section:
        header = header[: first_section.start()]
    return [match.strip() for match in MARKER_PATTERNS[name].findall(header)]
def requirement_definition_source(root: Path) -> Path:
    """Node 2 of the declared Agent document route: the specification that owns stable requirement
    identities. The pointer is read from `policy/fitness.json`, which `validate_agent_document_route`
    already owns, so this atom introduces no fourth document hop and no second copy of the path."""
    route = load_json(root / "policy/fitness.json").get("agent_document_route") or []
    if len(route) < 2 or not str(route[1]).endswith(".md"):
        raise GateError("agent document route declares no specification node for requirement identities")
    return root / str(route[1])
def system_requirement_ids(root: Path | None = None) -> frozenset[str]:
    try:
        text = requirement_definition_source(root or ENGINE_ROOT).read_text(encoding="utf-8")
    except (GateError, OSError) as exc:
        raise GateError(f"stable requirement definitions are unreadable: {exc}") from exc
    return issue_contract.requirement_ids(text)
def parse_issue_contract(body: str, expected_subject: str | None = None) -> dict[str, Any]:
    role = one_marker(body, "role")
    target = one_marker(body, "target")
    subject_value = one_marker(body, "subject")
    state_value = one_marker(body, "state")
    feature_value = one_marker(body, "feature", required=False)
    component_value = one_marker(body, "component", required=False)
    if component_value is not None and not COMPONENT_NAME_RE.fullmatch(component_value):
        raise GateError(f"noodles-component must name one lowercase component token from {COMPONENT_MAP_PATH}, got {component_value!r}")
    if role != "repository-mutating-atom":
        raise GateError(f"unsupported noodles-role: {role}")
    subject = parse_subject(subject_value or "")
    if target != subject.repo:
        raise GateError(f"target {target!r} does not match subject repository {subject.repo!r}")
    if expected_subject and subject.value != expected_subject:
        raise GateError(f"issue subject {subject.value} does not match expected {expected_subject}")
    if state_value not in ALLOWED_ISSUE_STATES:
        raise GateError(f"unsupported noodles-state: {state_value}")
    offending = N_CLASS_EVIDENCE_RE.search(body or "")
    if offending:
        raise GateError(f"{offending.group(1).lower()} field must cite a machine artifact, not N-class prose: {offending.group(2)}")
    declared = one_marker(body, "depends_on", required=False)
    dependencies = None if declared is None else list(issue_contract.parse_dependencies(declared, subject.value, error_cls=GateError))
    write_boundary = issue_contract.parse_write_boundary(one_marker(body, "write_boundary", required=False))
    # constraint: ed3c/noodles#187 - a duplicate marker fails in one_marker, a
    # constraint: malformed or unknown value fails in the token parser, and a
    # constraint: missing marker parses to None so admission can name it undeclared;
    # constraint: four separate diagnostics, all before any claim or branch exists.
    executor = issue_contract.parse_executor(one_marker(body, "executor", required=False), error_cls=GateError)
    runtime_token = issue_contract.parse_capability("runtime", one_marker(body, "runtime", required=False), error_cls=GateError)
    evidence = issue_contract.parse_capability("evidence", one_marker(body, "evidence", required=False), error_cls=GateError)
    blocker = issue_contract.parse_blocker(one_marker(body, "blocker", required=False), state_value or "", error_cls=GateError)
    # constraint: ed3c/noodles#120 - bounded multiplicity, so this marker parses into ids plus named
    # constraint: diagnostics instead of raising: a malformed declaration must reach the frontier as
    # constraint: an unschedulable Issue with an exact reason, never as an Issue schedule_snapshot
    # constraint: silently drops.
    requirements, requirement_errors = issue_contract.parse_requirements(declared_markers(body, "requirement"))
    return {
        "role": role,
        "target": target or "",
        "subject": subject.value,
        "state": state_value or "",
        "feature": feature_value or "",
        "component": component_value or "",
        "requirements": list(requirements),
        "requirement_errors": list(requirement_errors),
        "dependencies": dependencies,
        "write_boundary": write_boundary,
        "executor": executor,
        "runtime": runtime_token,
        "evidence": evidence,
        "admission": issue_contract.executor_admission(executor, runtime_token, evidence),
        "blocker": blocker,
    }


def replace_marker(body: str, name: str, value: str) -> str:
    pattern = MARKER_PATTERNS[name]
    replacement = f"<!-- noodles-{name.replace('_', '-')}: {value} -->"
    matches = pattern.findall(body or "")
    if len(matches) > 1:
        raise GateError(f"cannot replace ambiguous noodles-{name.replace('_', '-')} marker")
    if matches:
        return pattern.sub(replacement, body, count=1)
    prefix = body.rstrip()
    return f"{prefix}\n{replacement}\n" if prefix else replacement + "\n"
def parse_pr_reference(body: str) -> str:
    if AUTO_CLOSE_RE.search(body or ""):
        raise GateError("auto-close keywords are forbidden; provider lander closes the issue")
    lines = (body or "").splitlines()
    refs = REF_RE.findall(body or "")
    if len(lines) != 1 or len(refs) != 1 or lines[0] != f"Refs {refs[0]}":
        raise GateError("PR body must be exactly one 'Refs owner/repo#N' line")
    return parse_subject(refs[0]).value
def tracked_entries(root: Path) -> list[tuple[str, str]]:
    raw = run(["git", "ls-files", "-z", "--stage"], cwd=root).stdout
    entries: list[tuple[str, str]] = []
    for record in raw.split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        mode = meta.split(" ", 1)[0]
        entries.append((mode, path))
    return entries


def text_line_count(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return 0
    if not text:
        return 0
    return len(text.splitlines())
def repository_metrics(root: Path) -> dict[str, Any]:
    entries = tracked_entries(root)
    regular = [(mode, path) for mode, path in entries if mode in {"100644", "100755"}]
    line_counts: dict[str, int] = {}
    markdown_lines = 0
    executable_lines = 0
    test_lines = 0
    for _, relative in regular:
        path = root / relative
        lines = text_line_count(path) if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"noodles"} else 0
        line_counts[relative] = lines
        if path.suffix.lower() == ".md":
            markdown_lines += lines
        if relative.startswith("tests/"):
            test_lines += lines
        elif path.suffix.lower() in EXEC_SUFFIXES or relative in {"noodles", ".noodle/adapters/github"}:
            executable_lines += lines
    total_lines = sum(line_counts.values())
    nonzero = [count for count in line_counts.values() if count > 0]
    entropy = 0.0
    normalized_entropy = 0.0
    if nonzero and sum(nonzero) > 0:
        total = float(sum(nonzero))
        entropy = -sum((count / total) * math.log2(count / total) for count in nonzero)
        normalized_entropy = entropy / math.log2(len(nonzero)) if len(nonzero) > 1 else 0.0
    roots = sorted({path.split("/", 1)[0] if "/" in path else "<root-files>" for _, path in regular})
    workflows = [path for _, path in regular if path.startswith(".github/workflows/")]
    providers_path = root / "policy/providers.lock.json"
    enabled_providers = 0
    if providers_path.exists():
        lock = load_json(providers_path)
        enabled_providers = sum(1 for provider in lock.get("providers", []) if provider.get("enabled"))
    claims_text = "\n".join(
        (root / path).read_text(encoding="utf-8", errors="ignore")
        for _, path in regular
        if path in {"AGENTS.md", "contracts/system-v1.md"}
    )
    claim_counts = {kind: len(re.findall(rf"(?m)^\|\s*{kind}-", claims_text)) for kind in "PLRN"}
    return {
        "schema_version": SCHEMA_VERSION,
        "tracked_files": len(regular),
        "root_surfaces": len(roots),
        "root_surface_names": roots,
        "total_text_lines": total_lines,
        "markdown_lines": markdown_lines,
        "markdown_share": round(markdown_lines / total_lines, 6) if total_lines else 0.0,
        "executable_lines": executable_lines,
        "test_lines": test_lines,
        "test_to_executable_ratio": round(test_lines / executable_lines, 6) if executable_lines else 0.0,
        "max_file_lines": max(line_counts.values(), default=0),
        "max_file": max(line_counts, key=line_counts.get) if line_counts else None,
        "line_entropy_bits": round(entropy, 6),
        "normalized_line_entropy": round(normalized_entropy, 6),
        "runtime_dependency_count": 0,
        "enabled_external_providers": enabled_providers,
        "workflow_count": len(workflows),
        "claim_counts": claim_counts,
    }
def metrics_readback(root: Path, policy_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    policy_root = (policy_root or root).resolve()
    return skill_contract.metrics_readback(
        repository_metrics(root),
        load_json(policy_root / "policy/fitness.json"),
    )


def validate_provider_lock(root: Path, max_enabled: int) -> list[str]:
    errors: list[str] = []
    path = root / "policy/providers.lock.json"
    if not path.exists():
        return ["missing policy/providers.lock.json"]
    try:
        payload = load_json(path)
        providers = payload["providers"]
    except (GateError, KeyError, TypeError) as exc:
        return [f"invalid provider lock: {exc}"]
    names: set[str] = set()
    enabled = 0
    enabled_names: set[str] = set()
    for item in providers:
        try:
            name = str(item["name"])
            commit = str(item["commit"])
            source = str(item["source"])
            subpath = str(item["subpath"])
            destination = str(item["destination"])
            license_path = str(item["license_path"])
        except (KeyError, TypeError) as exc:
            errors.append(f"provider entry missing field: {exc}")
            continue
        if name == runtime_contract.RETIRED_PROVIDER:
            errors.append(f"provider {name} is retired and must not remain in the lock")
        if name in names:
            errors.append(f"duplicate provider name: {name}")
        names.add(name)
        if not HEX40_RE.fullmatch(commit):
            errors.append(f"provider {name} is not pinned to an exact 40-hex commit")
        if not source.startswith("https://github.com/") and os.getenv("NOODLES_TEST_ALLOW_LOCAL_PROVIDER") != "1":
            errors.append(f"provider {name} source must be a GitHub HTTPS URL")
        if Path(subpath).is_absolute() or ".." in Path(subpath).parts:
            errors.append(f"provider {name} has unsafe subpath")
        if not destination.startswith(".noodle/providers/") or ".." in Path(destination).parts:
            errors.append(f"provider {name} destination must stay under .noodle/providers")
        if Path(license_path).is_absolute() or ".." in Path(license_path).parts:
            errors.append(f"provider {name} has unsafe license path")
        admission = item.get("admission")
        if admission is not None:
            errors.extend(runtime_contract.validate_admission_policy(name, admission))
        if item.get("enabled"):
            enabled += 1
            enabled_names.add(name)
    if enabled > max_enabled:
        errors.append(f"enabled providers {enabled} exceed limit {max_enabled}")
    errors.extend(runtime_contract.validate_enabled_provider_names(enabled_names)); return errors
def validate_migration_ledger(root: Path) -> list[str]:
    path = root / "migrations/skills-shared/ledger.json"
    if not path.exists():
        return ["missing migration ledger"]
    try:
        payload = load_json(path)
        capabilities = payload["capabilities"]
    except (GateError, KeyError, TypeError) as exc:
        return [f"invalid migration ledger: {exc}"]
    errors: list[str] = []
    ids: set[str] = set()
    for item in capabilities:
        identifier = str(item.get("id", ""))
        disposition = item.get("disposition")
        if not identifier or identifier in ids:
            errors.append(f"missing or duplicate migration id: {identifier!r}")
        ids.add(identifier)
        if disposition not in ALLOWED_MIGRATION_STATES:
            errors.append(f"{identifier}: invalid disposition {disposition!r}")
        if not item.get("claim") or not item.get("non_claims"):
            errors.append(f"{identifier}: claim and non_claims are required")
        evidence = item.get("physical_evidence", [])
        if disposition == "MIGRATE" and not evidence:
            errors.append(f"{identifier}: MIGRATE requires physical evidence")
    return errors
def validate_comment_tags(root: Path, paths: Iterable[str]) -> list[str]:
    errors: list[str] = []
    for python_path in sorted(path for path in paths if path.endswith(".py")):
        try:
            with (root / python_path).open("rb") as handle:
                for token in tokenize.tokenize(handle.readline):
                    if token.type == tokenize.COMMENT and not (token.start[0] == 1 and token.string.startswith("#!")) and not token.string.startswith(ALLOWED_COMMENT_TAGS):
                        errors.append(f"untagged comment {python_path}:{token.start[0]}: {token.string}")
        except (OSError, SyntaxError, IndentationError, UnicodeDecodeError, tokenize.TokenizeError) as exc:
            errors.append(f"comment scan failed for {python_path}: {exc}")
    for other_path in sorted(path for path in paths if path.endswith(".sh") or path.endswith(".toml")):
        try:
            lines = (root / other_path).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            errors.append(f"comment scan failed for {other_path}: {exc}")
            continue
        for lineno, line in enumerate(lines, start=1):
            stripped = line.lstrip()
            if stripped.startswith("#") and not (lineno == 1 and stripped.startswith("#!")) and not stripped.startswith(ALLOWED_COMMENT_TAGS):
                errors.append(f"untagged comment {other_path}:{lineno}: {stripped}")
    return errors


def validate_task_profile_single_source(root: Path, paths: set[str], policy: dict[str, Any], profiles: dict[str, dict[str, str]]) -> list[str]:
    # constraint: an admitted task model may be written down only in policy/fitness.json and in the
    # constraint: exempt surfaces that cannot read it (Noodle's own .noodle.toml, frozen provider
    # constraint: fixtures); every other tracked file must derive it, so a sixth literal fails here.
    errors: list[str] = []
    exempt = set(policy["task_profile_literal_exempt_paths"])
    for missing in sorted(exempt - paths):
        errors.append(f"task profile literal exemption names an untracked path: {missing}")
    models = sorted({profile["model"] for profile in profiles.values()})
    for relative in sorted(paths - exempt):
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for model in models:
            if model in text:
                errors.append(f"{relative} pins task model {model!r}; derive it from policy/fitness.json via skill_contract.task_profiles")
    return errors


def verify_repository(root: Path, policy_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    policy_root = (policy_root or root).resolve()
    policy = load_json(policy_root / "policy/fitness.json")
    errors: list[str] = []
    expected_task_profiles = skill_contract.task_profiles(ENGINE_ROOT)
    required_task_profiles = policy.get("required_codex_task_profiles")
    if required_task_profiles != expected_task_profiles: errors.append(f"policy required_codex_task_profiles must be exactly {expected_task_profiles!r}")
    try:
        entries = tracked_entries(root)
    except GateError as exc:
        return {"ok": False, "errors": [str(exc)], "metrics": {}, "introduces": []}
    allowed_modes = {"100644", "100755"}
    for mode, relative in entries:
        if mode not in allowed_modes:
            errors.append(f"forbidden git mode {mode}: {relative}")
    paths = {relative for _, relative in entries}
    errors.extend(validate_task_profile_single_source(root, paths, policy, expected_task_profiles))
    errors.extend(validate_noodle_worktree_ignore(root, paths))
    errors.extend(validate_agent_document_route(root, paths, policy))
    # constraint: ed3c/noodles#277 - reads the CANDIDATE's own policy/fitness.json, not policy_root's:
    # constraint: an orphan key must red on the candidate that added it, which is exactly the gate
    # constraint: that would have caught the six orphan workflow phrase lists ed3c/noodles#84 removed.
    errors.extend(validate_policy_key_consumption(root, paths))
    for required in policy["required_paths"]:
        if required not in paths:
            errors.append(f"missing required tracked path: {required}")
    forbidden_names = set(policy["forbidden_path_names"])
    for relative in paths:
        parts = set(Path(relative).parts)
        if parts & forbidden_names or relative.startswith(".noodle/providers/") or relative.startswith(".noodle/runtime/"):
            errors.append(f"forbidden tracked residue: {relative}")
    forbidden_manifests = set(policy["forbidden_dependency_manifests"])
    errors.extend(f"runtime dependency manifest forbidden: {path}" for path in sorted(paths & forbidden_manifests))
    try:
        noodle_config = tomllib.loads((root / ".noodle.toml").read_text(encoding="utf-8"))
        if noodle_config.get("mode") != policy["required_noodle_mode"]:
            errors.append(f".noodle.toml mode must be {policy['required_noodle_mode']!r}")
        schedule_profile = required_task_profiles.get("schedule") if isinstance(required_task_profiles, dict) else None
        schedule_model = schedule_profile.get("model") if isinstance(schedule_profile, dict) else None
        if noodle_config.get("routing", {}).get("defaults", {}).get("model") != schedule_model: errors.append(f".noodle.toml routing model must be schedule model {schedule_model!r}")
        errors.extend(codex_isolation.validate_codex_agent_config(root, noodle_config))
        errors.extend(runtime_contract.validate_skill_config_paths([str(path) for path in noodle_config.get("skills", {}).get("paths", [])]))
        adapter_scripts = noodle_config.get("adapters", {}).get("backlog", {}).get("scripts", {})
        expected_adapter = ".noodle/adapters/github"
        for action in ("sync", "add", "edit", "done"):
            if not str(adapter_scripts.get(action, "")).startswith(expected_adapter + " "):
                errors.append(f"backlog adapter action {action} must route through {expected_adapter}")
        errors.extend(validate_concurrency_proof(root, noodle_config))
        errors.extend(validate_backlog_scheduler(root, noodle_config))
        errors.extend(validate_execute_task(root, noodle_config))
        errors.extend(runtime_contract.validate_execute_route_bundle_contract(root))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"invalid .noodle.toml: {exc}")
    errors.extend(validate_runtime_lock(root))
    errors.extend(validate_provider_lock(root, int(policy["max_enabled_providers"])))
    errors.extend(structural_contract.validate_parser_lock(root))
    errors.extend(retrieval_contract.validate_retrieval_lock(root))
    errors.extend(validate_migration_ledger(root))
    for executable in policy["required_executables"]:
        full = root / executable
        if full.exists() and not (full.stat().st_mode & stat.S_IXUSR):
            errors.append(f"required executable bit missing: {executable}")
    for python_path in sorted(path for path in paths if path.endswith(".py")):
        try:
            compile((root / python_path).read_text(encoding="utf-8"), python_path, "exec")
        except (OSError, SyntaxError) as exc:
            errors.append(f"python syntax failed for {python_path}: {exc}")
    for shell_path in sorted(path for path in paths if path.endswith(".sh") or path == "noodles"):
        result = run(["bash", "-n", str(root / shell_path)], check=False)
        if result.returncode != 0:
            errors.append(f"shell syntax failed for {shell_path}: {result.stderr.strip()}")
    errors.extend(validate_comment_tags(root, paths))
    errors.extend(findings_register_errors(root, policy_root))
    schedule_receipt = root / ".noodle/schedule-cycle.json"
    if schedule_receipt.exists():
        try:
            errors.extend(skill_contract.validate_cycle_receipt(load_json(schedule_receipt)))
        except GateError as exc:
            errors.append(f"schedule cycle receipt unreadable: {exc}")
    # constraint: ed3c/noodles#84 - the AGENTS.md exact-phrase grep that stood here is retired: it
    # constraint: proved the bytes existed somewhere, not that the document owned the rule.
    # constraint: ed3c/noodles#277 closed that staged transition by deleting the orphaned policy list
    # constraint: the retired read used to consume; the key-consumption gate above now names any
    # constraint: successor orphan by its own key rather than letting it sit as a fictional gate.
    errors.extend(validate_agent_guarantee_classes(root))
    workflow_paths = sorted(path for path in paths if path.startswith(".github/workflows/"))
    if len(workflow_paths) != policy["max_workflows"]:
        errors.append(f"workflow count must equal {policy['max_workflows']}, got {len(workflow_paths)}")
    workflow_boundary_errors, _workflow_boundary = github_protection.workflow_boundary_readback(root, sha256_file)
    errors.extend(workflow_boundary_errors)
    metrics_result = metrics_readback(root, policy_root)
    metrics = {key: value for key, value in metrics_result.items() if key not in {"warnings", "warning_readback"}}
    for key, (direction, policy_key) in skill_contract.FAILING_FITNESS_LIMITS.items():
        threshold = policy[policy_key]
        value = metrics[key]
        if skill_contract.threshold_exceeded(value, direction, threshold):
            errors.append(skill_contract.failing_fitness_message(key, value, direction, threshold))
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": metrics_result["warnings"],
        "warning_readback": metrics_result["warning_readback"],
        "metrics": metrics,
        "introduces": introduced_components(policy_root, root),
    }
def provider_check(root: Path) -> list[dict[str, Any]]:
    return runtime_provider_check(root, error_cls=GateError)
def provider_sync(root: Path) -> list[dict[str, Any]]:
    return runtime_provider_sync(root, error_cls=GateError)
def runtime_check(root: Path) -> dict[str, Any]:
    return runtime_binary_check(root, gh_api, error_cls=GateError)
def runtime_discovery(root: Path) -> dict[str, Any]:
    runtime_receipt = runtime_check(root)
    discovery_receipt = skill_discovery_check(root, runtime_receipt["binary_path"], error_cls=GateError)
    return {"runtime": runtime_receipt, "skills": discovery_receipt}


def _preflight_command(
    capability: str,
    argv: Sequence[str],
    *,
    root: Path,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = run(argv, cwd=root, input_text=input_text, check=False, timeout=3.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"preflight missing capability: {capability}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise GateError(f"preflight missing capability: {capability}: {detail}")
    return result


def _preflight_provider_network(root: Path) -> dict[str, Any]:
    capability = "provider network reach"
    try:
        providers = runtime_contract.provider_items(root, error_cls=GateError)
    except GateError as exc:
        raise GateError(f"preflight missing capability: {capability}: {exc}") from exc
    names: list[str] = []
    for provider in providers:
        name = provider.get("name")
        source = provider.get("source")
        if not isinstance(name, str) or not name or not isinstance(source, str) or not source:
            raise GateError(f"preflight missing capability: {capability}: enabled provider has no name or source")
        _preflight_command(capability, ["git", "ls-remote", "--exit-code", source, "HEAD"], root=root)
        names.append(name)
    return {"capability": capability, "providers": names}


def _preflight_gh_auth(root: Path) -> dict[str, Any]:
    capability = "gh auth readback"
    try:
        repository = runtime_gh_repo_from_git(root, error_cls=GateError)
    except GateError as exc:
        raise GateError(f"preflight missing capability: {capability}: {exc}") from exc
    observed = _preflight_command(
        capability,
        ["gh", "api", f"repos/{repository}", "--jq", ".full_name"],
        root=root,
    ).stdout.strip()
    if observed != repository:
        raise GateError(
            f"preflight missing capability: {capability}: repository readback {observed!r} != {repository!r}"
        )
    return {"capability": capability, "repository": repository}


def _preflight_git_metadata(root: Path) -> dict[str, Any]:
    capability = "git metadata write"
    head = _preflight_command(capability, ["git", "rev-parse", "HEAD"], root=root).stdout.strip()
    tree = _preflight_command(capability, ["git", "rev-parse", "HEAD^{tree}"], root=root).stdout.strip()
    root_digest = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    scratch_ref = f"refs/noodles/preflight/{root_digest}-{os.getpid()}"
    created_commit: str | None = None
    try:
        created_commit = _preflight_command(
            capability,
            ["git", "commit-tree", tree, "-p", head],
            root=root,
            input_text=f"noodles preflight {root_digest}-{os.getpid()}\n",
        ).stdout.strip()
        if not HEX40_RE.fullmatch(created_commit):
            raise GateError(f"preflight missing capability: {capability}: commit-tree returned no commit")
        _preflight_command(
            capability,
            ["git", "update-ref", scratch_ref, created_commit, "0" * 40],
            root=root,
        )
        observed = _preflight_command(capability, ["git", "rev-parse", scratch_ref], root=root).stdout.strip()
        if observed != created_commit:
            raise GateError(f"preflight missing capability: {capability}: scratch ref readback drifted")
    finally:
        if created_commit:
            try:
                cleanup = run(
                    ["git", "update-ref", "-d", scratch_ref, created_commit],
                    cwd=root,
                    check=False,
                    timeout=3.0,
                )
                residue = run(
                    ["git", "show-ref", "--verify", "--quiet", scratch_ref],
                    cwd=root,
                    check=False,
                    timeout=3.0,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise GateError(f"preflight missing capability: {capability}: cleanup failed: {exc}") from exc
            if cleanup.returncode != 0 or residue.returncode == 0:
                detail = cleanup.stderr.strip() or cleanup.stdout.strip() or "scratch ref remains"
                raise GateError(f"preflight missing capability: {capability}: cleanup failed: {detail}")
    return {"capability": capability, "scratch_ref_deleted": True}


def _preflight_feature_verify(root: Path) -> dict[str, Any]:
    capability = "feature-verify tool presence"
    _preflight_command(capability, [str(root / "noodles"), "feature", "verify", "--help"], root=root)
    return {"capability": capability, "command": "./noodles feature verify <feature-id>"}


def preflight(root: Path) -> dict[str, Any]:
    root = root.resolve()
    probes = (
        _preflight_provider_network,
        _preflight_gh_auth,
        _preflight_git_metadata,
        _preflight_feature_verify,
    )
    return {"schema_version": 1, "ok": True, "capabilities": [probe(root) for probe in probes]}


def gh_api(endpoint: str, *, method: str = "GET", payload: Any | None = None, token: str | None = None) -> Any:
    # constraint: ed3c/noodles#291 - headers are requested on every machine call so the rate-limit
    # constraint: balance reaches the carrier, which is the only component positioned to act on it.
    # constraint: Callers still receive the body alone; nothing above this line changes shape.
    _headers, body = github_protection.gh_api_response(
        run,
        GateError,
        endpoint,
        method=method,
        payload=payload,
        token=token,
        include_headers=True,
    )
    return body


def issue_read(subject_value: str) -> dict[str, Any]:
    subject = parse_subject(subject_value)
    issue = gh_api(f"repos/{subject.repo}/issues/{subject.number}")
    if not isinstance(issue, dict) or "pull_request" in issue:
        raise GateError(f"subject does not resolve to an issue: {subject_value}")
    parse_issue_contract(issue.get("body") or "", expected_subject=subject_value)
    return issue
def issue_set_state(subject_value: str, new_state: str) -> dict[str, Any]:
    if new_state not in ALLOWED_ISSUE_STATES:
        raise GateError(f"unsupported issue state: {new_state}")
    subject = parse_subject(subject_value)
    issue = issue_read(subject_value)
    if new_state == "blocked" and not one_marker(issue.get("body") or "", "blocker", required=False):
        raise GateError(f"{subject_value} cannot become blocked without a noodles-blocker owner/reason; dependency waiting is derived from provider readback")
    body = replace_marker(issue.get("body") or "", "state", new_state)
    gh_api(f"repos/{subject.repo}/issues/{subject.number}", method="PATCH", payload={"body": body})
    readback = issue_read(subject_value)
    contract = parse_issue_contract(readback.get("body") or "", expected_subject=subject_value)
    if contract["state"] != new_state:
        raise GateError(f"issue state readback failed for {subject_value}")
    return readback


def dependency_readback(subject_value: str) -> dict[str, Any]:
    """Read one predecessor's own provider truth; a failed read never reads as satisfied."""
    try:
        issue = issue_read(subject_value)
        contract = parse_issue_contract(issue.get("body") or "", expected_subject=subject_value)
    except GateError as exc:
        return {"subject": subject_value, "provider_state": None, "state": None, "error": str(exc)}
    return {"subject": subject_value, "provider_state": issue.get("state"), "state": contract["state"], "error": None}


def issue_contract_readback(subject_value: str, dependency_cache: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Read-only typed Issue contract with dependency eligibility derived from provider readback."""
    return issue_contract_payload(issue_read(subject_value), subject_value, dependency_cache)


def issue_contract_payload(
    issue: dict[str, Any],
    subject_value: str | None,
    dependency_cache: dict[str, dict[str, Any]] | None = None,
    known_requirements: frozenset[str] | None = None,
) -> dict[str, Any]:
    # constraint: ed3c/noodles#120 monitor reconcile - known_requirements defaults to a fresh
    # constraint: system_requirement_ids() call for callers that read one Issue at a time, but a
    # constraint: batch caller over many issues (schedule_snapshot, adapter_sync) must resolve it
    # constraint: ONCE outside their per-issue `except GateError` boundary and pass it in here. Read
    # constraint: inside that per-issue try, a spec-unreadable GateError fires identically for every
    # constraint: issue and each is silently dropped in turn - the whole backlog vanishes with no
    # constraint: diagnostic instead of one loud top-level failure.
    body = issue.get("body") or ""
    contract = parse_issue_contract(body, expected_subject=subject_value)
    cache = dependency_cache if dependency_cache is not None else {}
    observed = {}
    for dependency in contract["dependencies"] or ():
        # constraint: ed3c/noodles#292 - `setdefault` evaluates its default even on a hit, so the
        # constraint: cache was reading every predecessor once per dependent instead of once.
        if dependency not in cache:
            cache[dependency] = dependency_readback(dependency)
        observed[dependency] = cache[dependency]
    body_sections = issue_contract.sections(body)
    resolved_requirements = known_requirements if known_requirements is not None else system_requirement_ids()
    derived = issue_contract.derive_schedulability(
        contract, str(issue.get("state") or ""), observed, body_sections, resolved_requirements
    )
    return {
        "subject": contract["subject"],
        "target": contract["target"],
        "feature": contract["feature"],
        "state": contract["state"],
        "provider_state": issue.get("state"),
        "url": issue.get("html_url"),
        "body_sha256": issue_contract.body_digest(body),
        "requirements": contract["requirements"],
        "dependencies": contract["dependencies"],
        "write_boundary": contract["write_boundary"],
        "executor": contract["executor"],
        "runtime": contract["runtime"],
        "evidence": contract["evidence"],
        "admission": contract["admission"],
        "dependency_states": observed,
        "blocker": contract["blocker"],
        "goal": body_sections.get("goal", ""),
        "physical_acceptance": body_sections.get("physical_acceptance", ""),
        "non_claims": body_sections.get("non_claims", ""),
        **derived,
    }


def registered_worktrees(root: Path) -> dict[Path, dict[str, str]]:
    # constraint: ed3c/noodles#46 - Git's own worktree registry is the single registry;
    # constraint: this reads it, it does not keep a second copy and does not create worktrees.
    records: dict[Path, dict[str, str]] = {}
    current: dict[str, str] = {}
    for line in [*git(root, "worktree", "list", "--porcelain").splitlines(), ""]:
        if line:
            key, _, value = line.partition(" ")
            current[key] = value
            continue
        if current:
            records[Path(current["worktree"]).resolve()] = current
            current = {}
    return records


def session_worktree_paths(project: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for spawn in sorted((project / ".noodle" / "sessions").glob("*/spawn.json")):
        payload = load_json(spawn)
        if not isinstance(payload, dict):
            raise GateError(f"Noodle session spawn record is not an object: {spawn}")
        declared = str(payload.get("worktree_path") or "").strip()
        if declared:
            paths[spawn.parent.name] = Path(declared).expanduser().resolve()
    return paths


def execute_provenance_admission(
    root: Path,
    subject_value: str,
    session_id: str,
    head: str,
    base_sha: str,
    default_branch: str,
) -> dict[str, Any]:
    # constraint: ed3c/noodles#46 - I2 provenance: one exact order binds one exact session,
    # constraint: one Git-registered worktree, one non-default branch, one candidate head, and
    # constraint: one reconciled provider base. Every other shape fails closed here, before any
    # constraint: Issue state or handoff mutation, so a rejected candidate leaves no residue.
    # constraint: fail fast on a malformed subject before any worktree readback.
    parse_subject(subject_value)
    root = root.resolve()
    context = validate_handoff_session(root, subject_value, session_id, error_cls=GateError)
    project = Path(context["project"]).resolve()
    # constraint: repository identity is checked once, by execute_handoff before this is
    # constraint: reached (noodles.py ~866); re-deriving it here from the same root would
    # constraint: reject nothing new since nothing mutates origin's remote URL in between.
    repository = runtime_gh_repo_from_git(root, error_cls=GateError)
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    if common.parent != project:
        raise GateError(f"execute worktree {root} is foreign: git common directory {common} is outside Noodle project {project}")
    registry = registered_worktrees(root)
    entry = registry.get(root)
    if entry is None:
        raise GateError(f"execute worktree {root} is not a registered Git worktree of {common}")
    branch_ref = entry.get("branch") or ""
    if not branch_ref:
        raise GateError(f"execute admission requires an attached branch; worktree {root} has a detached HEAD at {entry.get('HEAD')}")
    branch = branch_ref.removeprefix("refs/heads/")
    if branch == default_branch:
        raise GateError(f"execute admission refuses default branch {default_branch}; the shared control checkout is read/reconcile only")
    expected_branch = execute_branch(subject_value)
    if branch != expected_branch:
        raise GateError(f"execute branch {branch} != exact order branch {expected_branch}")
    # constraint: a `prunable` entry is git's own signal that the worktree directory is gone
    # constraint: (removed without `git worktree remove`); it is not a live conflict and must
    # constraint: not block this branch, or a stale registry record would need a manual
    # constraint: `git worktree prune` before any future handoff for that order could proceed.
    duplicates = sorted(
        str(path)
        for path, item in registry.items()
        if path != root and item.get("branch") == branch_ref and "prunable" not in item
    )
    if duplicates:
        raise GateError(f"execute branch {branch} is already checked out in registered worktree {duplicates[0]}")
    sharing = sorted(name for name, path in session_worktree_paths(project).items() if path == root and name != session_id)
    if sharing:
        raise GateError(f"execute worktree {root} is registered to sessions {session_id} and {sharing[0]}; provenance is ambiguous")
    if entry.get("HEAD") != head or git(root, "rev-parse", "HEAD") != head:
        raise GateError(f"execute worktree HEAD {entry.get('HEAD')} != admitted candidate head {head}")
    if not HEX40_RE.fullmatch(base_sha or ""):
        raise GateError(f"execute admission requires an exact reconciled provider base; got {base_sha!r}")
    merge_base = run(["git", "merge-base", "--is-ancestor", base_sha, head], cwd=root, check=False)
    if merge_base.returncode == 128:
        detail = merge_base.stderr.strip() or merge_base.stdout.strip() or "object not present"
        raise GateError(f"execute admission cannot verify provider base {base_sha} in worktree {root}: {detail}")
    if merge_base.returncode != 0:
        raise GateError(f"execute branch {branch} does not contain admitted provider base {base_sha}")
    return {
        "order": subject_value,
        "session_id": session_id,
        "session_spawn": str(project / ".noodle" / "sessions" / session_id / "spawn.json"),
        "repository": repository,
        "git_common_dir": str(common),
        "worktree_path": str(root),
        "branch": branch,
        "default_branch": default_branch,
        "candidate_head": head,
        "base_sha": base_sha,
    }


def execute_handoff(root: Path, subject_value: str, pr_number: int, pr: dict[str, Any]) -> dict[str, Any]:
    subject = parse_subject(subject_value)
    if subject.repo != runtime_gh_repo_from_git(root, error_cls=GateError):
        raise GateError("handoff subject repository does not match current worktree")
    if pr.get("state") != "open" or pr.get("draft"):
        raise GateError("handoff PR must be open and non-draft")
    if parse_pr_reference(pr.get("body") or "") != subject_value:
        raise GateError("handoff PR does not exactly reference the issue")
    policy = protection_policy(root)
    if pr.get("base", {}).get("ref") != policy["default_branch"]:
        raise GateError(f"handoff PR base must be {policy['default_branch']}")
    head = git(root, "rev-parse", "HEAD")
    if pr.get("head", {}).get("sha") != head:
        raise GateError("handoff PR head does not match current worktree HEAD")
    session_id = os.getenv("NOODLE_SESSION_ID", "").strip()
    provenance = execute_provenance_admission(
        root,
        subject_value,
        session_id,
        head,
        str(pr.get("base", {}).get("sha") or ""),
        str(policy["default_branch"]),
    )
    resolve_locked_runtime_binary(root, error_cls=GateError)
    contract = parse_issue_contract(issue_read(subject_value).get("body") or "", expected_subject=subject_value)
    evidence = feature_contract.admit_acceptance_evidence(root, contract["feature"], head, error_cls=GateError)
    base_ref = pr.get("base", {}).get("ref")
    # constraint: ed3c/noodles#264 - the journey-compilation gate is not here. This route is one of
    # constraint: several that reach awaiting_land, and the ones real lanes take cannot run it, so a
    # constraint: gate placed here is enforced only where it is not needed. It lives at the single
    # constraint: confluence every candidate must cross instead: verify_pull_request.
    issue_set_state(subject_value, "awaiting_land")
    receipt = blocking_handoff_readback(root, subject_value, pr_number, head, session_id, error_cls=GateError)
    if receipt is None:
        intent = handoff_rerun_intent_readback(
            root, subject_value, pr_number, head, session_id, error_cls=GateError
        )
        if intent is None:
            failed_run = github_protection.failed_required_workflow_run_readback(
                gh_api,
                GateError,
                subject.repo,
                head,
                name=str(policy["required_check"]),
                path=".github/workflows/verify.yml",
                event="pull_request_target",
                default_branch=str(policy["default_branch"]),
                pr_number=pr_number,
            )
            intent = emit_handoff_rerun_intent(
                root,
                subject_value,
                pr_number,
                head,
                int(failed_run["run"]["id"]),
                int(failed_run["run"]["run_attempt"]),
                session_id,
                error_cls=GateError,
            )
        source = github_protection.trusted_workflow_run_readback(
            gh_api,
            GateError,
            subject.repo,
            int(intent["workflow_run_id"]),
            name=str(policy["required_check"]),
            path=".github/workflows/verify.yml",
            event="pull_request_target",
            default_branch=str(policy["default_branch"]),
        )
        run = source["run"]
        if run["head_sha"] != head or pr_number not in run["pull_request_numbers"]:
            raise GateError("execute handoff verify rerun intent workflow head or PR drifted")
        baseline_attempt = int(intent["baseline_run_attempt"])
        current_attempt = int(run["run_attempt"])
        if current_attempt == baseline_attempt:
            if run["status"] != "completed" or run["conclusion"] not in github_protection.FAILED_WORKFLOW_CONCLUSIONS:
                raise GateError("execute handoff verify rerun baseline is not a completed failed workflow run")
            gh_api(f"repos/{subject.repo}/actions/runs/{run['id']}/rerun", method="POST")
        elif current_attempt == baseline_attempt + 1:
            active_states = {"queued", "in_progress", "requested", "waiting", "pending"}
            if run["status"] not in active_states | {"completed"}:
                raise GateError("execute handoff verify rerun adopted workflow state is invalid")
            if run["status"] == "completed" and not run["conclusion"]:
                raise GateError("execute handoff verify rerun completed attempt has no conclusion")
            if run["status"] != "completed" and run["conclusion"]:
                raise GateError("execute handoff verify rerun active attempt has a conclusion")
        else:
            raise GateError("execute handoff verify rerun attempt drifted from its durable intent")
        receipt = emit_blocking_handoff(
            root,
            subject_value,
            pr_number,
            head,
            int(intent["workflow_run_id"]),
            baseline_attempt,
            session_id,
            error_cls=GateError,
        )
    specialized = evidence["specialized"]
    return {
        "subject": subject_value,
        "pr": pr_number,
        "state": "awaiting_land",
        "acceptance": feature_contract.BASELINE_CONTRACT_ID,
        "base": base_ref,
        "provenance": provenance,
        "tree": evidence["tree"],
        "feature": specialized["feature_id"] if specialized else None,
        "feature_code_surface_sha256": specialized["code_surface_sha256"] if specialized else None,
        **receipt,
    }
def protection_policy(root: Path) -> dict[str, Any]:
    return load_json(root / "policy/github.json")
def protection_readback(repo: str, branch: str, required_check: str) -> dict[str, Any]:
    return github_protection.protection_readback(
        lambda endpoint, **kwargs: github_protection.gh_api_response(run, GateError, endpoint, **kwargs),
        GateError,
        repo,
        branch,
        required_check,
    )


def control_checkout_admission(root: Path) -> dict[str, Any]:
    return runtime_control_checkout_admission(root, str(protection_policy(root)["default_branch"]), error_cls=GateError)
def reconcile_checkout_admission(root: Path) -> dict[str, Any]:
    return runtime_reconcile_checkout_admission(root, str(protection_policy(root)["default_branch"]), error_cls=GateError)


def component_map(policy_root: Path) -> dict[str, list[str]]:
    path = policy_root / COMPONENT_MAP_PATH
    payload = load_json(path)
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "components"} or payload["schema_version"] != 1:
        raise GateError(f"{COMPONENT_MAP_PATH} must contain exactly schema_version 1 and a components object")
    raw_components = payload["components"]
    if not isinstance(raw_components, dict) or not raw_components:
        raise GateError(f"{COMPONENT_MAP_PATH} components must be a non-empty object of component -> path globs")
    components: dict[str, list[str]] = {}
    for name, globs in raw_components.items():
        if not isinstance(name, str) or not COMPONENT_NAME_RE.fullmatch(name):
            raise GateError(f"{COMPONENT_MAP_PATH} component name {name!r} is not one lowercase component token")
        if not isinstance(globs, list) or not globs or not all(isinstance(glob, str) and glob for glob in globs):
            raise GateError(f"{COMPONENT_MAP_PATH} component {name} must declare a non-empty list of path glob strings")
        components[name] = list(globs)
    return components
def component_surface_errors(component: str, components: dict[str, list[str]], changed_files: Sequence[str]) -> list[str]:
    if not component:
        return [
            f"issue declares no noodles-component marker; every issue must declare one owned component from {COMPONENT_MAP_PATH}"
        ]
    globs = components.get(component)
    if globs is None:
        return [
            f"declared component {component!r} is not in {COMPONENT_MAP_PATH}; admitted components: {', '.join(sorted(components))}"
        ]
    offending = sorted(path for path in changed_files if not any(fnmatch.fnmatchcase(path, glob) for glob in globs))
    if offending:
        return [f"mutation outside admitted component {component!r}: {', '.join(offending)}"]
    return []
FINDINGS_REGISTER_PATH = "docs/findings/register.json"
FINDING_FIELDS = ("id", "date", "severity", "finding", "receipts", "owner_component", "status", "chain")
FINDING_STATUSES = ("open", "promoted", "retired")
FINDING_SEVERITIES = ("S1", "S2", "S3")
FINDING_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def finding_chain(entry: Mapping[str, Any], previous: str) -> str:
    """Commit one entry to every entry before it, so appending is the only mutation that survives.

    Editing, reordering, or silently dropping an entry changes this value for that entry and for
    every entry after it, which `findings_register_errors` recomputes from scratch."""
    payload = {key: value for key, value in entry.items() if key != "chain"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{previous}\n{canonical}".encode("utf-8")).hexdigest()


def findings_register_errors(root: Path, policy_root: Path | None = None) -> list[str]:
    # constraint: ed3c/noodles#263 - the register is N-class: an entry gates nothing and admits
    # constraint: nothing. What is L here is the register's shape - a malformed entry and a
    # constraint: silently removed entry both fail this recomputation, so the durable home cannot
    # constraint: rot into prose. Non-claim: removing the *last* entry leaves a self-consistent
    # constraint: chain; only the Git history of this file witnesses that, which is why
    # constraint: policy/fitness.json also requires the path to exist at all.
    path = root / FINDINGS_REGISTER_PATH
    if not path.exists():
        return [f"missing findings register: {FINDINGS_REGISTER_PATH}"]
    try:
        payload = load_json(path)
        components = set(component_map(policy_root or root))
    except GateError as exc:
        return [f"{FINDINGS_REGISTER_PATH} unreadable: {exc}"]
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "entries"} or payload["schema_version"] != 1:
        return [f"{FINDINGS_REGISTER_PATH} must contain exactly schema_version 1 and an entries array"]
    entries = payload["entries"]
    if not isinstance(entries, list) or not entries:
        return [f"{FINDINGS_REGISTER_PATH} entries must be a non-empty array"]
    previous = ""
    for index, entry in enumerate(entries, start=1):
        label = f"{FINDINGS_REGISTER_PATH} entry {index}"
        if not isinstance(entry, dict):
            return [f"{label} is not an object"]
        expected_fields = set(FINDING_FIELDS) | ({"promoted_to"} if entry.get("status") == "promoted" else set())
        if set(entry) != expected_fields:
            return [
                f"{label} field set is wrong: missing {sorted(expected_fields - set(entry))}, "
                f"unexpected {sorted(set(entry) - expected_fields)}"
            ]
        if entry["id"] != index:
            return [f"{label} declares id {entry['id']!r} at append position {index}; an entry was removed or reordered"]
        if not isinstance(entry["date"], str) or not FINDING_DATE_RE.fullmatch(entry["date"]):
            return [f"{label} date {entry['date']!r} is not an exact YYYY-MM-DD day"]
        if entry["severity"] not in FINDING_SEVERITIES:
            return [f"{label} severity {entry['severity']!r} is not one of {', '.join(FINDING_SEVERITIES)}"]
        if not isinstance(entry["finding"], str) or not entry["finding"].strip():
            return [f"{label} finding must be one non-empty statement"]
        receipts = entry["receipts"]
        if not isinstance(receipts, list) or not receipts or not all(isinstance(item, str) and item.strip() for item in receipts):
            return [f"{label} receipts must be a non-empty list of non-empty receipt strings"]
        if entry["owner_component"] not in components:
            return [f"{label} owner_component {entry['owner_component']!r} is not in {COMPONENT_MAP_PATH}"]
        if entry["status"] not in FINDING_STATUSES:
            return [f"{label} status {entry['status']!r} is not one of {', '.join(FINDING_STATUSES)}"]
        if entry["status"] == "promoted" and not SUBJECT_RE.fullmatch(str(entry["promoted_to"])):
            return [f"{label} promoted_to {entry['promoted_to']!r} is not an exact owner/repo#N subject"]
        expected_chain = finding_chain(entry, previous)
        if entry["chain"] != expected_chain:
            return [f"{label} chain {entry['chain']!r} != recomputed {expected_chain!r}; the register was mutated, not appended"]
        previous = expected_chain
    return []


def open_findings(root: Path) -> list[dict[str, Any]]:
    """Register entries whose disposition is still open - the register's whole reader contract."""
    payload = load_json(root / FINDINGS_REGISTER_PATH)
    return [entry for entry in payload["entries"] if entry.get("status") == "open"]


def findings_backlog_items(root: Path) -> list[dict[str, Any]]:
    # constraint: ed3c/noodles#263 - open findings ride the same surface agents already read for
    # constraint: ready work, so the register has a reader by construction. `open` is not `ready`
    # constraint: and the id is not an owner/repo#N subject, so the schedule skill's admission
    # constraint: cannot turn one of these lines into an order.
    return [
        {
            "id": f"finding-{entry['id']}",
            "title": entry["finding"],
            "status": entry["status"],
            "kind": "finding",
            "severity": entry["severity"],
            "date": entry["date"],
            "owner_component": entry["owner_component"],
            "receipts": entry["receipts"],
        }
        for entry in open_findings(root)
    ]


def parse_python(source: str, label: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError as exc:
        raise GateError(f"cannot parse {label} as Python: {exc}") from exc
def python_import_targets(source: str, label: str) -> set[str]:
    """Every absolute dotted module name this source imports.

    Ceiling: `from . import x` is not resolved - this repository has no relative import and a flat
    module layout, so an unresolved relative edge would be inside its own package directory anyway.
    A second, unrelated ceiling: this only walks `ast.Import`/`ast.ImportFrom` nodes, so a module
    loaded at runtime through `importlib` is invisible to it regardless of where the loaded path
    lives. Two real instances exist today - `tests/support.py`'s `spec_from_file_location` loading
    `noodles.py`, and `tests/test_gh_pacing.py`'s `SourceFileLoader` loading the `gh` fixture binary -
    and neither has produced a false negative because both loaded targets already sit inside every
    component's own globs; nothing here would catch a future `importlib` load that crossed a real
    boundary. Unparsable source is a refusal, never an empty edge set: a file whose imports cannot be
    read is not a file that imports nothing."""
    targets: set[str] = set()
    for node in ast.walk(parse_python(source, label)):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            targets.update({node.module, *(f"{node.module}.{alias.name}" for alias in node.names)})
    return targets
def repo_module_target(dotted: str, *roots: Path) -> str | None:
    """Repository-relative path of the module `dotted` names, when one of these trees provides it.

    A name no tree provides is stdlib or absent, and neither belongs to any component's surface."""
    base = dotted.replace(".", "/")
    for relative in (f"{base}.py", f"{base}/__init__.py"):
        if any((root / relative).is_file() for root in roots):
            return relative
    return None
# constraint: ed3c/noodles#257 - path globs bound which files a candidate may touch and say nothing
# constraint: about what those files start coupling to, so a declared surface stayed honest-looking
# constraint: while the diff imported another component's module. Only edges this diff introduces are
# constraint: judged; an edge already on the base tree is the base tree's declaration, not this one's.
# constraint: a component whose surface is the whole repository ("contract", glob "*") is bounded by
# constraint: nothing this function can check, same as component_owner_errors below; both special-case
# constraint: it explicitly rather than relying on fnmatch("*") matching everything by coincidence.
def component_import_edge_errors(
    component: str,
    components: dict[str, list[str]],
    changed_files: Sequence[str],
    base_root: Path,
    candidate_root: Path,
) -> list[str]:
    globs = components.get(component)
    if not globs or "*" in globs:
        return []
    errors: list[str] = []
    for path in sorted(set(changed_files)):
        after = candidate_root / path
        if not path.endswith(".py") or not after.is_file():
            continue
        before = base_root / path
        introduced = python_import_targets(after.read_text(encoding="utf-8"), path) - (
            python_import_targets(before.read_text(encoding="utf-8"), path) if before.is_file() else set()
        )
        for dotted in sorted(introduced):
            target = repo_module_target(dotted, candidate_root, base_root)
            if target and not any(fnmatch.fnmatchcase(target, glob) for glob in globs):
                errors.append(
                    f"{path} newly imports {dotted} ({target}), outside admitted component {component!r}"
                )
    return errors
def component_owner_map(policy_root: Path) -> dict[str, dict[str, tuple[str, ...]]]:
    """Per-definition ownership for files that more than one component's globs admit at once.

    Absent on a tree that predates the map, which is the only shape that lets the map land at all:
    the gate reads it from the trusted default-branch checkout, so the candidate that introduces it
    is judged by a trusted tree that does not have it yet. Present-but-malformed is a refusal."""
    path = policy_root / COMPONENT_OWNER_MAP_PATH
    if not path.exists():
        return {}
    payload = load_json(path)
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "owners"} or payload["schema_version"] != 1:
        raise GateError(f"{COMPONENT_OWNER_MAP_PATH} must contain exactly schema_version 1 and an owners object")
    raw_owners = payload["owners"]
    if not isinstance(raw_owners, dict) or not raw_owners:
        raise GateError(f"{COMPONENT_OWNER_MAP_PATH} owners must be a non-empty object of path -> definition ownership")
    owners: dict[str, dict[str, tuple[str, ...]]] = {}
    for path_key, definitions in raw_owners.items():
        if not isinstance(definitions, dict) or not definitions:
            raise GateError(f"{COMPONENT_OWNER_MAP_PATH} entry {path_key!r} must map definition names to owning components")
        entry: dict[str, tuple[str, ...]] = {}
        for name, names in definitions.items():
            if (
                not isinstance(names, list)
                or not names
                or not all(isinstance(item, str) and COMPONENT_NAME_RE.fullmatch(item) for item in names)
            ):
                raise GateError(
                    f"{COMPONENT_OWNER_MAP_PATH} definition {path_key}:{name} must list at least one lowercase component token"
                )
            entry[str(name)] = tuple(names)
        owners[str(path_key)] = entry
    return owners
def top_level_definitions(source: str, label: str) -> dict[str, str]:
    """Exact source text of every top-level function and class, keyed by its name."""
    lines = source.splitlines()
    definitions: dict[str, str] = {}
    for node in parse_python(source, label).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
            definitions[node.name] = "\n".join(lines[start - 1 : node.end_lineno])
    return definitions
# constraint: ed3c/noodles#268 - noodles.py is admitted by schedule, verify and carrier at once, so
# constraint: the file glob cannot object to a verify-declared atom rewriting schedule dispatch: the
# constraint: file matched every component before the atom existed. Ownership is hand-kept per
# constraint: definition; a definition with no entry is unowned and this check stays silent on it.
def component_owner_errors(
    component: str,
    components: dict[str, list[str]],
    changed_files: Sequence[str],
    owners: Mapping[str, Mapping[str, Sequence[str]]],
    base_root: Path,
    candidate_root: Path,
) -> list[str]:
    globs = components.get(component)
    if not globs or "*" in globs:
        return []
    errors: list[str] = []
    for path in sorted(set(changed_files) & set(owners)):
        before, after = base_root / path, candidate_root / path
        if not after.is_file():
            # constraint: a file the candidate no longer carries is a file-level event, not a
            # constraint: definition-level crossing; policy/fitness.json required_paths owns whether
            # constraint: it may go missing at all. Deleting a definition inside a kept file is a
            # constraint: crossing and is judged below.
            continue
        before_definitions = top_level_definitions(before.read_text(encoding="utf-8"), path) if before.is_file() else {}
        after_definitions = top_level_definitions(after.read_text(encoding="utf-8"), path)
        for name in sorted(set(before_definitions) | set(after_definitions)):
            owning = tuple(owners[path].get(name) or ())
            if owning and component not in owning and before_definitions.get(name) != after_definitions.get(name):
                errors.append(
                    f"{path}:{name} is owned by {', '.join(owning)} but this candidate declares {component!r}"
                )
    return errors
def pinned_entries(root: Path) -> set[str]:
    """Identity path of every pinned unit in this tree's `policy/*.lock.json` files.

    A unit's path is built from container keys and list-item names only, so changing a pinned
    scalar (a version, a commit) never changes the set; declaring a new dependency always does.
    """
    found: set[str] = set()

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict):
            if PINNING_KEYS & set(node):
                found.add(prefix)
            for key, value in node.items():
                walk(value, f"{prefix}.{key}")
        elif isinstance(node, list):
            for item in node:
                name = item.get("name") if isinstance(item, dict) else None
                walk(item, f"{prefix}[{name}]" if isinstance(name, str) and name else prefix)

    for path in sorted((root / "policy").glob("*.lock.json")):
        walk(load_json(path), path.name)
    return found
def introduced_components(base_root: Path, candidate_root: Path) -> list[str]:
    """Components the candidate declares that the base tree does not: new pinned lock entries and
    new top-level runtime modules. Language dependency manifests need no case here because
    `forbidden_dependency_manifests` already rejects every one of them outright."""
    base_modules = {path.name for path in base_root.glob("*.py")}
    return sorted(
        [f"pinned lock entry {entry}" for entry in pinned_entries(candidate_root) - pinned_entries(base_root)]
        + [f"top-level module {path.name}" for path in candidate_root.glob("*.py") if path.name not in base_modules]
    )
def component_introduction_missing_answers(issue_body: str) -> list[str]:
    section = next(
        (block for block in re.split(r"(?m)^#{1,6}\s+", issue_body or "") if block.lower().startswith(COMPONENT_INTRODUCTION_HEADING)),
        "",
    ).lower()
    missing: list[str] = []
    for question in COMPONENT_INTRODUCTION_QUESTIONS:
        _, found, answer = section.partition(question)
        for other in COMPONENT_INTRODUCTION_QUESTIONS:
            if other != question:
                answer = answer.partition(other)[0]
        if not found or not answer.strip(" \t\r\n-*+>#"):
            missing.append(question)
    return missing
def component_introduction_errors(introductions: Sequence[str], issue_body: str) -> list[str]:
    if not introductions:
        return []
    missing = component_introduction_missing_answers(issue_body)
    if not missing:
        return []
    return [
        f"candidate introduces {', '.join(introductions)}; the driving issue must answer both gate "
        f"questions under a '## Component introduction' section, unanswered: {' | '.join(missing)}"
    ]
def compare_changed_files(comparison: Any) -> list[str]:
    if not isinstance(comparison, dict) or not isinstance(comparison.get("files"), list):
        raise GateError("provider compare readback has no files list")
    files = comparison["files"]
    if len(files) >= COMPARE_FILES_CEILING:
        raise GateError(f"provider compare readback reached the {COMPARE_FILES_CEILING}-file ceiling; the changed-file set is not fully observable")
    changed: set[str] = set()
    for item in files:
        filename = item.get("filename") if isinstance(item, dict) else None
        if not isinstance(filename, str) or not filename:
            raise GateError("provider compare readback contains a file entry without a filename")
        changed.add(filename)
        previous = item.get("previous_filename")
        if isinstance(previous, str) and previous:
            changed.add(previous)
    return sorted(changed)
def merge_base_changed_files(repository: str, base_ref: str, head_sha: str) -> list[str]:
    return compare_changed_files(gh_api(f"repos/{repository}/compare/{base_ref}...{head_sha}"))
EVIDENCE_CUSTODY_ROOT = "GitHub-Actions-Evidence/v1"
EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_HEAD_RE = re.compile(r"[0-9a-f]{40}")
EVIDENCE_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
EVIDENCE_REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
EVIDENCE_MEMBER_RE = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
EVIDENCE_RUNNER_ENV = ("RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion", "GITHUB_EVENT_NAME", "GITHUB_WORKFLOW_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
# constraint: ed3c/noodles#188 - bounded credential value shapes. They match a materialized
# constraint: secret, never a `${{ secrets.X }}` reference, so a workflow that names a secret is
# constraint: not a leak while a token that reached the archive is. A finding carries the member
# constraint: and the pattern id only; the matched bytes are never copied into any diagnostic.
EVIDENCE_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("github-token", re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("github-pat", re.compile(rb"github_pat_[A-Za-z0-9_]{30,}")),
    ("google-api-key", re.compile(rb"AIza[0-9A-Za-z_-]{35}")),
    ("google-service-account-key", re.compile(rb"\"private_key_id\"[ \t]*:")),
    ("openai-key", re.compile(rb"sk-[A-Za-z0-9_-]{32,}")),
    ("private-key-block", re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("authorization-header", re.compile(rb"(?i)authorization[ \t]*:[ \t]*(?:bearer|basic|token)[ \t]+[^\s\"']")),
)
EVIDENCE_CREDENTIAL_FILE_RE = re.compile(r"(?:^|/)gha-creds-[^/]*\.json$")
def evidence_custody_folder(repository: str, issue_number: int, pr_number: int, head_sha: str, run_id: int, run_attempt: int) -> str:
    """The one deterministic custody path for exactly this Issue, PR, candidate head, run, attempt.

    The folder is the idempotency key: a retry of the same attempt recomputes the identical path
    instead of growing a second tree, and every component is exact so nothing can be defaulted into
    a path that names a run which never happened."""
    if not EVIDENCE_REPOSITORY_RE.fullmatch(repository or ""):
        raise GateError(f"evidence custody repository {repository!r} is not one exact owner/repo")
    if not EVIDENCE_HEAD_RE.fullmatch(head_sha or ""):
        raise GateError(f"evidence custody head {head_sha!r} is not one exact 40-hex candidate head")
    for name, value in (("issue", issue_number), ("pr", pr_number), ("run id", run_id), ("run attempt", run_attempt)):
        if type(value) is not int or value < 1:
            raise GateError(f"evidence custody {name} {value!r} is not a positive integer")
    return f"{EVIDENCE_CUSTODY_ROOT}/{repository}/issue-{issue_number}/pr-{pr_number}/{head_sha}/run-{run_id}-attempt-{run_attempt}"
def evidence_blob_path(digest: str) -> str:
    if not EVIDENCE_DIGEST_RE.fullmatch(digest or ""):
        raise GateError(f"evidence blob digest {digest!r} is not one sha256 hex digest")
    return f"{EVIDENCE_CUSTODY_ROOT}/blobs/sha256/{digest}"
def evidence_scrub_findings(name: str, data: bytes) -> list[str]:
    """Every bounded credential shape this member carries, named without carrying its value."""
    findings = [f"{name}: generated-credential-file"] if EVIDENCE_CREDENTIAL_FILE_RE.search(name) else []
    for pattern_id, pattern in EVIDENCE_SECRET_PATTERNS:
        match = pattern.search(data)
        if match is not None:
            findings.append(f"{name}: {pattern_id} at byte offset {match.start()}")
    return findings
def build_evidence_publication(folder: str, members: Mapping[str, bytes]) -> dict[str, Any]:
    """Package one run's evidence into the canonical manifest durable custody would carry.

    Scrub runs before packaging and one finding refuses the whole publication, so there is no
    partial archive and no secret value in any diagnostic. An empty member set is refused too: the
    admitted non-case is a run that generated no extra files, never a run with no denominator."""
    if not members:
        raise GateError(f"evidence publication {folder} has an empty member denominator")
    findings: list[str] = []
    entries: list[dict[str, Any]] = []
    for name in sorted(members):
        data = members[name]
        if not EVIDENCE_MEMBER_RE.fullmatch(name):
            raise GateError(f"evidence member name {name!r} is not one exact relative archive path")
        if not isinstance(data, bytes):
            raise GateError(f"evidence member {name} must be exact bytes, got {type(data).__name__}")
        findings.extend(evidence_scrub_findings(name, data))
        digest = hashlib.sha256(data).hexdigest()
        entries.append({"name": name, "sha256": digest, "bytes": len(data), "blob": evidence_blob_path(digest)})
    if findings:
        raise GateError("evidence publication scrub refused: " + "; ".join(findings))
    manifest = {"schema_version": EVIDENCE_SCHEMA_VERSION, "folder": folder, "members": entries}
    return {"folder": folder, "manifest": manifest, **evidence_manifest_digest(manifest)}
def evidence_manifest_digest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    canonical = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return {"manifest_sha256": hashlib.sha256(canonical).hexdigest(), "manifest_bytes": len(canonical)}
def evidence_publication_readback(publication: Mapping[str, Any], folder: str, members: Mapping[str, bytes]) -> dict[str, Any]:
    """Prove the manifest describes exactly these bytes under exactly this custody key.

    This is the byte readback custody owes, run here against a second read of the packaged source
    and reusable verbatim against a re-downloaded copy once a transport is admitted. A wrong-head
    or wrong-attempt folder, a missing member, an extra member, a truncation, a tampered digest, and
    a retry that would write a different manifest under the same key each fail closed here."""
    errors: list[str] = []
    if publication.get("folder") != folder:
        errors.append(f"manifest folder {publication.get('folder')!r} != expected custody folder {folder!r}")
    manifest = publication.get("manifest") or {}
    recorded = {str(entry.get("name")): entry for entry in manifest.get("members") or []}
    errors.extend(f"manifest member {name} is absent from the readback source" for name in sorted(set(recorded) - set(members)))
    errors.extend(f"readback source member {name} is absent from the manifest" for name in sorted(set(members) - set(recorded)))
    for name in sorted(set(recorded) & set(members)):
        data = members[name]
        if recorded[name].get("bytes") != len(data):
            errors.append(f"member {name} manifest byte count {recorded[name].get('bytes')!r} != readback {len(data)}")
        digest = hashlib.sha256(data).hexdigest()
        if recorded[name].get("sha256") != digest:
            errors.append(f"member {name} manifest sha256 {recorded[name].get('sha256')!r} != readback {digest}")
    if publication.get("manifest_sha256") != evidence_manifest_digest(manifest)["manifest_sha256"]:
        errors.append("published manifest digest does not describe the manifest it is published with")
    if errors:
        raise GateError("evidence publication readback refused: " + "; ".join(errors))
    return {"folder": folder, "members": len(recorded), "bytes": sum(len(data) for data in members.values())}
def evidence_publication_members(candidate_root: Path, receipt: Mapping[str, Any]) -> dict[str, bytes]:
    """The exact bytes this run consumed and produced, read from the candidate as untrusted data.

    Nothing here is executed: the verification receipt, the runner/tool metadata, the pinned
    dependency locks and the pinned workflow definitions are hashed as bytes. The denominator stays
    non-empty even for a candidate that produced no extra files."""
    def canonical(value: Any) -> bytes:
        return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

    members: dict[str, bytes] = {
        "verification/receipt.json": canonical(dict(receipt)),
        "runtime/runner.json": canonical({key.lower(): os.getenv(key) for key in EVIDENCE_RUNNER_ENV}),
        "runtime/tools.json": canonical({"python": sys.version.split()[0], "platform": sys.platform}),
    }
    for prefix, pattern in (("policy", "policy/*.lock.json"), ("workflows", ".github/workflows/*.yml")):
        for path in sorted(candidate_root.glob(pattern)):
            try:
                members[f"candidate/{prefix}/{path.name}"] = path.read_bytes()
            except OSError as exc:
                raise GateError(f"evidence publication cannot read candidate member {path.name}: {exc}") from exc
    return members
def evidence_publication(candidate_root: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Package, scrub and read back this run's evidence, and name the transport state exactly.

    Durable custody transport is not admitted by this atom: no Google credential path exists inside
    Actions, so the publication is packaged, scrubbed, digest-bound and reported as
    `custody_unadmitted` while the bytes stay on the GitHub artifact spool. An execution with no
    GitHub run identity has no custody key at all and says so. Neither absence is allowed to look
    like a completed publication, and neither is correctness or merge authority."""
    identity = [int(raw) if (raw := (os.getenv(name) or "").strip()).isdigit() else 0 for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")]
    if min(identity) < 1:
        return {"status": "run_identity_absent", "folder": None, "manifest_sha256": None, "members": 0,
                "reason": "GITHUB_RUN_ID/GITHUB_RUN_ATTEMPT absent: this execution has no GitHub Actions custody key"}
    folder = evidence_custody_folder(
        str(receipt["repository"]), parse_subject(str(receipt["issue_subject"])).number,
        int(receipt["pr_number"]), str(receipt["head_sha"]), identity[0], identity[1],
    )
    publication = build_evidence_publication(folder, evidence_publication_members(candidate_root, receipt))
    readback = evidence_publication_readback(publication, folder, evidence_publication_members(candidate_root, receipt))
    return {"status": "custody_unadmitted", **publication, **readback,
            "reason": "no admitted Google Drive destination credential exists for GitHub Actions; the packaged evidence stays on the GitHub artifact spool"}
GHA_HOSTED_LANE = "gha-agentic"
GHA_TRUSTED_WORKFLOW_PATHS = (".github/workflows/verify.yml", ".github/workflows/land.yml")
# constraint: ed3c/noodles#189 - the exact typed declaration one target-local execution task is
# constraint: bound to. Task identity is the sha256 of these fields and nothing else, so the
# constraint: idempotency nonce is derived and never supplied: a sender cannot hold an identity
# constraint: that disagrees with the content it identifies, and a duplicate dispatch converges on
# constraint: the same task by construction instead of by the sender remembering a nonce.
GHA_TASK_FIELDS = ("target", "subject", "subject_body_sha256", "base_sha", "runtime", "evidence", "write_boundary")
GHA_ADMITTED_STATUSES = ("task_admitted", "task_reused", "apply_admitted")
GHA_STATUS_MEANINGS = {
    "task_admitted": "this dispatch created one target-local execution task bound to the exact issue, target, base, runtime, evidence policy, and write boundary",
    "task_reused": "an active target-local task already carries this exact derived identity, so the duplicate dispatch converged on it instead of creating a second task",
    "apply_admitted": "the proposed safe output stays inside the task's branch, write boundary, PR body shape, and bound evidence, so the apply step may create at most this one branch and PR",
    "gha_lane_refused": "the capability table does not admit this issue on the hosted agentic lane, so no target-local task, branch, or PR is created for it here",
    "gha_boundary_undeclared": "the issue declares no machine-readable write boundary, so the hosted lane has no surface to constrain the apply step to and fails closed",
    "gha_target_mismatch": "the dispatch names a target repository the exact issue does not declare, so no target owns this mutation and nothing is created",
    "gha_subject_mismatch": "the dispatch names a source subject the exact issue body does not declare as its own subject",
    "gha_subject_digest_stale": "the dispatch carries a provider body digest that is not the digest of the issue body this gate read, so the issue changed after dispatch",
    "gha_base_mismatch": "the dispatch names a base commit that is not the exact base head this task is admitted against",
    "gha_runtime_mismatch": "the dispatch declares a runtime the exact issue does not declare, so the deterministic runtime step would not be the one the issue was admitted for",
    "gha_evidence_policy_mismatch": "the dispatch declares an evidence policy the exact issue does not declare",
    "gha_boundary_mismatch": "the dispatch declares a write boundary that is not the exact boundary the issue declares",
    "gha_duplicate_claim": "another active target-local task already holds this subject's exact ephemeral execute branch under a different identity",
    "gha_boundary_conflict": "this task's declared write boundary intersects an already-active target-local task's boundary, so admitting both concurrently could collide at landing",
    "gha_task_unadmitted": "the apply step was handed something other than an admitted target-local task, so there is no bound surface to judge the proposal against",
    "gha_proposal_malformed": "the agent safe output is not one exact branch, one exact PR body, and a non-empty list of exact repository-relative changed paths",
    "gha_default_branch_push": "the proposed apply would write the default branch, which no hosted lane may ever do",
    "gha_branch_mismatch": "the proposed apply names a branch that is not this task's exact ephemeral execute branch",
    "gha_trusted_workflow_edit": "the proposed apply would rewrite the trusted workflow bytes that judge it, which would let the agent lane approve itself",
    "gha_write_boundary_escape": "the proposed changed paths leave the issue's declared write boundary, named path by path, before any commit or push exists",
    "gha_pr_body_refused": "the proposed PR body is not exactly one 'Refs owner/repo#N' line naming this task's own subject",
    "gha_evidence_absent": "no complete evidence publication is bound to this candidate, so the run cannot report a custody receipt for what it executed",
}
def gha_outcome(status: str, **extra: Any) -> dict[str, Any]:
    # constraint: ed3c/noodles#189 - both hosted-lane gates leave through this one
    # constraint: exit, so a status without a machine-owned meaning cannot reach a
    # constraint: receipt and no reader has to re-derive what a refusal meant.
    meaning = GHA_STATUS_MEANINGS.get(status)
    if meaning is None:
        raise GateError(f"gha execution emitted undefined status: {status!r}")
    return {"admitted": status in GHA_ADMITTED_STATUSES, "status": status, "meaning": meaning, **extra}
def gha_task_identity(declaration: Mapping[str, Any]) -> str:
    """The derived idempotency key of one exact target-local execution task."""
    missing = [name for name in GHA_TASK_FIELDS if declaration.get(name) is None]
    if missing:
        raise GateError(f"gha task identity needs every declared field, missing: {', '.join(missing)}")
    canonical = json.dumps({name: declaration[name] for name in GHA_TASK_FIELDS}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
def gha_within_boundary(path: str, prefixes: Sequence[str]) -> bool:
    # constraint: ed3c/noodles#98 - delegates to the one segment-wise containment rule
    # constraint: instead of restating it, so a tightening at its declared home
    # constraint: (issue_contract.boundary_conflict) is inherited here automatically.
    return issue_contract.boundary_conflict((path,), tuple(prefixes)) is not None
def gha_execution_task(
    issue_body: str,
    dispatch: Mapping[str, Any],
    *,
    base_head: str,
    active_tasks: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Validate one dispatch against the exact issue bytes before any branch or PR exists.

    The gate parses the issue body itself, so the digest it compares the dispatch against is the
    digest of the text it read: an issue edited after dispatch fails as stale instead of executing
    against a body nobody validated. Only typed markers are inputs - issue prose, including planted
    injection prose, is never read, so it cannot widen the target, the lane, or the boundary. Every
    refusal returns before an identity exists, so a rejected dispatch leaves no branch and no PR."""
    if not HEX40_RE.fullmatch(base_head or ""):
        raise GateError(f"gha execution base head {base_head!r} is not one exact 40-hex commit")
    contract = parse_issue_contract(issue_body)
    admission = contract["admission"]
    if admission["lane"] != GHA_HOSTED_LANE:
        return gha_outcome(
            "gha_lane_refused",
            task=None,
            branch=None,
            admitted_lanes=list(admission["admitted_lanes"]),
            reasons=list(admission["reasons"]) or [f"admitted lane is {admission['lane']!r}, not {GHA_HOSTED_LANE!r}"],
        )
    boundary = contract["write_boundary"]
    if boundary is None:
        return gha_outcome("gha_boundary_undeclared", task=None, branch=None,
                           reasons=["issue declares no machine-readable noodles-write-boundary"])
    declaration = {
        "target": contract["target"],
        "subject": contract["subject"],
        "subject_body_sha256": issue_contract.body_digest(issue_body),
        "base_sha": base_head,
        "runtime": contract["runtime"],
        "evidence": contract["evidence"],
        "write_boundary": list(boundary),
    }
    for field, status in (
        ("target", "gha_target_mismatch"),
        ("subject", "gha_subject_mismatch"),
        ("subject_body_sha256", "gha_subject_digest_stale"),
        ("base_sha", "gha_base_mismatch"),
        ("runtime", "gha_runtime_mismatch"),
        ("evidence", "gha_evidence_policy_mismatch"),
        ("write_boundary", "gha_boundary_mismatch"),
    ):
        if dispatch.get(field) != declaration[field]:
            return gha_outcome(status, task=None, branch=None,
                               reasons=[f"dispatch {field} {dispatch.get(field)!r} != target-local {declaration[field]!r}"])
    task = gha_task_identity(declaration)
    branch = execute_branch(declaration["subject"])
    binding = {"task": task, "branch": branch, "checkout": issue_contract.EPHEMERAL_CHECKOUT, **declaration}
    if any(str(active.get("task")) == task for active in active_tasks):
        return gha_outcome("task_reused", **binding)
    duplicate = next((active for active in active_tasks if str(active.get("branch")) == branch), None)
    if duplicate is not None:
        return gha_outcome("gha_duplicate_claim", task=None, branch=None,
                           reasons=[f"branch {branch} is already held by target-local task {duplicate.get('task')!r}"])
    # constraint: ed3c/noodles#98 - reuse the landed disjointness machinery instead of a second
    # constraint: copy of it; an active task whose own boundary is undeclared blocks closed.
    conflict = boundary_admission_conflict(
        tuple(boundary),
        [(str(active.get("subject")), tuple(active["write_boundary"]) if active.get("write_boundary") is not None else None)
         for active in active_tasks],
    )
    if conflict is not None:
        return gha_outcome("gha_boundary_conflict", task=None, branch=None,
                           reasons=[f"declared write boundary intersects active task {conflict[0]} at {conflict[1]}"])
    return gha_outcome("task_admitted", **binding)
def gha_apply_admission(
    task: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    default_branch: str,
    evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Judge one agent safe output against the typed task before any commit, push, or PR exists.

    The agent job holds no write authority: what it emits is data, judged here against the task the
    issue was admitted under. Trusted workflow bytes are refused first and unconditionally, so a
    task whose declared boundary happens to contain `.github` still cannot rewrite the gate that
    judges it. One task admits exactly one branch and one PR body, so no proposal shape can fan
    out into a second branch or a second PR."""
    if not task.get("admitted") or not task.get("branch"):
        return gha_outcome("gha_task_unadmitted", reasons=[f"apply needs an admitted target-local task, got {task.get('status')!r}"])
    for field in ("branch", "pr_body"):
        if not isinstance(proposal.get(field), str) or not proposal[field]:
            return gha_outcome("gha_proposal_malformed", reasons=[f"apply proposal {field} must be exactly one non-empty string, got {proposal.get(field)!r}"])
    paths = proposal.get("changed_paths")
    if not isinstance(paths, list) or not paths or not all(isinstance(item, str) and item for item in paths):
        return gha_outcome("gha_proposal_malformed", reasons=["apply proposal changed_paths must be a non-empty list of exact repository-relative paths"])
    escaping = sorted(item for item in paths if item.startswith("/") or {".", ".."} & set(item.split("/")))
    if escaping:
        return gha_outcome("gha_proposal_malformed", reasons=[f"apply proposal changed paths are not repository-relative: {', '.join(escaping)}"])
    if proposal["branch"] == default_branch:
        return gha_outcome("gha_default_branch_push", reasons=[f"apply proposes writing the default branch {default_branch!r}"])
    if proposal["branch"] != task["branch"]:
        return gha_outcome("gha_branch_mismatch", reasons=[f"apply branch {proposal['branch']!r} is not the task's exact ephemeral branch {task['branch']!r}"])
    trusted = sorted(set(paths) & set(GHA_TRUSTED_WORKFLOW_PATHS))
    if trusted:
        return gha_outcome("gha_trusted_workflow_edit", reasons=[f"apply would rewrite the trusted workflow bytes that judge it: {', '.join(trusted)}"])
    boundary = list(task.get("write_boundary") or ())
    outside = sorted(item for item in paths if not gha_within_boundary(item, boundary))
    if outside:
        return gha_outcome("gha_write_boundary_escape", reasons=[
            f"changed paths outside the declared write boundary "
            f"{', '.join(boundary) or issue_contract.NO_WRITE_BOUNDARY}: {', '.join(outside)}"
        ])
    try:
        referenced = parse_pr_reference(proposal["pr_body"])
    except GateError as exc:
        return gha_outcome("gha_pr_body_refused", reasons=[str(exc)])
    if referenced != task["subject"]:
        return gha_outcome("gha_pr_body_refused", reasons=[f"PR body references {referenced} rather than this task's own subject {task['subject']}"])
    published = evidence or {}
    if not str(published.get("folder") or "") or not str(published.get("manifest_sha256") or ""):
        return gha_outcome("gha_evidence_absent", reasons=[f"no complete evidence publication is bound to this candidate: {published.get('status')!r}"])
    return gha_outcome("apply_admitted", task=task["task"], branch=task["branch"], subject=task["subject"],
                       changed_paths=sorted(paths), evidence_folder=published["folder"])
def verify_pull_request(root: Path, event_path: Path, candidate_root: Path, receipt_path: Path) -> dict[str, Any]:
    event = load_json(event_path)
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        raise GateError("verify requires a pull_request_target event")
    repository = event["repository"]["full_name"]
    number = int(pr["number"])
    head_sha = str(pr["head"]["sha"])
    base_ref = str(pr["base"]["ref"])
    policy = protection_policy(root)
    if repository not in policy["allowed_repositories"]:
        raise GateError(f"repository not admitted: {repository}")
    if base_ref != policy["default_branch"]:
        raise GateError(f"PR base must be {policy['default_branch']}")
    if pr.get("draft"):
        raise GateError("draft PR cannot produce a landing receipt")
    subject_value = parse_pr_reference(pr.get("body") or "")
    subject = parse_subject(subject_value)
    if subject.repo != repository:
        raise GateError("v1 requires issue and PR to be in the same repository")
    issue = issue_read(subject_value)
    contract = parse_issue_contract(issue.get("body") or "", expected_subject=subject_value)
    if issue.get("state") != "open" or contract["state"] != "awaiting_land":
        raise GateError("issue must be open and awaiting_land before PR verification")
    actual_head = git(candidate_root, "rev-parse", "HEAD")
    if actual_head != head_sha:
        raise GateError(f"candidate checkout {actual_head} != event head {head_sha}")
    changed_files = merge_base_changed_files(repository, base_ref, head_sha)
    components = component_map(root)
    surface_errors = component_surface_errors(contract["component"], components, changed_files)
    if surface_errors:
        raise GateError("candidate component-surface gate failed: " + "; ".join(surface_errors))
    import_edge_errors = component_import_edge_errors(
        contract["component"], components, changed_files, root, candidate_root
    )
    if import_edge_errors:
        raise GateError("candidate component-import-edge gate failed: " + "; ".join(import_edge_errors))
    owner_errors = component_owner_errors(
        contract["component"], components, changed_files, component_owner_map(root), root, candidate_root
    )
    if owner_errors:
        raise GateError("candidate component-ownership gate failed: " + "; ".join(owner_errors))
    introductions = introduced_components(root, candidate_root)
    introduction_errors = component_introduction_errors(introductions, issue.get("body") or "")
    if introduction_errors:
        raise GateError("candidate component-introduction gate failed: " + "; ".join(introduction_errors))
    # constraint: ed3c/noodles#264 - route truth: awaiting_land has several writers and the route
    # constraint: real lanes take cannot run `./noodles issue handoff`, so the journey-compilation
    # constraint: gate is compiled here, at the one confluence every candidate crosses on its way to
    # constraint: a landing receipt, over the same trusted provider compare readback the component
    # constraint: surface uses. Reaching awaiting_land by any writer therefore buys no bypass.
    feature_map = None
    declared_feature = (contract["feature"] or "").strip()
    if declared_feature:
        try:
            feature_map = feature_contract.compile_handoff_feature_map(declared_feature, changed_files, error_cls=GateError)
        except GateError as exc:
            raise GateError(
                f"candidate feature-journey gate failed: {exc}. Supported path: change the declared "
                f"feature's code surface in this candidate, land the feature contract before the "
                f"candidate that declares it, or drop the noodles-feature marker from {subject_value}"
            ) from exc
    result = verify_repository(candidate_root, root)
    if not result["ok"]:
        raise GateError("candidate repository gate failed: " + "; ".join(result["errors"]))
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "pr_number": number,
        "issue_subject": subject_value,
        "head_sha": head_sha,
        "tree_sha": git(candidate_root, "rev-parse", "HEAD^{tree}"),
        "base_ref": base_ref,
        "workflow_run_id": int(os.getenv("GITHUB_RUN_ID", "0")),
        "metrics": result["metrics"],
        "component": contract["component"],
        "introduces": introductions,
        "feature": feature_map["feature_id"] if feature_map else None,
        "feature_changed_node": feature_map["changed_node"] if feature_map else None,
        "feature_transitions": feature_map["transitions"] if feature_map else None,
        "feature_journeys": feature_map["journeys"] if feature_map else None,
        "gates": ["trusted-inventory", "positive-controls", "negative-controls", "issue-contract", "exact-head", "component-surface", "component-import-edges", "component-ownership", "component-introduction", "feature-journey", "evidence-publication"],
    }
    receipt["evidence_publication"] = evidence_publication(candidate_root, receipt)
    # constraint: ed3c/noodles#189 - the hosted agentic lane's safe-output boundary is judged here,
    # constraint: in the trusted checkout taken from the default branch, over provider-read changed
    # constraint: files and the exact issue body. The agent job never runs this gate and cannot
    # constraint: reach the bytes that implement it, so the lane cannot approve itself.
    if contract["admission"]["lane"] == GHA_HOSTED_LANE:
        receipt["gha_execution"] = gha_pull_request_admission(pr, repository, subject_value, issue, base_ref, changed_files, receipt, str(policy["default_branch"]))
        receipt["gates"].append("gha-execution")
    write_json(receipt_path, receipt)
    return receipt
def gha_pull_request_admission(
    pr: Mapping[str, Any],
    repository: str,
    subject_value: str,
    issue: Mapping[str, Any],
    base_ref: str,
    changed_files: Sequence[str],
    receipt: Mapping[str, Any],
    default_branch: str,
) -> dict[str, Any]:
    """Rebuild this candidate's target-local task from provider truth and judge the landed patch.

    The dispatch is reconstructed from what the provider itself reports about the candidate, so at
    the same-repository canary source and target coincide and the seven declaration comparisons are
    self-consistent by construction; they become live refusals only for a cross-repository
    `repository_dispatch`, which `policy/github.json` still holds. What refuses here today is the
    apply half: the head branch, the write boundary, the trusted workflow bytes, the PR body shape,
    and the bound evidence publication."""
    body = str(issue.get("body") or "")
    contract = parse_issue_contract(body, expected_subject=subject_value)
    base_sha = str(pr.get("base", {}).get("sha") or "")
    dispatch = {
        "target": repository,
        "subject": subject_value,
        "subject_body_sha256": issue_contract.body_digest(body),
        "base_sha": base_sha,
        "runtime": contract["runtime"],
        "evidence": contract["evidence"],
        "write_boundary": list(contract["write_boundary"] or ()),
    }
    task = gha_execution_task(body, dispatch, base_head=base_sha)
    if not task["admitted"]:
        raise GateError(f"candidate gha-execution task gate failed: {task['status']}: " + "; ".join(task.get("reasons") or ()))
    apply_result = gha_apply_admission(
        task,
        {"branch": str(pr.get("head", {}).get("ref") or ""), "changed_paths": list(changed_files), "pr_body": str(pr.get("body") or "")},
        default_branch=default_branch,
        evidence=receipt.get("evidence_publication"),
    )
    if not apply_result["admitted"]:
        raise GateError(f"candidate gha-execution apply gate failed: {apply_result['status']}: " + "; ".join(apply_result.get("reasons") or ()))
    return {"task": task, "apply": apply_result}


RECEIPT_ANCHOR_PREFIX = "physical-receipt-anchor:"


def post_receipt_anchor(repository: str, pr_number: int, merge_sha: str, merged_at: str) -> str:
    """One idempotent N-class receipt comment carrying the provider's own merge truth.

    Emitted per land, after the merge and Issue closure already succeeded, so it can never gate a
    landing: no admission path reads it back. One comment per land is naturally paced, which is what
    the replaced manual bulk backfill was not - that batch tripped GitHub's secondary content-creation
    limit. The Drive-index URL stays out of scope; host evidence is unreachable from the Action.

    Ceiling: existence is checked over the first 100 issue comments, matching the landing train's own
    comment scan. A PR carrying more than 100 comments before its land could take a second anchor."""
    existing = gh_api(f"repos/{repository}/issues/{pr_number}/comments?per_page=100")
    if any(RECEIPT_ANCHOR_PREFIX in str(comment.get("body") or "") for comment in existing or []):
        return "existing"
    gh_api(
        f"repos/{repository}/issues/{pr_number}/comments",
        method="POST",
        payload={"body": f"{RECEIPT_ANCHOR_PREFIX} pr={pr_number} merge-commit={merge_sha} merged-at={merged_at}"},
    )
    return "posted"


def land_pull_request(root: Path, event_path: Path, receipt_path: Path) -> dict[str, Any]:
    event = load_json(event_path)
    workflow = event.get("workflow_run")
    if not isinstance(workflow, dict):
        raise GateError("land requires workflow_run event")
    if workflow.get("name") != "verify" or workflow.get("conclusion") != "success":
        raise GateError("only successful verify workflow runs may land")
    pulls = workflow.get("pull_requests") or []
    if len(pulls) != 1:
        raise GateError(f"expected one PR on workflow run, got {len(pulls)}")
    receipt = load_json(receipt_path)
    repository = str(event["repository"]["full_name"])
    pr_number = int(pulls[0]["number"])
    head_sha = str(workflow["head_sha"])
    expected = {
        "repository": repository,
        "pr_number": pr_number,
        "head_sha": head_sha,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise GateError(f"receipt {key}={receipt.get(key)!r} != event {value!r}")
    policy = protection_policy(root)
    if repository not in policy["allowed_repositories"]:
        raise GateError(f"repository not admitted: {repository}")
    workflow_boundary_errors, workflow_boundary = github_protection.workflow_boundary_readback(root, sha256_file)
    if workflow_boundary_errors:
        raise GateError("trusted workflow boundary invalid: " + "; ".join(workflow_boundary_errors))
    verify_source = github_protection.trusted_workflow_run_readback(
        gh_api, GateError, repository, int(workflow.get("id") or 0), name="verify", path=".github/workflows/verify.yml", event="pull_request_target", default_branch=policy["default_branch"]
    )
    current_run_id = int(os.getenv("GITHUB_RUN_ID", "0") or "0")
    land_source: dict[str, Any] | None = None
    if current_run_id > 0:
        land_source = github_protection.trusted_workflow_run_readback(
            gh_api, GateError, repository, current_run_id, name="land", path=".github/workflows/land.yml", event="workflow_run", default_branch=policy["default_branch"]
        )
    protection_receipt = github_protection.protection_audit(
        lambda endpoint, **kwargs: github_protection.gh_api_response(run, GateError, endpoint, **kwargs),
        GateError,
        repository,
        policy["default_branch"],
        policy["required_check"],
    )
    pr = gh_api(f"repos/{repository}/pulls/{pr_number}")
    if pr.get("state") != "open" or pr.get("merged") or pr.get("draft"):
        raise GateError("PR must be open, unmerged, and non-draft")
    if pr["head"]["sha"] != head_sha or pr["base"]["ref"] != policy["default_branch"]:
        raise GateError("PR exact head/base readback failed")
    commit = gh_api(f"repos/{repository}/git/commits/{head_sha}")
    if commit.get("tree", {}).get("sha") != receipt.get("tree_sha"):
        raise GateError("receipt tree does not match GitHub head tree")
    subject_value = parse_pr_reference(pr.get("body") or "")
    if subject_value != receipt.get("issue_subject"):
        raise GateError("receipt subject does not match PR body")
    issue = issue_read(subject_value)
    contract = parse_issue_contract(issue.get("body") or "", expected_subject=subject_value)
    if issue.get("state") != "open" or contract["state"] != "awaiting_land":
        raise GateError("issue drifted before landing")
    merge = gh_api(
        f"repos/{repository}/pulls/{pr_number}/merge",
        method="PUT",
        payload={"sha": head_sha, "merge_method": "merge"},
    )
    if not merge or not merge.get("merged"):
        raise GateError(f"GitHub merge failed: {merge}")
    merge_sha = str(merge["sha"])
    pr_readback = gh_api(f"repos/{repository}/pulls/{pr_number}")
    if not pr_readback.get("merged") or pr_readback.get("merge_commit_sha") != merge_sha:
        raise GateError("merged PR readback failed")
    merge_commit = gh_api(f"repos/{repository}/git/commits/{merge_sha}")
    parents = {parent["sha"] for parent in merge_commit.get("parents", [])}
    if head_sha not in parents:
        raise GateError("merge commit does not retain the exact PR head as a parent")
    branch = gh_api(f"repos/{repository}/branches/{policy['default_branch']}")
    if branch.get("commit", {}).get("sha") != merge_sha:
        raise GateError("default branch did not advance to the observed merge commit")
    subject = parse_subject(subject_value)
    body = issue.get("body") or ""
    body = replace_marker(body, "state", "landed")
    body = replace_marker(body, "landed_pr", f"{repository}#{pr_number}")
    body = replace_marker(body, "head", head_sha)
    body = replace_marker(body, "merge", merge_sha)
    gh_api(f"repos/{subject.repo}/issues/{subject.number}", method="PATCH", payload={"body": body})
    gh_api(
        f"repos/{subject.repo}/issues/{subject.number}",
        method="PATCH",
        payload={"state": "closed", "state_reason": "completed"},
    )
    closed = issue_read(subject_value)
    closed_contract = parse_issue_contract(closed.get("body") or "", expected_subject=subject_value)
    if closed.get("state") != "closed" or closed_contract["state"] != "landed":
        raise GateError("issue closure readback failed")
    # constraint: the merge and Issue closure above are already durable provider state by this point;
    # constraint: the anchor comment is additive and N-class (see post_receipt_anchor's own docstring),
    # constraint: so nothing past here - including a missing merged_at or a failed comment POST - may
    # constraint: raise and report the land as failed once the merge and closure it is reporting on
    # constraint: already succeeded.
    try:
        merged_at = str(pr_readback.get("merged_at") or "")
        if not merged_at:
            raise GateError("merged PR readback carries no merged_at timestamp")
        anchor = post_receipt_anchor(repository, pr_number, merge_sha, merged_at)
    except GateError:
        anchor = "failed"
    return {
        "repository": repository,
        "pr_number": pr_number,
        "issue_subject": subject_value,
        "head_sha": head_sha,
        "merge_sha": merge_sha,
        "issue_closed": True,
        "receipt_anchor": anchor,
        "protection_readback": protection_receipt,
        "trusted_workflows": {
            "verify_run": verify_source["run"],
            "land_run": land_source["run"] if land_source else None,
            "provider_workflow_identity": {"verify": verify_source["workflow"], "land": land_source["workflow"] if land_source else None, "default_branch": verify_source["provider_default_branch"]},
            "boundary": workflow_boundary,
        },
    }


def train_failback_marker(head_sha: str) -> str:
    return f"<!-- noodles-train-failback: {head_sha} -->"


def train_verify_failed_head(repository: str, head_sha: str, required_check: str) -> bool:
    """Has this exact head already completed a trusted `verify` run concluded failed?

    Stateless starvation guard. A head that rebases cleanly never earns a fail-back marker, so a head
    whose verify is red for a reason a rebase cannot fix stays the oldest behind candidate forever and
    blocks every newer one. A COMPLETED failure at this exact head means re-selecting the same head only
    reproduces the same failure; the train defers to the owner pushing a new head, exactly like fail-back.
    A success, an in-progress run, or no run at all is not a completed failure and never skips.

    Reuses `workflow_runs_for_head` (the same runs-API surface `failed_required_workflow_run_readback`
    is built on) instead of re-deriving the endpoint call, so a malformed payload raises here exactly as
    it does everywhere else that reads this API, rather than reading as an untriggered guard. Matches the
    repo's own failed-conclusion taxonomy (`FAILED_WORKFLOW_CONCLUSIONS`), not just literal `failure`, and
    checks `event` the same way `trusted_workflow_run_readback` does. Stops short of that function's full
    immutable-workflow-identity verification: this is an advisory skip signal evaluated for every behind
    candidate, not the land-time trust boundary, and its only failure direction is deferring a candidate
    to the next cycle, never landing anything."""
    runs = github_protection.workflow_runs_for_head(gh_api, GateError, repository, head_sha)
    return any(
        run["name"] == required_check
        and run["path"] == ".github/workflows/verify.yml"
        and run["event"] == "pull_request_target"
        and run["status"] == "completed"
        and run["conclusion"] in github_protection.FAILED_WORKFLOW_CONCLUSIONS
        for run in runs
    )


def train_select(repository: str, default_branch: str, pulls: list[dict[str, Any]], required_check: str) -> dict[str, Any] | None:
    """Oldest open awaiting_land PR whose branch is behind the default branch; a head already failed back, or already red at verify, waits for its owner."""
    for pr in sorted(pulls, key=lambda item: (str(item.get("created_at") or ""), int(item.get("number") or 0))):
        head = pr.get("head") or {}
        if pr.get("state") != "open" or pr.get("draft"):
            continue
        if (pr.get("base") or {}).get("ref") != default_branch or (head.get("repo") or {}).get("full_name") != repository:
            continue
        try:
            subject_value = parse_pr_reference(pr.get("body") or "")
            issue = issue_read(subject_value)
        except GateError:
            continue
        contract = parse_issue_contract(issue.get("body") or "", expected_subject=subject_value)
        if issue.get("state") != "open" or contract["state"] != "awaiting_land":
            continue
        head_sha = str(head.get("sha") or "")
        compare = gh_api(f"repos/{repository}/compare/{default_branch}...{head_sha}")
        if int((compare or {}).get("behind_by") or 0) <= 0:
            continue
        comments = gh_api(f"repos/{repository}/issues/{pr['number']}/comments?per_page=100")
        if any(train_failback_marker(head_sha) in str(comment.get("body") or "") for comment in comments or []):
            continue
        try:
            skip = train_verify_failed_head(repository, head_sha, required_check)
        except GateError:
            continue
        if skip:
            continue
        return pr
    return None


def train_rebase(workdir: Path, remote_url: str, default_branch: str, head_ref: str, head_sha: str) -> dict[str, Any]:
    """Mechanical rebase only: git's textual replay, any conflict aborts; the force-push holds the observed-head lease."""
    workdir.mkdir(parents=True, exist_ok=True)
    git(workdir, "init", "--quiet", "--initial-branch", "noodles-train-scratch")
    git(workdir, "remote", "add", "origin", remote_url)
    git(
        workdir,
        "fetch",
        "--quiet",
        "origin",
        f"+refs/heads/{default_branch}:refs/remotes/origin/{default_branch}",
        f"+refs/heads/{head_ref}:refs/remotes/origin/{head_ref}",
    )
    remote_tip = git(workdir, "rev-parse", f"refs/remotes/origin/{head_ref}")
    if remote_tip != head_sha:
        raise GateError(f"landing train head drifted for {head_ref}: selected {head_sha} but remote is {remote_tip}")
    base_sha = git(workdir, "rev-parse", f"refs/remotes/origin/{default_branch}")
    git(workdir, "checkout", "--quiet", "-B", head_ref, head_sha)
    rebase = run(
        [
            "git",
            "-c", "user.name=noodles-train",
            "-c", "user.email=noodles-train@users.noreply.github.com",
            "-c", "commit.gpgsign=false",
            "rebase", f"refs/remotes/origin/{default_branch}",
        ],
        cwd=workdir,
        check=False,
    )
    if rebase.returncode != 0:
        conflicts = sorted(path for path in git(workdir, "diff", "--name-only", "--diff-filter=U", check=False).splitlines() if path)
        run(["git", "rebase", "--abort"], cwd=workdir, check=False)
        return {"rebased": False, "base_sha": base_sha, "conflicts": conflicts, "detail": rebase.stderr.strip() or rebase.stdout.strip()}
    new_head = git(workdir, "rev-parse", "HEAD")
    git(workdir, "push", "--quiet", f"--force-with-lease=refs/heads/{head_ref}:{head_sha}", "origin", f"HEAD:refs/heads/{head_ref}")
    pushed = git(workdir, "ls-remote", "origin", f"refs/heads/{head_ref}").split()
    if not pushed or pushed[0] != new_head:
        raise GateError(f"landing train push readback failed for {head_ref}: expected {new_head}, remote has {pushed[0] if pushed else 'nothing'}")
    return {"rebased": True, "base_sha": base_sha, "new_head": new_head}


def landing_train(root: Path, remote_url: str | None = None) -> dict[str, Any]:
    policy = protection_policy(root)
    repository = str(policy["repository"])
    default_branch = str(policy["default_branch"])
    pulls = gh_api(f"repos/{repository}/pulls?state=open&base={default_branch}&sort=created&direction=asc&per_page=100")
    if not isinstance(pulls, list):
        raise GateError("landing train pull request listing readback failed")
    selected = train_select(repository, default_branch, pulls, str(policy["required_check"]))
    if selected is None:
        return {"action": "idle", "repository": repository, "selected": None}
    head_ref = str(selected["head"]["ref"])
    head_sha = str(selected["head"]["sha"])
    pr_number = int(selected["number"])
    if remote_url is None:
        token = os.getenv("NOODLES_TRAIN_PUSH_TOKEN", "").strip()
        if not token:
            raise GateError("landing train push token absent: NOODLES_TRAIN_PUSH_TOKEN must carry the scoped Contents-write App token")
        remote_url = f"https://x-access-token:{token}@github.com/{repository}"
    with tempfile.TemporaryDirectory(prefix="noodles-train-") as temp_name:
        outcome = train_rebase(Path(temp_name), remote_url, default_branch, head_ref, head_sha)
    receipt = {
        "repository": repository,
        "pr_number": pr_number,
        "head_ref": head_ref,
        "old_head": head_sha,
        "base_sha": outcome["base_sha"],
    }
    if not outcome["rebased"]:
        named = ", ".join(outcome["conflicts"]) if outcome["conflicts"] else (outcome["detail"] or "unknown rebase failure")
        gh_api(
            f"repos/{repository}/issues/{pr_number}/comments",
            method="POST",
            payload={
                "body": (
                    f"{train_failback_marker(head_sha)}\n"
                    f"Landing train fail-back: mechanical rebase of `{head_ref}` ({head_sha}) onto `{default_branch}` "
                    f"({outcome['base_sha']}) stopped on conflicts in: {named}. The train never auto-resolves content; "
                    "rebase manually and push a new head to re-enter the queue."
                )
            },
        )
        return {"action": "failback", "conflicts": outcome["conflicts"], **receipt}
    return {"action": "rebased", "new_head": outcome["new_head"], **receipt}


def http_json(url: str, *, payload: Any | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GateError(f"Noodle control request failed for {url}: {exc}") from exc


def provider_landed(subject_value: str) -> tuple[int, str, str]:
    issue = issue_read(subject_value)
    contract = parse_issue_contract(issue.get("body") or "", expected_subject=subject_value)
    if issue.get("state") != "closed" or contract["state"] != "landed":
        raise GateError(f"provider has not landed {subject_value}")
    body = issue.get("body") or ""
    landed_pr = one_marker(body, "landed_pr")
    head_sha = one_marker(body, "head")
    merge_sha = one_marker(body, "merge")
    pr_subject = parse_subject(landed_pr or "")
    if pr_subject.repo != parse_subject(subject_value).repo:
        raise GateError("landed PR repository does not match issue")
    pr = gh_api(f"repos/{pr_subject.repo}/pulls/{pr_subject.number}")
    if not pr.get("merged") or pr.get("head", {}).get("sha") != head_sha or pr.get("merge_commit_sha") != merge_sha:
        raise GateError("landed PR readback does not match issue receipt")
    return pr_subject.number, head_sha or "", merge_sha or ""


def reconcile_once(root: Path, control_url: str) -> list[str]:
    branch = str(reconcile_checkout_admission(root)["branch"])
    snapshot = http_json(control_url.rstrip("/") + "/api/snapshot")
    completed: list[str] = []
    for review in snapshot.get("pending_reviews") or []:
        order_id = str(review.get("order_id") or "")
        try:
            parse_subject(order_id)
            provider_landed(order_id)
        except GateError:
            continue
        git(root, "fetch", "--quiet", "origin", branch)
        git(root, "merge", "--ff-only", f"origin/{branch}")
        provider_head = git(root, "rev-parse", f"refs/remotes/origin/{branch}")
        local_after = git(root, "rev-parse", "HEAD")
        if local_after != provider_head:
            raise GateError(f"reconcile fast-forward readback drift: branch {branch} local {local_after} provider {provider_head}")
        command_id = f"noodles-reconcile-{hashlib.sha256(order_id.encode()).hexdigest()[:12]}"
        ack = http_json(
            control_url.rstrip("/") + "/api/control",
            payload={"id": command_id, "action": "merge", "order_id": order_id},
        )
        if ack.get("id") != command_id or ack.get("action") != "merge" or ack.get("status") != "ok":
            raise GateError(f"Noodle rejected machine reconciliation for {order_id}: {ack}")
        completed.append(order_id)
    return completed


def issue_template(repo: str, number: int, title: str) -> str:
    subject = f"{repo}#{number}"
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {repo} -->\n"
        f"<!-- noodles-subject: {subject} -->\n"
        "<!-- noodles-state: ready -->\n"
        "<!-- noodles-depends-on: none -->\n\n"
        f"## Goal\n\n{title}\n\n"
        "## Physical acceptance\n\n- Exact-subject positive and planted-negative controls pass.\n"
        "- Direct source/provider readback proves only the stated claim.\n"
        "- `./noodles verify` passes with zero tracked residue.\n\n"
        "## Non-claims\n\n- No adjacent capability is admitted by prose or inference.\n"
    )


INTAKE_BLOCKER_OWNER = "intake-normalizer"
INTAKE_BLOCKER_PLACEHOLDER = f"<!-- noodles-blocker: {INTAKE_BLOCKER_OWNER}: contract intake normalization pending -->"
INTAKE_DEFECTS_IN_COMMENT = "contract intake defects are named in the intake comment"
INTAKE_CURE_LIMIT = 8


def intake_has_marker(body: str, name: str) -> bool:
    return bool(MARKER_PATTERNS[name].search(body or ""))


def intake_body(header: Sequence[str], body: str) -> str:
    return "".join(f"{line}\n" for line in header) + ("\n" if header else "") + (body or "")


def intake_cure(reason: str, subject: Subject) -> tuple[str, bool] | None:
    """One marker line for one exact parser diagnostic, plus whether its value is derived.

    A derived value comes from provider truth or from the single supported literal; a value that
    is only a fail-closed default is not derived, and one of those turns the whole repair into a
    blocked normalization instead of a silent migration."""
    if reason == "missing noodles-role marker":
        return "<!-- noodles-role: repository-mutating-atom -->", True
    if reason == "missing noodles-target marker":
        return f"<!-- noodles-target: {subject.repo} -->", True
    if reason == "missing noodles-subject marker":
        return f"<!-- noodles-subject: {subject.value} -->", True
    if reason == "missing noodles-state marker":
        return "<!-- noodles-state: blocked -->", False
    if reason.startswith("noodles-state: blocked requires"):
        return INTAKE_BLOCKER_PLACEHOLDER, False
    return None


def intake_normalization(body: str, subject: Subject, title: str) -> dict[str, Any] | None:
    """Plan the one-shot intake repair of a nonconforming issue, or None when nothing is owed.

    Every cure is a marker line inserted above the original body, which is never edited: a defect
    the exact parser still reports after curing therefore stays visible instead of being silently
    overwritten. The receipt marker makes the repair happen exactly once."""
    if intake_has_marker(body, "normalized"):
        return None
    header: list[str] = []
    defects: list[str] = []
    derivable = True
    for _ in range(INTAKE_CURE_LIMIT):
        try:
            parse_issue_contract(intake_body(header, body), expected_subject=subject.value)
            break
        except GateError as exc:
            reason = str(exc)
            defects.append(reason)
            cure = intake_cure(reason, subject)
            if cure is None:
                derivable = False
                break
            header.append(cure[0])
            derivable = derivable and cure[1]
    else:
        raise GateError(f"intake normalization did not converge for {subject.value}: {'; '.join(defects)}")
    if not intake_has_marker(intake_body(header, body), "depends_on"):
        declared = issue_contract.derive_dependencies(body, subject.value)
        if declared is None:
            derivable = False
        else:
            header.append(f"<!-- noodles-depends-on: {declared} -->")
    if not header and not defects:
        return None
    if not derivable:
        reason = "; ".join(defects) or "contract intake normalization"
        # constraint: a blocker reason carrying dependency prose is rejected by the exact contract, so
        # constraint: the individually named defects fall back to the intake comment, never to a failed write.
        if issue_contract.DEPENDENCY_PROSE_RE.search(reason):
            reason = INTAKE_DEFECTS_IN_COMMENT
        blocker = f"<!-- noodles-blocker: {INTAKE_BLOCKER_OWNER}: {reason} -->"
        header = [blocker if line == INTAKE_BLOCKER_PLACEHOLDER else line for line in header]
    header.append(f"<!-- noodles-normalized: {issue_contract.body_digest(body)} -->")
    normalized = intake_body(header, body)
    if derivable:
        # constraint: a migration claims the issue now conforms, so prove it against the exact
        # constraint: parser before writing instead of discovering a bad derivation at the next sync.
        parse_issue_contract(normalized, expected_subject=subject.value)
    return {"body": normalized, "comment": "" if derivable else intake_comment(subject, title, defects)}


def intake_comment(subject: Subject, title: str, defects: Sequence[str]) -> str:
    """Name each defect and carry the canonical template; never author Goal or acceptance prose."""
    named = "\n".join(f"- {item}" for item in defects) or "- contract intake normalization"
    return (
        "Intake normalization: this issue did not satisfy the noodles Issue contract, so "
        "`noodles adapter sync` inserted the mechanically derivable markers above the original "
        "body and left the original body byte-intact. It is blocked until a human or atom repairs "
        "the named defects and sets it back to `ready`.\n\n"
        f"Named contract defects:\n\n{named}\n\n"
        "Canonical shape:\n\n"
        "```markdown\n"
        f"{issue_template(subject.repo, subject.number, title)}"
        "```\n"
    )


def intake_normalize(issue: dict[str, Any], repository: str, *, verify_live: bool = False) -> dict[str, Any]:
    """Apply the intake repair to one open issue and read the write back; conforming issues are untouched."""
    subject = Subject(repository, int(issue.get("number") or 0))
    body = issue.get("body") or ""
    plan = intake_normalization(body, subject, str(issue.get("title") or subject.value))
    if plan is None:
        return issue
    if verify_live:
        # constraint: ed3c/noodles#292 - a resumed cycle's finalists snapshot can be older than the
        # constraint: bucket death that interrupted it; refuse to overwrite a body a human has since
        # constraint: edited rather than silently discarding the edit underneath the derived markers.
        live = gh_api(f"repos/{repository}/issues/{subject.number}")
        if not isinstance(live, dict) or (live.get("body") or "") != body:
            raise GateError(
                f"intake normalization snapshot is stale for {subject.value}: live body changed since derivation"
            )
    updated = gh_api(
        f"repos/{repository}/issues/{subject.number}", method="PATCH", payload={"body": plan["body"]}
    )
    if not isinstance(updated, dict) or (updated.get("body") or "") != plan["body"]:
        raise GateError(f"intake normalization body readback failed for {subject.value}")
    if plan["comment"]:
        gh_api(
            f"repos/{repository}/issues/{subject.number}/comments",
            method="POST",
            payload={"body": plan["comment"]},
        )
    return {**issue, "body": plan["body"]}


def backlog_graphql_snapshot(repository: str) -> dict[str, Any]:
    """One pointed GraphQL query in place of the whole per-issue REST fan-out.

    ed3c/noodles#292 - open issues with their bodies plus the open pull requests a later cycle
    correlates against, on GraphQL's own point budget. A malformed or errored response is named and
    fails closed here: falling back to N REST reads would restore exactly the spend this replaces."""
    owner, _, name = repository.partition("/")
    if not owner or not name:
        raise GateError(f"backlog GraphQL bulk sync needs an owner/name repository, got {repository!r}")
    issues: list[dict[str, Any]] = []
    pull_requests: list[dict[str, Any]] = []
    issue_cursor: str | None = None
    pull_cursor: str | None = None
    issue_done = pull_done = False
    for _ in range(BACKLOG_GRAPHQL_PAGE_LIMIT):
        payload = gh_api(
            "graphql",
            method="POST",
            payload={
                "query": BACKLOG_GRAPHQL_QUERY,
                "variables": {"owner": owner, "name": name, "issues": issue_cursor, "pulls": pull_cursor},
            },
        )
        repo = (payload.get("data") or {}).get("repository") if isinstance(payload, dict) else None
        if not isinstance(payload, dict) or payload.get("errors") or not isinstance(repo, dict):
            detail = json.dumps(payload.get("errors") if isinstance(payload, dict) else payload, default=str)[:400]
            raise GateError(
                f"backlog GraphQL bulk sync failed for {repository}: {detail}; "
                "refusing to fall back to per-issue REST reads"
            )
        issue_page, pull_page = repo.get("issues"), repo.get("pullRequests")
        if not isinstance(issue_page, dict) or not isinstance(pull_page, dict):
            raise GateError(
                f"backlog GraphQL bulk sync for {repository} returned no issues/pullRequests connections; "
                "refusing to fall back to per-issue REST reads"
            )
        # constraint: one query carries two independently paginated connections, so an exhausted one
        # constraint: keeps re-serving its first page while the other advances; consuming that page
        # constraint: twice would silently duplicate every entry in it.
        if not issue_done:
            issues.extend(graphql_issue_records(repository, issue_page.get("nodes")))
            issue_done = not bool((issue_page.get("pageInfo") or {}).get("hasNextPage"))
            issue_cursor = str((issue_page.get("pageInfo") or {}).get("endCursor") or "") or None
        if not pull_done:
            pull_requests.extend(graphql_pull_records(repository, pull_page.get("nodes")))
            pull_done = not bool((pull_page.get("pageInfo") or {}).get("hasNextPage"))
            pull_cursor = str((pull_page.get("pageInfo") or {}).get("endCursor") or "") or None
        if issue_done and pull_done:
            return {"repository": repository, "issues": issues, "pull_requests": pull_requests}
    raise GateError(f"backlog GraphQL bulk sync for {repository} did not terminate within {BACKLOG_GRAPHQL_PAGE_LIMIT} pages")


def graphql_issue_records(repository: str, nodes: Any) -> list[dict[str, Any]]:
    """GraphQL issue nodes in the exact shape every existing contract reader already consumes."""
    if not isinstance(nodes, list):
        raise GateError(f"backlog GraphQL issue nodes for {repository} were not an array")
    records: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("number"), int):
            raise GateError(f"backlog GraphQL issue node for {repository} was malformed")
        records.append(
            {
                "number": node["number"],
                "state": str(node.get("state") or "").lower() or "open",
                "title": node.get("title") or "",
                "body": node.get("body") or "",
                "html_url": node.get("url") or "",
            }
        )
    return records


def graphql_pull_records(repository: str, nodes: Any) -> list[dict[str, Any]]:
    if not isinstance(nodes, list):
        raise GateError(f"backlog GraphQL pull request nodes for {repository} were not an array")
    records: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("number"), int):
            raise GateError(f"backlog GraphQL pull request node for {repository} was malformed")
        records.append(
            {
                "number": node["number"],
                "head_ref": str((node.get("headRef") or {}).get("name") or node.get("headRefName") or ""),
                "body": node.get("body") or "",
                "url": node.get("url") or "",
            }
        )
    return records


def backlog_backoff_seconds(consecutive_empty: int) -> float:
    """How long an empty frontier is held before it is derived again.

    ed3c/noodles#292 - 19 cycles x ~250 calls in one window, every one ending with no orders, is
    what emptied the bucket. Re-polling an empty frontier at full price every three minutes is the
    dominant idle waste, and doubling the hold is the smallest thing that removes it."""
    if consecutive_empty <= 0:
        return 0.0
    return min(BACKLOG_EMPTY_BASE_SECONDS * float(2 ** min(consecutive_empty - 1, 20)), BACKLOG_EMPTY_CEILING_SECONDS)


def backlog_cycle_path(project: Path, repository: str) -> Path:
    return project / f"{BACKLOG_CYCLE_PREFIX}{repository.replace('/', '-')}.json"


def backlog_cycle_record(project: Path, repository: str) -> dict[str, Any]:
    try:
        payload = json.loads(backlog_cycle_path(project, repository).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) and payload.get("repository") == repository else {}


def write_backlog_cycle(project: Path, repository: str, record: dict[str, Any]) -> None:
    path = backlog_cycle_path(project, repository)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def backlog_items(
    repository: str,
    finalists: Mapping[str, Any],
    dependency_cache: dict[str, dict[str, Any]],
    known_requirements: frozenset[str],
    *,
    resumed: bool = False,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for issue in finalists.get("issues") or ():
        if "pull_request" in issue:
            continue
        try:
            issue = intake_normalize(issue, repository, verify_live=resumed)
            contract = issue_contract_payload(issue, None, dependency_cache, known_requirements)
        except GateError as exc:
            number = issue.get("number")
            output.append(
                {
                    "id": f"{repository}#{number}",
                    "title": issue.get("title") or f"{repository}#{number}",
                    "status": "blocked",
                    "url": issue.get("html_url"),
                    "diagnostic": f"issue contract invalid: {exc}",
                }
            )
            continue
        output.append(
            {
                "id": contract["subject"],
                "title": issue.get("title") or contract["subject"],
                "status": contract["state"],
                "url": issue.get("html_url"),
                "target": contract["target"],
                "feature": contract["feature"],
                "dependencies": contract["dependencies"],
                "blocker": contract["blocker"],
                "body_sha256": contract["body_sha256"],
                "requirements": contract["requirements"],
                "schedulable": contract["schedulable"],
                "reasons": contract["reasons"],
            }
        )
    return output


def sync_backlog(
    project: Path,
    repository: str,
    dependency_cache: dict[str, dict[str, Any]],
    known_requirements: frozenset[str],
    *,
    now: float,
) -> list[dict[str, Any]]:
    """One backlog cycle: front-loaded, resumable, and held when the frontier keeps coming back empty.

    ed3c/noodles#292 - the finalists are persisted the moment they exist, before any per-subject
    spend, so a bucket death in the finishing stage resumes from that derivation instead of paying
    for it again. A cycle that produced nothing schedulable holds the next derivation for an
    exponentially growing interval, and both the count and the interval live in the cycle record."""
    record = backlog_cycle_record(project, repository)
    empty_before = int(record.get("consecutive_empty") or 0)
    if record.get("stage") == "complete" and now < float(record.get("next_derivation_at") or 0.0):
        write_backlog_cycle(project, repository, {**record, "served": "backoff_hold"})
        return [dict(item) for item in record.get("items") or ()]
    finalists = record.get("finalists") if record.get("stage") == "finalists" else None
    resumed = finalists is not None
    if not resumed:
        finalists = backlog_graphql_snapshot(repository)
        write_backlog_cycle(project, repository, {
            "repository": repository,
            "stage": "finalists",
            "finalists": finalists,
            "consecutive_empty": empty_before,
            "derived_at": now,
            "resumed": False,
            "served": "derived",
        })
    items = backlog_items(repository, finalists or {}, dependency_cache, known_requirements, resumed=resumed)
    empty = 0 if any(item.get("schedulable") for item in items) else empty_before + 1
    interval = backlog_backoff_seconds(empty)
    write_backlog_cycle(project, repository, {
        "repository": repository,
        "stage": "complete",
        "finalists": finalists,
        "items": items,
        "consecutive_empty": empty,
        "interval_seconds": interval,
        "derived_at": now,
        "next_derivation_at": now + interval,
        "resumed": resumed,
        "served": "derived",
    })
    return items


def adapter_sync() -> int:
    root = repo_root()
    repositories = [item.strip() for item in os.getenv("NOODLES_REPOSITORIES", "").split(",") if item.strip()]
    if not repositories:
        repositories = [runtime_gh_repo_from_git(root, error_cls=GateError)]
    output: list[dict[str, Any]] = []
    dependency_cache: dict[str, dict[str, Any]] = {}
    # constraint: ed3c/noodles#120 monitor reconcile - resolved once rather than once per issue below:
    # constraint: not silent here (each dropped issue still prints its own diagnostic), but an
    # constraint: unreadable specification would otherwise read as N unrelated per-issue defects
    # constraint: instead of one cause.
    known_requirements = system_requirement_ids()
    project = runtime_contract.noodle_project_root(root, error_cls=GateError)
    now = time.time()
    for repository in repositories:
        output.extend(sync_backlog(project, repository, dependency_cache, known_requirements, now=now))
    output.extend(findings_backlog_items(root))
    for item in output:
        print(json.dumps(item, separators=(",", ":")))
    return 0


def adapter_add(title: str) -> int:
    root = repo_root()
    repository = os.getenv("NOODLES_TARGET_REPOSITORY") or runtime_gh_repo_from_git(root, error_cls=GateError)
    provisional = {
        "title": title,
        "body": "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {repository} -->\n"
        "<!-- noodles-subject: pending -->\n"
        "<!-- noodles-state: ready -->\n",
    }
    created = gh_api(f"repos/{repository}/issues", method="POST", payload=provisional)
    number = int(created["number"])
    body = issue_template(repository, number, title)
    gh_api(f"repos/{repository}/issues/{number}", method="PATCH", payload={"body": body})
    readback = issue_read(f"{repository}#{number}")
    print(json.dumps({"id": f"{repository}#{number}", "title": readback["title"], "status": "ready"}, separators=(",", ":")))
    return 0


def adapter_edit(item_id: str, new_status: str) -> int:
    issue_set_state(item_id, new_status)
    return 0


def adapter_done(item_id: str) -> int:
    provider_landed(item_id)
    return 0


def adapter_main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        raise GateError("adapter action required")
    action = args[0]
    if action == "sync" and len(args) == 1:
        return adapter_sync()
    if action == "add" and len(args) == 2:
        return adapter_add(args[1])
    if action == "edit" and len(args) == 3:
        return adapter_edit(args[1], args[2])
    if action == "done" and len(args) == 2:
        return adapter_done(args[1])
    raise GateError(f"invalid adapter invocation: {args}")


def start_unattended(
    root: Path,
    control_url: str,
    interval: float,
    admission_timeout: float = daemon_lease.DEFAULT_ADMISSION_TIMEOUT,
) -> int:
    control_checkout_admission(root)
    verified = verify_repository(root)
    if not verified["ok"]:
        raise GateError("repository verification failed: " + "; ".join(verified["errors"]))
    runtime_receipt = runtime_check(root)
    provider_sync(root)
    skill_discovery_check(root, runtime_receipt["binary_path"], error_cls=GateError)
    codex_isolation.codex_surface_canary(root, error_cls=GateError)
    policy = protection_policy(root)
    protection_readback(policy["repository"], policy["default_branch"], policy["required_check"])
    project = runtime_contract.noodle_project_root(root, error_cls=GateError)
    daemon_lease.reject_existing_lease(project, error_cls=GateError)
    env = os.environ.copy()
    env.setdefault("NOODLE_NO_BROWSER", "1")
    process = subprocess.Popen([runtime_receipt["binary_path"], "start"], cwd=root, env=env)
    try:
        # constraint: poll_interval matches the start-entrypoint test harness's listener-served polling cadence so this wrapper's real admission cannot lose the race and get torn down mid-check
        lease = daemon_lease.admit_started_daemon(
            project, control_url, process, error_cls=GateError, timeout=admission_timeout, poll_interval=0.02
        )
    except BaseException as admission_failure:
        try:
            daemon_lease.terminate_own_child(process, control_url, error_cls=GateError)
        except GateError as residue:
            raise GateError(f"{admission_failure}; {residue}") from admission_failure
        raise
    print(json.dumps({"daemon_lease": lease}, separators=(",", ":"), sort_keys=True), file=sys.stderr)

    def stop(_signum: int, _frame: Any) -> None:
        process.terminate()

    old_int = signal.signal(signal.SIGINT, stop)
    old_term = signal.signal(signal.SIGTERM, stop)
    try:
        while process.poll() is None:
            try:
                repair_pending_reviews(root, control_url)
            except GateError as exc:
                print(f"repair: {exc}", file=sys.stderr)
            try:
                for outcome in sweep_dead_claims(root):
                    if outcome.get("action") in ("adopted", "released", "held"):
                        print(json.dumps(outcome, separators=(",", ":"), sort_keys=True), file=sys.stderr)
            except GateError as exc:
                print(f"claims: {exc}", file=sys.stderr)
            try:
                reconcile_once(root, control_url)
            except GateError as exc:
                print(f"reconcile: {exc}", file=sys.stderr)
            time.sleep(interval)
        return int(process.returncode or 0)
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
        if process.poll() is None:
            process.terminate()


def git_ok(root: Path, *args: str) -> bool:
    return run(["git", *args], cwd=root, check=False).returncode == 0


def commit_identity(root: Path) -> tuple[str, str]:
    identity = protection_policy(root).get("commit_identity")
    name = str(identity.get("name") or "").strip() if isinstance(identity, dict) else ""
    email = str(identity.get("email") or "").strip() if isinstance(identity, dict) else ""
    if not name or not email:
        raise GateError("policy/github.json must declare commit_identity with a non-empty name and email")
    return name, email


def identity_git_argv(root: Path) -> list[str]:
    name, email = commit_identity(root)
    # constraint: inline -c only - writing git config mutates shared checkout state that every other session on this tree reads.
    return ["git", "-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "commit.gpgsign=false"]


def unsaved_content_commits(root: Path, provider_head: str, local_head: str) -> list[str]:
    # constraint: a daemon-made local merge commit carries no unique content, so containment is demanded only of non-merge commits.
    revisions = [line.strip() for line in git(root, "rev-list", "--no-merges", f"{provider_head}..{local_head}").splitlines() if line.strip()]
    return [revision for revision in revisions if not git(root, "branch", "-r", "--contains", revision, check=False).strip()]


def heal_control_checkout(root: Path, default_branch: str, *, salvage_push: bool = True) -> dict[str, Any]:
    branch = git(root, "branch", "--show-current")
    if branch != default_branch:
        raise GateError(f"heal refuses a control checkout on {branch or '<detached>'}, not default branch {default_branch}")
    dirty = [line for line in git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines() if line.strip()]
    if dirty:
        raise GateError("heal refuses a dirty control checkout: " + "; ".join(dirty[:5]))
    remote_ref = f"refs/remotes/origin/{default_branch}"
    git(root, "fetch", "--quiet", "--no-tags", "origin", f"refs/heads/{default_branch}:{remote_ref}")
    local_head = git(root, "rev-parse", "HEAD")
    provider_head = git(root, "rev-parse", remote_ref)
    actions: list[str] = []
    salvage_ref = ""
    if local_head != provider_head and not git_ok(root, "merge-base", "--is-ancestor", local_head, provider_head):
        unsaved = unsaved_content_commits(root, provider_head, local_head)
        if unsaved:
            if not salvage_push:
                raise GateError(f"heal refuses to reset {branch}: unsaved content commits {' '.join(unsaved)}")
            salvage_ref = f"salvage-{default_branch}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}"
            git(root, "push", "--quiet", "origin", f"{local_head}:refs/heads/{salvage_ref}")
            git(root, "fetch", "--quiet", "--no-tags", "origin", f"refs/heads/{salvage_ref}:refs/remotes/origin/{salvage_ref}")
            if git(root, "rev-parse", f"refs/remotes/origin/{salvage_ref}") != local_head:
                raise GateError(f"salvage push readback failed for origin/{salvage_ref}; refusing to reset {branch}")
            actions.append("salvage_push")
        git(root, "update-ref", f"refs/heads/{default_branch}", provider_head, local_head)
        git(root, "reset", "--hard", "--quiet", provider_head)
        actions.append("lossless_reset")
    if git(root, "rev-parse", "HEAD") != provider_head:
        git(root, "merge", "--ff-only", "--quiet", remote_ref)
        actions.append("fast_forward")
    healed_head = git(root, "rev-parse", "HEAD")
    if healed_head != provider_head:
        raise GateError(f"heal readback drift: local {healed_head} provider {provider_head}")
    project = runtime_contract.noodle_project_root(root, error_cls=GateError)
    lease_path = project / daemon_lease.LOCK_RELATIVE
    lease_pid, lease_text = daemon_lease.read_lease(project)
    if lease_pid is not None and not daemon_lease.process_alive(lease_pid):
        lease_path.unlink()
        if lease_path.exists():
            raise GateError(f"stale lease readback failed: {lease_path} survived removal")
        actions.append("cleared_stale_lease")
    elif lease_pid is not None:
        raise GateError(f"heal refuses to touch {lease_path}: pid {lease_pid} is alive")
    elif lease_text:
        raise GateError(f"heal refuses an unreadable lease: {lease_path} holds {lease_text!r}")
    status = daemon_lease.read_status(project)
    if not lease_path.exists() and str(status.get("loop_state") or "") in daemon_lease.LIVE_LOOP_STATES:
        # constraint: with no lease a live loop_state is stale by construction, and daemon_lease.reject_existing_lease refuses to start over it.
        write_json(project / daemon_lease.STATUS_RELATIVE, {**status, "loop_state": "idle"})
        if str(daemon_lease.read_status(project).get("loop_state") or "") != "idle":
            raise GateError("status-ghost cure readback failed")
        actions.append("cured_status_ghost")
    return {
        "branch": default_branch,
        "local_head_before": local_head,
        "provider_head": provider_head,
        "local_head_after": healed_head,
        "salvage_ref": salvage_ref,
        "actions": actions,
    }


def rate_limit_cooldown(payload: Any, now: float) -> float:
    core = payload.get("resources", {}).get("core") if isinstance(payload, dict) else None
    if not isinstance(core, dict):
        raise GateError("rate limit readback is missing resources.core")
    remaining = int(core.get("remaining") or 0)
    reset = float(core.get("reset") or 0)
    if remaining > SECONDARY_BURST_REMAINING:
        # constraint: a full primary bucket means the 403 was secondary limiting, whose window is short and unrelated to reset.
        return SECONDARY_BURST_COOLDOWN_SECONDS
    wait = reset - now + RATE_LIMIT_RESET_MARGIN_SECONDS
    return wait if 0 < wait < RATE_LIMIT_COOLDOWN_CEILING_SECONDS else RATE_LIMIT_COOLDOWN_FALLBACK_SECONDS


def cycle_status(
    receipt: Mapping[str, Any],
    read_rate_limit: Callable[[], Any],
    backoff_seconds: float,
) -> tuple[str, float]:
    """Classify one supervised cycle and name the wait it earns.

    ed3c/noodles#291 - a depleted bucket is a schedulable wait, not a defect. A generation that
    stopped on the provider's own budget gets its own status and backs off until that budget's
    reset; only a generation the budget does not explain is a failure."""
    if receipt["returncode"] == 0 and receipt["reason"] == "exited":
        return "ok", 0.0
    declared = float(receipt.get("declared_quota_wait") or 0.0)
    if declared > 0:
        return "quota_wait", declared
    if receipt["returncode"] != 0 and RATE_LIMIT_TAIL_RE.search(receipt["tail"]):
        return "quota_wait", rate_limit_cooldown(read_rate_limit(), time.time())
    if receipt["returncode"] != 0 and receipt["reason"] == "exited":
        return "failed", backoff_seconds
    return "failed", 0.0


def rotation_env(base: Mapping[str, str], token_command: str) -> dict[str, str]:
    env = dict(base)
    env.setdefault("NOODLE_NO_BROWSER", "1")
    if not token_command.strip():
        return env
    token = run(["bash", "-c", token_command]).stdout.strip()
    if not token or any(character.isspace() for character in token):
        raise GateError(f"{TOKEN_COMMAND_ENV} produced no single-token installation credential")
    env["GH_TOKEN"] = token
    env["GITHUB_TOKEN"] = token
    return env


def run_supervised_generation(
    root: Path,
    argv: Sequence[str],
    *,
    wedge_seconds: float,
    rotate_after_seconds: float,
    env: Mapping[str, str] | None = None,
    now_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    process = subprocess.Popen(
        list(argv),
        cwd=str(root),
        env=dict(env) if env is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    started = last_output = now_fn()
    tail: collections.deque[str] = collections.deque(maxlen=SUPERVISE_TAIL_LINES)
    reason = "exited"
    quota_wait_until = 0.0
    declared_quota_wait = 0.0
    while process.poll() is None:
        ready, _, _ = select.select([process.stdout], [], [], SUPERVISE_POLL_SECONDS)
        now = now_fn()
        # constraint: the deadlines are checked every pass, not only on a silent one - a chatty generation must still rotate.
        if now - started >= rotate_after_seconds:
            reason = "rotation"
            break
        # constraint: ed3c/noodles#291 - a child that declared a quota wait is silent because the
        # constraint: provider told it to be. Killing it at the ordinary deadline is how the 13:20
        # constraint: generation died with no stderr; a child that declared nothing is still killed.
        if now - last_output >= wedge_seconds and now >= quota_wait_until:
            reason = "wedge"
            break
        if not ready:
            continue
        line = process.stdout.readline()
        if line:
            tail.append(line.rstrip("\n"))
            last_output = now
            declared = DECLARED_QUOTA_WAIT_RE.search(line)
            if declared is not None:
                declared_quota_wait = float(declared.group(1))
                quota_wait_until = now + declared_quota_wait
            continue
        try:
            process.wait(timeout=SUPERVISE_TERMINATE_GRACE)
        except subprocess.TimeoutExpired:
            reason = "output_closed"
        break
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=SUPERVISE_TERMINATE_GRACE)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=SUPERVISE_TERMINATE_GRACE)
    # ponytail: the pipe is drained non-blocking because a surviving grandchild can hold its write end open forever; a blocking read would wedge the supervisor itself.
    try:
        os.set_blocking(process.stdout.fileno(), False)
        for line in (process.stdout.read() or "").splitlines():
            tail.append(line)
    except (BlockingIOError, OSError, ValueError):
        pass
    process.stdout.close()
    joined = "\n".join(tail)
    trailing = DECLARED_QUOTA_WAIT_RE.findall(joined)
    return {
        "reason": reason,
        "returncode": int(process.returncode if process.returncode is not None else -1),
        "seconds": round(now_fn() - started, 3),
        "tail": joined,
        "declared_quota_wait": max([declared_quota_wait, *(float(value) for value in trailing)] or [0.0]),
    }


def append_supervise_log(root: Path, receipt: Mapping[str, Any]) -> None:
    project = runtime_contract.noodle_project_root(root, error_cls=GateError)
    path = project / SUPERVISE_LOG_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **receipt}, sort_keys=True) + "\n")


def supervise(
    root: Path,
    control_url: str,
    *,
    generations: int = 0,
    wedge_seconds: float = DEFAULT_WEDGE_SECONDS,
    rotate_after_seconds: float = DEFAULT_ROTATE_AFTER_SECONDS,
    backoff_seconds: float = DEFAULT_RESTART_BACKOFF_SECONDS,
    child_argv: Sequence[str] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    rate_limit_fn: Callable[[], Any] | None = None,
) -> list[dict[str, Any]]:
    default_branch = str(protection_policy(root)["default_branch"])
    argv = list(child_argv or [sys.executable, str(root / "noodles.py"), "start", "--control-url", control_url])
    read_rate_limit = rate_limit_fn or (lambda: gh_api("rate_limit"))
    receipts: list[dict[str, Any]] = []
    generation = 0
    while generations <= 0 or generation < generations:
        generation += 1
        receipt: dict[str, Any] = {"generation": generation}
        try:
            receipt["heal"] = heal_control_checkout(root, default_branch)
            env = rotation_env(os.environ, os.environ.get(TOKEN_COMMAND_ENV, ""))
        except GateError as exc:
            receipt["error"] = str(exc)
            receipt["status"] = "failed"
            receipt["meaning"] = CYCLE_STATUS_MEANINGS["failed"]
            receipt["cooldown"] = backoff_seconds
            receipts.append(receipt)
            append_supervise_log(root, receipt)
            sleep_fn(backoff_seconds)
            continue
        receipt.update(run_supervised_generation(
            root, argv, wedge_seconds=wedge_seconds, rotate_after_seconds=rotate_after_seconds, env=env
        ))
        status, cooldown = cycle_status(receipt, read_rate_limit, backoff_seconds)
        receipt["status"] = status
        receipt["meaning"] = CYCLE_STATUS_MEANINGS[status]
        receipt["cooldown"] = cooldown
        receipts.append(receipt)
        append_supervise_log(root, receipt)
        if cooldown > 0:
            sleep_fn(cooldown)
    return receipts


def paced_gh(root: Path, argv: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    carrier = root / GH_CARRIER_RELATIVE
    if not os.access(carrier, os.X_OK):
        raise GateError(f"paced gh carrier is missing or not executable: {carrier}")
    return run([str(carrier), *argv], cwd=root, check=check)


def ceremony_commit(root: Path, message: str, paths: Sequence[str]) -> dict[str, Any]:
    if not message.strip():
        raise GateError("ceremony commit requires a non-empty message")
    name, email = commit_identity(root)
    if paths:
        run(["git", "add", "--", *paths], cwd=root)
    result = run([*identity_git_argv(root), "commit", "-m", message], cwd=root, check=False)
    if result.returncode != 0:
        # constraint: a rejected commit leaves the shared index staged, and the next session's commit would carry these paths under its own message.
        if paths:
            run(["git", "restore", "--staged", "--", *paths], cwd=root, check=False)
        raise GateError(f"ceremony commit rejected: {(result.stderr or result.stdout).strip()}")
    head, author_name, author_email, committer_name, committer_email = git(root, "log", "-1", "--format=%H%n%an%n%ae%n%cn%n%ce").splitlines()
    if (author_name, author_email, committer_name, committer_email) != (name, email, name, email):
        raise GateError(
            f"commit identity readback failed at {head}: author {author_name} <{author_email}> committer {committer_name} <{committer_email}> != {name} <{email}>"
        )
    return {"verb": "commit", "head": head, "identity": f"{name} <{email}>", "paths": list(paths)}


def ceremony_rebase(root: Path, upstream: str) -> dict[str, Any]:
    before = git(root, "rev-parse", "HEAD")
    result = run([*identity_git_argv(root), "rebase", upstream], cwd=root, check=False)
    if result.returncode != 0:
        run(["git", "rebase", "--abort"], cwd=root, check=False)
        raise GateError(f"ceremony rebase onto {upstream} failed and was aborted: {(result.stderr or result.stdout).strip()}")
    for state in ("rebase-merge", "rebase-apply"):
        if Path(git(root, "rev-parse", "--git-path", state)).exists():
            raise GateError(f"ceremony rebase onto {upstream} left {state} in progress")
    return {"verb": "rebase", "upstream": upstream, "before": before, "head": git(root, "rev-parse", "HEAD")}


def branch_tip_readback(gh_api_fn: Callable[..., Any], repository: str, branch: str) -> str:
    payload = gh_api_fn(f"repos/{repository}/git/ref/heads/{branch}")
    sha = payload.get("object", {}).get("sha") if isinstance(payload, dict) else None
    if not isinstance(sha, str) or not HEX40_RE.fullmatch(sha):
        raise GateError(f"branch tip readback failed for {repository} {branch}")
    return sha


def select_workflow_run(gh_api_fn: Callable[..., Any], repository: str, head_sha: str, workflow: str) -> dict[str, Any]:
    runs = [item for item in github_protection.workflow_runs_for_head(gh_api_fn, GateError, repository, head_sha) if item["name"] == workflow]
    if not runs:
        raise GateError(f"no {workflow!r} workflow run for {repository} head {head_sha}")
    return max(runs, key=lambda item: (item["run_attempt"], item["id"]))


def workflow_run_readback(gh_api_fn: Callable[..., Any], repository: str, run_id: int) -> dict[str, Any]:
    payload = gh_api_fn(f"repos/{repository}/actions/runs/{run_id}")
    head_sha = payload.get("head_sha") if isinstance(payload, dict) else None
    if not isinstance(head_sha, str) or not HEX40_RE.fullmatch(head_sha) or int(payload.get("id") or 0) != run_id:
        raise GateError(f"workflow run readback failed for {repository} run {run_id}")
    return {"id": run_id, "name": str(payload.get("name") or ""), "head_sha": head_sha, "head_branch": str(payload.get("head_branch") or "")}


def ceremony_run(gh_api_fn: Callable[..., Any], repository: str, branch: str, workflow: str) -> dict[str, Any]:
    branch_tip = branch_tip_readback(gh_api_fn, repository, branch)
    return {"verb": "run", "repository": repository, "branch": branch, "branch_tip": branch_tip, "run": select_workflow_run(gh_api_fn, repository, branch_tip, workflow)}


def ceremony_rerun(
    root: Path,
    gh_api_fn: Callable[..., Any],
    repository: str,
    branch: str,
    *,
    workflow: str | None = None,
    run_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    branch_tip = branch_tip_readback(gh_api_fn, repository, branch)
    if run_id is not None:
        selected = workflow_run_readback(gh_api_fn, repository, run_id)
    elif workflow:
        selected = select_workflow_run(gh_api_fn, repository, branch_tip, workflow)
    else:
        raise GateError("ceremony rerun requires --workflow or --run-id")
    if selected["head_sha"] != branch_tip:
        raise GateError(
            f"ceremony rerun refused: run {selected['id']} head {selected['head_sha']} != {branch} tip {branch_tip}; "
            "rerunning a stale head cancels the live head's run under the per-PR concurrency group"
        )
    if not dry_run:
        paced_gh(root, ["run", "rerun", str(selected["id"]), "--repo", repository])
    return {"verb": "rerun", "repository": repository, "branch": branch, "branch_tip": branch_tip, "run": selected, "dry_run": dry_run}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noodles")
    parser.add_argument("--root", default=None, help="repository root (testing/audit only)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    verify = sub.add_parser("verify")
    verify.add_argument("--policy-root")
    verify.add_argument("--json", action="store_true")
    verify.add_argument("--trusted-preview", action="store_true", help="also run the default-branch test modules against this working tree, as the trusted CI job would")
    verify.add_argument("--trusted-ref", default="origin/main", help="ref the trusted preview treats as the default-branch tip")
    metrics = sub.add_parser("metrics")
    metrics.add_argument("--json", action="store_true")
    structural = sub.add_parser("structural")
    structural.add_argument("action", choices=["verify"])
    structural.add_argument("--json", action="store_true")
    runtime = sub.add_parser("runtime")
    runtime.add_argument("action", choices=["check", "discover"])
    providers = sub.add_parser("providers")
    providers.add_argument("action", choices=["check", "sync"])
    retrieval = sub.add_parser("retrieval")
    retrieval.add_argument("action", choices=["probe", "canary"])
    retrieval.add_argument("--index-root", required=True)
    issue = sub.add_parser("issue")
    issue_sub = issue.add_subparsers(dest="issue_action", required=True)
    issue_validate = issue_sub.add_parser("validate")
    issue_validate.add_argument("subject")
    issue_contract_command = issue_sub.add_parser("contract")
    issue_contract_command.add_argument("subject")
    issue_handoff = issue_sub.add_parser("handoff")
    issue_handoff.add_argument("subject")
    issue_handoff.add_argument("--pr", type=int, required=True)
    feature = sub.add_parser("feature")
    feature.add_argument("action", choices=["verify"])
    feature.add_argument("feature_id")
    acceptance = sub.add_parser("acceptance")
    acceptance.add_argument("action", choices=["verify"])
    acceptance.add_argument("--feature")
    eval_sub = sub.add_parser("eval").add_subparsers(dest="eval_action", required=True)
    eval_gh = eval_sub.add_parser("gh-boundary")
    eval_gh.add_argument("--tool", action="append", default=[]); eval_gh.add_argument("child_command", nargs=argparse.REMAINDER)
    skill_eval_sub = sub.add_parser("skill-eval").add_subparsers(dest="skill_eval_action", required=True)
    skill_eval_sweep = skill_eval_sub.add_parser("sweep")
    skill_eval_sweep.add_argument("--lane-index", required=True, help="caller-supplied lane index; the sweep reads no clock and no live backlog")
    skill_eval_sweep.add_argument("--archive-root", required=True)
    skill_eval_sweep.add_argument("--out", required=True)
    skill_eval_sweep.add_argument("--sample", action="append", default=[], help="explicit owner/repo#N lane to package on top of every non-landed lane")
    skill_eval_sweep.add_argument("--since", default="")
    skill_eval_sweep.add_argument("--until", default="")
    github = sub.add_parser("github")
    github_sub = github.add_subparsers(dest="github_action", required=True)
    protect = github_sub.add_parser("protect")
    protect.add_argument("action", choices=["audit", "apply"])
    protect.add_argument("--repository")
    verify_pr = github_sub.add_parser("verify-pr")
    verify_pr.add_argument("--event", required=True)
    verify_pr.add_argument("--candidate", required=True)
    verify_pr.add_argument("--receipt", required=True)
    land = github_sub.add_parser("land")
    land.add_argument("--event", required=True)
    land.add_argument("--receipt", required=True)
    github_sub.add_parser("train")
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--control-url", default=os.getenv("NOODLE_CONTROL_URL", "http://127.0.0.1:3210"))
    reconcile.add_argument("--watch", action="store_true")
    reconcile.add_argument("--interval", type=float, default=5.0)
    repair = sub.add_parser("repair")
    repair.add_argument("--control-url", default=os.getenv("NOODLE_CONTROL_URL", "http://127.0.0.1:3210"))
    start = sub.add_parser("start")
    start.add_argument("--control-url", default=os.getenv("NOODLE_CONTROL_URL", "http://127.0.0.1:3210"))
    start.add_argument("--interval", type=float, default=5.0)
    start.add_argument("--admission-timeout", type=float, default=daemon_lease.DEFAULT_ADMISSION_TIMEOUT)
    supervise_command = sub.add_parser("supervise")
    supervise_command.add_argument("--control-url", default=os.getenv("NOODLE_CONTROL_URL", "http://127.0.0.1:3210"))
    supervise_command.add_argument("--generations", type=int, default=0, help="stop after N daemon generations (0 = unbounded)")
    supervise_command.add_argument("--wedge-seconds", type=float, default=DEFAULT_WEDGE_SECONDS)
    supervise_command.add_argument("--rotate-after", type=float, default=DEFAULT_ROTATE_AFTER_SECONDS)
    supervise_command.add_argument("--heal-only", action="store_true", help="run the heal conditions and print the receipt without spawning a daemon")
    ceremony = sub.add_parser("ceremony")
    ceremony_sub = ceremony.add_subparsers(dest="ceremony_verb", required=True)
    ceremony_commit_command = ceremony_sub.add_parser("commit")
    ceremony_commit_command.add_argument("-m", "--message", required=True)
    ceremony_commit_command.add_argument("--path", action="append", default=[])
    ceremony_rebase_command = ceremony_sub.add_parser("rebase")
    ceremony_rebase_command.add_argument("upstream")
    ceremony_run_command = ceremony_sub.add_parser("run")
    ceremony_run_command.add_argument("--workflow", required=True)
    ceremony_run_command.add_argument("--branch", required=True)
    ceremony_run_command.add_argument("--repository")
    ceremony_rerun_command = ceremony_sub.add_parser("rerun")
    ceremony_rerun_command.add_argument("--branch", required=True)
    ceremony_rerun_command.add_argument("--workflow")
    ceremony_rerun_command.add_argument("--run-id", type=int)
    ceremony_rerun_command.add_argument("--repository")
    ceremony_rerun_command.add_argument("--dry-run", action="store_true")
    ceremony_gh_command = ceremony_sub.add_parser("gh")
    ceremony_gh_command.add_argument("argv", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    try:
        if args.command == "preflight":
            print(json.dumps(preflight(root), indent=2, sort_keys=True))
            return 0
        if args.command == "verify":
            result = verify_repository(root, repo_root(args.policy_root) if args.policy_root else None)
            if args.trusted_preview:
                preview = trusted_preview.preview_trusted_verify(root, trusted_ref=args.trusted_ref, error_cls=GateError)
                result["trusted_preview"] = preview
                if not preview["ok"]:
                    result["ok"] = False
                    result["errors"] = [*result["errors"], *(f"trusted verify would red: {name}" for name in preview["would_red"]), preview["diagnostic"]]
                if not args.json:
                    print(f"trusted-preview {preview['trusted_ref']}@{preview['trusted_sha'][:12]} ({preview['fetch']}): {'PASS' if preview['ok'] else 'FAIL'}")
            print(json.dumps(result, indent=2, sort_keys=True) if args.json else ("PASS" if result["ok"] else "FAIL"))
            if not result["ok"]:
                for error in result["errors"]:
                    print(f"- {error}", file=sys.stderr)
                return 1
            return 0
        if args.command == "structural":
            result = structural_contract.structural_readback(root, error_cls=GateError)
            print(json.dumps(result, indent=2, sort_keys=True) if args.json else ("PASS" if result["ok"] else "FAIL"))
            if not result["ok"]:
                for error in result["errors"]:
                    print(f"- {error}", file=sys.stderr)
                return 1
            return 0
        if args.command == "metrics":
            metrics = metrics_readback(root)
            print(json.dumps(metrics, indent=2, sort_keys=True) if args.json else json.dumps(metrics, sort_keys=True))
            return 0
        if args.command == "runtime":
            result = runtime_check(root) if args.action == "check" else runtime_discovery(root)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "providers":
            receipts = provider_sync(root) if args.action == "sync" else provider_check(root)
            print(json.dumps(receipts, indent=2, sort_keys=True))
            return 0
        if args.command == "retrieval":
            if args.action == "canary":
                receipt = retrieval_contract.code_intel_canary(
                    root, Path(args.index_root), retrieval_contract.CANARY_SUBJECT, error_cls=GateError
                )
                write_json(root / retrieval_contract.CANARY_EVIDENCE_PATH, receipt)
            else:
                receipt = retrieval_contract.retrieval_probe(root, Path(args.index_root), error_cls=GateError)
                write_json(root / retrieval_contract.EVIDENCE_PATH, receipt)
            print(json.dumps(receipt, indent=2, sort_keys=True))
            return 0
        if args.command == "issue":
            if args.issue_action == "validate":
                issue = issue_read(args.subject)
                print(json.dumps(parse_issue_contract(issue.get("body") or "", args.subject), indent=2, sort_keys=True))
                return 0
            if args.issue_action == "contract":
                print(json.dumps(issue_contract_readback(args.subject), indent=2, sort_keys=True))
                return 0
            if args.issue_action == "handoff":
                subject = parse_subject(args.subject)
                pr = gh_api(f"repos/{subject.repo}/pulls/{args.pr}")
                print(json.dumps(execute_handoff(root, args.subject, args.pr, pr)))
                return 0
        if args.command == "feature":
            evidence = feature_contract.verify_feature(root, args.feature_id, error_cls=GateError)
            write_json(root / feature_contract.EVIDENCE_PATH, evidence)
            print(json.dumps(evidence, indent=2, sort_keys=True))
            return 0
        if args.command == "acceptance":
            evidence = feature_contract.verify_acceptance(root, args.feature, error_cls=GateError)
            write_json(root / feature_contract.ACCEPTANCE_EVIDENCE_PATH, evidence)
            print(json.dumps(evidence, indent=2, sort_keys=True))
            return 0
        if args.command == "eval":
            if args.eval_action != "gh-boundary":
                raise GateError(f"unsupported eval action: {args.eval_action}")
            command = list(args.child_command[1:] if args.child_command[:1] == ["--"] else args.child_command)
            print(json.dumps(github_protection.run_bounded_gh_admission_eval(root, command, required_tools=args.tool, error_cls=GateError), indent=2, sort_keys=True))
            return 0
        if args.command == "skill-eval":
            if args.skill_eval_action != "sweep":
                raise GateError(f"unsupported skill-eval action: {args.skill_eval_action}")
            manifest = runtime_contract.sweep_skill_eval(
                Path(args.lane_index),
                Path(args.archive_root),
                Path(args.out),
                sample=args.sample,
                since=args.since,
                until=args.until,
                error_cls=GateError,
            )
            print(json.dumps(manifest, indent=2, sort_keys=True))
            return 0
        if args.command == "github":
            if args.github_action == "protect":
                policy = protection_policy(root)
                repository = args.repository or policy["repository"]
                if args.action == "apply":
                    github_protection.protection_apply(
                        gh_api,
                        lambda endpoint, **kwargs: github_protection.gh_api_response(run, GateError, endpoint, **kwargs),
                        GateError,
                        repository,
                        policy["default_branch"],
                        policy["required_check"],
                    )
                result = github_protection.protection_audit(
                    lambda endpoint, **kwargs: github_protection.gh_api_response(run, GateError, endpoint, **kwargs),
                    GateError,
                    repository,
                    policy["default_branch"],
                    policy["required_check"],
                )
                print(json.dumps(result, indent=2, sort_keys=True))
                return 0
            if args.github_action == "verify-pr":
                receipt = verify_pull_request(root, Path(args.event), Path(args.candidate), Path(args.receipt))
                print(json.dumps(receipt, indent=2, sort_keys=True))
                return 0
            if args.github_action == "land":
                result = land_pull_request(root, Path(args.event), Path(args.receipt))
                print(json.dumps(result, indent=2, sort_keys=True))
                return 0
            if args.github_action == "train":
                print(json.dumps(landing_train(root), indent=2, sort_keys=True))
                return 0
        if args.command == "reconcile":
            if args.watch:
                while True:
                    completed = reconcile_once(root, args.control_url)
                    if completed:
                        print(json.dumps({"reconciled": completed}))
                    time.sleep(args.interval)
            else:
                candidate = os.environ.get("NOODLES_CANDIDATE_ROOT")
                sweep_root = repo_root(candidate) if candidate else root
                print(json.dumps({
                    "reconciled": reconcile_once(root, args.control_url),
                    "claims": sweep_dead_claims(root),
                    "closures": sweep_closure_dispositions(sweep_root),
                }))
            return 0
        if args.command == "repair":
            print(json.dumps({"repairable": repair_pending_reviews(root, args.control_url)}, indent=2, sort_keys=True))
            return 0
        if args.command == "start":
            return start_unattended(root, args.control_url, args.interval, args.admission_timeout)
        if args.command == "supervise":
            if args.heal_only:
                print(json.dumps(heal_control_checkout(root, str(protection_policy(root)["default_branch"])), indent=2, sort_keys=True))
                return 0
            receipts = supervise(
                root,
                args.control_url,
                generations=args.generations,
                wedge_seconds=args.wedge_seconds,
                rotate_after_seconds=args.rotate_after,
            )
            print(json.dumps({"generations": receipts}, indent=2, sort_keys=True))
            return 0
        if args.command == "ceremony":
            repository = str(protection_policy(root)["repository"])
            if args.ceremony_verb == "commit":
                print(json.dumps(ceremony_commit(root, args.message, args.path), indent=2, sort_keys=True))
                return 0
            if args.ceremony_verb == "rebase":
                print(json.dumps(ceremony_rebase(root, args.upstream), indent=2, sort_keys=True))
                return 0
            if args.ceremony_verb == "run":
                print(json.dumps(ceremony_run(gh_api, args.repository or repository, args.branch, args.workflow), indent=2, sort_keys=True))
                return 0
            if args.ceremony_verb == "rerun":
                receipt = ceremony_rerun(
                    root,
                    gh_api,
                    args.repository or repository,
                    args.branch,
                    workflow=args.workflow,
                    run_id=args.run_id,
                    dry_run=args.dry_run,
                )
                print(json.dumps(receipt, indent=2, sort_keys=True))
                return 0
            if args.ceremony_verb == "gh":
                child = list(args.argv[1:] if args.argv[:1] == ["--"] else args.argv)
                result = paced_gh(root, child, check=False)
                sys.stdout.write(result.stdout)
                sys.stderr.write(result.stderr)
                return int(result.returncode)
    except GateError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 2


def execute_branch(subject_value: str) -> str:
    subject = parse_subject(subject_value)
    return f"{subject.repo.replace('/', '-')}-{subject.number}-0-execute"


def matching_open_pull_requests(repository: str, subject_value: str) -> list[dict[str, Any]]:
    # constraint: ed3c/noodles#99 - I4 open-PR correlation. A subject with an open PR is a
    # constraint: lane already in flight, but #46's duplicate-active-branch control cannot see
    # constraint: it: a second attempt carries its own branch, so the exact execute ref is free
    # constraint: and the subject reads back unclaimed. Correlate on the provider's own PR list
    # constraint: instead - the exact lane branch, or the exact `Refs owner/repo#N` body every
    # constraint: PR here must carry. Paginated like open_issues: an unpaginated read silently
    # constraint: stops matching past the provider's first page of open pull requests.
    # constraint: repair_contract.find_open_pr_for_subject does not route through this exit yet
    # constraint: (ed3c/noodles#272): repair_contract.py is not in the "schedule" component and
    # constraint: that map is read from the trusted default branch, not the candidate, so this
    # constraint: PR cannot widen its own component boundary to use it.
    lane = execute_branch(subject_value)
    matched: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = gh_api(f"repos/{repository}/pulls?state=open&per_page=100&page={page}")
        if not isinstance(payload, list):
            raise GateError(f"provider open pull request readback for {repository} was not an array")
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get("number"), int):
                raise GateError(f"provider open pull request readback for {repository} was malformed")
            try:
                referenced = parse_pr_reference(str(item.get("body") or ""))
            except GateError:
                referenced = None
            if str((item.get("head") or {}).get("ref") or "") == lane or referenced == subject_value:
                matched.append(item)
        if len(payload) < 100:
            break
        page += 1
    matched.sort(key=lambda item: item["number"])
    return matched


def subject_open_pull_requests(repository: str, subject_value: str) -> list[str]:
    return [f"{repository}#{item['number']}" for item in matching_open_pull_requests(repository, subject_value)]


def matching_branch_refs(repository: str, prefix: str) -> dict[str, str]:
    payload = gh_api(f"repos/{repository}/git/matching-refs/heads/{prefix}")
    if not isinstance(payload, list):
        raise GateError(f"provider matching refs readback for {repository} was not an array")
    refs: dict[str, str] = {}
    for item in payload:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("ref"), str)
            or not isinstance(item.get("object"), dict)
            or not isinstance(item["object"].get("sha"), str)
            or not HEX40_RE.fullmatch(item["object"]["sha"])
        ):
            raise GateError(f"provider matching refs readback for {repository} was malformed")
        ref = str(item["ref"])
        if ref in refs:
            raise GateError(f"provider matching refs readback for {repository} contained duplicate {ref}")
        refs[ref] = str(item["object"]["sha"])
    return refs


def active_execute_claims(repository: str, refs: dict[str, str]) -> set[str]:
    branch_prefix = repository.replace("/", "-") + "-"
    pattern = re.compile(rf"^refs/heads/{re.escape(branch_prefix)}([1-9][0-9]*)-0-execute$")
    return {
        f"{repository}#{match.group(1)}"
        for ref in refs
        if (match := pattern.fullmatch(ref)) is not None
    }


def open_issues(repository: str) -> tuple[dict[str, Any], ...]:
    issues: list[dict[str, Any]] = []
    seen: set[int] = set()
    page = 1
    while True:
        payload = gh_api(
            f"repos/{repository}/issues?state=open&sort=created&direction=asc&per_page=100&page={page}"
        )
        if not isinstance(payload, list):
            raise GateError(f"provider issue frontier page {page} for {repository} was not an array")
        for issue in payload:
            if not isinstance(issue, dict):
                raise GateError(f"provider issue frontier page {page} for {repository} was malformed")
            number = issue.get("number")
            if not isinstance(number, int) or number < 1:
                raise GateError(f"provider issue frontier for {repository} has an invalid issue number")
            if number in seen:
                raise GateError(f"provider issue frontier for {repository} contained duplicate issue {number}")
            seen.add(number)
            issues.append(issue)
        if len(payload) < 100:
            return tuple(issues)
        page += 1


def schedule_snapshot(repository: str) -> tuple[schedule_domain.ScheduleIssue, ...]:
    # constraint: ed3c/noodles#120 monitor reconcile - resolved once, outside the per-issue
    # constraint: `except GateError: continue` below, so an unreadable specification raises loudly
    # constraint: here instead of silently emptying the whole frontier one dropped issue at a time.
    known_requirements = system_requirement_ids()
    branch_prefix = repository.replace("/", "-") + "-"
    claimed_subjects = active_execute_claims(repository, matching_branch_refs(repository, branch_prefix))
    dependency_cache: dict[str, dict[str, Any]] = {}
    snapshot: list[schedule_domain.ScheduleIssue] = []
    emitted_subjects: set[str] = set()
    provider_issues = open_issues(repository)
    open_subjects = {
        f"{repository}#{issue['number']}"
        for issue in provider_issues
        if "pull_request" not in issue
    }
    for issue in provider_issues:
        if "pull_request" in issue:
            continue
        number = issue.get("number")
        assert isinstance(number, int)
        subject_value = f"{repository}#{number}"
        try:
            contract = issue_contract_payload(issue, subject_value, dependency_cache, known_requirements)
        except GateError:
            continue
        emitted_subjects.add(subject_value)
        snapshot.append(
            schedule_domain.ScheduleIssue(
                subject=subject_value,
                repository=repository,
                number=number,
                dependencies=tuple(contract["dependencies"] or ()),
                p0=bool(P0_TITLE_RE.match(str(issue.get("title") or ""))),
                schedulable=bool(contract["schedulable"]),
                claimed=subject_value in claimed_subjects,
                write_boundary=contract["write_boundary"],
            )
        )
    malformed_claims = claimed_subjects.intersection(open_subjects) - emitted_subjects
    for subject_value in sorted(malformed_claims, key=lambda value: parse_subject(value).number):
        snapshot.append(
            schedule_domain.ScheduleIssue(
                subject=subject_value,
                repository=repository,
                number=parse_subject(subject_value).number,
                dependencies=(),
                p0=False,
                schedulable=False,
                claimed=True,
                malformed=True,
            )
        )
    return tuple(snapshot)


def claim_execute_branch(repository: str, branch: str, head: str) -> dict[str, Any]:
    exact_ref = f"refs/heads/{branch}"
    try:
        created = gh_api(
            f"repos/{repository}/git/refs",
            method="POST",
            payload={"ref": exact_ref, "sha": head},
        )
    except GateError:
        if exact_ref in matching_branch_refs(repository, branch):
            return {"status": "claimed_elsewhere", "branch": branch, "head": None}
        raise
    if (
        not isinstance(created, dict)
        or created.get("ref") != exact_ref
        or created.get("object", {}).get("sha") != head
    ):
        raise GateError(f"provider claim readback for {exact_ref} did not match created head {head}")
    return {"status": "claimed", "branch": branch, "head": head}


def schedule_claim_outcome(subject: str, status: str, **extra: Any) -> dict[str, Any]:
    # constraint: ed3c/noodles#191 - every publish outcome leaves through this
    # constraint: one exit, so a status without a machine-owned meaning cannot
    # constraint: reach the receipt and no reader has to re-derive one.
    meaning = skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS.get(status)
    if meaning is None:
        raise GateError(f"schedule publish emitted undefined claim status: {status!r}")
    return {"subject": subject, "status": status, "meaning": meaning, **extra}


def boundary_admission_conflict(
    candidate: tuple[str, ...],
    reserved: Sequence[tuple[str, tuple[str, ...] | None]],
) -> tuple[str, str] | None:
    # constraint: ed3c/noodles#98 - return the first reserved lane the candidate
    # constraint: intersects, as (subject, intersecting-prefix); a reserved lane
    # constraint: whose own boundary is undeclared (None) could write anywhere and
    # constraint: blocks the candidate closed, named by NO_WRITE_BOUNDARY.
    for reserved_subject, reserved_boundary in reserved:
        if reserved_boundary is None:
            return (reserved_subject, issue_contract.NO_WRITE_BOUNDARY)
        prefix = issue_contract.boundary_conflict(candidate, reserved_boundary)
        if prefix is not None:
            return (reserved_subject, prefix)
    return None


def local_handoff_body(subject_value: str, contract: dict[str, Any], boundary: tuple[str, ...]) -> str:
    return (
        f"<!-- noodles-local-handoff: {contract['body_sha256']} -->\n"
        f"local-noodle handoff for {subject_value}\n"
        f"- target: {contract['target']}\n"
        f"- local capability: {contract['runtime']}\n"
        f"- evidence policy: {contract['evidence']}\n"
        f"- write boundary: {', '.join(boundary) or issue_contract.NO_WRITE_BOUNDARY}\n"
        "Noodle remains the sole owner of the persistent worktree lifecycle for this lane."
    )


def emit_local_handoff(subject_value: str, contract: dict[str, Any], boundary: tuple[str, ...]) -> dict[str, Any]:
    # constraint: ed3c/noodles#187 - the local lane's handoff task is provider-backed
    # constraint: and idempotent: the source Issue body digest is the key, so a repeated
    # constraint: cycle reads back the exact existing task instead of emitting a second
    # constraint: one, and a digest change is a different task rather than a mutation.
    subject = parse_subject(subject_value)
    endpoint = f"repos/{subject.repo}/issues/{subject.number}/comments"
    marker = f"<!-- noodles-local-handoff: {contract['body_sha256']} -->"
    body = local_handoff_body(subject_value, contract, boundary)

    def matching() -> list[dict[str, Any]]:
        observed = gh_api(f"{endpoint}?per_page=100")
        if not isinstance(observed, list):
            raise GateError(f"provider handoff task readback for {subject_value} is not a list")
        return [item for item in observed if isinstance(item, dict) and marker in str(item.get("body") or "")]

    existing = matching()
    if len(existing) > 1:
        raise GateError(f"provider carries duplicate local handoff tasks for {subject_value}")
    status = "reused"
    if not existing:
        gh_api(endpoint, method="POST", payload={"body": body})
        existing = matching()
        status = "emitted"
    if len(existing) != 1 or str(existing[0].get("body")) != body:
        raise GateError(f"provider local handoff readback failed for {subject_value}")
    return {
        "status": status,
        "id": existing[0].get("id"),
        "issue_digest": contract["body_sha256"],
        "target": contract["target"],
        "capability": contract["runtime"],
        "write_boundary": list(boundary),
    }


def schedule_publish(root: Path, candidate_path: Path) -> dict[str, Any]:
    root = root.resolve()
    candidate = candidate_path if candidate_path.is_absolute() else root / candidate_path
    try:
        proposed = skill_contract.validate_schedule_candidate(root, candidate)
    except ValueError as exc:
        raise GateError(str(exc)) from exc
    policy = protection_policy(root)
    repositories = tuple(sorted(set(policy.get("allowed_repositories") or ())))
    if not repositories or not all(isinstance(repository, str) and repository for repository in repositories):
        raise GateError("GitHub policy has no exact allowed repositories")
    order_by_subject: dict[str, dict[str, Any]] = {}
    for order in proposed["orders"]:
        raw_subject = order.get("id")
        if not isinstance(raw_subject, str) or raw_subject != raw_subject.strip():
            raise GateError(f"schedule candidate order id is not canonical: {raw_subject!r}")
        subject_value = raw_subject
        subject = parse_subject(subject_value)
        if subject.repo not in repositories:
            raise GateError(f"schedule target repository is not admitted: {subject.repo}")
        if subject_value in order_by_subject:
            raise GateError(f"schedule candidate contains duplicate order: {subject_value}")
        order_by_subject[subject_value] = order

    issues = tuple(issue for repository in repositories for issue in schedule_snapshot(repository))
    decision = schedule_domain.schedule_decision(issues)
    initial_winners = set(decision.winners)
    # constraint: ed3c/noodles#98 - I3 disjoint admitted mutation boundaries: an
    # constraint: active lane's declared write surface is reserved so an overlapping
    # constraint: candidate cannot also be admitted; boundaries are repository-scoped
    # constraint: because paths only collide within one repository.
    reserved_boundaries: dict[str, list[tuple[str, tuple[str, ...] | None]]] = {}
    for issue in issues:
        if issue.claimed:
            reserved_boundaries.setdefault(issue.repository, []).append((issue.subject, issue.write_boundary))
    claimed_orders: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    default_branch = str(policy["default_branch"])
    for subject_value in sorted(order_by_subject, key=lambda value: (parse_subject(value).repo, parse_subject(value).number)):
        if subject_value not in initial_winners:
            outcomes.append(schedule_claim_outcome(subject_value, "not_in_winners"))
            continue
        subject = parse_subject(subject_value)
        fresh = schedule_domain.schedule_decision(schedule_snapshot(subject.repo))
        if subject_value not in fresh.winners:
            outcomes.append(schedule_claim_outcome(subject_value, "frontier_changed"))
            continue
        contract = issue_contract_readback(subject_value)
        if not contract["schedulable"]:
            outcomes.append(schedule_claim_outcome(subject_value, "dependency_changed", reasons=contract["reasons"]))
            continue
        # constraint: ed3c/noodles#187 - classify the executor before any claim, branch,
        # constraint: checkout, or worktree exists, so a lane that cannot physically
        # constraint: complete the work never holds the subject's exact execute ref.
        admission = contract["admission"]
        if not admission["admitted"]:
            outcomes.append(schedule_claim_outcome(
                subject_value,
                admission["status"],
                reasons=list(admission["reasons"]),
                admitted_lanes=list(admission["admitted_lanes"]),
            ))
            continue
        # constraint: ed3c/noodles#98 - prove write-boundary disjointness before any
        # constraint: provider ref is created, so a rejected candidate leaves no residue;
        # constraint: a missing or ambiguous own boundary fails closed distinctly.
        candidate_boundary = contract["write_boundary"]
        if candidate_boundary is None:
            outcomes.append(schedule_claim_outcome(subject_value, "boundary_undeclared"))
            continue
        conflict = boundary_admission_conflict(candidate_boundary, reserved_boundaries.get(subject.repo, ()))
        if conflict is not None:
            outcomes.append(schedule_claim_outcome(
                subject_value, "boundary_conflict", conflict_with=conflict[0], prefix=conflict[1]
            ))
            continue
        # constraint: ed3c/noodles#99 - I4: refuse a subject that already has an open PR
        # constraint: before any provider ref is created, so the rejected candidate leaves no
        # constraint: residue, and route the named PR to the repair owner rather than opening a
        # constraint: second attempt against the same subject. This readback is keyed on
        # constraint: subject_value, not hoisted per-repository the way reserved_boundaries is:
        # constraint: two surviving candidates in one repository re-fetch the same open-PR list.
        # constraint: Correctness does not depend on the hoist - each fetch still correlates
        # constraint: correctly - only the provider call count per cycle does; not hoisted here
        # constraint: because order batches are small in practice and a per-repo cache would be
        # constraint: unexercised abstraction until a batch actually makes it matter.
        open_prs = subject_open_pull_requests(subject.repo, subject_value)
        if open_prs:
            outcomes.append(schedule_claim_outcome(
                subject_value, "open_pr_exists", pull_requests=open_prs, repair_owner=OPEN_PR_REPAIR_OWNER
            ))
            continue
        default_ref = gh_api(f"repos/{subject.repo}/git/ref/heads/{default_branch}")
        head = default_ref.get("object", {}).get("sha") if isinstance(default_ref, dict) else None
        if not isinstance(head, str) or not HEX40_RE.fullmatch(head):
            raise GateError(f"provider default branch head readback failed for {subject.repo}/{default_branch}")
        # constraint: ed3c/noodles#189 - the hosted agentic lane's target-local task identity is
        # constraint: derived from the exact declaration and this exact base head before the
        # constraint: execute ref exists, so a repeated cycle recomputes the identical task instead
        # constraint: of creating a second one and a malformed declaration claims nothing.
        hosted_task = None
        if admission["lane"] == GHA_HOSTED_LANE:
            hosted_task = gha_task_identity({
                "target": subject.repo,
                "subject": subject_value,
                "subject_body_sha256": contract["body_sha256"],
                "base_sha": head,
                "runtime": contract["runtime"],
                "evidence": contract["evidence"],
                "write_boundary": list(candidate_boundary),
            })
        claim = claim_execute_branch(subject.repo, execute_branch(subject_value), head)
        if claim["status"] != "claimed":
            # constraint: ed3c/noodles#187 - a lost claim binds nothing: another
            # constraint: executor holds the ref, so this run's lane/checkout/base_sha
            # constraint: would misreport a binding it never actually won.
            outcomes.append(schedule_claim_outcome(subject_value, **claim))
            continue
        # constraint: ed3c/noodles#187 - an admitted lane is bound to one exact Issue,
        # constraint: target, base SHA, runtime, and evidence policy; the hosted lanes
        # constraint: get only this ephemeral branch for the run and never a managed
        # constraint: worktree, so only the local lane emits a handoff task.
        binding = {
            "lane": admission["lane"],
            "checkout": admission["checkout"],
            "target": subject.repo,
            "base_sha": head,
            "runtime": contract["runtime"],
            "evidence": contract["evidence"],
            "write_boundary": list(candidate_boundary),
        }
        if hosted_task is not None:
            binding["task"] = hosted_task
        if admission["lane"] == issue_contract.LOCAL_LANE:
            binding["handoff"] = emit_local_handoff(subject_value, contract, candidate_boundary)
        outcomes.append(schedule_claim_outcome(subject_value, **claim, **binding))
        claimed_orders.append(order_by_subject[subject_value])
        reserved_boundaries.setdefault(subject.repo, []).append((subject_value, candidate_boundary))

    filtered = {key: value for key, value in proposed.items() if key != "orders"}
    filtered["orders"] = claimed_orders
    write_json(candidate.resolve(), filtered)
    destination = skill_contract.publish_schedule_output(root, candidate.resolve())
    brief = {
        "schema_version": SCHEMA_VERSION,
        "frontier": list(decision.frontier),
        "winners": list(decision.winners),
        "components": [list(component) for component in decision.components],
        "max_useful_workers": decision.max_useful_workers,
        "claims": outcomes,
        "destination": str(destination),
    }
    receipt_errors = skill_contract.validate_cycle_receipt(brief)
    if receipt_errors:
        raise GateError("schedule cycle receipt rejected: " + "; ".join(receipt_errors))
    write_json(root / ".noodle/schedule-cycle.json", brief)
    return brief


if __name__ == "__main__":
    raise SystemExit(main())
