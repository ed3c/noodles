"""Closure disposition receipts: retiring a marker-bearing Issue as not-planned is a contract event.

A bare `not_planned` closure silently deletes the reasoning chain, so the same proposal returns weeks
later and the machine re-litigates it at full cost. This module gives that closure a machine-checkable
receipt shape - payload custody routing every absorbed half to an owning Issue ref, a falsifiable
reopen condition, and a trade-off record - and reopens the bare ones into `blocked` so a retired
proposal never re-enters scheduling as work (ed3c/noodles#184).

It checks receipt SHAPE only. Whether the trade-off is wise stays with the closer; only its
legibility becomes mechanical. Landed closures are out of scope: the merge is their receipt.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# constraint: GitHub's own `state_reason` value for a retirement, distinct from `completed`.
NOT_PLANNED = "not_planned"
POSITIVE_FIXTURE_SUBJECT = "ed3c/noodles#151"
DIAGNOSTIC_MARKER = "<!-- noodles-disposition-defect -->"
BLOCKER_OWNER = "closer"
BLOCKER_REASON = (
    "not-planned closure carried no disposition receipt; post one closing comment with payload "
    "custody, a falsifiable reopen condition, and a trade-off record, then close as not planned again"
)
# constraint: bare `#N` or fully qualified `owner/repo#N`, the two custody-ref shapes the repo writes.
ISSUE_REF = r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#[1-9][0-9]*"
PAGE_SIZE = 100
# ponytail: bounded page walk instead of a Search-API query, upgrade when closed issues exceed this.
MAX_CLOSED_PAGES = 20

REQUIRED_ELEMENTS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "payload_custody",
        re.compile(rf"(?im)^.*payload custody.*?->[^\S\n]*{ISSUE_REF}.*$"),
        "one `PAYLOAD CUSTODY ...: <absorbed half> -> owner/repo#N; ...` line routing every absorbed "
        "half to the Issue that now owns it",
    ),
    (
        "reopen_condition",
        re.compile(r"(?i)reopen condition[^\S\n]*:[^\S\n]*\S"),
        "one `FALSIFIABLE REOPEN CONDITION: <physical evidence that would revive this>` line",
    ),
    (
        "trade_off",
        re.compile(r"(?i)trade-?off[^\S\n]+record[^\S\n]*:?[^\S\n]*\S"),
        "one `TRADE-OFF RECORD:` line stating what the retired path would buy and what it costs",
    ),
)


def disposition_defects(thread: str) -> tuple[str, ...]:
    """Names of the required receipt elements this closing thread does not carry, in declared order."""
    text = thread or ""
    return tuple(name for name, pattern, _ in REQUIRED_ELEMENTS if not pattern.search(text))


def disposition_diagnostic(subject: str, defects: tuple[str, ...]) -> str:
    """The reopen comment: names every missing element and the one supported path back to closed."""
    described = {name: description for name, _, description in REQUIRED_ELEMENTS}
    return "\n".join([
        DIAGNOSTIC_MARKER,
        f"Reopened `{subject}`: a not-planned closure of a marker-bearing Issue is a contract event, "
        "and this closing thread carries no disposition receipt.",
        "",
        "Missing receipt elements:",
        *(f"- `{name}`: {described[name]}" for name in defects),
        "",
        "Supported path: post one closing comment carrying every element above, then close as not "
        f"planned again. `{POSITIVE_FIXTURE_SUBJECT}`'s closing comment is the reference shape. This "
        "check reads receipt shape only - whether the trade-off is wise stays with the closer.",
    ])


def _engine():
    main = sys.modules.get("__main__")
    if main is not None and Path(getattr(main, "__file__", "")).resolve() == (Path(__file__).resolve().with_name("noodles.py")):
        return main
    import noodles as engine
    return engine


def subject_marker(body: str) -> str | None:
    """The exact `noodles-subject` marker, or None when the Issue bears no readable one.

    Marker-bearing is deliberately weaker than a full contract parse: a retired Issue may carry a
    body its own parser now rejects (ed3c/noodles#151 does), and that is not its closure's defect.
    """
    engine = _engine()
    try:
        return engine.one_marker(body or "", "subject", required=False)
    except engine.GateError:
        return None


def closed_not_planned(repository: str) -> list[dict[str, Any]]:
    """Every closed-as-not-planned Issue of one repository, lowest number first, by exact paged readback."""
    engine = _engine()
    found: list[dict[str, Any]] = []
    for page in range(1, MAX_CLOSED_PAGES + 1):
        batch = engine.gh_api(f"repos/{repository}/issues?state=closed&per_page={PAGE_SIZE}&page={page}")
        if not isinstance(batch, list):
            raise engine.GateError(f"closed-issue readback for {repository} page {page} is not a list")
        found.extend(
            item for item in batch
            if isinstance(item, dict) and "pull_request" not in item and item.get("state_reason") == NOT_PLANNED
        )
        if len(batch) < PAGE_SIZE:
            break
    else:
        raise engine.GateError(
            f"closed-issue readback for {repository} exceeded {MAX_CLOSED_PAGES} pages; "
            "no not-planned closure was validated rather than a partial page reading as complete"
        )
    return sorted(found, key=lambda item: int(item["number"]))


def closing_thread(repository: str, number: int) -> list[str]:
    """Every comment body on one Issue, in provider order; the closing receipt is posted as a comment."""
    engine = _engine()
    comments = engine.gh_api(f"repos/{repository}/issues/{number}/comments?per_page={PAGE_SIZE}")
    if not isinstance(comments, list):
        raise engine.GateError(f"comment readback for {repository}#{number} is not a list")
    return [str(item.get("body") or "") for item in comments if isinstance(item, dict)]


def receipt_text(thread: list[str]) -> str:
    """The thread minus this sweep's own diagnostics.

    The diagnostic quotes every required element by name, so counting it as evidence would let a bare
    closure launder the sweep's own complaint into a passing receipt on the next pass.
    """
    return "\n".join(body for body in thread if DIAGNOSTIC_MARKER not in body)


def reopen_bare_closure(repository: str, number: int, subject: str, body: str, thread: list[str], defects: tuple[str, ...]) -> dict[str, Any]:
    """Flag and reopen one receipt-less retirement, into `blocked` so it never re-enters scheduling."""
    engine = _engine()
    diagnostic = disposition_diagnostic(subject, defects)
    if diagnostic not in thread:  # constraint: identical standing diagnostic, never re-posted
        engine.gh_api(
            f"repos/{repository}/issues/{number}/comments",
            method="POST",
            payload={"body": diagnostic},
        )
    patched = body
    if subject_marker(patched) and engine.one_marker(patched, "state", required=False) != "blocked":
        patched = engine.replace_marker(patched, "state", "blocked")
        if not engine.one_marker(patched, "blocker", required=False):
            patched = engine.replace_marker(patched, "blocker", f"{BLOCKER_OWNER}: {BLOCKER_REASON}")
    payload: dict[str, Any] = {"state": "open", "state_reason": "reopened"}
    if patched != body:
        payload["body"] = patched
    engine.gh_api(f"repos/{repository}/issues/{number}", method="PATCH", payload=payload)
    readback = engine.gh_api(f"repos/{repository}/issues/{number}")
    if not isinstance(readback, dict) or readback.get("state") != "open":
        raise engine.GateError(f"reopen readback failed for {subject}: {readback!r}")
    if patched != body and engine.one_marker(str(readback.get("body") or ""), "state", required=False) != "blocked":
        raise engine.GateError(f"reopened {subject} did not read back as blocked; a retired atom must not re-enter scheduling")
    if not any(DIAGNOSTIC_MARKER in item for item in closing_thread(repository, number)):
        raise engine.GateError(f"disposition diagnostic readback failed for {subject}")
    return {"subject": subject, "action": "reopened", "defects": list(defects), "blocked": patched != body}


def sweep_closure_dispositions(root: Path) -> list[dict[str, Any]]:
    """Validate every not-planned closure of a marker-bearing Issue; reopen the bare ones."""
    engine = _engine()
    policy = engine.protection_policy(root)
    repositories = tuple(sorted(set(policy.get("allowed_repositories") or ())))
    if not repositories or not all(isinstance(item, str) and item for item in repositories):
        raise engine.GateError("GitHub policy has no exact allowed repositories")
    outcomes: list[dict[str, Any]] = []
    for repository in repositories:
        for issue in closed_not_planned(repository):
            number = int(issue["number"])
            subject = f"{repository}#{number}"
            body = str(issue.get("body") or "")
            if subject_marker(body) != subject:
                outcomes.append({"subject": subject, "action": "skipped", "reason": "issue bears no exact noodles-subject marker"})
                continue
            thread = closing_thread(repository, number)
            defects = disposition_defects(receipt_text(thread))
            if not defects:
                outcomes.append({"subject": subject, "action": "receipt_admitted", "defects": []})
                continue
            outcomes.append(reopen_bare_closure(repository, number, subject, body, thread, defects))
    return outcomes
