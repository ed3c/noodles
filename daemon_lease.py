"""Bounded startup admission for exactly one truthful upstream Noodle daemon lease."""
from __future__ import annotations
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

LOCK_RELATIVE = ".noodle/noodle.lock"
STATUS_RELATIVE = ".noodle/status.json"
LIVE_LOOP_STATES = frozenset({"running", "starting", "paused"})
DEFAULT_ADMISSION_TIMEOUT = 30.0


def control_endpoint(control_url: str) -> tuple[str, int]:
    parts = urllib.parse.urlsplit(control_url)
    return parts.hostname or "127.0.0.1", int(parts.port or 3210)


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def listener_pids(host: str, port: int) -> list[int]:
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-t", f"-iTCP@{host}:{port}", "-sTCP:LISTEN"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except (FileNotFoundError, PermissionError) as exc:
        raise RuntimeError(f"noodles-start listener-probe-missing: cannot probe {host}:{port} listener ownership: {exc}") from exc
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"noodles-start listener-probe-failed: lsof exit {result.returncode} probing {host}:{port}: {result.stderr.strip()}"
        )
    return sorted({int(token) for token in result.stdout.split() if token.isdigit()})


def read_lease(project: Path) -> tuple[int | None, str]:
    try:
        text = (project / LOCK_RELATIVE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None, ""
    except OSError as exc:
        return None, f"<unreadable: {exc}>"
    return (int(text) if text.isdigit() and int(text) > 0 else None), text


def read_status(project: Path) -> dict[str, Any]:
    try:
        payload = json.loads((project / STATUS_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_snapshot(control_url: str) -> tuple[Any, str]:
    request = urllib.request.Request(control_url.rstrip("/") + "/api/snapshot", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return None, f"snapshot payload is {type(payload).__name__}, not an object"
    return payload, ""


def reject_existing_lease(project: Path, *, error_cls: type[Exception]) -> None:
    """Fail closed when any lease already exists, so a second concurrent start never spawns a child."""
    pid, text = read_lease(project)
    loop_state = str(read_status(project).get("loop_state") or "")
    lease_path = project / LOCK_RELATIVE
    if pid is None and not text:
        if loop_state in LIVE_LOOP_STATES:
            raise error_cls(
                f"noodles-start status-ghost: {STATUS_RELATIVE} claims loop_state={loop_state!r} but {lease_path} holds no Noodle lease"
            )
        return
    if pid is None:
        raise error_cls(f"noodles-start lease-unreadable: {lease_path} holds {text!r} instead of a Noodle process id")
    if process_alive(pid):
        raise error_cls(
            f"noodles-start lease-held: {lease_path} is held by live Noodle pid {pid}; refusing to spawn a second daemon"
        )
    raise error_cls(
        f"noodles-start lease-dead-pid: {lease_path} names pid {pid} which is not alive; clear the stale Noodle lease before starting"
    )


def admission_defect(project: Path, control_url: str, child_pid: int) -> tuple[str, dict[str, Any]]:
    """Return ('', receipt) only when the lease, listener, snapshot, and status all describe the exact spawned child."""
    host, port = control_endpoint(control_url)
    lease_path = project / LOCK_RELATIVE
    receipt: dict[str, Any] = {
        "child_pid": child_pid,
        "control_host": host,
        "control_port": port,
        "lease_path": str(lease_path),
    }
    pid, text = read_lease(project)
    if pid is None:
        if not text:
            return f"noodles-start lease-absent: {lease_path} does not exist for spawned Noodle child pid {child_pid}", receipt
        return f"noodles-start lease-unreadable: {lease_path} holds {text!r} instead of a Noodle process id", receipt
    receipt["lease_pid"] = pid
    if pid != child_pid:
        return (
            f"noodles-start lease-foreign-pid: {lease_path} names pid {pid}, not the spawned Noodle child pid {child_pid}",
            receipt,
        )
    if not process_alive(pid):
        return f"noodles-start lease-dead-pid: {lease_path} names pid {pid} which is not alive", receipt
    owners = listener_pids(host, port)
    receipt["listener_pids"] = owners
    if not owners:
        return f"noodles-start listener-absent: locked Noodle child pid {pid} owns no {host}:{port} listener", receipt
    if owners != [pid]:
        observed = ", ".join(str(item) for item in owners)
        return (
            f"noodles-start listener-foreign: {host}:{port} listener is owned by pid {observed}, not locked Noodle child pid {pid}",
            receipt,
        )
    snapshot, snapshot_error = read_snapshot(control_url)
    if snapshot_error:
        return f"noodles-start snapshot-unreadable: {control_url}/api/snapshot readback failed: {snapshot_error}", receipt
    receipt["snapshot_keys"] = sorted(snapshot)
    loop_state = str(read_status(project).get("loop_state") or "")
    if loop_state not in LIVE_LOOP_STATES:
        return (
            f"noodles-start status-inconsistent: {STATUS_RELATIVE} loop_state={loop_state!r} is not live while"
            f" locked Noodle child pid {pid} serves {host}:{port}",
            receipt,
        )
    receipt["loop_state"] = loop_state
    receipt["admitted"] = True
    return "", receipt


def admit_started_daemon(
    project: Path,
    control_url: str,
    child: Any,
    *,
    error_cls: type[Exception],
    timeout: float = DEFAULT_ADMISSION_TIMEOUT,
    poll_interval: float = 0.25,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    diagnostic = f"noodles-start lease-absent: {project / LOCK_RELATIVE} was never observed"
    while True:
        returncode = child.poll()
        if returncode is not None:
            raise error_cls(
                f"noodles-start lease-child-exited: spawned Noodle child pid {child.pid} exited with {returncode}"
                f" before admission; last defect: {diagnostic}"
            )
        try:
            diagnostic, receipt = admission_defect(project, control_url, child.pid)
        except RuntimeError as exc:
            raise error_cls(str(exc)) from exc
        if not diagnostic:
            return receipt
        if time.monotonic() >= deadline:
            raise error_cls(f"noodles-start admission-timeout: no truthful lease within {timeout}s; last defect: {diagnostic}")
        time.sleep(poll_interval)


def terminate_own_child(child: Any, control_url: str, *, error_cls: type[Exception], timeout: float = 10.0) -> dict[str, Any]:
    """Terminate only the child this wrapper created, then read back that it owns no surviving process or listener."""
    host, port = control_endpoint(control_url)
    pid = child.pid
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=timeout)
    try:
        owners = listener_pids(host, port)
    except RuntimeError as exc:
        raise error_cls(str(exc)) from exc
    residue = []
    if child.poll() is None:
        residue.append(f"spawned Noodle child pid {pid} survived termination")
    if pid in owners:
        residue.append(f"spawned Noodle child pid {pid} still owns {host}:{port}")
    receipt = {"child_pid": pid, "child_returncode": child.poll(), "listener_pids": owners, "residue": residue}
    if residue:
        raise error_cls("noodles-start orphan-residue: " + "; ".join(residue))
    return receipt
