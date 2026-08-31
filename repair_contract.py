from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

import github_protection
from runtime_contract import (
    emit_session_event,
    read_session_events,
    validate_pending_review_session,
    worktree_exec,
)

REPAIR_MAX_ATTEMPTS = 3


def _engine():
    main = sys.modules.get("__main__")
    if main is not None and Path(getattr(main, "__file__", "")).resolve() == (Path(__file__).resolve().with_name("noodles.py")):
        return main
    import noodles as engine
    return engine


def find_open_pr_for_subject(repository: str, subject_value: str) -> dict[str, Any]:
    engine = _engine()
    pulls = engine.gh_api(f"repos/{repository}/pulls?state=open&per_page=100")
    if not isinstance(pulls, list):
        raise engine.GateError(f"open PR readback failed for {repository}")
    matches = [item for item in pulls if isinstance(item, dict) and engine.parse_pr_reference(item.get("body") or "") == subject_value]
    if len(matches) != 1:
        raise engine.GateError(f"expected exactly one open PR referencing {subject_value}, got {len(matches)}")
    return matches[0]


def repair_receipt_path(project: Path, session_id: str, pr_number: int, head_sha: str) -> Path:
    return project / ".noodle" / "repair" / f"{session_id}-pr{pr_number}-{head_sha[:12]}.json"


def ensure_session_event(
    root: Path,
    session_context: Mapping[str, Any],
    event_type: str,
    payload: dict[str, Any],
) -> None:
    engine = _engine()
    events = read_session_events(Path(session_context["events_path"]), error_cls=engine.GateError)
    observed = [
        item for item in events
        if item.get("type") == event_type and item.get("payload") == payload
    ]
    if len(observed) > 1:
        raise engine.GateError(f"duplicate {event_type} events observed for exact session")
    if not observed:
        emit_session_event(root, str(session_context["session_id"]), event_type, payload, error_cls=engine.GateError)
        events = read_session_events(Path(session_context["events_path"]), error_cls=engine.GateError)
        observed = [
            item for item in events
            if item.get("type") == event_type and item.get("payload") == payload
        ]
    if len(observed) != 1:
        raise engine.GateError(f"{event_type} direct readback failed for exact session")


def repair_review(root: Path, subject_value: str, review: Mapping[str, Any], pr: dict[str, Any]) -> dict[str, Any]:
    engine = _engine()
    subject = engine.parse_subject(subject_value)
    review_subject = str(review.get("order_id") or "").strip()
    if review_subject != subject_value:
        raise engine.GateError(f"pending review order {review_subject!r} != exact subject {subject_value!r}")
    session_context = validate_pending_review_session(root, subject_value, review, error_cls=engine.GateError)
    repository = subject.repo
    policy = engine.protection_policy(root)
    if repository not in policy["allowed_repositories"]:
        raise engine.GateError(f"repository not admitted: {repository}")
    if pr.get("state") != "open" or pr.get("merged") or pr.get("draft"):
        raise engine.GateError("repair requires an open, unmerged, non-draft PR")
    if engine.parse_pr_reference(pr.get("body") or "") != subject_value:
        raise engine.GateError("repair PR does not exactly reference the issue")
    if pr.get("base", {}).get("ref") != policy["default_branch"]:
        raise engine.GateError(f"repair PR base must be {policy['default_branch']}")
    issue = engine.issue_read(subject_value)
    contract = engine.parse_issue_contract(issue.get("body") or "", expected_subject=subject_value)
    if issue.get("state") != "open" or contract["state"] != "awaiting_land":
        raise engine.GateError("issue must remain open and awaiting_land for repair")
    worktree_name = str(session_context["worktree_name"])
    worktree_top = worktree_exec(root, worktree_name, ["git", "rev-parse", "--show-toplevel"], error_cls=engine.GateError)
    if Path(worktree_top).resolve() != Path(session_context["worktree_path"]).resolve():
        raise engine.GateError("worktree exec readback does not match pending review worktree_path")
    tracked_status = worktree_exec(root, worktree_name, ["git", "status", "--short"], error_cls=engine.GateError)
    if tracked_status.strip():
        raise engine.GateError("repair worktree has tracked modifications; refusing to risk discard")
    head_sha = str(pr.get("head", {}).get("sha") or "")
    worktree_head = worktree_exec(root, worktree_name, ["git", "rev-parse", "HEAD"], error_cls=engine.GateError)
    if worktree_head != head_sha:
        raise engine.GateError(f"repair worktree head {worktree_head} != PR head {head_sha}")
    failed_run = github_protection.failed_required_workflow_run_readback(
        engine.gh_api,
        engine.GateError,
        repository,
        head_sha,
        name=policy["required_check"],
        path=".github/workflows/verify.yml",
        event="pull_request_target",
        default_branch=policy["default_branch"],
    )
    failed_job = github_protection.failed_workflow_job_readback(
        engine.gh_api,
        engine.GateError,
        repository,
        failed_run["run"]["id"],
    )
    prior_receipts = [
        item.get("payload")
        for item in list(session_context["events"])
        if item.get("type") == "repair_receipt"
        and isinstance(item.get("payload"), dict)
        and item["payload"].get("issue_subject") == subject_value
        and int(item["payload"].get("pr_number") or 0) == int(pr["number"])
    ]
    existing_receipt = next(
        (
            payload for payload in prior_receipts
            if payload.get("head_sha") == head_sha
            and payload.get("failed_workflow_run", {}).get("id") == failed_run["run"]["id"]
            and payload.get("failed_job", {}).get("id") == failed_job["id"]
        ),
        None,
    )
    existing_attempts = len(prior_receipts)
    attempt = int(existing_receipt.get("repair", {}).get("attempt") or 0) if isinstance(existing_receipt, dict) else 0
    if attempt <= 0:
        attempt = existing_attempts + 1
    receipt = {
        "schema_version": engine.SCHEMA_VERSION,
        "repository": repository,
        "issue_subject": subject_value,
        "pr_number": int(pr["number"]),
        "pr_head_ref": str(pr.get("head", {}).get("ref") or ""),
        "head_sha": head_sha,
        "issue_state": contract["state"],
        "pr_state": str(pr.get("state") or ""),
        "required_check": policy["required_check"],
        "failed_workflow_run": {
            "id": failed_run["run"]["id"],
            "name": failed_run["run"]["name"],
            "status": failed_run["run"]["status"],
            "conclusion": failed_run["run"]["conclusion"],
            "html_url": failed_run["run"]["html_url"],
        },
        "failed_job": failed_job,
        "session": {
            "id": str(session_context["session_id"]),
            "worktree_name": worktree_name,
            "worktree_path": str(Path(session_context["worktree_path"]).resolve()),
        },
        "worktree_readback": {
            "top": worktree_top,
            "head": worktree_head,
            "clean": True,
        },
        "repair": {
            "attempt": attempt,
            "max_attempts": REPAIR_MAX_ATTEMPTS,
        },
    }
    path = repair_receipt_path(Path(session_context["project"]), str(session_context["session_id"]), int(pr["number"]), head_sha)
    if existing_receipt is not None:
        if not path.exists():
            engine.write_json(path, receipt)
        readback = engine.load_json(path)
        if readback != receipt:
            raise engine.GateError(f"repair receipt readback failed for {path}")
        return {**receipt, "repair_receipt_path": str(path)}
    if existing_attempts >= REPAIR_MAX_ATTEMPTS:
        blocker = (
            f"repair attempts exhausted for {subject_value} PR #{pr['number']} at head {head_sha}; "
            f"failed job {failed_job['name']}#{failed_job['id']} concluded {failed_job['conclusion']}; "
            f"worktree {session_context['worktree_name']} remains parked at {session_context['worktree_path']}"
        )
        escalation = {
            "issue_subject": subject_value,
            "pr_number": int(pr["number"]),
            "head_sha": head_sha,
            "session_id": str(session_context["session_id"]),
            "worktree_name": str(session_context["worktree_name"]),
            "worktree_path": str(Path(session_context["worktree_path"]).resolve()),
            "attempts": existing_attempts,
            "max_attempts": REPAIR_MAX_ATTEMPTS,
            "blocker": blocker,
        }
        ensure_session_event(root, session_context, "repair_escalation", escalation)
        raise engine.GateError(blocker)
    ensure_session_event(root, session_context, "repair_receipt", dict(receipt))
    engine.write_json(path, receipt)
    readback = engine.load_json(path)
    if readback != receipt:
        raise engine.GateError(f"repair receipt readback failed for {path}")
    return {**receipt, "repair_receipt_path": str(path)}


def repair_pending_reviews(root: Path, control_url: str) -> list[dict[str, Any]]:
    engine = _engine()
    snapshot = engine.http_json(control_url.rstrip("/") + "/api/snapshot")
    reviews = snapshot.get("pending_reviews") or []
    if not isinstance(reviews, list):
        raise engine.GateError("Noodle snapshot pending_reviews must be an array")
    repaired: list[dict[str, Any]] = []
    for review in reviews:
        if not isinstance(review, dict):
            continue
        subject_value = str(review.get("order_id") or "").strip()
        try:
            subject = engine.parse_subject(subject_value)
        except engine.GateError:
            continue
        pr = find_open_pr_for_subject(subject.repo, subject_value)
        head_sha = str(pr.get("head", {}).get("sha") or "")
        policy = engine.protection_policy(root)
        runs = github_protection.workflow_runs_for_head(engine.gh_api, engine.GateError, subject.repo, head_sha)
        failed = any(
            item["name"] == policy["required_check"]
            and item["path"] == ".github/workflows/verify.yml"
            and item["event"] == "pull_request_target"
            and item["status"] == "completed"
            and item["conclusion"] in github_protection.FAILED_WORKFLOW_CONCLUSIONS
            for item in runs
        )
        if not failed:
            continue
        repaired.append(repair_review(root, subject_value, review, pr))
    return repaired
