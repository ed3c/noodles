from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from provider_contract import (
    CONTROL_NOODLE_DESTINATION,
    CONTROL_NOODLE_DISCOVERY_ROOT,
    CONTROL_NOODLE_PROVIDER,
    CONTROL_NOODLE_SKILL,
    RETIRED_PROVIDER,
    RETIRED_PROVIDER_DESTINATION,
    RETIRED_PROVIDER_DISCOVERY_ROOT,
    validate_admission_policy,
    validate_enabled_provider_names as validate_provider_names,
    validate_skill_config_paths,
)

HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
PROJECT_SKILLS_ROOT = ".agents/skills"
PROJECT_REQUIRED_SKILLS = ("execute", "schedule")
CURSOR_PSTACK_PROVIDER = "cursor-pstack"
CURSOR_PSTACK_DESTINATION = ".noodle/providers/cursor-pstack"
CURSOR_PSTACK_NATIVE_ROOT = ".noodle/providers/cursor-pstack/pstack/skills"
CURSOR_PSTACK_COMPAT_SOURCE_ROOT = "cursor-team-kit/skills"
CURSOR_PSTACK_COMPAT_SKILLS = ("control-cli", "deslop")
CURSOR_PSTACK_REQUIRED_NATIVE_SKILLS = (
    "poteto-mode",
    "how",
    "architect",
    "arena",
    "swarm",
    "interrogate",
    "unslop",
    "technical-writing",
    "no-comments",
    "show-me-your-work",
    "create-verification-skill",
    "maintain-verification-skill",
)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)


def _symlink_exact_bytes(source: Path, link: Path) -> None:
    relative = os.path.relpath(source, start=link.parent)
    os.symlink(relative, link, target_is_directory=source.is_dir())


def _cursor_provider_destination(root: Path, providers: list[dict[str, Any]]) -> Path | None:
    for item in providers:
        if str(item.get("name")) == CURSOR_PSTACK_PROVIDER:
            return (root / str(item["destination"])).resolve()
    return None


def _compat_skill_root(root: Path, skill: str) -> Path:
    return root / PROJECT_SKILLS_ROOT / skill


def _materialize_exact_skill_root(source: Path, mapped_root: Path, *, label: str, error_cls: type[Exception]) -> None:
    if not (source / "SKILL.md").is_file():
        raise error_cls(f"{label} missing mapped skill bytes at {source}")
    if mapped_root.exists() or mapped_root.is_symlink():
        _remove_path(mapped_root)
    mapped_root.mkdir()
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        _symlink_exact_bytes(child, mapped_root / child.name)


def _validate_exact_skill_root(source: Path, mapped_root: Path, *, label: str, error_cls: type[Exception]) -> str:
    if not mapped_root.is_dir() or mapped_root.is_symlink():
        raise error_cls(f"{label} must materialize as a real directory")
    source_entries = {path.name: path for path in source.iterdir()}
    mapped_entries = {path.name: path for path in mapped_root.iterdir()}
    extra_entries = sorted(name for name in mapped_entries if name not in source_entries)
    if extra_entries:
        raise error_cls(f"{label} must expose exact provider entries; unexpected {', '.join(extra_entries)}")
    for name, source_entry in sorted(source_entries.items()):
        mapped_entry = mapped_root / name
        if not mapped_entry.exists() and not mapped_entry.is_symlink():
            raise error_cls(f"{label} missing mapped entry {name}")
        if not mapped_entry.is_symlink() or mapped_entry.resolve() != source_entry.resolve():
            raise error_cls(f"{label} entry {name} does not resolve to pinned provider bytes")
    skill_file = mapped_root / "SKILL.md"
    if not skill_file.is_file() or skill_file.resolve() != (source / "SKILL.md").resolve():
        raise error_cls(f"{label} does not resolve exact SKILL.md bytes")
    return str(skill_file.resolve())


def materialize_cursor_compat_root(root: Path, providers: list[dict[str, Any]], *, error_cls: type[Exception]) -> dict[str, Any] | None:
    destination = _cursor_provider_destination(root, providers)
    if destination is None:
        return None
    source_root = destination / CURSOR_PSTACK_COMPAT_SOURCE_ROOT
    if not source_root.is_dir():
        raise error_cls(
            f"provider {CURSOR_PSTACK_PROVIDER} missing compatibility source root {CURSOR_PSTACK_COMPAT_SOURCE_ROOT}"
        )
    compat_root = root / PROJECT_SKILLS_ROOT
    compat_root.mkdir(parents=True, exist_ok=True)
    mapped_skills: dict[str, str] = {}
    for skill in CURSOR_PSTACK_COMPAT_SKILLS:
        source = source_root / skill
        mapped_root = _compat_skill_root(root, skill)
        _materialize_exact_skill_root(source, mapped_root, label=f"cursor-team-kit compatibility skill {skill}", error_cls=error_cls)
        mapped_skills[skill] = str((mapped_root / "SKILL.md").resolve())
    return {
        "compatibility_root": str(compat_root.resolve()),
        "compatibility_source_root": str(source_root.resolve()),
        "mapped_skills": mapped_skills,
    }


def validate_cursor_compat_root(root: Path, providers: list[dict[str, Any]], *, error_cls: type[Exception]) -> dict[str, Any] | None:
    destination = _cursor_provider_destination(root, providers)
    if destination is None:
        return None
    source_root = destination / CURSOR_PSTACK_COMPAT_SOURCE_ROOT
    compat_root = root / PROJECT_SKILLS_ROOT
    if not source_root.is_dir():
        raise error_cls(
            f"provider {CURSOR_PSTACK_PROVIDER} missing compatibility source root {CURSOR_PSTACK_COMPAT_SOURCE_ROOT}"
        )
    if not compat_root.is_dir():
        raise error_cls(f"provider {CURSOR_PSTACK_PROVIDER} compatibility root missing: {compat_root.resolve()}")
    if compat_root.resolve() == source_root.resolve():
        raise error_cls("cursor-team-kit compatibility root must not expose the entire cursor-team-kit/skills root")
    mapped_skills: dict[str, str] = {}
    for skill in CURSOR_PSTACK_COMPAT_SKILLS:
        link = _compat_skill_root(root, skill)
        target = source_root / skill
        if not target.is_dir():
            raise error_cls(
                f"provider {CURSOR_PSTACK_PROVIDER} missing mapped skill bytes for {skill} under {CURSOR_PSTACK_COMPAT_SOURCE_ROOT}"
            )
        mapped_skills[skill] = _validate_exact_skill_root(target, link, label=f"cursor-team-kit compatibility skill {skill}", error_cls=error_cls)
    return {
        "compatibility_root": str(compat_root.resolve()),
        "compatibility_source_root": str(source_root.resolve()),
        "mapped_skills": mapped_skills,
    }


def _required_skill_roots(root: Path) -> tuple[str, str]:
    native_root = str((root / CURSOR_PSTACK_NATIVE_ROOT).resolve())
    project_root = str((root / PROJECT_SKILLS_ROOT).resolve())
    return native_root, project_root


def _control_noodle_source_root(root: Path, providers: list[dict[str, Any]]) -> Path | None:
    for item in providers:
        if str(item.get("name")) == CONTROL_NOODLE_PROVIDER:
            return (root / str(item["destination"]) / "skills/control-noodle").resolve()
    return None


def materialize_control_noodle_root(root: Path, providers: list[dict[str, Any]], *, error_cls: type[Exception]) -> str | None:
    source_root = _control_noodle_source_root(root, providers)
    if source_root is None:
        return None
    mapped_root = _compat_skill_root(root, CONTROL_NOODLE_SKILL)
    _materialize_exact_skill_root(source_root, mapped_root, label=CONTROL_NOODLE_SKILL, error_cls=error_cls)
    return str((mapped_root / "SKILL.md").resolve())


def validate_control_noodle_root(root: Path, providers: list[dict[str, Any]], *, error_cls: type[Exception]) -> str | None:
    source_root = _control_noodle_source_root(root, providers)
    if source_root is None:
        return None
    return _validate_exact_skill_root(source_root, _compat_skill_root(root, CONTROL_NOODLE_SKILL), label=CONTROL_NOODLE_SKILL, error_cls=error_cls)


def _validate_execute_route_files(root: Path, required_skill_paths: dict[str, dict[str, str]], *, error_cls: type[Exception]) -> None:
    entrypoint = required_skill_paths.get("poteto-mode")
    if entrypoint is None:
        raise error_cls("missing required skill readback for poteto-mode")
    poteto_skill_file = Path(entrypoint["resolved_path"])
    playbook_dir = poteto_skill_file.parent / "playbooks"
    for name in ("investigation.md", "feature.md", "multi-phase-plan.md"):
        path = playbook_dir / name
        if not path.is_file():
            raise error_cls(f"execute route reference missing pinned playbook bytes: {path}")


def run(
    argv: Sequence[str],
    *,
    error_cls: type[Exception],
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(argv),
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if check and result.returncode != 0:
        command = " ".join(argv)
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise error_cls(f"command failed: {command}: {detail}")
    return result


def git(root: Path, *args: str, error_cls: type[Exception], check: bool = True) -> str:
    return run(["git", *args], cwd=root, check=check, error_cls=error_cls).stdout.strip()


def gh_repo_from_git(root: Path, *, error_cls: type[Exception]) -> str:
    url = git(root, "remote", "get-url", "origin", error_cls=error_cls)
    match = re.search(r"github\.com[/:]([^/]+/[^/.]+)(?:\.git)?$", url)
    if not match:
        raise error_cls(f"cannot derive GitHub repository from origin: {url}")
    return match.group(1)


def _control_checkout_readback(root: Path, default_branch: str, *, error_cls: type[Exception]) -> dict[str, Any]:
    branch = git(root, "branch", "--show-current", error_cls=error_cls)
    if branch != default_branch:
        observed = branch or "<detached>"
        raise error_cls(f"control checkout branch {observed} != default branch {default_branch}")
    status_output = run(["git", "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"], cwd=root, error_cls=error_cls).stdout.splitlines()
    ignored = [line for line in status_output if line.startswith("!! ")]
    porcelain = [line for line in status_output if not line.startswith("!! ")]
    if porcelain:
        raise error_cls("control checkout has tracked or untracked non-ignored changes: " + "; ".join(porcelain[:5]))
    remote_ref = f"refs/remotes/origin/{default_branch}"
    git(root, "fetch", "--quiet", "--no-tags", "origin", f"refs/heads/{default_branch}:{remote_ref}", error_cls=error_cls)
    local_head = git(root, "rev-parse", "HEAD", error_cls=error_cls)
    provider_head = git(root, "rev-parse", remote_ref, error_cls=error_cls)
    ahead_count = behind_count = 0
    if local_head == provider_head:
        relation = "equal"
    else:
        ahead_count, behind_count = (int(value) for value in git(root, "rev-list", "--left-right", "--count", f"HEAD...{remote_ref}", error_cls=error_cls).split())
        relation = "diverged" if ahead_count and behind_count else "ahead" if ahead_count else "behind" if behind_count else "stale"
    return {
        "branch": branch,
        "local_head": local_head,
        "provider_head": provider_head,
        "relation": relation,
        "ahead_count": ahead_count,
        "behind_count": behind_count,
        "porcelain": porcelain,
        "ignored": ignored,
        "clean": True,
    }


def control_checkout_admission(root: Path, default_branch: str, *, error_cls: type[Exception]) -> dict[str, Any]:
    receipt = _control_checkout_readback(root, default_branch, error_cls=error_cls)
    if receipt["relation"] != "equal":
        raise error_cls(f"control checkout is provider-stale ({receipt['relation']}): branch {receipt['branch']} local {receipt['local_head']} provider {receipt['provider_head']}")
    return receipt


def reconcile_checkout_admission(root: Path, default_branch: str, *, error_cls: type[Exception]) -> dict[str, Any]:
    receipt = _control_checkout_readback(root, default_branch, error_cls=error_cls)
    if receipt["relation"] not in {"equal", "behind"}:
        raise error_cls(f"control checkout is provider-stale ({receipt['relation']}): branch {receipt['branch']} local {receipt['local_head']} provider {receipt['provider_head']}")
    return receipt


def load_json(path: Path, *, error_cls: type[Exception]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise error_cls(f"cannot read JSON {path}: {exc}") from exc


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


def _safe_relative_path(value: str, *, field: str, provider_name: str, error_cls: type[Exception]) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise error_cls(f"provider {provider_name} has unsafe {field}")
    return path


def validate_enabled_provider_names(enabled_names: set[str]) -> list[str]:
    return validate_provider_names(enabled_names, CURSOR_PSTACK_PROVIDER)


def _load_subject_file_digests(subject_files: Any, *, provider_name: str, error_cls: type[Exception]) -> dict[str, str]:
    if not isinstance(subject_files, list):
        raise error_cls(f"provider {provider_name} admission subject_files must be a list")
    digests: dict[str, str] = {}
    for item in subject_files:
        if not isinstance(item, Mapping):
            raise error_cls(f"provider {provider_name} admission subject_files entry must be an object")
        path = str(item.get("path") or "")
        sha256 = str(item.get("sha256") or "")
        if not path:
            raise error_cls(f"provider {provider_name} admission subject_files entry missing path")
        if not HEX64_RE.fullmatch(sha256):
            raise error_cls(f"provider {provider_name} admission subject file {path} has invalid sha256")
        digests[path] = sha256
    return digests


def _provider_admission_receipt(
    destination: Path,
    provider: Mapping[str, Any],
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    provider_name = str(provider["name"])
    policy = provider.get("admission")
    if not isinstance(policy, Mapping):
        return {}
    path = _safe_relative_path(str(policy["path"]), field="admission path", provider_name=provider_name, error_cls=error_cls)
    admission_file = destination / path
    if not admission_file.is_file():
        raise error_cls(f"provider {provider_name} admission path missing: {path}")
    expected_admission_sha256 = str(policy["sha256"])
    observed_admission_sha256 = sha256_file(admission_file)
    if observed_admission_sha256 != expected_admission_sha256:
        raise error_cls(
            f"provider {provider_name} admission digest {observed_admission_sha256} != locked {expected_admission_sha256}"
        )
    payload = load_json(admission_file, error_cls=error_cls)
    expected_skill = str(policy["skill"])
    observed_skill = str(payload.get("skill") or "")
    if observed_skill != expected_skill:
        raise error_cls(f"provider {provider_name} admission skill {observed_skill!r} != locked {expected_skill!r}")
    if str(payload.get("status") or "") != "ADMITTED":
        raise error_cls(f"provider {provider_name} admission status must be 'ADMITTED'")
    expected_skill_tree_sha256 = str(policy["skill_tree_sha256"])
    observed_skill_tree_sha256 = str(payload.get("skill_tree_sha256") or "")
    if observed_skill_tree_sha256 != expected_skill_tree_sha256:
        raise error_cls(
            "provider "
            f"{provider_name} admission skill-tree digest {observed_skill_tree_sha256} != locked {expected_skill_tree_sha256}"
        )
    observed_subject_digests = _load_subject_file_digests(
        payload.get("subject_files"),
        provider_name=provider_name,
        error_cls=error_cls,
    )
    locked_subject_files = policy.get("subject_files")
    if not isinstance(locked_subject_files, Mapping) or not locked_subject_files:
        raise error_cls(f"provider {provider_name} admission subject_files must be an object")
    subject_receipt: dict[str, str] = {}
    for raw_path, raw_sha256 in locked_subject_files.items():
        subject_path = str(raw_path)
        expected_subject_sha256 = str(raw_sha256)
        _safe_relative_path(subject_path, field="admission subject path", provider_name=provider_name, error_cls=error_cls)
        if not HEX64_RE.fullmatch(expected_subject_sha256):
            raise error_cls(f"provider {provider_name} admission subject file {subject_path} has invalid locked sha256")
        observed_subject_sha256 = observed_subject_digests.get(subject_path)
        if observed_subject_sha256 != expected_subject_sha256:
            raise error_cls(
                "provider "
                f"{provider_name} admission subject file {subject_path} sha256 {observed_subject_sha256} != locked {expected_subject_sha256}"
            )
        subject_file = destination / subject_path
        if not subject_file.is_file():
            raise error_cls(f"provider {provider_name} admission subject file missing: {subject_path}")
        installed_subject_sha256 = sha256_file(subject_file)
        if installed_subject_sha256 != expected_subject_sha256:
            raise error_cls(
                "provider "
                f"{provider_name} installed subject file {subject_path} sha256 {installed_subject_sha256} != admitted {expected_subject_sha256}"
            )
        subject_receipt[subject_path] = installed_subject_sha256
    return {
        "admission_path": str(path),
        "admission_sha256": observed_admission_sha256,
        "admission_skill": observed_skill,
        "admission_skill_tree_sha256": observed_skill_tree_sha256,
        "subject_file_sha256": subject_receipt,
    }


def resolve_platform_key(*, error_cls: type[Exception], system_name: str | None = None, machine_name: str | None = None) -> str:
    system_value = (system_name or platform.system()).lower()
    machine_value = (machine_name or platform.machine()).lower()
    system_map = {"darwin": "darwin", "linux": "linux", "windows": "windows"}
    machine_map = {"arm64": "arm64", "aarch64": "arm64", "amd64": "amd64", "x86_64": "amd64"}
    if system_value not in system_map or machine_value not in machine_map:
        raise error_cls(f"unsupported noodle runtime platform: {system_value}/{machine_value}")
    return f"{system_map[system_value]}_{machine_map[machine_value]}"


def validate_runtime_lock(root: Path) -> list[str]:
    path = root / "policy/runtime.lock.json"
    if not path.exists():
        return ["missing policy/runtime.lock.json"]
    try:
        payload = load_json(path, error_cls=RuntimeError)
        runtime = payload["runtime"]
        platforms = runtime["platforms"]
    except (RuntimeError, KeyError, TypeError) as exc:
        return [f"invalid runtime lock: {exc}"]
    errors: list[str] = []
    repository = str(runtime.get("repository", ""))
    release = str(runtime.get("release", ""))
    commit = str(runtime.get("commit", ""))
    command = str(runtime.get("command", ""))
    if repository != "poteto/noodle":
        errors.append(f"runtime repository must be 'poteto/noodle', got {repository!r}")
    if not re.fullmatch(r"v\d+\.\d+\.\d+", release):
        errors.append(f"runtime release must be exact v-semver, got {release!r}")
    if not HEX40_RE.fullmatch(commit):
        errors.append("runtime commit must be an exact 40-hex SHA")
    if not command.strip():
        errors.append("runtime command is required")
    if not isinstance(platforms, dict) or not platforms:
        errors.append("runtime platforms must be a non-empty object")
        return errors
    for platform_key, item in platforms.items():
        if not re.fullmatch(r"[a-z]+_(amd64|arm64)", str(platform_key)):
            errors.append(f"runtime platform key invalid: {platform_key!r}")
            continue
        if not isinstance(item, dict):
            errors.append(f"runtime platform {platform_key} must be an object")
            continue
        asset_name = str(item.get("asset_name", ""))
        asset_sha256 = str(item.get("asset_sha256", ""))
        binary_sha256 = str(item.get("binary_sha256", ""))
        if not asset_name.startswith("noodle_"):
            errors.append(f"runtime platform {platform_key} asset name invalid: {asset_name!r}")
        if not HEX64_RE.fullmatch(asset_sha256):
            errors.append(f"runtime platform {platform_key} asset_sha256 must be 64 hex")
        if not HEX64_RE.fullmatch(binary_sha256):
            errors.append(f"runtime platform {platform_key} binary_sha256 must be 64 hex")
    return errors


def _load_runtime_policy(root: Path, *, error_cls: type[Exception]) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = load_json(root / "policy/runtime.lock.json", error_cls=error_cls)
    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        raise error_cls("runtime lock missing runtime object")
    platforms = runtime.get("platforms")
    if not isinstance(platforms, dict):
        raise error_cls("runtime lock missing platforms object")
    return payload, runtime


def _release_commit(repository: str, release: str, gh_get_json: Callable[[str], Any], *, error_cls: type[Exception]) -> str:
    ref = gh_get_json(f"repos/{repository}/git/ref/tags/{release}")
    tag_object = ref.get("object") if isinstance(ref, dict) else None
    if not isinstance(tag_object, dict):
        raise error_cls(f"release tag readback missing object for {repository}@{release}")
    object_type = str(tag_object.get("type") or "")
    object_sha = str(tag_object.get("sha") or "")
    if object_type == "commit":
        return object_sha
    if object_type != "tag":
        raise error_cls(f"release tag {release} must resolve to commit or tag, got {object_type!r}")
    tag_body = gh_get_json(f"repos/{repository}/git/tags/{object_sha}")
    target = tag_body.get("object") if isinstance(tag_body, dict) else None
    if not isinstance(target, dict) or str(target.get("type") or "") != "commit":
        raise error_cls(f"annotated tag {release} must point to a commit")
    return str(target.get("sha") or "")


def _resolve_binary(root: Path, command: str, *, error_cls: type[Exception]) -> Path:
    expanded = Path(os.path.expanduser(command))
    if expanded.is_absolute() or "/" in command:
        candidate = expanded if expanded.is_absolute() else (root / expanded)
        binary = candidate.resolve()
    else:
        resolved = shutil.which(command)
        if not resolved:
            raise error_cls(f"required noodle runtime command not found: {command}")
        binary = Path(resolved).resolve()
    if not binary.is_file():
        raise error_cls(f"required noodle runtime binary missing: {binary}")
    if not os.access(binary, os.X_OK):
        raise error_cls(f"required noodle runtime binary is not executable: {binary}")
    return binary


def resolve_locked_runtime_binary(root: Path, *, error_cls: type[Exception]) -> Path:
    _payload, runtime = _load_runtime_policy(root, error_cls=error_cls)
    binary = _resolve_binary(root, str(runtime.get("command") or ""), error_cls=error_cls)
    version = run([str(binary), "--version"], cwd=root, error_cls=error_cls).stdout.strip()
    release = str(runtime.get("release") or "")
    if version != release:
        raise error_cls(f"noodle version {version} != locked {release}")
    digest = sha256_file(binary)
    platforms = runtime.get("platforms") or {}
    if not any(isinstance(item, dict) and item.get("binary_sha256") == digest for item in platforms.values()):
        raise error_cls(f"noodle binary digest {digest} is not admitted by the runtime lock")
    return binary


def _noodle_project_root(root: Path, *, error_cls: type[Exception]) -> Path:
    configured = os.getenv("NOODLE_PROJECT_DIR", "").strip()
    if configured:
        project = Path(configured).expanduser().resolve()
    else:
        common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir", error_cls=error_cls)).resolve()
        if common.name != ".git":
            raise error_cls(f"cannot resolve Noodle project from git common directory: {common}")
        project = common.parent
    if not (project / ".noodle").is_dir():
        raise error_cls(f"Noodle runtime directory missing from project: {project}")
    return project


def _session_events(path: Path, *, error_cls: type[Exception]) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise error_cls(f"cannot read Noodle session events {path}: {exc}") from exc
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise error_cls(f"invalid Noodle session event in {path}: {exc}") from exc
        if not isinstance(event, dict):
            raise error_cls(f"invalid Noodle session event in {path}: expected object")
        events.append(event)
    return events


def read_session_events(path: Path, *, error_cls: type[Exception]) -> list[dict[str, Any]]:
    return _session_events(path, error_cls=error_cls)


def validate_handoff_session(
    root: Path,
    subject: str,
    session_id: str,
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    session_id = session_id.strip()
    if not session_id or Path(session_id).name != session_id:
        raise error_cls("current NOODLE_SESSION_ID is missing or unsafe")
    project = _noodle_project_root(root.resolve(), error_cls=error_cls)
    session = project / ".noodle" / "sessions" / session_id
    if not session.is_dir():
        raise error_cls(f"current Noodle session does not exist: {session_id}")
    spawn = load_json(session / "spawn.json", error_cls=error_cls)
    worktree = Path(str(spawn.get("worktree_path") or "")).expanduser().resolve()
    if worktree != root.resolve():
        raise error_cls(f"Noodle session worktree {worktree} != current worktree {root.resolve()}")
    events_path = session / "events.ndjson"
    events = _session_events(events_path, error_cls=error_cls)
    order_marker = f"[order:{subject}]"
    if not any(
        isinstance(item.get("payload"), dict) and order_marker in str(item["payload"].get("message") or "")
        for item in events
    ):
        raise error_cls(f"Noodle session {session_id} is not tied to exact order {subject}")
    return {"project": project, "events_path": events_path, "events": events}


def validate_pending_review_session(
    root: Path,
    subject: str,
    review: Mapping[str, Any],
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    project = _noodle_project_root(root.resolve(), error_cls=error_cls)
    session_id = str(review.get("session_id") or "").strip()
    if not session_id or Path(session_id).name != session_id:
        raise error_cls("pending review session_id is missing or unsafe")
    worktree_name = str(review.get("worktree_name") or "").strip()
    if not worktree_name:
        raise error_cls("pending review worktree_name is missing")
    worktree_raw = str(review.get("worktree_path") or "").strip()
    if not worktree_raw:
        raise error_cls("pending review worktree_path is missing")
    worktree_path = Path(worktree_raw).expanduser().resolve()
    if not worktree_path.is_dir():
        raise error_cls(f"pending review worktree is missing: {worktree_path}")
    session = project / ".noodle" / "sessions" / session_id
    if not session.is_dir():
        raise error_cls(f"pending review session does not exist: {session_id}")
    spawn = load_json(session / "spawn.json", error_cls=error_cls)
    spawned_path = Path(str(spawn.get("worktree_path") or "")).expanduser().resolve()
    if spawned_path != worktree_path:
        raise error_cls(f"pending review worktree {worktree_path} != session worktree {spawned_path}")
    spawned_name = str(spawn.get("worktree_name") or "").strip()
    if spawned_name and spawned_name != worktree_name:
        raise error_cls(f"pending review worktree name {worktree_name} != session worktree name {spawned_name}")
    events_path = session / "events.ndjson"
    events = _session_events(events_path, error_cls=error_cls)
    order_marker = f"[order:{subject}]"
    if not any(
        isinstance(item.get("payload"), dict) and order_marker in str(item["payload"].get("message") or "")
        for item in events
    ):
        raise error_cls(f"Noodle session {session_id} is not tied to exact order {subject}")
    return {
        "project": project,
        "session_id": session_id,
        "worktree_name": worktree_name,
        "worktree_path": worktree_path,
        "events_path": events_path,
        "events": events,
    }


def emit_session_event(
    root: Path,
    session_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    error_cls: type[Exception],
) -> None:
    session_id = session_id.strip()
    event_type = event_type.strip()
    if not session_id or Path(session_id).name != session_id:
        raise error_cls("current NOODLE_SESSION_ID is missing or unsafe")
    if not event_type:
        raise error_cls("session event type is required")
    project = _noodle_project_root(root.resolve(), error_cls=error_cls)
    binary = resolve_locked_runtime_binary(root, error_cls=error_cls)
    run(
        [
            str(binary),
            "--project-dir",
            str(project),
            "event",
            "emit",
            event_type,
            "--session",
            session_id,
            "--payload",
            json.dumps(dict(payload), separators=(",", ":")),
        ],
        cwd=root,
        error_cls=error_cls,
    )


def worktree_exec(
    root: Path,
    worktree_name: str,
    command: Sequence[str],
    *,
    error_cls: type[Exception],
) -> str:
    worktree_name = worktree_name.strip()
    if not worktree_name:
        raise error_cls("pending review worktree_name is missing")
    if not command:
        raise error_cls("worktree exec requires a command")
    project = _noodle_project_root(root.resolve(), error_cls=error_cls)
    binary = resolve_locked_runtime_binary(root, error_cls=error_cls)
    result = run(
        [str(binary), "worktree", "exec", worktree_name, *command],
        cwd=project,
        error_cls=error_cls,
    )
    return result.stdout.strip()


def emit_blocking_handoff(
    root: Path,
    subject: str,
    pr_number: int,
    head: str,
    session_id: str,
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    context = validate_handoff_session(root, subject, session_id, error_cls=error_cls)
    message = f"Provider handoff ready: {subject} PR #{pr_number} exact head {head}; park until trusted provider landing readback."
    payload = {"message": message, "blocking": True}

    def matching(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            item for item in events
            if item.get("type") == "stage_message"
            and isinstance(item.get("payload"), dict)
            and item["payload"].get("message") == message
        ]

    existing = matching(context["events"])
    if len(existing) > 1:
        raise error_cls("execute handoff has duplicate blocking stage messages")
    if not existing:
        binary = resolve_locked_runtime_binary(root, error_cls=error_cls)
        run(
            [str(binary), "--project-dir", str(context["project"]), "event", "emit", "stage_message", "--session", session_id, "--payload", json.dumps(payload, separators=(",", ":"))],
            cwd=root,
            error_cls=error_cls,
        )
    events = _session_events(context["events_path"], error_cls=error_cls)
    observed = matching(events)
    stage_messages = [item for item in events if item.get("type") == "stage_message"]
    if len(observed) != 1 or not stage_messages or stage_messages[-1] is not observed[0]:
        raise error_cls("execute handoff stage message direct readback failed")
    event = observed[0]
    if event.get("session_id") != session_id or event["payload"].get("blocking") is not True:
        raise error_cls("execute handoff stage message is not blocking for the exact session")
    return {"session_id": session_id, "head": head, "message": message, "blocking": True}


def runtime_check(
    root: Path,
    gh_get_json: Callable[[str], Any],
    *,
    error_cls: type[Exception],
    platform_key: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    _payload, runtime = _load_runtime_policy(root, error_cls=error_cls)
    selected_platform = platform_key or resolve_platform_key(error_cls=error_cls)
    platform_policy = runtime.get("platforms", {}).get(selected_platform)
    if not isinstance(platform_policy, dict):
        raise error_cls(f"runtime platform not admitted: {selected_platform}")
    repository = str(runtime.get("repository") or "")
    release = str(runtime.get("release") or "")
    commit = str(runtime.get("commit") or "")
    command = str(runtime.get("command") or "")
    binary = _resolve_binary(root, command, error_cls=error_cls)
    version = run([str(binary), "--version"], cwd=root, error_cls=error_cls).stdout.strip()
    if version != release:
        raise error_cls(f"noodle version {version} != locked {release}")
    installed_sha256 = sha256_file(binary)
    if installed_sha256 != platform_policy.get("binary_sha256"):
        raise error_cls(f"noodle binary digest {installed_sha256} != locked {platform_policy.get('binary_sha256')}")
    release_body = gh_get_json(f"repos/{repository}/releases/tags/{release}")
    observed_release = str(release_body.get("tag_name") or "")
    if observed_release != release:
        raise error_cls(f"release readback {observed_release!r} != locked {release!r}")
    observed_commit = _release_commit(repository, release, gh_get_json, error_cls=error_cls)
    if observed_commit != commit:
        raise error_cls(f"release commit {observed_commit} != locked {commit}")
    assets = release_body.get("assets")
    if not isinstance(assets, list):
        raise error_cls(f"release {release} assets are unreadable")
    asset_name = str(platform_policy.get("asset_name") or "")
    asset = next((item for item in assets if isinstance(item, dict) and item.get("name") == asset_name), None)
    if asset is None:
        raise error_cls(f"release {release} missing platform asset {asset_name}")
    observed_digest = str(asset.get("digest") or "")
    expected_digest = f"sha256:{platform_policy.get('asset_sha256')}"
    if observed_digest != expected_digest:
        raise error_cls(f"release asset digest {observed_digest!r} != locked {expected_digest!r}")
    receipt = {
        "repository": repository,
        "release": release,
        "commit": observed_commit,
        "platform": selected_platform,
        "asset_name": asset_name,
        "asset_sha256": str(platform_policy.get("asset_sha256") or ""),
        "binary_sha256": installed_sha256,
        "binary_path": str(binary),
        "command": command,
        "version": version,
    }
    write_json(root / ".noodle/receipts/runtime/noodle.json", {**receipt, "observed_at": int(time.time())})
    return receipt


def provider_items(root: Path, *, error_cls: type[Exception]) -> list[dict[str, Any]]:
    payload = load_json(root / "policy/providers.lock.json", error_cls=error_cls)
    providers = payload.get("providers")
    if not isinstance(providers, list):
        raise error_cls("provider lock missing providers array")
    return [item for item in providers if isinstance(item, dict) and item.get("enabled")]


def provider_check(root: Path, *, error_cls: type[Exception]) -> list[dict[str, Any]]:
    root = root.resolve()
    providers = provider_items(root, error_cls=error_cls)
    receipts: list[dict[str, Any]] = []
    retired_destination = (root / RETIRED_PROVIDER_DESTINATION).resolve()
    if retired_destination.exists():
        raise error_cls(f"retired provider checkout still present: {RETIRED_PROVIDER_DESTINATION}")
    for item in providers:
        destination = (root / str(item["destination"])).resolve()
        if root not in destination.parents:
            raise error_cls(f"unsafe provider destination: {destination}")
        if not destination.is_dir():
            raise error_cls(f"provider {item['name']} is not installed at {item['destination']}")
        head = git(destination, "rev-parse", "HEAD", error_cls=error_cls)
        if head != item["commit"]:
            raise error_cls(f"provider {item['name']} HEAD {head} != locked {item['commit']}")
        if run(["git", "symbolic-ref", "-q", "HEAD"], cwd=destination, error_cls=error_cls, check=False).returncode == 0:
            raise error_cls(f"provider {item['name']} checkout is not detached")
        if git(destination, "status", "--porcelain", error_cls=error_cls):
            raise error_cls(f"provider {item['name']} checkout is dirty")
        skill_root = destination / str(item["subpath"])
        skills = sorted(skill_root.rglob("SKILL.md")) if skill_root.is_dir() else []
        license_file = destination / str(item["license_path"])
        if not skills:
            raise error_cls(f"provider {item['name']} has no SKILL.md under {item['subpath']}")
        if not license_file.is_file():
            raise error_cls(f"provider {item['name']} license path missing: {item['license_path']}")
        receipts.append(
            {
                "name": str(item["name"]),
                "commit": head,
                "tree": git(destination, "rev-parse", "HEAD^{tree}", error_cls=error_cls),
                "destination": str(item["destination"]),
                "skill_path": str(item["subpath"]),
                "skill_count": len(skills),
                "license_path": str(item["license_path"]),
                "license_blob": git(destination, "rev-parse", f"HEAD:{item['license_path']}", error_cls=error_cls),
                "license_sha256": sha256_file(license_file),
                "detached": True,
                "clean": True,
                **_provider_admission_receipt(destination, item, error_cls=error_cls),
            }
        )
    compat_receipt = validate_cursor_compat_root(root, providers, error_cls=error_cls)
    if compat_receipt is not None:
        for receipt in receipts:
            if receipt["name"] == CURSOR_PSTACK_PROVIDER:
                receipt.update(compat_receipt)
                break
    mapped_control_noodle = validate_control_noodle_root(root, providers, error_cls=error_cls)
    if mapped_control_noodle is not None:
        for receipt in receipts:
            if receipt["name"] == CONTROL_NOODLE_PROVIDER:
                receipt["mapped_skill"] = mapped_control_noodle
                break
    return receipts


def provider_sync(root: Path, *, error_cls: type[Exception]) -> list[dict[str, Any]]:
    root = root.resolve()
    providers = provider_items(root, error_cls=error_cls)
    provider_root = root / ".noodle/providers"
    provider_root.mkdir(parents=True, exist_ok=True)
    for item in providers:
        destination = (root / str(item["destination"])).resolve()
        if root not in destination.parents or provider_root.resolve() not in destination.parents:
            raise error_cls(f"unsafe provider destination: {destination}")
        with tempfile.TemporaryDirectory(prefix="noodles-provider-", dir=str(provider_root)) as temp_name:
            stage = Path(temp_name) / "checkout"
            stage.mkdir()
            git(stage, "init", "-q", error_cls=error_cls)
            git(stage, "remote", "add", "origin", str(item["source"]), error_cls=error_cls)
            git(stage, "fetch", "-q", "--depth", "1", "origin", str(item["commit"]), error_cls=error_cls)
            git(stage, "checkout", "-q", "--detach", "FETCH_HEAD", error_cls=error_cls)
            if git(stage, "rev-parse", "HEAD", error_cls=error_cls) != item["commit"]:
                raise error_cls(f"provider {item['name']} fetch readback did not reach locked commit")
            if destination.exists():
                shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage, destination)
    retired_destination = root / RETIRED_PROVIDER_DESTINATION
    if retired_destination.exists():
        shutil.rmtree(retired_destination)
    materialize_cursor_compat_root(root, providers, error_cls=error_cls)
    materialize_control_noodle_root(root, providers, error_cls=error_cls)
    receipts = provider_check(root, error_cls=error_cls)
    receipt_dir = root / ".noodle/receipts/providers"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    for receipt in receipts:
        write_json(receipt_dir / f"{receipt['name']}.json", {**receipt, "observed_at": int(time.time())})
    return receipts


def skill_discovery_check(root: Path, noodle_binary: str | Path, *, error_cls: type[Exception]) -> dict[str, Any]:
    root = root.resolve()
    config = tomllib.loads((root / ".noodle.toml").read_text(encoding="utf-8"))
    configured_paths: list[str] = []
    compat_source_root = str((root / CURSOR_PSTACK_DESTINATION / CURSOR_PSTACK_COMPAT_SOURCE_ROOT).resolve())
    required_control_noodle_root = str((root / CONTROL_NOODLE_DISCOVERY_ROOT).resolve())
    retired_matt_root = str((root / RETIRED_PROVIDER_DISCOVERY_ROOT).resolve())
    for raw_path in config.get("skills", {}).get("paths", []):
        candidate = Path(os.path.expanduser(str(raw_path)))
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = str(candidate.resolve())
        if resolved == compat_source_root:
            raise error_cls("configured skill path must not expose the entire cursor-team-kit/skills root")
        configured_paths.append(resolved)
    if required_control_noodle_root not in configured_paths:
        raise error_cls(f"configured skill paths must include {required_control_noodle_root}")
    if retired_matt_root in configured_paths:
        raise error_cls("configured skill paths must not retain retired matt-engineering discovery")
    output = run(
        [str(noodle_binary), "--project-dir", str(root), "skills", "list"],
        cwd=root,
        error_cls=error_cls,
    ).stdout
    skills_by_root: dict[str, dict[str, dict[str, str]]] = {}
    for raw_line in output.splitlines():
        if not raw_line.strip():
            continue
        columns = raw_line.split("\t")
        if len(columns) != 4:
            raise error_cls(f"unexpected noodle skills list output: {raw_line!r}")
        name, skill_root, enabled, _skill_path = columns
        if enabled != "true":
            continue
        resolved_root = str(Path(skill_root).resolve())
        resolved_skill = Path(_skill_path).resolve()
        skill_file = resolved_skill / "SKILL.md" if resolved_skill.is_dir() else resolved_skill
        if not skill_file.is_file():
            raise error_cls(f"discovered skill {name!r} missing SKILL.md at {skill_file}")
        resolved_skill_path = str(skill_file.resolve())
        skills_by_root.setdefault(resolved_root, {})[name] = {
            "declared_path": _skill_path,
            "resolved_path": resolved_skill_path,
        }
    if retired_matt_root in skills_by_root:
        raise error_cls("noodle skill discovery must not expose retired matt-engineering skills")
    missing = [path for path in configured_paths if path != required_control_noodle_root and not skills_by_root.get(path)]
    if missing:
        raise error_cls(f"noodle skill discovery missing configured paths: {', '.join(missing)}")
    native_root, project_root = _required_skill_roots(root)
    required_skill_paths: dict[str, dict[str, str]] = {}
    native_skills = skills_by_root.get(native_root, {})
    for skill in CURSOR_PSTACK_REQUIRED_NATIVE_SKILLS:
        info = native_skills.get(skill)
        if info is None:
            raise error_cls(f"noodle skill discovery missing required native skill {skill!r} from {native_root}")
        expected_path = str((root / CURSOR_PSTACK_NATIVE_ROOT / skill / "SKILL.md").resolve())
        if info["resolved_path"] != expected_path:
            raise error_cls(f"native skill {skill!r} resolved path {info['resolved_path']} != {expected_path}")
        required_skill_paths[skill] = {"root": native_root, **info}
    project_skills = skills_by_root.get(project_root, {})
    for skill in PROJECT_REQUIRED_SKILLS:
        info = project_skills.get(skill)
        if info is None:
            raise error_cls(f"noodle skill discovery missing required project skill {skill!r} from {project_root}")
        expected_path = str((root / PROJECT_SKILLS_ROOT / skill / "SKILL.md").resolve())
        if info["resolved_path"] != expected_path:
            raise error_cls(f"project skill {skill!r} resolved path {info['resolved_path']} != {expected_path}")
        required_skill_paths[skill] = {"root": project_root, **info}
    control_noodle_skills = skills_by_root.get(project_root, {})
    control_noodle_info = control_noodle_skills.get(CONTROL_NOODLE_SKILL)
    if control_noodle_info is None:
        raise error_cls(f"noodle skill discovery missing required external skill {CONTROL_NOODLE_SKILL!r} from {project_root}")
    expected_control_noodle_path = str((root / CONTROL_NOODLE_DISCOVERY_ROOT / "SKILL.md").resolve())
    if control_noodle_info["resolved_path"] != expected_control_noodle_path:
        raise error_cls(
            "external skill "
            f"{CONTROL_NOODLE_SKILL!r} resolved path {control_noodle_info['resolved_path']} != {expected_control_noodle_path}"
        )
    required_skill_paths[CONTROL_NOODLE_SKILL] = {"root": project_root, **control_noodle_info}
    compat_skills = {
        skill: info
        for skill, info in project_skills.items()
        if Path(info["resolved_path"]).is_relative_to(Path(compat_source_root))
    }
    if sorted(compat_skills) != list(CURSOR_PSTACK_COMPAT_SKILLS):
        raise error_cls(
            "cursor-team-kit compatibility discovery must expose exactly "
            f"{', '.join(CURSOR_PSTACK_COMPAT_SKILLS)}; got {', '.join(sorted(compat_skills)) or '<empty>'}"
        )
    for skill in CURSOR_PSTACK_COMPAT_SKILLS:
        info = compat_skills[skill]
        expected_path = str((root / CURSOR_PSTACK_DESTINATION / CURSOR_PSTACK_COMPAT_SOURCE_ROOT / skill / "SKILL.md").resolve())
        if info["resolved_path"] != expected_path:
            raise error_cls(f"mapped skill {skill!r} resolved path {info['resolved_path']} != {expected_path}")
        required_skill_paths[skill] = {"root": project_root, **info}
    _validate_execute_route_files(root, required_skill_paths, error_cls=error_cls)
    receipt = {
        "configured_paths": configured_paths,
        "discovered_paths": sorted(skills_by_root),
        "skills_by_path": {path: len(skills_by_root[path]) for path in sorted(skills_by_root)},
        "required_skill_paths": required_skill_paths,
        "total_skills": sum(len(items) for items in skills_by_root.values()),
    }
    write_json(root / ".noodle/receipts/runtime/skills.json", {**receipt, "observed_at": int(time.time())})
    return receipt
