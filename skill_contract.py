from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CONCURRENCY_PROOF_PATH = "policy/concurrency-proof.json"
CONCURRENCY_PROOF_INVARIANTS = ("I1", "I2", "I3", "I4")


SCHEDULE_OWNERSHIP_PHRASE = "Noodle alone injects and owns the transient `schedule` order."
SCHEDULE_ACTIVE_ORDER_PHRASE = "Do not re-emit any active non-schedule order."
SCHEDULE_PUBLISH_COMMAND = "python3 skill_contract.py publish .noodle/orders-next.candidate.json"
SCHEDULE_TASK_MODEL_PHRASE = (
    "Read `required_codex_task_profiles.execute.model` from `policy/fitness.json` and set that exact model "
    "on the order's only `execute` stage."
)
EXECUTE_PREFLIGHT_PHRASE = "0. Run `./noodles preflight` before any source edit. Stop if it names a missing capability."
EXECUTE_ENTRYPOINT_PHRASE = "Every execute task enters `poteto-mode` before any matched playbook or leaf skill."
EXECUTE_BYPASS_PHRASE = "Do not bypass `poteto-mode` by entering a leaf skill directly."
EXECUTE_EVIDENCE_PHRASE = "Record the selected P-class route and required physical oracle in the evidence packet."
EXECUTE_INVESTIGATION_ROUTE = (
    "- `investigation` -> `poteto-mode/playbooks/investigation.md`; "
    "oracle `exact issue readback plus direct source/runtime/provider readback`"
)
EXECUTE_FEATURE_ROUTE = (
    "- `function-boundary feature work` -> `architect` plus `poteto-mode/playbooks/feature.md`; "
    "oracle `tests plus direct source/runtime readback`"
)
EXECUTE_MULTI_PHASE_ROUTE = (
    "- `long multi-phase work` -> `show-me-your-work` plus "
    "`poteto-mode/playbooks/multi-phase-plan.md`; oracle `decision trail plus direct readback`"
)
EXECUTE_VERIFICATION_ROUTE = (
    "- `verification skill work` -> `create-verification-skill` or `maintain-verification-skill`; "
    "oracle `declared feature operation plus deterministic observed-state check`"
)
EXECUTE_VERIFICATION_P_CLASS_PHRASE = (
    "Output from `create-verification-skill` or `maintain-verification-skill` stays P-class until "
    "`./noodles feature verify <feature-id>` runs the declared operation and its oracle checks observed state."
)
EXECUTE_CONTROL_CLI_ROUTE = "- `CLI control` -> mapped `control-cli`; oracle `same-surface reproduction plus direct readback`"
EXECUTE_DESLOP_ROUTE = "- `pre-commit cleanup` -> mapped `deslop`; oracle `diff/status readback`"
EXECUTE_UNSUPPORTED_PHRASE = "Unsupported routes fail closed:"
EXECUTE_RESOLUTION_PHRASE = "If a referenced playbook or mapped skill does not resolve from the pinned provider bytes, fail closed."
SCHEDULE_SUMMARY_COMMAND = "python3 skill_contract.py summary .noodle/schedule-summary.md"
SCHEDULE_RECEIPT_VERBATIM_PHRASE = (
    "Quote `frontier`, `winners`, `max_useful_workers`, and every per-subject status line verbatim from "
    "`.noodle/schedule-cycle.json`. Never re-derive, rename, or paraphrase a decision the receipt already states."
)
SCHEDULE_STARVATION_DIAGNOSTIC_PHRASE = (
    "- signal: consecutive empty proposals while `mise.json` still lists schedulable ready issues; "
    "action: quote the receipt verbatim, then run the starvation diagnostic in order "
    "(remote claim branches vs their subject issue states -> claimed components vs ready pool -> "
    "receipt status definitions), and publish the diagnostic as data, never a re-derived causal story; "
    "why: a re-derived causal story misdiagnosed the 2026-08-31 starvation for hours."
)
SCHEDULE_CLAIM_STATUS_MEANINGS = {
    "claimed": "this cycle created the subject's exact execute branch on the provider",
    "claimed_elsewhere": "the subject's exact execute branch already existed, so another executor holds the claim",
    "dependency_changed": "the subject stopped reading back schedulable before its branch was claimed",
    "frontier_changed": "the subject left the winner set between proposal and claim",
    "not_in_winners": "the subject was absent from the winner set this cycle computed; this is not another executor's claim",
    "boundary_conflict": "the subject's declared write boundary intersects an already-admitted active order's boundary, so admitting both concurrently could collide at landing",
    "boundary_undeclared": "the subject declares no machine-readable write boundary, so its mutation surface cannot be proven disjoint and it fails closed",
    "executor_undeclared": "the subject declares no complete executor/runtime/evidence triple, so its execution lane cannot be classified and it fails closed before any claim",
    "executor_refused": "the subject's declared executor cannot physically supply its declared runtime or evidence policy, so the capability table refuses that lane and names the admitted route instead",
    "open_pr_exists": "the subject already has an open pull request, so a fresh attempt would be a duplicate lane the exact-execute-ref claim cannot see; the named PR routes to the repair owner instead",
}
COMPACT_ORDER_TOP_LEVEL_FIELDS = frozenset({"orders", "action_needed"})
COMPACT_ORDER_FIELDS = frozenset({"id", "plan", "rationale", "stages", "title"})
COMPACT_STAGE_FIELDS = frozenset({"do", "extra", "extra_prompt", "group", "model", "prompt", "runtime", "with"})
REPORT_ONLY_FITNESS_LIMITS = {
    "tracked_files": ("max", "max_tracked_files"),
    "max_file_lines": ("max", "max_file_lines"),
    "markdown_share": ("max", "max_markdown_share"),
    "normalized_line_entropy": ("min", "min_normalized_entropy"),
    "test_to_executable_ratio": ("min", "min_test_to_executable_ratio"),
    "root_surfaces": ("max", "max_root_surfaces"),
}
FAILING_FITNESS_LIMITS = {
    "enabled_external_providers": ("max", "max_enabled_providers"),
}


def _has_scheduler_frontmatter(content: str) -> bool:
    lines = content.lstrip(" \t\r\n").splitlines()
    if not lines or lines[0] != "---":
        return False
    try:
        closing = lines.index("---", 1)
    except ValueError:
        return False
    for line in lines[1:closing]:
        if not line.startswith("schedule:"):
            continue
        try:
            value = json.loads(line.partition(":")[2].strip())
        except json.JSONDecodeError:
            return False
        return isinstance(value, str) and bool(value.strip())
    return False


def _resolve_skill_file(root: Path, config: dict[str, Any], skill_name: str) -> Path | None:
    for raw_path in config.get("skills", {}).get("paths", []):
        if not isinstance(raw_path, str):
            continue
        skill_root = Path(os.path.expanduser(raw_path))
        if not skill_root.is_absolute():
            skill_root = root / skill_root
        candidate = skill_root / skill_name / "SKILL.md"
        if candidate.is_file():
            return candidate
    return None


def validate_backlog_scheduler(root: Path, config: dict[str, Any]) -> list[str]:
    skill_name = config.get("adapters", {}).get("backlog", {}).get("skill")
    if not isinstance(skill_name, str) or not skill_name.strip():
        return ["backlog adapter must configure one scheduler-capable skill"]
    skill_file = _resolve_skill_file(root, config, skill_name.strip())
    if skill_file is None:
        return [f"backlog adapter skill {skill_name!r} does not resolve from configured skill paths"]
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read backlog adapter skill {skill_name!r}: {exc}"]
    if not _has_scheduler_frontmatter(content):
        relative = os.path.relpath(skill_file, root)
        return [
            f"backlog adapter skill {skill_name!r} is not scheduler-capable: "
            f"{relative} requires non-empty top-level schedule frontmatter"
        ]
    required_contracts = (
        (SCHEDULE_OWNERSHIP_PHRASE, "self-order ownership"),
        (SCHEDULE_ACTIVE_ORDER_PHRASE, "active-order preservation"),
        (SCHEDULE_PUBLISH_COMMAND, "deterministic publish gate"),
        (SCHEDULE_TASK_MODEL_PHRASE, "task-model routing"),
        (SCHEDULE_RECEIPT_VERBATIM_PHRASE, "receipt-verbatim summary"),
        (SCHEDULE_SUMMARY_COMMAND, "deterministic summary gate"),
        (SCHEDULE_STARVATION_DIAGNOSTIC_PHRASE, "starvation diagnostic routing"),
    )
    errors = []
    for phrase, label in required_contracts:
        if phrase not in content:
            errors.append(f"backlog adapter skill {skill_name!r} missing {label} contract")
    return errors


def validate_execute_task(root: Path, config: dict[str, Any]) -> list[str]:
    skill_name = "execute"
    skill_file = _resolve_skill_file(root, config, skill_name)
    if skill_file is None:
        return [f"project task skill {skill_name!r} does not resolve from configured skill paths"]
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read project task skill {skill_name!r}: {exc}"]
    if not _has_scheduler_frontmatter(content):
        relative = os.path.relpath(skill_file, root)
        return [
            f"project task skill {skill_name!r} is not task-type resolvable: "
            f"{relative} requires non-empty top-level schedule frontmatter"
        ]
    required_contracts = (
        (EXECUTE_PREFLIGHT_PHRASE, "step-0 preflight"),
        (EXECUTE_ENTRYPOINT_PHRASE, "poteto-mode entrypoint"),
        (EXECUTE_BYPASS_PHRASE, "direct leaf bypass refusal"),
        (EXECUTE_EVIDENCE_PHRASE, "route evidence packet"),
        (EXECUTE_INVESTIGATION_ROUTE, "investigation fixture"),
        (EXECUTE_FEATURE_ROUTE, "function-boundary feature fixture"),
        (EXECUTE_MULTI_PHASE_ROUTE, "multi-phase fixture"),
        (EXECUTE_VERIFICATION_ROUTE, "verification-skill fixture"),
        (EXECUTE_VERIFICATION_P_CLASS_PHRASE, "verification-skill P-class refusal"),
        (EXECUTE_CONTROL_CLI_ROUTE, "CLI control fixture"),
        (EXECUTE_DESLOP_ROUTE, "pre-commit cleanup fixture"),
        (EXECUTE_UNSUPPORTED_PHRASE, "unsupported route refusal"),
        (EXECUTE_RESOLUTION_PHRASE, "pinned provider resolution refusal"),
    )
    content_lines = content.splitlines()
    errors = []
    for phrase, label in required_contracts:
        present = (
            any(line.startswith(phrase) for line in content_lines)
            if phrase == EXECUTE_UNSUPPORTED_PHRASE
            else phrase in content
        )
        if not present:
            errors.append(f"project task skill {skill_name!r} missing {label} contract")
    return errors


def validate_agent_document_route(root: Path, tracked_paths: set[str], policy: dict[str, Any]) -> list[str]:
    route = policy.get("agent_document_route")
    max_hops = policy.get("max_agent_document_hops")
    if not isinstance(route, list) or not route or not all(isinstance(node, str) and node for node in route):
        return ["agent document route must be a non-empty string list"]
    if not isinstance(max_hops, int) or max_hops < 1:
        return ["max_agent_document_hops must be a positive integer"]
    errors = []
    if len(route) > max_hops:
        errors.append(f"agent document route has {len(route)} nodes; maximum is {max_hops}")
    for index, node in enumerate(route):
        if not node.endswith(".md"):
            continue
        if node not in tracked_paths:
            errors.append(f"agent document route missing tracked node: {node}")
            continue
        if index + 1 < len(route) and route[index + 1] not in (root / node).read_text(encoding="utf-8", errors="ignore"):
            errors.append(f"agent document route pointer missing: {node} -> {route[index + 1]}")
    return errors


def threshold_exceeded(value: int | float, direction: str, threshold: int | float) -> bool:
    if direction == "max":
        return value > threshold
    if direction == "min":
        return value < threshold
    raise ValueError(f"unsupported threshold direction: {direction!r}")


def threshold_relation(direction: str) -> str:
    if direction == "max":
        return "exceeds"
    if direction == "min":
        return "below"
    raise ValueError(f"unsupported threshold direction: {direction!r}")


def architecture_warning_message(key: str, value: int | float, direction: str, threshold: int | float) -> str:
    return f"architecture warning {key}={value} {threshold_relation(direction)} {threshold}"


def failing_fitness_message(key: str, value: int | float, direction: str, threshold: int | float) -> str:
    return f"fitness {key}={value} {threshold_relation(direction)} {threshold}"


def report_only_threshold_readback(metrics: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    readback: list[dict[str, Any]] = []
    for key, (direction, policy_key) in REPORT_ONLY_FITNESS_LIMITS.items():
        value = metrics[key]
        threshold = policy[policy_key]
        status = "warning" if threshold_exceeded(value, direction, threshold) else "ok"
        readback.append(
            {
                "metric": key,
                "policy_key": policy_key,
                "classification": "report-only",
                "authority": "N",
                "direction": direction,
                "threshold": threshold,
                "value": value,
                "status": status,
                "message": architecture_warning_message(key, value, direction, threshold) if status == "warning" else None,
            }
        )
    return readback


def metrics_readback(metrics: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    warning_readback = report_only_threshold_readback(metrics, policy)
    warnings = [item["message"] for item in warning_readback if item["status"] == "warning"]
    return {
        **metrics,
        "warnings": warnings,
        "warning_readback": warning_readback,
    }


def _orders(payload: Any, label: str) -> tuple[list[Any], list[str]]:
    if not isinstance(payload, dict):
        return [], [f"{label} must be a JSON object"]
    orders = payload.get("orders")
    if not isinstance(orders, list):
        return [], [f"{label} must contain an orders array"]
    return orders, []


def _unknown_fields(payload: dict[str, Any], allowed: frozenset[str], label: str) -> list[str]:
    allowed_fields = ", ".join(sorted(allowed))
    return [
        f"{label} has unknown field {field!r}; allowed fields: {allowed_fields}"
        for field in sorted(payload)
        if field not in allowed
    ]


def _validate_action_needed(payload: dict[str, Any]) -> list[str]:
    if "action_needed" not in payload:
        return []
    action_needed = payload["action_needed"]
    if not isinstance(action_needed, list):
        return ["scheduler output action_needed must be an array of strings"]
    errors = []
    for index, item in enumerate(action_needed):
        if not isinstance(item, str):
            errors.append(f"scheduler output action_needed[{index}] must be a string")
    return errors


def validate_schedule_output(
    current: Any,
    proposed: Any,
    required_task_profiles: dict[str, dict[str, str]],
) -> list[str]:
    current_orders, errors = _orders(current, "current orders")
    proposed_orders, proposed_errors = _orders(proposed, "scheduler output")
    errors.extend(proposed_errors)
    if isinstance(proposed, dict):
        errors.extend(_unknown_fields(proposed, COMPACT_ORDER_TOP_LEVEL_FIELDS, "scheduler output"))
        errors.extend(_validate_action_needed(proposed))
    if errors:
        return errors

    active_ids = {
        str(order.get("id", "")).strip().casefold(): str(order.get("id", "")).strip()
        for order in current_orders
        if isinstance(order, dict)
        and str(order.get("status", "")).strip().casefold() == "active"
        and str(order.get("id", "")).strip().casefold() != "schedule"
    }
    for index, order in enumerate(proposed_orders):
        if not isinstance(order, dict):
            errors.append(f"scheduler output order[{index}] must be a JSON object")
            continue
        errors.extend(_unknown_fields(order, COMPACT_ORDER_FIELDS, f"scheduler output order[{index}]"))
        raw_id = order.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            errors.append(f"scheduler output order[{index}] requires a non-empty string id")
            continue
        order_id = raw_id.strip()
        normalized_id = order_id.casefold()
        if normalized_id == "schedule":
            errors.append("scheduler output must not contain Noodle-owned transient schedule order 'schedule'")
            continue
        if normalized_id in active_ids:
            errors.append(
                f"scheduler output must omit active non-schedule order {active_ids[normalized_id]!r}; "
                "Noodle preserves its exact order/stage fields"
            )
            continue
        stages = order.get("stages")
        if not isinstance(stages, list):
            errors.append(f"scheduler output order {order_id!r} stages must be an array")
            continue
        if len(stages) != 1:
            errors.append(
                f"scheduler output order {order_id!r} must contain exactly one stage; found {len(stages)}"
            )
            continue
        stage = stages[0]
        if not isinstance(stage, dict):
            errors.append(f"scheduler output order {order_id!r} stage[0] must be a JSON object")
            continue
        errors.extend(_unknown_fields(stage, COMPACT_STAGE_FIELDS, f"scheduler output order {order_id!r} stage[0]"))
        raw_do = stage.get("do")
        if not isinstance(raw_do, str) or not raw_do.strip():
            errors.append(
                f"scheduler output order {order_id!r} stage[0] requires canonical non-empty do"
            )
            continue
        task_key = raw_do.strip().casefold()
        if task_key == "schedule":
            errors.append(f"scheduler output order {order_id!r} must not contain a schedule stage")
            continue
        if task_key != "execute":
            errors.append(
                f"scheduler output order {order_id!r} stage[0] has unresolved do {raw_do.strip()!r}; "
                "expected 'execute'"
            )
            continue
        task_profile = required_task_profiles.get(task_key, {})
        required_model = task_profile.get("model")
        raw_model = stage.get("model")
        if not isinstance(raw_model, str) or not raw_model.strip():
            errors.append(
                f"scheduler output order {order_id!r} stage[0] requires explicit model {required_model!r} "
                "for execute"
            )
            continue
        if raw_model != required_model:
            errors.append(
                f"scheduler output order {order_id!r} stage[0] model must be {required_model!r} "
                f"for execute; found {raw_model!r}"
            )
    return errors


def tracked_test_exists(root: Path, identifier: str) -> bool:
    # constraint: ed3c/noodles#100 - resolve `tests.module.Class.test_name` against the tracked
    # constraint: source with ast, not by importing it: verify must stay side-effect free, and the
    # constraint: question is only whether the named control exists in the suite.
    parts = identifier.split(".")
    if len(parts) != 4 or parts[0] != "tests" or not parts[3].startswith("test_"):
        return False
    path = root / "tests" / f"{parts[1]}.py"
    if not path.is_file():
        return False
    try:
        module = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == parts[2]:
            return any(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == parts[3]
                for item in node.body
            )
    return False


def validate_concurrency_proof(root: Path, config: dict[str, Any]) -> list[str]:
    """ed3c/noodles#100 - bind declared concurrency capacity to evidence instead of to a number.

    `max_concurrency` is never bounded above here: a declared value greater than one is a claim that
    the four N-independent invariants hold, so the only thing this gate demands is that the lock
    recording them exists, parses, and names planted-negative controls that are really in the suite.
    N-dependent behaviour (per-lane wall time, repair rate, provider throttling) stays report-only in
    `./noodles metrics`; gating on it would reintroduce the numeric stop-loss this atom refuses."""
    declared = config.get("concurrency", {}).get("max_concurrency")
    if not isinstance(declared, int) or isinstance(declared, bool) or declared <= 1:
        return []
    path = root / CONCURRENCY_PROOF_PATH
    if not path.is_file():
        return [
            f".noodle.toml declares max_concurrency={declared} but {CONCURRENCY_PROOF_PATH} is absent; "
            "concurrency above one is admitted by the invariant proof lock, never by the number alone"
        ]
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{CONCURRENCY_PROOF_PATH} is unreadable: {exc}"]
    if not isinstance(lock, dict) or lock.get("schema_version") != 1:
        return [f"{CONCURRENCY_PROOF_PATH} must be an object with schema_version 1"]
    residuals = lock.get("known_residuals")
    if not isinstance(residuals, list) or not all(isinstance(item, str) and item.strip() for item in residuals):
        return [f"{CONCURRENCY_PROOF_PATH} must carry a known_residuals list of non-empty strings"]
    invariants = lock.get("invariants")
    if not isinstance(invariants, list) or {
        item.get("id") for item in invariants if isinstance(item, dict)
    } != set(CONCURRENCY_PROOF_INVARIANTS):
        return [
            f"{CONCURRENCY_PROOF_PATH} must record exactly the invariants "
            f"{', '.join(CONCURRENCY_PROOF_INVARIANTS)}"
        ]
    errors: list[str] = []
    for entry in invariants:
        invariant = entry.get("id")
        subject = entry.get("subject")
        receipt = entry.get("receipt")
        if not isinstance(subject, str) or not subject.strip():
            errors.append(f"{CONCURRENCY_PROOF_PATH} invariant {invariant} names no landed subject")
        if not isinstance(receipt, dict) or not isinstance(receipt.get("digest"), str) or len(receipt.get("digest") or "") != 40:
            errors.append(f"{CONCURRENCY_PROOF_PATH} invariant {invariant} carries no exact receipt digest")
        named = entry.get("planted_negatives")
        if not isinstance(named, list) or not named:
            errors.append(f"{CONCURRENCY_PROOF_PATH} invariant {invariant} names no planted-negative control")
            continue
        for identifier in named:
            if not isinstance(identifier, str) or not tracked_test_exists(root, identifier):
                errors.append(
                    f"{CONCURRENCY_PROOF_PATH} invariant {invariant} names planted-negative "
                    f"{identifier!r}, which is absent from the tracked suite"
                )
    return errors


def validate_cycle_receipt(receipt: Any) -> list[str]:
    # constraint: ed3c/noodles#191 - the schedule receipt is the single frontier
    # constraint: authority, so every status it publishes must be one of the
    # constraint: machine-owned values carrying that value's exact meaning.
    if not isinstance(receipt, dict):
        return ["schedule cycle receipt must be a JSON object"]
    errors = [
        f"schedule cycle receipt {key} must be an array"
        for key in ("frontier", "winners")
        if not isinstance(receipt.get(key), list)
    ]
    if not isinstance(receipt.get("max_useful_workers"), int) or isinstance(receipt.get("max_useful_workers"), bool):
        errors.append("schedule cycle receipt max_useful_workers must be an integer")
    claims = receipt.get("claims")
    if not isinstance(claims, list):
        return errors + ["schedule cycle receipt claims must be an array"]
    defined = ", ".join(sorted(SCHEDULE_CLAIM_STATUS_MEANINGS))
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not isinstance(claim.get("subject"), str):
            errors.append(f"schedule cycle receipt claim[{index}] must be an object with a string subject")
            continue
        status = claim.get("status")
        meaning = SCHEDULE_CLAIM_STATUS_MEANINGS.get(status) if isinstance(status, str) else None
        if meaning is None:
            errors.append(
                f"schedule cycle receipt claim[{index}] has undefined status {status!r}; defined statuses: {defined}"
            )
            continue
        if claim.get("meaning") != meaning:
            errors.append(
                f"schedule cycle receipt claim[{index}] status {status!r} must carry its exact meaning {meaning!r}"
            )
    return errors


def cycle_summary_lines(receipt: dict[str, Any]) -> list[str]:
    lines = [
        f"frontier: {json.dumps(receipt['frontier'], separators=(',', ':'))}",
        f"winners: {json.dumps(receipt['winners'], separators=(',', ':'))}",
        f"max_useful_workers: {receipt['max_useful_workers']}",
    ]
    lines.extend(f"{claim['subject']}: {claim['status']} - {claim['meaning']}" for claim in receipt["claims"])
    return lines


def validate_cycle_summary(receipt: Any, summary: str) -> list[str]:
    # constraint: ed3c/noodles#191 - a published cycle summary that contradicts
    # constraint: the receipt fails closed here; containment of every required
    # constraint: line is what makes "quote it" mechanically checkable.
    errors = validate_cycle_receipt(receipt)
    if errors:
        return errors
    return [
        f"cycle summary does not quote the receipt verbatim: missing {line!r}"
        for line in cycle_summary_lines(receipt)
        if line not in summary
    ]


def _summary_command(root: Path, summary_path: Path) -> int:
    receipt_path = root / ".noodle/schedule-cycle.json"
    try:
        receipt = _read_json(receipt_path, "schedule cycle receipt")
        summary = summary_path.read_text(encoding="utf-8")
    except (ValueError, OSError) as exc:
        print(f"schedule summary FAIL: {exc}", file=sys.stderr)
        return 1
    errors = validate_cycle_summary(receipt, summary)
    if errors:
        print("schedule summary FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"schedule summary PASS: {summary_path} quotes {receipt_path} verbatim")
    return 0


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc


def task_profiles(root: Path) -> dict[str, dict[str, str]]:
    # constraint: policy/fitness.json holds the only committed definition of the codex task profiles.
    # constraint: every other reader derives its expectation here so a profile change touches one file.
    policy = _read_json(root / "policy/fitness.json", "fitness policy")
    profiles = policy.get("required_codex_task_profiles") if isinstance(policy, dict) else None
    if (
        not isinstance(profiles, dict)
        or set(profiles) != {"schedule", "execute"}
        or not all(
            isinstance(profile, dict)
            and set(profile) == {"model", "reasoning_effort"}
            and all(isinstance(value, str) and value for value in profile.values())
            for profile in profiles.values()
        )
    ):
        raise ValueError("fitness policy requires exact non-empty schedule/execute task profiles")
    return profiles


def validate_schedule_candidate(root: Path, candidate_path: Path) -> dict[str, Any]:
    root = root.resolve()
    runtime = root / ".noodle"
    expected_candidate = runtime / "orders-next.candidate.json"
    candidate = candidate_path if candidate_path.is_absolute() else root / candidate_path
    candidate = candidate.resolve()
    if candidate != expected_candidate.resolve():
        raise ValueError(f"schedule candidate must be {expected_candidate}")
    current_path = runtime / "orders.json"
    current = _read_json(current_path, "current orders") if current_path.exists() else {"orders": []}
    proposed = _read_json(candidate, "schedule candidate")
    required_task_profiles = task_profiles(root)
    errors = validate_schedule_output(current, proposed, required_task_profiles)
    if errors:
        raise ValueError("schedule output rejected: " + "; ".join(errors))
    return proposed


def publish_schedule_output(root: Path, candidate_path: Path) -> Path:
    root = root.resolve()
    runtime = root / ".noodle"
    candidate = candidate_path if candidate_path.is_absolute() else root / candidate_path
    candidate = candidate.resolve()
    validate_schedule_candidate(root, candidate)
    destination = runtime / "orders-next.json"
    os.replace(candidate, destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) == 2 and args[0] == "summary":
        return _summary_command(Path.cwd(), Path(args[1]))
    if len(args) != 2 or args[0] != "publish":
        print(
            "usage: python3 skill_contract.py publish .noodle/orders-next.candidate.json\n"
            "       python3 skill_contract.py summary .noodle/schedule-summary.md",
            file=sys.stderr,
        )
        return 2
    try:
        from noodles import schedule_publish
        result = schedule_publish(Path.cwd(), Path(args[1]))
        destination = result["destination"]
    except (ValueError, RuntimeError) as exc:
        print(f"schedule contract FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"schedule contract PASS: {destination} max_useful_workers={result['max_useful_workers']}")
    return 0


def validate_noodle_worktree_ignore(root: Path, tracked_paths: set[str]) -> list[str]:
    diagnostic = "Noodle worktree root .worktrees requires exact tracked ignore rule .worktrees/"
    if ".gitignore" not in tracked_paths:
        return [diagnostic]
    try:
        ignore_lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    except OSError:
        return [diagnostic]
    if ".worktrees/" not in ignore_lines:
        return [diagnostic]
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".worktrees/"], cwd=root, check=False
    )
    return [] if result.returncode == 0 else [diagnostic]


if __name__ == "__main__":
    raise SystemExit(main())
