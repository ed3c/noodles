"""Dead-claim lifecycle: deterministic detection, adoption, and release of orphaned execute claims.

A claim is the provider branch ref created by `claim_execute_branch` (ed3c/noodles#138). When the
claiming cook dies after handoff, the subject wedges: issue awaiting_land, PR open (often red), and
the branch-existence claim check blocks re-admission forever. This module gives that state a
mechanical owner. Post-PR liveness keeps its ledger-age rule. Pre-PR adoption additionally refuses
a recorded live process or unknown process metadata; a quiet worker is not an orphan.
"""
from __future__ import annotations

import hashlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import github_protection
from daemon_lease import process_alive
from repair_contract import repair_review
from runtime_contract import noodle_project_root, read_session_events

SESSION_LIVENESS_WINDOW_SECONDS = 3600
SALVAGE_BRANCH_PREFIX = "progress-"


def _engine():
    main = sys.modules.get("__main__")
    if main is not None and Path(getattr(main, "__file__", "")).resolve() == (Path(__file__).resolve().with_name("noodles.py")):
        return main
    import noodles as engine
    return engine


def _event_epoch(event: dict[str, Any]) -> float | None:
    raw = str(event.get("timestamp") or "").strip()
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def subject_sessions(root: Path, subject: str) -> list[dict[str, Any]]:
    """Ledger sessions tied to the exact order subject, oldest-activity first."""
    engine = _engine()
    project = noodle_project_root(root.resolve(), error_cls=engine.GateError)
    sessions_dir = project / ".noodle" / "sessions"
    if not sessions_dir.is_dir():
        return []
    marker = f"[order:{subject}]"
    tied: list[dict[str, Any]] = []
    for events_path in sorted(sessions_dir.glob("*/events.ndjson")):
        events = read_session_events(events_path, error_cls=engine.GateError)
        if not any(
            isinstance(item.get("payload"), dict) and marker in str(item["payload"].get("message") or "")
            for item in events
        ):
            continue
        epochs = [value for value in (_event_epoch(item) for item in events) if value is not None]
        tied.append({
            "session_id": events_path.parent.name,
            "last_event_epoch": max(epochs) if epochs else None,
        })
    tied.sort(key=lambda item: (item["last_event_epoch"] is not None, item["last_event_epoch"] or 0.0))
    return tied


def salvage_branch(subject_value: str, head: str) -> str:
    engine = _engine()
    return f"{SALVAGE_BRANCH_PREFIX}{engine.parse_subject(subject_value).number}-{head[:12]}"


def _dirty_paths(engine: Any, worktree: Path) -> list[str]:
    fields = engine.git(worktree, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields) and fields[index]:
        entry = fields[index]
        paths.append(entry[3:])
        renamed = any(code in "RC" for code in entry[:2])
        if renamed and index + 1 < len(fields) and fields[index + 1]:
            paths.append(fields[index + 1])
        index += 2 if renamed else 1
    return sorted(paths)


def pre_pr_claim_record(
    root: Path,
    repository: str,
    subject: str,
    branch: str,
    provider_head: str,
    contract: dict[str, Any],
    sessions: list[dict[str, Any]],
    *,
    now: float,
) -> dict[str, Any]:
    """Bind an unowned provider mutex to its one exact Git-registered worktree."""
    engine = _engine()
    live = [
        item["session_id"] for item in sessions
        if item["last_event_epoch"] is not None and now - item["last_event_epoch"] <= SESSION_LIVENESS_WINDOW_SECONDS
    ]
    identity = {
        "repository": repository,
        "subject": subject,
        "body_sha256": contract["body_sha256"],
        "branch": branch,
        "provider_head": provider_head,
        "open_pull_requests": [],
        "live_session_ids": live,
    }
    if live:
        return {**identity, "class": "held_live", "reason": f"claim {subject} remains bound to live session {live[0]}"}

    project = noodle_project_root(root.resolve(), error_cls=engine.GateError)
    sessions_root = project / ".noodle" / "sessions"
    process_sessions = {sessions_root / item["session_id"] for item in sessions}
    # constraint: a process can start before its first order event; Noodle's exact execute-session
    # constraint: namespace still binds that process record to this claim, without a second worker registry.
    process_sessions.update(path for path in sessions_root.glob(f"{branch}-*") if path.is_dir())
    for session_path in sorted(process_sessions):
        process_path = session_path / "process.json"
        try:
            process = engine.load_json(process_path)
            if not isinstance(process, dict) or process.get("session_id") != session_path.name:
                raise ValueError("process session identity mismatch")
            pid = process.get("pid")
            if type(pid) is not int or pid <= 0:
                raise ValueError("process pid must be a positive integer")
            alive = process_alive(pid)
        except (engine.GateError, OSError, ValueError, OverflowError) as exc:
            return {**identity, "class": "held", "reason": f"claim {subject} process record {process_path} is unknown: {exc}"}
        if alive:
            return {
                **identity, "class": "held_live", "live_session_ids": [session_path.name],
                "reason": f"claim {subject} recorded process {pid} still exists for session {session_path.name}; refusing adoption",
            }
    common = Path(engine.git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    identity["git_common_dir"] = str(common)
    if common.parent != project:
        return {**identity, "class": "held", "reason": f"claim {subject} git common directory {common} is outside Noodle project {project}"}
    registry = engine.registered_worktrees(root)
    branch_ref = f"refs/heads/{branch}"
    candidates = sorted(
        (path, item) for path, item in registry.items()
        if item.get("branch") == branch_ref and "prunable" not in item
    )
    if len(candidates) != 1:
        observed = [f"{path}:{item.get('branch') or 'detached'}@{item.get('HEAD')}" for path, item in sorted(registry.items())]
        return {
            **identity,
            "class": "held",
            "reason": f"claim {subject} requires exactly one registered worktree on {branch_ref}; found {len(candidates)}; registered={observed}",
        }
    path, entry = candidates[0]
    local_head = engine.git(path, "rev-parse", "HEAD")
    local_branch = (entry.get("branch") or "").removeprefix("refs/heads/")
    bound = {
        **identity,
        "worktree_path": str(path),
        "local_branch": local_branch,
        "local_head": local_head,
        "dirty_paths": _dirty_paths(engine, path),
    }
    if entry.get("HEAD") != provider_head or local_head != provider_head:
        return {
            **bound,
            "class": "held",
            "reason": f"claim {subject} provider head {provider_head} != registered/local heads {entry.get('HEAD')}/{local_head} at {path}",
        }
    return {**bound, "class": "pre_pr_orphan"}


def dead_claim_snapshot(
    root: Path,
    repository: str,
    *,
    now: float | None = None,
    subjects: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Deterministically classify every active execute claim of one repository.

    Classes: pre_pr_orphan (ready + zero PRs + no live session + one exact worktree), held_live,
    held, dead_claim (awaiting_land + one open PR + no live ledger session), released_residue
    (a release crashed mid-flight: ready + open PR + no live session + salvage ref already at the
    claim head), live_session, not_awaiting_land, no_single_open_pr, head_drift, unreadable_issue.
    """
    engine = _engine()
    moment = time.time() if now is None else float(now)
    refs = engine.matching_branch_refs(repository, repository.replace("/", "-") + "-")
    records: list[dict[str, Any]] = []
    for subject in sorted(engine.active_execute_claims(repository, refs), key=lambda value: engine.parse_subject(value).number):
        if subjects is not None and subject not in subjects:
            continue
        branch = engine.execute_branch(subject)
        head = refs[f"refs/heads/{branch}"]
        record: dict[str, Any] = {"subject": subject, "branch": branch, "head": head}
        try:
            issue = engine.issue_read(subject)
            body = str(issue.get("body") or "")
            contract = engine.parse_issue_contract(body, expected_subject=subject)
            contract["body_sha256"] = hashlib.sha256(body.encode()).hexdigest()
        except engine.GateError as exc:
            records.append({**record, "class": "unreadable_issue", "reason": str(exc)})
            continue
        state = contract["state"]
        if issue.get("state") != "open" or state not in ("awaiting_land", "ready"):
            records.append({
                **record,
                "class": "not_awaiting_land",
                "reason": f"issue provider_state={issue.get('state')!r} state={state!r}",
            })
            continue
        sessions = subject_sessions(root, subject)
        prs = engine.matching_open_pull_requests(repository, subject)
        if not prs:
            if state != "ready":
                records.append({**record, "class": "no_single_open_pr", "reason": f"claim {subject} has zero open pull requests in state {state}"})
                continue
            records.append(pre_pr_claim_record(root, repository, subject, branch, head, contract, sessions, now=moment))
            continue
        if len(prs) != 1:
            records.append({**record, "class": "no_single_open_pr", "reason": f"claim {subject} has {len(prs)} open pull requests: {[item['number'] for item in prs]}"})
            continue
        pr = prs[0]
        live = [
            item["session_id"] for item in sessions
            if item["last_event_epoch"] is not None and moment - item["last_event_epoch"] <= SESSION_LIVENESS_WINDOW_SECONDS
        ]
        if live:
            records.append({**record, "class": "live_session", "pr_number": int(pr["number"]), "session_ids": live})
            continue
        pr_head = str(pr.get("head", {}).get("sha") or "")
        if pr_head != head:
            records.append({
                **record,
                "class": "head_drift",
                "pr_number": int(pr["number"]),
                "reason": f"open PR head {pr_head} != claim branch head {head}",
            })
            continue
        if state == "ready":
            preserved_ref = f"refs/heads/{salvage_branch(subject, head)}"
            preserved = engine.matching_branch_refs(repository, salvage_branch(subject, head))
            if preserved.get(preserved_ref) != head:
                records.append({
                    **record,
                    "class": "not_awaiting_land",
                    "reason": "issue is ready with an open PR but no salvage receipt branch proves an in-flight release",
                })
                continue
            records.append({
                **record,
                "class": "released_residue",
                "pr_number": int(pr["number"]),
                "pr": pr,
                "session_ids": [item["session_id"] for item in sessions],
            })
            continue
        records.append({
            **record,
            "class": "dead_claim",
            "pr_number": int(pr["number"]),
            "pr": pr,
            "session_ids": [item["session_id"] for item in sessions],
        })
    return records


def adopt_dead_claim(root: Path, subject: str, pr: dict[str, Any], session_id: str) -> dict[str, Any]:
    """Re-admit the newest dead session's worktree as the claim owner via the existing repair ceremony."""
    engine = _engine()
    project = noodle_project_root(root.resolve(), error_cls=engine.GateError)
    spawn = engine.load_json(project / ".noodle" / "sessions" / session_id / "spawn.json")
    worktree_path = str(spawn.get("worktree_path") or "")
    review = {
        "order_id": subject,
        "session_id": session_id,
        "worktree_name": str(spawn.get("worktree_name") or Path(worktree_path).name),
        "worktree_path": worktree_path,
    }
    receipt = repair_review(root, subject, review, pr)
    return {
        "action": "adopted",
        "session_id": session_id,
        "attempt": receipt["repair"]["attempt"],
        "repair_receipt_path": receipt["repair_receipt_path"],
    }


def release_dead_claim(
    root: Path,
    repository: str,
    subject: str,
    branch: str,
    head: str,
    pr: dict[str, Any],
    *,
    adoption_blocker: str,
) -> dict[str, Any]:
    """Release an unadoptable claim: salvage-preserve the branch, flip the issue ready, free the claim name.

    Step order keeps the subject visible to the detector until the final delete: a crash after the
    salvage step is still a dead_claim, a crash after the state flip is a released_residue, so every
    partial release stays mechanically owned instead of wedging.
    """
    engine = _engine()
    policy = engine.protection_policy(root)
    failed_run = github_protection.failed_required_workflow_run_readback(
        engine.gh_api,
        engine.GateError,
        repository,
        head,
        name=policy["required_check"],
        path=".github/workflows/verify.yml",
        event="pull_request_target",
        default_branch=policy["default_branch"],
    )
    failed_job = github_protection.failed_workflow_job_readback(engine.gh_api, engine.GateError, repository, failed_run["run"]["id"])
    preserved = salvage_branch(subject, head)
    preserved_ref = f"refs/heads/{preserved}"
    existing = engine.matching_branch_refs(repository, preserved)
    if preserved_ref in existing:
        if existing[preserved_ref] != head:
            raise engine.GateError(f"salvage branch {preserved} already exists at {existing[preserved_ref]}, not claim head {head}")
    else:
        created = engine.gh_api(
            f"repos/{repository}/git/refs",
            method="POST",
            payload={"ref": preserved_ref, "sha": head},
        )
        if not isinstance(created, dict) or created.get("ref") != preserved_ref or created.get("object", {}).get("sha") != head:
            raise engine.GateError(f"salvage branch readback for {preserved_ref} did not match claim head {head}")
    engine.issue_set_state(subject, "ready")
    engine.gh_api(f"repos/{repository}/git/refs/heads/{branch}", method="DELETE")
    remaining = engine.matching_branch_refs(repository, branch)
    if f"refs/heads/{branch}" in remaining:
        raise engine.GateError(f"released claim branch {branch} still exists after delete readback")
    receipt = {
        "schema_version": engine.SCHEMA_VERSION,
        "action": "released",
        "repository": repository,
        "subject": subject,
        "branch": branch,
        "head": head,
        "preserved_branch": preserved,
        "pr_number": int(pr["number"]),
        "required_check": str(policy["required_check"]),
        "failed_workflow_run": {
            "id": failed_run["run"]["id"],
            "name": failed_run["run"]["name"],
            "conclusion": failed_run["run"]["conclusion"],
            "html_url": failed_run["run"]["html_url"],
        },
        "failed_job": failed_job,
        "adoption_blocker": adoption_blocker,
        "released_state": "ready",
    }
    project = noodle_project_root(root.resolve(), error_cls=engine.GateError)
    path = project / ".noodle" / "claims" / f"release-{branch}-{head[:12]}.json"
    engine.write_json(path, receipt)
    if engine.load_json(path) != receipt:
        raise engine.GateError(f"release receipt readback failed for {path}")
    return {**receipt, "release_receipt_path": str(path)}


def sweep_dead_claims(root: Path, *, now: float | None = None) -> list[dict[str, Any]]:
    """Adopt or release every dead claim of every admitted repository; one receipt record per claim."""
    engine = _engine()
    policy = engine.protection_policy(root)
    repositories = tuple(sorted(set(policy.get("allowed_repositories") or ())))
    if not repositories or not all(isinstance(repository, str) and repository for repository in repositories):
        raise engine.GateError("GitHub policy has no exact allowed repositories")
    outcomes: list[dict[str, Any]] = []
    for repository in repositories:
        for record in dead_claim_snapshot(root, repository, now=now):
            pr = record.pop("pr", None)
            if record["class"] not in ("dead_claim", "released_residue"):
                outcomes.append({**record, "action": "skipped"})
                continue
            adoption_blocker = f"release resumed for {record['subject']}: in-flight release residue"
            if record["class"] == "dead_claim":
                session_ids = record.get("session_ids") or []
                if session_ids:
                    try:
                        outcomes.append({**record, **adopt_dead_claim(root, record["subject"], pr, session_ids[-1])})
                        continue
                    except engine.GateError as exc:
                        adoption_blocker = str(exc)
                else:
                    adoption_blocker = f"no session ledger entry ties {record['subject']} to a resumable worktree"
            try:
                outcomes.append({
                    **record,
                    **release_dead_claim(
                        root,
                        repository,
                        record["subject"],
                        record["branch"],
                        record["head"],
                        pr,
                        adoption_blocker=adoption_blocker,
                    ),
                })
            except engine.GateError as exc:
                outcomes.append({**record, "action": "held", "reason": str(exc), "adoption_blocker": adoption_blocker})
    return outcomes
