from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEDULE_OWNERSHIP_PHRASE = "Noodle alone injects and owns the transient `schedule` order."
SCHEDULE_ACTIVE_ORDER_PHRASE = "Do not re-emit any active non-schedule order."
SCHEDULE_PUBLISH_COMMAND = "python3 skill_contract.py publish .noodle/orders-next.candidate.json"
SCHEDULE_TASK_MODEL_PHRASE = (
    "Read `required_codex_task_profiles.execute.model` from `policy/fitness.json` and set that exact model "
    "on the order's only `execute` stage."
)
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
EXECUTE_CONTROL_CLI_ROUTE = "- `CLI control` -> mapped `control-cli`; oracle `same-surface reproduction plus direct readback`"
EXECUTE_DESLOP_ROUTE = "- `pre-commit cleanup` -> mapped `deslop`; oracle `diff/status readback`"
EXECUTE_UNSUPPORTED_PHRASE = (
    "Unsupported routes fail closed: `control-ui`, Cursor `create-skill`, Cursor `/loop`, "
    "Graphite `gt`, cloud-agent infrastructure, standalone `goal`."
)
EXECUTE_RESOLUTION_PHRASE = "If a referenced playbook or mapped skill does not resolve from the pinned provider bytes, fail closed."
COMPACT_ORDER_TOP_LEVEL_FIELDS = frozenset({"orders", "action_needed"})
COMPACT_ORDER_FIELDS = frozenset({"id", "plan", "rationale", "stages", "title"})
COMPACT_STAGE_FIELDS = frozenset({"do", "extra", "extra_prompt", "group", "model", "prompt", "runtime", "with"})
REPORT_ONLY_FITNESS_LIMITS = {
    "tracked_files": ("max", "max_tracked_files"),
    "max_file_lines": ("max", "max_file_lines"),
    "markdown_share": ("max", "max_markdown_share"),
    "normalized_line_entropy": ("min", "min_normalized_entropy"),
    "test_to_executable_ratio": ("min", "min_test_to_executable_ratio"),
}
FAILING_FITNESS_LIMITS = {
    "root_surfaces": ("max", "max_root_surfaces"),
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
        (EXECUTE_ENTRYPOINT_PHRASE, "poteto-mode entrypoint"),
        (EXECUTE_BYPASS_PHRASE, "direct leaf bypass refusal"),
        (EXECUTE_EVIDENCE_PHRASE, "route evidence packet"),
        (EXECUTE_INVESTIGATION_ROUTE, "investigation fixture"),
        (EXECUTE_FEATURE_ROUTE, "function-boundary feature fixture"),
        (EXECUTE_MULTI_PHASE_ROUTE, "multi-phase fixture"),
        (EXECUTE_CONTROL_CLI_ROUTE, "CLI control fixture"),
        (EXECUTE_DESLOP_ROUTE, "pre-commit cleanup fixture"),
        (EXECUTE_UNSUPPORTED_PHRASE, "unsupported route refusal"),
        (EXECUTE_RESOLUTION_PHRASE, "pinned provider resolution refusal"),
    )
    errors = []
    for phrase, label in required_contracts:
        if phrase not in content:
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


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc


def publish_schedule_output(root: Path, candidate_path: Path) -> Path:
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
    policy = _read_json(root / "policy/fitness.json", "fitness policy")
    required_task_profiles = policy.get("required_codex_task_profiles") if isinstance(policy, dict) else None
    if (
        not isinstance(required_task_profiles, dict)
        or set(required_task_profiles) != {"schedule", "execute"}
        or not all(
            isinstance(profile, dict)
            and set(profile) == {"model", "reasoning_effort"}
            and all(isinstance(value, str) and value for value in profile.values())
            for profile in required_task_profiles.values()
        )
    ):
        raise ValueError("fitness policy requires exact non-empty schedule/execute task profiles")
    errors = validate_schedule_output(current, proposed, required_task_profiles)
    if errors:
        raise ValueError("schedule output rejected: " + "; ".join(errors))
    destination = runtime / "orders-next.json"
    os.replace(candidate, destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 2 or args[0] != "publish":
        print("usage: python3 skill_contract.py publish .noodle/orders-next.candidate.json", file=sys.stderr)
        return 2
    try:
        destination = publish_schedule_output(Path.cwd(), Path(args[1]))
    except ValueError as exc:
        print(f"schedule contract FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"schedule contract PASS: {destination}")
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
