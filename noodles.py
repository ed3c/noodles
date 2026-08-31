#!/usr/bin/env python3
"""Small deterministic policy/evidence layer around Noodle and GitHub; requires Python, git, gh, and noodle."""
from __future__ import annotations
import argparse
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
    validate_backlog_scheduler,
    validate_execute_task,
    validate_noodle_worktree_ignore,
)
SCHEMA_VERSION = 1
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
    matches = MARKER_PATTERNS[name].findall(body or "")
    if not matches:
        if required:
            raise GateError(f"missing noodles-{name.replace('_', '-')} marker")
        return None
    if len(matches) != 1:
        raise GateError(f"expected one noodles-{name.replace('_', '-')} marker, found {len(matches)}")
    return matches[0].strip()
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
    return {
        "role": role,
        "target": target or "",
        "subject": subject.value,
        "state": state_value or "",
        "feature": feature_value or "",
        "component": component_value or "",
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
        errors.extend(validate_backlog_scheduler(root, noodle_config))
        errors.extend(validate_execute_task(root, noodle_config))
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
    schedule_receipt = root / ".noodle/schedule-cycle.json"
    if schedule_receipt.exists():
        try:
            errors.extend(skill_contract.validate_cycle_receipt(load_json(schedule_receipt)))
        except GateError as exc:
            errors.append(f"schedule cycle receipt unreadable: {exc}")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8", errors="ignore") if (root / "AGENTS.md").exists() else ""
    for phrase in policy["required_agent_phrases"]:
        if phrase not in agents:
            errors.append(f"AGENTS.md missing required invariant: {phrase}")
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
    _headers, body = github_protection.gh_api_response(
        run,
        GateError,
        endpoint,
        method=method,
        payload=payload,
        token=token,
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


def issue_contract_payload(issue: dict[str, Any], subject_value: str | None, dependency_cache: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    body = issue.get("body") or ""
    contract = parse_issue_contract(body, expected_subject=subject_value)
    cache = dependency_cache if dependency_cache is not None else {}
    observed = {}
    for dependency in contract["dependencies"] or ():
        observed[dependency] = cache.setdefault(dependency, dependency_readback(dependency))
    body_sections = issue_contract.sections(body)
    derived = issue_contract.derive_schedulability(contract, str(issue.get("state") or ""), observed, body_sections)
    return {
        "subject": contract["subject"],
        "target": contract["target"],
        "feature": contract["feature"],
        "state": contract["state"],
        "provider_state": issue.get("state"),
        "url": issue.get("html_url"),
        "body_sha256": issue_contract.body_digest(body),
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
    validate_handoff_session(root, subject_value, session_id, error_cls=GateError)
    resolve_locked_runtime_binary(root, error_cls=GateError)
    contract = parse_issue_contract(issue_read(subject_value).get("body") or "", expected_subject=subject_value)
    evidence = feature_contract.admit_acceptance_evidence(root, contract["feature"], head, error_cls=GateError)
    base_ref = pr.get("base", {}).get("ref")
    declared_feature = (contract["feature"] or "").strip()
    feature_map = None
    if declared_feature:
        # constraint: compile the exact base..head changed code nodes into the declared feature's required-journey denominator before awaiting_land; an unmapped journey (feature surface absent from the diff) fails closed here, never after the state flip. A no-feature subject skips this by the mechanically checked non-case: no marker, so admit_acceptance_evidence already rejects any specialized oracle.
        feature_map = feature_contract.compile_handoff_feature_map(
            declared_feature, merge_base_changed_files(subject.repo, base_ref, head), error_cls=GateError
        )
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
        "tree": evidence["tree"],
        "feature": specialized["feature_id"] if specialized else None,
        "feature_code_surface_sha256": specialized["code_surface_sha256"] if specialized else None,
        "feature_changed_node": feature_map["changed_node"] if feature_map else None,
        "feature_transitions": feature_map["transitions"] if feature_map else None,
        "feature_journeys": feature_map["journeys"] if feature_map else None,
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
    surface_errors = component_surface_errors(
        contract["component"], component_map(root), merge_base_changed_files(repository, base_ref, head_sha)
    )
    if surface_errors:
        raise GateError("candidate component-surface gate failed: " + "; ".join(surface_errors))
    introductions = introduced_components(root, candidate_root)
    introduction_errors = component_introduction_errors(introductions, issue.get("body") or "")
    if introduction_errors:
        raise GateError("candidate component-introduction gate failed: " + "; ".join(introduction_errors))
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
        "gates": ["trusted-inventory", "positive-controls", "negative-controls", "issue-contract", "exact-head", "component-surface", "component-introduction"],
    }
    write_json(receipt_path, receipt)
    return receipt


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
    return {
        "repository": repository,
        "pr_number": pr_number,
        "issue_subject": subject_value,
        "head_sha": head_sha,
        "merge_sha": merge_sha,
        "issue_closed": True,
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


def intake_normalize(issue: dict[str, Any], repository: str) -> dict[str, Any]:
    """Apply the intake repair to one open issue and read the write back; conforming issues are untouched."""
    subject = Subject(repository, int(issue.get("number") or 0))
    body = issue.get("body") or ""
    plan = intake_normalization(body, subject, str(issue.get("title") or subject.value))
    if plan is None:
        return issue
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


def adapter_sync() -> int:
    repositories = [item.strip() for item in os.getenv("NOODLES_REPOSITORIES", "").split(",") if item.strip()]
    if not repositories:
        repositories = [runtime_gh_repo_from_git(repo_root(), error_cls=GateError)]
    output: list[dict[str, Any]] = []
    dependency_cache: dict[str, dict[str, Any]] = {}
    for repository in repositories:
        issues = gh_api(f"repos/{repository}/issues?state=open&per_page=100")
        for issue in issues:
            if "pull_request" in issue:
                continue
            try:
                issue = intake_normalize(issue, repository)
                contract = issue_contract_payload(issue, None, dependency_cache)
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
                    "schedulable": contract["schedulable"],
                    "reasons": contract["reasons"],
                }
            )
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
    while process.poll() is None:
        ready, _, _ = select.select([process.stdout], [], [], SUPERVISE_POLL_SECONDS)
        now = now_fn()
        # constraint: the deadlines are checked every pass, not only on a silent one - a chatty generation must still rotate.
        if now - started >= rotate_after_seconds:
            reason = "rotation"
            break
        if now - last_output >= wedge_seconds:
            reason = "wedge"
            break
        if not ready:
            continue
        line = process.stdout.readline()
        if line:
            tail.append(line.rstrip("\n"))
            last_output = now
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
    return {
        "reason": reason,
        "returncode": int(process.returncode if process.returncode is not None else -1),
        "seconds": round(now_fn() - started, 3),
        "tail": "\n".join(tail),
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
            receipt["cooldown"] = backoff_seconds
            receipts.append(receipt)
            append_supervise_log(root, receipt)
            sleep_fn(backoff_seconds)
            continue
        receipt.update(run_supervised_generation(
            root, argv, wedge_seconds=wedge_seconds, rotate_after_seconds=rotate_after_seconds, env=env
        ))
        cooldown = 0.0
        if receipt["returncode"] != 0 and RATE_LIMIT_TAIL_RE.search(receipt["tail"]):
            cooldown = rate_limit_cooldown(read_rate_limit(), time.time())
        elif receipt["returncode"] != 0 and receipt["reason"] == "exited":
            cooldown = backoff_seconds
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
            contract = issue_contract_payload(issue, subject_value, dependency_cache)
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
        default_ref = gh_api(f"repos/{subject.repo}/git/ref/heads/{default_branch}")
        head = default_ref.get("object", {}).get("sha") if isinstance(default_ref, dict) else None
        if not isinstance(head, str) or not HEX40_RE.fullmatch(head):
            raise GateError(f"provider default branch head readback failed for {subject.repo}/{default_branch}")
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
