#!/usr/bin/env python3
"""Small deterministic policy/evidence layer around Noodle and GitHub; requires Python, git, gh, and noodle."""

from __future__ import annotations

import argparse
import hashlib
import github_protection
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from skill_contract import validate_backlog_scheduler, validate_noodle_worktree_ignore

SCHEMA_VERSION = 1
ALLOWED_MIGRATION_STATES = {"MIGRATE", "REVALIDATE", "ADAPT_EXTERNAL", "DROP", "HOLD"}
ALLOWED_ISSUE_STATES = {"ready", "in_progress", "awaiting_land", "landed", "blocked"}
SUBJECT_RE = re.compile(r"^(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<number>[1-9][0-9]*)$")
MARKER_PATTERNS = {
    "role": re.compile(r"<!--\s*noodles-role:\s*([^>]+?)\s*-->", re.I),
    "target": re.compile(r"<!--\s*noodles-target:\s*([^>]+?)\s*-->", re.I),
    "subject": re.compile(r"<!--\s*noodles-subject:\s*([^>]+?)\s*-->", re.I),
    "state": re.compile(r"<!--\s*noodles-state:\s*([^>]+?)\s*-->", re.I),
    "landed_pr": re.compile(r"<!--\s*noodles-landed-pr:\s*([^>]+?)\s*-->", re.I),
    "head": re.compile(r"<!--\s*noodles-head:\s*([0-9a-f]{40})\s*-->", re.I),
    "merge": re.compile(r"<!--\s*noodles-merge:\s*([0-9a-f]{40})\s*-->", re.I),
}
REF_RE = re.compile(r"(?m)^Refs\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*)\s*$")
AUTO_CLOSE_RE = re.compile(r"(?im)^\s*(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#[0-9]+")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".toml", ".yml", ".yaml", ".txt"}
EXEC_SUFFIXES = {".py", ".sh"}
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


def parse_issue_contract(body: str, expected_subject: str | None = None) -> dict[str, str]:
    role = one_marker(body, "role")
    target = one_marker(body, "target")
    subject_value = one_marker(body, "subject")
    state_value = one_marker(body, "state")
    if role != "repository-mutating-atom":
        raise GateError(f"unsupported noodles-role: {role}")
    subject = parse_subject(subject_value or "")
    if target != subject.repo:
        raise GateError(f"target {target!r} does not match subject repository {subject.repo!r}")
    if expected_subject and subject.value != expected_subject:
        raise GateError(f"issue subject {subject.value} does not match expected {expected_subject}")
    if state_value not in ALLOWED_ISSUE_STATES:
        raise GateError(f"unsupported noodles-state: {state_value}")
    return {"role": role, "target": target or "", "subject": subject.value, "state": state_value or ""}


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
    refs = REF_RE.findall(body or "")
    if len(refs) != 1:
        raise GateError(f"expected exactly one 'Refs owner/repo#N' line, found {len(refs)}")
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
        if item.get("enabled"):
            enabled += 1
    if enabled > max_enabled:
        errors.append(f"enabled providers {enabled} exceed limit {max_enabled}")
    return errors


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

def verify_repository(root: Path, policy_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    policy_root = (policy_root or root).resolve()
    policy = load_json(policy_root / "policy/fitness.json")
    errors: list[str] = []
    try:
        entries = tracked_entries(root)
    except GateError as exc:
        return {"ok": False, "errors": [str(exc)], "metrics": {}}
    allowed_modes = {"100644", "100755"}
    for mode, relative in entries:
        if mode not in allowed_modes:
            errors.append(f"forbidden git mode {mode}: {relative}")
    paths = {relative for _, relative in entries}
    errors.extend(validate_noodle_worktree_ignore(root, paths))
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
        if noodle_config.get("routing", {}).get("defaults", {}).get("model") != policy["required_codex_model"]: errors.append(f".noodle.toml routing model must be {policy['required_codex_model']!r}")
        adapter_scripts = noodle_config.get("adapters", {}).get("backlog", {}).get("scripts", {})
        expected_adapter = ".noodle/adapters/github"
        for action in ("sync", "add", "edit", "done"):
            if not str(adapter_scripts.get(action, "")).startswith(expected_adapter + " "):
                errors.append(f"backlog adapter action {action} must route through {expected_adapter}")
        errors.extend(validate_backlog_scheduler(root, noodle_config))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"invalid .noodle.toml: {exc}")
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
    agents = (root / "AGENTS.md").read_text(encoding="utf-8", errors="ignore") if (root / "AGENTS.md").exists() else ""
    for phrase in policy["required_agent_phrases"]:
        if phrase not in agents:
            errors.append(f"AGENTS.md missing required invariant: {phrase}")
    workflow_paths = sorted(path for path in paths if path.startswith(".github/workflows/"))
    if len(workflow_paths) != policy["max_workflows"]:
        errors.append(f"workflow count must equal {policy['max_workflows']}, got {len(workflow_paths)}")
    verify_workflow = (root / ".github/workflows/verify.yml").read_text(encoding="utf-8", errors="ignore") if (root / ".github/workflows/verify.yml").exists() else ""
    land_workflow = (root / ".github/workflows/land.yml").read_text(encoding="utf-8", errors="ignore") if (root / ".github/workflows/land.yml").exists() else ""
    for phrase in policy["trusted_verify_workflow_phrases"]:
        if phrase not in verify_workflow:
            errors.append(f"verify workflow missing trusted boundary phrase: {phrase}")
    workflow_jobs = github_protection.workflow_job_bodies(verify_workflow)
    for job_name, required_phrases in (("candidate-self-tests", policy["candidate_self_test_job_phrases"]), ("verify", policy["trusted_verification_job_phrases"])):
        for phrase in required_phrases:
            if phrase not in workflow_jobs.get(job_name, ""):
                errors.append(f"verify job {job_name} missing required phrase: {phrase}")
    for job_name, policy_key in (("candidate-self-tests", "candidate_self_test_job_forbidden_phrases"), ("verify", "trusted_verification_job_forbidden_phrases")):
        for phrase in policy[policy_key]:
            if phrase in workflow_jobs.get(job_name, ""):
                errors.append(f"verify job {job_name} forbids candidate execution phrase: {phrase}")
    for phrase in policy["trusted_land_workflow_phrases"]:
        if phrase not in land_workflow:
            errors.append(f"land workflow missing trusted boundary phrase: {phrase}")
    workflow_boundary_errors, _workflow_boundary = github_protection.workflow_boundary_readback(root, sha256_file)
    errors.extend(workflow_boundary_errors)
    metrics = repository_metrics(root)
    numeric_limits = {
        "tracked_files": ("max", policy["max_tracked_files"]),
        "root_surfaces": ("max", policy["max_root_surfaces"]),
        "max_file_lines": ("max", policy["max_file_lines"]),
        "markdown_share": ("max", policy["max_markdown_share"]),
        "normalized_line_entropy": ("min", policy["min_normalized_entropy"]),
        "test_to_executable_ratio": ("min", policy["min_test_to_executable_ratio"]),
        "enabled_external_providers": ("max", policy["max_enabled_providers"]),
    }
    for key, (direction, threshold) in numeric_limits.items():
        value = metrics[key]
        if direction == "max" and value > threshold:
            errors.append(f"fitness {key}={value} exceeds {threshold}")
        if direction == "min" and value < threshold:
            errors.append(f"fitness {key}={value} below {threshold}")
    return {"ok": not errors, "errors": errors, "metrics": metrics}


def provider_items(root: Path) -> list[dict[str, Any]]:
    payload = load_json(root / "policy/providers.lock.json")
    return [item for item in payload["providers"] if item.get("enabled")]


def provider_check(root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    receipts: list[dict[str, Any]] = []
    for item in provider_items(root):
        destination = (root / item["destination"]).resolve()
        if root not in destination.parents:
            raise GateError(f"unsafe provider destination: {destination}")
        if not destination.is_dir():
            raise GateError(f"provider {item['name']} is not installed at {item['destination']}")
        head = git(destination, "rev-parse", "HEAD")
        if head != item["commit"]:
            raise GateError(f"provider {item['name']} HEAD {head} != locked {item['commit']}")
        if git(destination, "status", "--porcelain"):
            raise GateError(f"provider {item['name']} checkout is dirty")
        skill_root = destination / item["subpath"]
        skills = sorted(skill_root.rglob("SKILL.md")) if skill_root.is_dir() else []
        license_file = destination / item["license_path"]
        if not skills:
            raise GateError(f"provider {item['name']} has no SKILL.md under {item['subpath']}")
        if not license_file.is_file():
            raise GateError(f"provider {item['name']} license path missing: {item['license_path']}")
        receipts.append(
            {
                "name": item["name"],
                "commit": head,
                "tree": git(destination, "rev-parse", "HEAD^{tree}"),
                "skill_count": len(skills),
                "license_sha256": sha256_file(license_file),
            }
        )
    return receipts


def provider_sync(root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    provider_root = root / ".noodle/providers"
    provider_root.mkdir(parents=True, exist_ok=True)
    for item in provider_items(root):
        destination = (root / item["destination"]).resolve()
        if root not in destination.parents or provider_root.resolve() not in destination.parents:
            raise GateError(f"unsafe provider destination: {destination}")
        with tempfile.TemporaryDirectory(prefix="noodles-provider-", dir=str(provider_root)) as temp_name:
            stage = Path(temp_name) / "checkout"
            stage.mkdir()
            git(stage, "init", "-q")
            git(stage, "remote", "add", "origin", item["source"])
            git(stage, "fetch", "-q", "--depth", "1", "origin", item["commit"])
            git(stage, "checkout", "-q", "--detach", "FETCH_HEAD")
            if git(stage, "rev-parse", "HEAD") != item["commit"]:
                raise GateError(f"provider {item['name']} fetch readback did not reach locked commit")
            if destination.exists():
                shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage, destination)
    receipts = provider_check(root)
    receipt_dir = root / ".noodle/receipts/providers"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    for receipt in receipts:
        write_json(receipt_dir / f"{receipt['name']}.json", {**receipt, "observed_at": int(time.time())})
    return receipts


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


def gh_repo_from_git(root: Path) -> str:
    url = git(root, "remote", "get-url", "origin")
    match = re.search(r"github\.com[/:]([^/]+/[^/.]+)(?:\.git)?$", url)
    if not match:
        raise GateError(f"cannot derive GitHub repository from origin: {url}")
    return match.group(1)


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
    body = replace_marker(issue.get("body") or "", "state", new_state)
    gh_api(f"repos/{subject.repo}/issues/{subject.number}", method="PATCH", payload={"body": body})
    readback = issue_read(subject_value)
    contract = parse_issue_contract(readback.get("body") or "", expected_subject=subject_value)
    if contract["state"] != new_state:
        raise GateError(f"issue state readback failed for {subject_value}")
    return readback


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
    snapshot = http_json(control_url.rstrip("/") + "/api/snapshot")
    completed: list[str] = []
    for review in snapshot.get("pending_reviews") or []:
        order_id = str(review.get("order_id") or "")
        try:
            parse_subject(order_id)
            provider_landed(order_id)
        except GateError:
            continue
        git(root, "fetch", "--quiet", "origin", "main")
        git(root, "merge", "--ff-only", "origin/main")
        command_id = f"noodles-reconcile-{hashlib.sha256(order_id.encode()).hexdigest()[:12]}"
        ack = http_json(
            control_url.rstrip("/") + "/api/control",
            payload={"id": command_id, "action": "merge", "order_id": order_id},
        )
        if not ack.get("ok", False):
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
        repositories = [gh_repo_from_git(repo_root())]
    output: list[dict[str, Any]] = []
    for repository in repositories:
        issues = gh_api(f"repos/{repository}/issues?state=open&per_page=100")
        for issue in issues:
            if "pull_request" in issue:
                continue
            try:
                contract = parse_issue_contract(issue.get("body") or "")
            except GateError:
                continue
            output.append(
                {
                    "id": contract["subject"],
                    "title": issue.get("title") or contract["subject"],
                    "status": contract["state"],
                    "url": issue.get("html_url"),
                }
            )
    for item in output:
        print(json.dumps(item, separators=(",", ":")))
    return 0


def adapter_add(title: str) -> int:
    root = repo_root()
    repository = os.getenv("NOODLES_TARGET_REPOSITORY") or gh_repo_from_git(root)
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


def start_unattended(root: Path, control_url: str, interval: float) -> int:
    verified = verify_repository(root)
    if not verified["ok"]:
        raise GateError("repository verification failed: " + "; ".join(verified["errors"]))
    provider_sync(root)
    policy = protection_policy(root)
    protection_readback(policy["repository"], policy["default_branch"], policy["required_check"])
    env = os.environ.copy()
    env.setdefault("NOODLE_NO_BROWSER", "1")
    process = subprocess.Popen(["noodle", "start"], cwd=root, env=env)

    def stop(_signum: int, _frame: Any) -> None:
        process.terminate()

    old_int = signal.signal(signal.SIGINT, stop)
    old_term = signal.signal(signal.SIGTERM, stop)
    try:
        while process.poll() is None:
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
    providers = sub.add_parser("providers")
    providers.add_argument("action", choices=["check", "sync"])
    issue = sub.add_parser("issue")
    issue_sub = issue.add_subparsers(dest="issue_action", required=True)
    issue_validate = issue_sub.add_parser("validate")
    issue_validate.add_argument("subject")
    issue_handoff = issue_sub.add_parser("handoff")
    issue_handoff.add_argument("subject")
    issue_handoff.add_argument("--pr", type=int, required=True)
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
            metrics = repository_metrics(root)
            print(json.dumps(metrics, indent=2, sort_keys=True) if args.json else json.dumps(metrics, sort_keys=True))
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
            if args.issue_action == "handoff":
                subject = parse_subject(args.subject)
                pr = gh_api(f"repos/{subject.repo}/pulls/{args.pr}")
                if pr.get("state") != "open" or parse_pr_reference(pr.get("body") or "") != args.subject:
                    raise GateError("handoff PR does not exactly reference the issue")
                issue_set_state(args.subject, "awaiting_land")
                print(json.dumps({"subject": args.subject, "pr": args.pr, "head": pr["head"]["sha"], "state": "awaiting_land"}))
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
        if args.command == "start":
            return start_unattended(root, args.control_url, args.interval)
    except GateError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
