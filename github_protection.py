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
        "head_branch": str(payload.get("head_branch") or ""),
        "head_sha": str(payload.get("head_sha") or ""),
        "workflow_id": int(payload.get("workflow_id") or 0),
    }
