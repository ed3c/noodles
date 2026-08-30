#!/usr/bin/env python3
"""Small deterministic policy/evidence layer around Noodle and GitHub; requires Python, git, gh, and noodle."""
from __future__ import annotations
import argparse
import codex_isolation
import feature_contract
import hashlib
import github_protection
import issue_contract
import json
import math
import os
import re
import runtime_contract
import signal
import skill_contract
import stat
import subprocess
import sys
import time
import tokenize
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from repair_contract import REPAIR_MAX_ATTEMPTS, repair_pending_reviews, repair_review
from runtime_contract import (
    control_checkout_admission as runtime_control_checkout_admission,
    emit_blocking_handoff,
    gh_repo_from_git as runtime_gh_repo_from_git,
    provider_check as runtime_provider_check,
    provider_sync as runtime_provider_sync,
    reconcile_checkout_admission as runtime_reconcile_checkout_admission,
    resolve_locked_runtime_binary,
    runtime_check as runtime_binary_check,
    skill_discovery_check,
    target_local_repository_admission as runtime_target_local_repository_admission,
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
    "depends_on": re.compile(r"<!--\s*noodles-depends-on:\s*([^>]+?)\s*-->", re.I),
    "blocker": re.compile(r"<!--\s*noodles-blocker:\s*([^>]+?)\s*-->", re.I),
    "landed_pr": re.compile(r"<!--\s*noodles-landed-pr:\s*([^>]+?)\s*-->", re.I),
    "head": re.compile(r"<!--\s*noodles-head:\s*([0-9a-f]{40})\s*-->", re.I),
    "merge": re.compile(r"<!--\s*noodles-merge:\s*([0-9a-f]{40})\s*-->", re.I),
}
REF_RE = re.compile(r"(?m)^Refs\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*)\s*$")
AUTO_CLOSE_RE = re.compile(r"(?im)^\s*(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#[0-9]+")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
N_CLASS_PREFIXES = ("docs/research/", "docs/design/")
N_CLASS_EVIDENCE_RE = re.compile(
    r"(?im)^[ \t]*(?:[-*+][ \t]+)?\*{0,2}(claim|acceptance|evidence)\*{0,2}[ \t]*:[^\n]*?"
    + r"((?:" + "|".join(prefix.rstrip("/") for prefix in N_CLASS_PREFIXES) + r")/[^\s`)\]]*)"
)
TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".toml", ".yml", ".yaml", ".txt"}
EXEC_SUFFIXES = {".py", ".sh"}
ALLOWED_COMMENT_TAGS = ("# constraint:", "# ponytail:")
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
    blocker = issue_contract.parse_blocker(one_marker(body, "blocker", required=False), state_value or "", error_cls=GateError)
    return {
        "role": role,
        "target": target or "",
        "subject": subject.value,
        "state": state_value or "",
        "feature": feature_value or "",
        "dependencies": dependencies,
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


def verify_repository(root: Path, policy_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    policy_root = (policy_root or root).resolve()
    policy = load_json(policy_root / "policy/fitness.json")
    errors: list[str] = []
    target_readback: dict[str, Any] | None = None
    try:
        target = target_local_repository(root)
        target_readback = {
            "repository": target.repository,
            "origin_repository": target.origin_repository,
            "default_branch": target.default_branch,
            "required_check": target.required_check,
            "cross_repository_status": target.cross_repository_status,
        }
    except GateError as exc:
        errors.append(f"target-local repository admission failed: {exc}")
    required_task_profiles = policy.get("required_codex_task_profiles"); expected_task_profiles = {"schedule": {"model": "gpt-5.6-luna", "reasoning_effort": "high"}, "execute": {"model": "gpt-5.6-sol", "reasoning_effort": "high"}}
    if required_task_profiles != expected_task_profiles: errors.append(f"policy required_codex_task_profiles must be exactly {expected_task_profiles!r}")
    try:
        entries = tracked_entries(root)
    except GateError as exc:
        return {"ok": False, "errors": [*errors, str(exc)], "metrics": {}, "target": target_readback}
    allowed_modes = {"100644", "100755"}
    for mode, relative in entries:
        if mode not in allowed_modes:
            errors.append(f"forbidden git mode {mode}: {relative}")
    paths = {relative for _, relative in entries}
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
        "target": target_readback,
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
def issue_set_state(
    subject_value: str,
    new_state: str,
    target: runtime_contract.TargetLocalRepositoryReceipt,
) -> dict[str, Any]:
    if new_state not in ALLOWED_ISSUE_STATES:
        raise GateError(f"unsupported issue state: {new_state}")
    subject = parse_subject(subject_value)
    target.require_repository(
        subject.repo,
        boundary="Issue state mutation",
        error_cls=GateError,
    )
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
        "dependency_states": observed,
        "blocker": contract["blocker"],
        "goal": body_sections.get("goal", ""),
        "physical_acceptance": body_sections.get("physical_acceptance", ""),
        "non_claims": body_sections.get("non_claims", ""),
        **derived,
    }


def execute_handoff(root: Path, subject_value: str, pr_number: int, pr: dict[str, Any]) -> dict[str, Any]:
    subject = parse_subject(subject_value)
    target = target_local_repository(root)
    target.require_repository(subject.repo, boundary="handoff subject", error_cls=GateError)
    if pr.get("state") != "open" or pr.get("draft"):
        raise GateError("handoff PR must be open and non-draft")
    if parse_pr_reference(pr.get("body") or "") != subject_value:
        raise GateError("handoff PR does not exactly reference the issue")
    if pr.get("base", {}).get("ref") != target.default_branch:
        raise GateError(f"handoff PR base must be {target.default_branch}")
    head = git(root, "rev-parse", "HEAD")
    if pr.get("head", {}).get("sha") != head:
        raise GateError("handoff PR head does not match current worktree HEAD")
    session_id = os.getenv("NOODLE_SESSION_ID", "").strip()
    session = validate_handoff_session(root, subject_value, session_id, error_cls=GateError)
    target.require_repository(
        runtime_gh_repo_from_git(Path(session["project"]), error_cls=GateError),
        boundary="handoff Noodle project",
        error_cls=GateError,
    )
    resolve_locked_runtime_binary(root, error_cls=GateError)
    contract = parse_issue_contract(issue_read(subject_value).get("body") or "", expected_subject=subject_value)
    evidence = feature_contract.admit_acceptance_evidence(root, contract["feature"], head, error_cls=GateError)
    issue_set_state(subject_value, "awaiting_land", target)
    receipt = emit_blocking_handoff(root, subject_value, pr_number, head, session_id, error_cls=GateError)
    specialized = evidence["specialized"]
    return {
        "subject": subject_value,
        "pr": pr_number,
        "state": "awaiting_land",
        "acceptance": feature_contract.BASELINE_CONTRACT_ID,
        "tree": evidence["tree"],
        "feature": specialized["feature_id"] if specialized else None,
        "feature_code_surface_sha256": specialized["code_surface_sha256"] if specialized else None,
        **receipt,
    }
def protection_policy(root: Path) -> dict[str, Any]:
    return load_json(root / "policy/github.json")


def target_local_repository(root: Path) -> runtime_contract.TargetLocalRepositoryReceipt:
    return runtime_target_local_repository_admission(root, protection_policy(root), error_cls=GateError)
def protection_readback(repo: str, branch: str, required_check: str) -> dict[str, Any]:
    return github_protection.protection_readback(
        lambda endpoint, **kwargs: github_protection.gh_api_response(run, GateError, endpoint, **kwargs),
        GateError,
        repo,
        branch,
        required_check,
    )


def control_checkout_admission(root: Path) -> dict[str, Any]:
    return runtime_control_checkout_admission(root, target_local_repository(root).default_branch, error_cls=GateError)
def reconcile_checkout_admission(root: Path) -> dict[str, Any]:
    return runtime_reconcile_checkout_admission(root, target_local_repository(root).default_branch, error_cls=GateError)


def verify_pull_request(root: Path, event_path: Path, candidate_root: Path, receipt_path: Path) -> dict[str, Any]:
    event = load_json(event_path)
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        raise GateError("verify requires a pull_request_target event")
    repository = event["repository"]["full_name"]
    number = int(pr["number"])
    head_sha = str(pr["head"]["sha"])
    base_ref = str(pr["base"]["ref"])
    target = target_local_repository(root)
    target.require_repository(repository, boundary="verify event", error_cls=GateError)
    if base_ref != target.default_branch:
        raise GateError(f"PR base must be {target.default_branch}")
    if pr.get("draft"):
        raise GateError("draft PR cannot produce a landing receipt")
    subject_value = parse_pr_reference(pr.get("body") or "")
    subject = parse_subject(subject_value)
    target.require_repository(subject.repo, boundary="verify Issue subject", error_cls=GateError)
    issue = issue_read(subject_value)
    contract = parse_issue_contract(issue.get("body") or "", expected_subject=subject_value)
    if issue.get("state") != "open" or contract["state"] != "awaiting_land":
        raise GateError("issue must be open and awaiting_land before PR verification")
    actual_head = git(candidate_root, "rev-parse", "HEAD")
    if actual_head != head_sha:
        raise GateError(f"candidate checkout {actual_head} != event head {head_sha}")
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
        "gates": ["trusted-inventory", "positive-controls", "negative-controls", "issue-contract", "exact-head"],
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
    target = target_local_repository(root)
    target.require_repository(repository, boundary="land event", error_cls=GateError)
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
    workflow_boundary_errors, workflow_boundary = github_protection.workflow_boundary_readback(root, sha256_file)
    if workflow_boundary_errors:
        raise GateError("trusted workflow boundary invalid: " + "; ".join(workflow_boundary_errors))
    verify_source = github_protection.trusted_workflow_run_readback(
        gh_api, GateError, repository, int(workflow.get("id") or 0), name="verify", path=".github/workflows/verify.yml", event="pull_request_target", default_branch=target.default_branch
    )
    current_run_id = int(os.getenv("GITHUB_RUN_ID", "0") or "0")
    land_source: dict[str, Any] | None = None
    if current_run_id > 0:
        land_source = github_protection.trusted_workflow_run_readback(
            gh_api, GateError, repository, current_run_id, name="land", path=".github/workflows/land.yml", event="workflow_run", default_branch=target.default_branch
        )
    protection_receipt = github_protection.protection_audit(
        lambda endpoint, **kwargs: github_protection.gh_api_response(run, GateError, endpoint, **kwargs),
        GateError,
        repository,
        target.default_branch,
        target.required_check,
    )
    pr = gh_api(f"repos/{repository}/pulls/{pr_number}")
    if pr.get("state") != "open" or pr.get("merged") or pr.get("draft"):
        raise GateError("PR must be open, unmerged, and non-draft")
    if pr["head"]["sha"] != head_sha or pr["base"]["ref"] != target.default_branch:
        raise GateError("PR exact head/base readback failed")
    commit = gh_api(f"repos/{repository}/git/commits/{head_sha}")
    if commit.get("tree", {}).get("sha") != receipt.get("tree_sha"):
        raise GateError("receipt tree does not match GitHub head tree")
    subject_value = parse_pr_reference(pr.get("body") or "")
    target.require_repository(
        parse_subject(subject_value).repo,
        boundary="land Issue subject",
        error_cls=GateError,
    )
    if subject_value != receipt.get("issue_subject"):
        raise GateError("receipt subject does not match PR body")
    issue = issue_read(subject_value)
    contract = parse_issue_contract(issue.get("body") or "", expected_subject=subject_value)
    if issue.get("state") != "open" or contract["state"] != "awaiting_land":
        raise GateError("issue drifted before landing")
    merge = gh_api(
        f"repos/{repository}/pulls/{pr_number}/merge",
        method="PUT",
        payload={"sha": head_sha, "merge_method": target.merge_method},
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
    branch = gh_api(f"repos/{repository}/branches/{target.default_branch}")
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
    target = target_local_repository(root)
    branch = str(reconcile_checkout_admission(root)["branch"])
    snapshot = http_json(control_url.rstrip("/") + "/api/snapshot")
    reviews = snapshot.get("pending_reviews") or []
    if not isinstance(reviews, list):
        raise GateError("Noodle snapshot pending_reviews must be an array")
    admitted: list[tuple[dict[str, Any], str]] = []
    for review in reviews:
        if not isinstance(review, dict):
            continue
        order_id = str(review.get("order_id") or "")
        try:
            subject = parse_subject(order_id)
        except GateError:
            continue
        target.require_repository(subject.repo, boundary="reconcile order", error_cls=GateError)
        admitted.append((review, order_id))
    completed: list[str] = []
    for _review, order_id in admitted:
        try:
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
    target = target_local_repository(root)
    repository = os.getenv("NOODLES_TARGET_REPOSITORY") or target.repository
    target.require_repository(repository, boundary="adapter add target", error_cls=GateError)
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
    target = target_local_repository(repo_root())
    target.require_repository(parse_subject(item_id).repo, boundary="adapter edit subject", error_cls=GateError)
    issue_set_state(item_id, new_status, target)
    return 0


def adapter_done(item_id: str) -> int:
    target_local_repository(repo_root()).require_repository(
        parse_subject(item_id).repo,
        boundary="adapter done subject",
        error_cls=GateError,
    )
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


def start_unattended(root: Path, control_url: str, interval: float) -> int:
    control_checkout_admission(root)
    verified = verify_repository(root)
    if not verified["ok"]:
        raise GateError("repository verification failed: " + "; ".join(verified["errors"]))
    runtime_receipt = runtime_check(root)
    provider_sync(root)
    skill_discovery_check(root, runtime_receipt["binary_path"], error_cls=GateError)
    codex_isolation.codex_surface_canary(root, error_cls=GateError)
    target = target_local_repository(root)
    protection_readback(target.repository, target.default_branch, target.required_check)
    env = os.environ.copy()
    env.setdefault("NOODLE_NO_BROWSER", "1")
    process = subprocess.Popen([runtime_receipt["binary_path"], "start"], cwd=root, env=env)

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noodles")
    parser.add_argument("--root", default=None, help="repository root (testing/audit only)")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--policy-root")
    verify.add_argument("--json", action="store_true")
    metrics = sub.add_parser("metrics")
    metrics.add_argument("--json", action="store_true")
    runtime = sub.add_parser("runtime")
    runtime.add_argument("action", choices=["check", "discover"])
    providers = sub.add_parser("providers")
    providers.add_argument("action", choices=["check", "sync"])
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
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--control-url", default=os.getenv("NOODLE_CONTROL_URL", "http://127.0.0.1:3210"))
    reconcile.add_argument("--watch", action="store_true")
    reconcile.add_argument("--interval", type=float, default=5.0)
    repair = sub.add_parser("repair")
    repair.add_argument("--control-url", default=os.getenv("NOODLE_CONTROL_URL", "http://127.0.0.1:3210"))
    start = sub.add_parser("start")
    start.add_argument("--control-url", default=os.getenv("NOODLE_CONTROL_URL", "http://127.0.0.1:3210"))
    start.add_argument("--interval", type=float, default=5.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    try:
        if args.command == "verify":
            result = verify_repository(root, repo_root(args.policy_root) if args.policy_root else None)
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
                target = target_local_repository(root)
                repository = args.repository or target.repository
                target.require_repository(repository, boundary="protection command", error_cls=GateError)
                if args.action == "apply":
                    github_protection.protection_apply(
                        gh_api,
                        lambda endpoint, **kwargs: github_protection.gh_api_response(run, GateError, endpoint, **kwargs),
                        GateError,
                        repository,
                        target.default_branch,
                        target.required_check,
                    )
                result = github_protection.protection_audit(
                    lambda endpoint, **kwargs: github_protection.gh_api_response(run, GateError, endpoint, **kwargs),
                    GateError,
                    repository,
                    target.default_branch,
                    target.required_check,
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
        if args.command == "reconcile":
            if args.watch:
                while True:
                    completed = reconcile_once(root, args.control_url)
                    if completed:
                        print(json.dumps({"reconciled": completed}))
                    time.sleep(args.interval)
            else:
                print(json.dumps({"reconciled": reconcile_once(root, args.control_url)}))
            return 0
        if args.command == "repair":
            print(json.dumps({"repairable": repair_pending_reviews(root, args.control_url)}, indent=2, sort_keys=True))
            return 0
        if args.command == "start":
            return start_unattended(root, args.control_url, args.interval)
    except GateError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
