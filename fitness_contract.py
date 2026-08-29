from __future__ import annotations

from typing import Any

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
