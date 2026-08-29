from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

TRUTHY = {"1", "true", "yes", "on"}
WORKFLOW_JOB_RE = re.compile(r"(?ms)^  ([A-Za-z0-9_-]+):\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)")
CANDIDATE_SECRET_PHRASES = (
    "NOODLES_GITHUB_PROTECTION_TOKEN",
    "NOODLES_APP_PRIVATE_KEY",
    "NOODLES_APP_CLIENT_ID",
    "GH_TOKEN",
    "github.token",
)
VERIFY_SECRET_PHRASES = (
    "NOODLES_GITHUB_PROTECTION_TOKEN",
    "NOODLES_APP_PRIVATE_KEY",
    "NOODLES_APP_CLIENT_ID",
    "actions/create-github-app-token@",
)
REQUIRED_LAND_PHRASES = {
    "actions/create-github-app-token@": "land workflow must mint a GitHub App installation token",
    "permission-administration: read": "land workflow app token must be scoped to Administration: read",
    "repositories: ${{ github.event.repository.name }}": "land workflow app token must be scoped to the current repository",
    "NOODLES_GITHUB_PROTECTION_TOKEN: ${{ steps.app-token.outputs.token }}": "land workflow must pass the protection-read token only to the land step",
    "NOODLES_REQUIRE_PROTECTION_READ_TOKEN: '1'": "land workflow must require a separate protection-read token",
}
FAILED_WORKFLOW_CONCLUSIONS = {"action_required", "cancelled", "failure", "stale", "startup_failure", "timed_out"}


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in TRUTHY


def workflow_job_bodies(workflow_text: str) -> dict[str, str]:
    body = workflow_text.partition("\njobs:\n")[2]
    return dict(WORKFLOW_JOB_RE.findall(body))


def gh_api_response(
    run_fn: Callable[..., Any],
    error_cls: type[Exception],
    endpoint: str,
    *,
    method: str = "GET",
    payload: Any | None = None,
    token: str | None = None,
    include_headers: bool = False,
) -> tuple[dict[str, str], Any]:
    argv = ["gh", "api", "--method", method, endpoint]
    if include_headers:
        argv.insert(2, "--include")
    if payload is not None:
        argv.extend(["--input", "-"])
    env = os.environ.copy() if token is not None else None
    if env is not None:
        env["GH_TOKEN"] = token
    result = run_fn(argv, input_text=json.dumps(payload) if payload is not None else None, env=env)
    stdout = result.stdout.replace("\r\n", "\n")
    headers: dict[str, str] = {}
    body = stdout
    if include_headers:
        head, separator, body = stdout.partition("\n\n")
        if not separator:
            raise error_cls(f"gh api did not return headers for {endpoint}")
        lines = [line for line in head.splitlines() if line.strip()]
        if not lines or not lines[0].startswith("HTTP/"):
            raise error_cls(f"gh api header readback failed for {endpoint}")
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    if not body.strip():
        return headers, None
    try:
        return headers, json.loads(body)
    except json.JSONDecodeError as exc:
        raise error_cls(f"gh api returned non-JSON for {endpoint}: {exc}") from exc


def protection_token_boundary(error_cls: type[Exception]) -> dict[str, Any]:
    protection_token = os.getenv("NOODLES_GITHUB_PROTECTION_TOKEN", "").strip() or None
    default_token = os.getenv("GH_TOKEN", "").strip() or None
    required = env_truthy("NOODLES_REQUIRE_PROTECTION_READ_TOKEN")
    if required and not protection_token:
        raise error_cls("separate protection-read token required but NOODLES_GITHUB_PROTECTION_TOKEN is missing")
    if protection_token and default_token and protection_token == default_token:
        raise error_cls("protection-read token must be separate from GH_TOKEN")
    if protection_token:
        return {
            "token": protection_token,
            "source": "NOODLES_GITHUB_PROTECTION_TOKEN",
            "separate_from_gh_token": True,
            "required": required,
        }
    return {
        "token": None,
        "source": "GH_TOKEN" if default_token else "gh-default",
        "separate_from_gh_token": False,
        "required": required,
    }


def protection_observe(
    gh_api_response_fn: Callable[..., tuple[dict[str, str], Any]],
    error_cls: type[Exception],
    repo: str,
    branch: str,
    required_check: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    boundary = protection_token_boundary(error_cls)
    headers, protection = gh_api_response_fn(
        f"repos/{repo}/branches/{branch}/protection",
        token=boundary["token"],
        include_headers=True,
    )
    if not isinstance(protection, dict):
        raise error_cls(f"branch protection missing for {repo}:{branch}")
    status = protection.get("required_status_checks") or {}
    contexts = set(status.get("contexts") or [])
    checks = status.get("checks") or []
    contexts.update(str(item.get("context")) for item in checks if item.get("context"))
    if not status.get("strict"):
        raise error_cls("branch protection must require strict up-to-date status checks")
    if required_check not in contexts:
        raise error_cls(f"required check {required_check!r} absent from branch protection: {sorted(contexts)}")
    reviews = protection.get("required_pull_request_reviews")
    if not isinstance(reviews, dict):
        raise error_cls("branch protection must require pull requests")
    if int(reviews.get("required_approving_review_count") or 0) != 0:
        raise error_cls("Human Verifier is forbidden: required approval count must be zero")
    if not (protection.get("enforce_admins") or {}).get("enabled"):
        raise error_cls("branch protection must include administrators")
    if (protection.get("allow_force_pushes") or {}).get("enabled"):
        raise error_cls("force pushes must be disabled")
    if (protection.get("allow_deletions") or {}).get("enabled"):
        raise error_cls("branch deletion must be disabled")
    return protection, headers, boundary


def protection_readback(
    gh_api_response_fn: Callable[..., tuple[dict[str, str], Any]],
    error_cls: type[Exception],
    repo: str,
    branch: str,
    required_check: str,
) -> dict[str, Any]:
    protection, _headers, _boundary = protection_observe(
        gh_api_response_fn, error_cls, repo, branch, required_check
    )
    return protection


def protection_audit(
    gh_api_response_fn: Callable[..., tuple[dict[str, str], Any]],
    error_cls: type[Exception],
    repo: str,
    branch: str,
    required_check: str,
) -> dict[str, Any]:
    protection, headers, boundary = protection_observe(
        gh_api_response_fn, error_cls, repo, branch, required_check
    )
    return {
        "repository": repo,
        "branch": branch,
        "required_check": required_check,
        "provider_response": {
            "sha256": sha256_json(protection),
            "etag": headers.get("etag"),
            "request_id": headers.get("x-github-request-id"),
            "accepted_github_permissions": headers.get("x-accepted-github-permissions"),
            "accepted_oauth_scopes": headers.get("x-accepted-oauth-scopes"),
            "oauth_scopes": headers.get("x-oauth-scopes"),
        },
        "token_boundary": {
            "source": boundary["source"],
            "separate_from_gh_token": boundary["separate_from_gh_token"],
            "required": boundary["required"],
        },
        "protection": protection,
    }


def protection_apply(
    gh_api_fn: Callable[..., Any],
    gh_api_response_fn: Callable[..., tuple[dict[str, str], Any]],
    error_cls: type[Exception],
    repository: str,
    branch: str,
    required_check: str,
) -> dict[str, Any]:
    payload = {
        "required_status_checks": {"strict": True, "contexts": [required_check]},
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
            "required_approving_review_count": 0,
            "require_last_push_approval": False,
        },
        "restrictions": None,
        "required_linear_history": False,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": False,
        "lock_branch": False,
        "allow_fork_syncing": False,
    }
    gh_api_fn(f"repos/{repository}/branches/{branch}/protection", method="PUT", payload=payload)
    return protection_readback(gh_api_response_fn, error_cls, repository, branch, required_check)


def workflow_boundary_readback(
    root: Path,
    sha256_file_fn: Callable[[Path], str],
) -> tuple[list[str], dict[str, Any]]:
    verify_path = root / ".github/workflows/verify.yml"
    land_path = root / ".github/workflows/land.yml"
    verify_workflow = verify_path.read_text(encoding="utf-8", errors="ignore") if verify_path.exists() else ""
    land_workflow = land_path.read_text(encoding="utf-8", errors="ignore") if land_path.exists() else ""
    verify_jobs = workflow_job_bodies(verify_workflow)
    land_jobs = workflow_job_bodies(land_workflow)
    candidate_job = verify_jobs.get("candidate-self-tests", "")
    trusted_verify_job = verify_jobs.get("verify", "")
    land_job = land_jobs.get("land", "")
    errors: list[str] = []
    for phrase in CANDIDATE_SECRET_PHRASES:
        if phrase in candidate_job:
            errors.append(f"candidate self-tests must not receive trusted token material: {phrase}")
    for phrase in VERIFY_SECRET_PHRASES:
        if phrase in trusted_verify_job:
            errors.append(f"trusted verify job must not receive protection-read secret material: {phrase}")
    for phrase, message in REQUIRED_LAND_PHRASES.items():
        if phrase not in land_job:
            errors.append(message)
    evidence = {
        "verify_workflow_path": ".github/workflows/verify.yml",
        "verify_workflow_sha256": sha256_file_fn(verify_path) if verify_path.exists() else None,
        "land_workflow_path": ".github/workflows/land.yml",
        "land_workflow_sha256": sha256_file_fn(land_path) if land_path.exists() else None,
        "candidate_self_tests_secret_free": not any(phrase in candidate_job for phrase in CANDIDATE_SECRET_PHRASES),
        "trusted_verify_job_free_of_app_secrets": not any(
            phrase in trusted_verify_job for phrase in VERIFY_SECRET_PHRASES
        ),
        "land_job_uses_separate_protection_token": (
            "NOODLES_GITHUB_PROTECTION_TOKEN: ${{ steps.app-token.outputs.token }}" in land_job
        ),
    }
    return errors, evidence


def workflow_run_readback(
    gh_api_fn: Callable[..., Any],
    error_cls: type[Exception],
    repo: str,
    run_id: int,
) -> dict[str, Any]:
    if run_id <= 0:
        raise error_cls("workflow run id must be a positive integer")
    payload = gh_api_fn(f"repos/{repo}/actions/runs/{run_id}")
    if not isinstance(payload, dict) or int(payload.get("id") or 0) != run_id:
        raise error_cls(f"workflow run readback failed for {repo} run {run_id}")
    return {
        "id": run_id,
        "name": str(payload.get("name") or ""),
        "path": str(payload.get("path") or ""),
        "event": str(payload.get("event") or ""),
        "status": str(payload.get("status") or ""),
        "conclusion": str(payload.get("conclusion") or ""),
        "head_branch": str(payload.get("head_branch") or ""),
        "head_sha": str(payload.get("head_sha") or ""),
        "html_url": str(payload.get("html_url") or ""),
        "workflow_id": int(payload.get("workflow_id") or 0),
    }


def workflow_runs_for_head(
    gh_api_fn: Callable[..., Any],
    error_cls: type[Exception],
    repo: str,
    head_sha: str,
) -> list[dict[str, Any]]:
    payload = gh_api_fn(f"repos/{repo}/actions/runs?head_sha={head_sha}&per_page=100")
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise error_cls(f"workflow runs readback failed for {repo} head {head_sha}")
    normalized: list[dict[str, Any]] = []
    for item in runs:
        if not isinstance(item, dict):
            continue
        run_id = int(item.get("id") or 0)
        if run_id <= 0:
            continue
        normalized.append({
            "id": run_id,
            "name": str(item.get("name") or ""),
            "path": str(item.get("path") or ""),
            "event": str(item.get("event") or ""),
            "status": str(item.get("status") or ""),
            "conclusion": str(item.get("conclusion") or ""),
            "head_branch": str(item.get("head_branch") or ""),
            "head_sha": str(item.get("head_sha") or ""),
            "html_url": str(item.get("html_url") or ""),
            "workflow_id": int(item.get("workflow_id") or 0),
        })
    return normalized


def trusted_workflow_run_readback(
    gh_api_fn: Callable[..., Any],
    error_cls: type[Exception],
    repo: str,
    run_id: int,
    *,
    name: str,
    path: str,
    event: str,
    default_branch: str,
) -> dict[str, Any]:
    run = workflow_run_readback(gh_api_fn, error_cls, repo, run_id)
    if run["event"] != event:
        raise error_cls(f"trusted workflow event must be {event}")
    if run["name"] != name or run["path"] != path:
        raise error_cls("trusted workflow run identity mismatch")
    repository = gh_api_fn(f"repos/{repo}")
    if (
        not isinstance(repository, dict)
        or repository.get("full_name") != repo
        or repository.get("default_branch") != default_branch
    ):
        raise error_cls("provider default branch identity mismatch")
    workflow = gh_api_fn(f"repos/{repo}/actions/workflows/{Path(path).name}")
    if not isinstance(workflow, dict) or run["workflow_id"] <= 0 or int(workflow.get("id") or 0) != run["workflow_id"]:
        raise error_cls("trusted immutable workflow id mismatch")
    if workflow.get("name") != name or workflow.get("path") != path or workflow.get("state") != "active":
        raise error_cls("trusted provider workflow identity mismatch")
    return {
        "run": run,
        "workflow": workflow,
        "provider_default_branch": str(repository.get("default_branch") or ""),
    }


def failed_required_workflow_run_readback(
    gh_api_fn: Callable[..., Any],
    error_cls: type[Exception],
    repo: str,
    head_sha: str,
    *,
    name: str,
    path: str,
    event: str,
    default_branch: str,
) -> dict[str, Any]:
    candidates = [
        run for run in workflow_runs_for_head(gh_api_fn, error_cls, repo, head_sha)
        if run["name"] == name
        and run["path"] == path
        and run["event"] == event
        and run["head_sha"] == head_sha
        and run["status"] == "completed"
        and run["conclusion"] in FAILED_WORKFLOW_CONCLUSIONS
    ]
    if not candidates:
        raise error_cls(f"required check {name} has no completed failed workflow run for {head_sha}")
    selected = max(candidates, key=lambda item: item["id"])
    source = trusted_workflow_run_readback(
        gh_api_fn,
        error_cls,
        repo,
        selected["id"],
        name=name,
        path=path,
        event=event,
        default_branch=default_branch,
    )
    if source["run"]["status"] != "completed" or source["run"]["conclusion"] not in FAILED_WORKFLOW_CONCLUSIONS:
        raise error_cls(f"required check {name} is not a completed failed workflow run for {head_sha}")
    return source


def workflow_run_jobs_readback(
    gh_api_fn: Callable[..., Any],
    error_cls: type[Exception],
    repo: str,
    run_id: int,
) -> list[dict[str, Any]]:
    payload = gh_api_fn(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise error_cls(f"workflow jobs readback failed for {repo} run {run_id}")
    normalized: list[dict[str, Any]] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        job_id = int(item.get("id") or 0)
        if job_id <= 0:
            continue
        normalized.append({
            "id": job_id,
            "name": str(item.get("name") or ""),
            "status": str(item.get("status") or ""),
            "conclusion": str(item.get("conclusion") or ""),
            "html_url": str(item.get("html_url") or ""),
        })
    return normalized


def failed_workflow_job_readback(
    gh_api_fn: Callable[..., Any],
    error_cls: type[Exception],
    repo: str,
    run_id: int,
) -> dict[str, Any]:
    failed = [
        job for job in workflow_run_jobs_readback(gh_api_fn, error_cls, repo, run_id)
        if job["status"] == "completed" and job["conclusion"] in FAILED_WORKFLOW_CONCLUSIONS
    ]
    if not failed:
        raise error_cls(f"workflow run {run_id} has no completed failed jobs")
    failed.sort(key=lambda item: (item["name"], item["id"]))
    return failed[0]
