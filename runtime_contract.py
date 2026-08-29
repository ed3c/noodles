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
from typing import Any, Callable, Sequence

HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


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
    receipts: list[dict[str, Any]] = []
    for item in provider_items(root, error_cls=error_cls):
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
                "license_sha256": sha256_file(license_file),
                "detached": True,
                "clean": True,
            }
        )
    return receipts


def provider_sync(root: Path, *, error_cls: type[Exception]) -> list[dict[str, Any]]:
    root = root.resolve()
    provider_root = root / ".noodle/providers"
    provider_root.mkdir(parents=True, exist_ok=True)
    for item in provider_items(root, error_cls=error_cls):
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
    for raw_path in config.get("skills", {}).get("paths", []):
        candidate = Path(os.path.expanduser(str(raw_path)))
        if not candidate.is_absolute():
            candidate = root / candidate
        configured_paths.append(str(candidate.resolve()))
    output = run(
        [str(noodle_binary), "--project-dir", str(root), "skills", "list"],
        cwd=root,
        error_cls=error_cls,
    ).stdout
    skills_by_root: dict[str, list[str]] = {}
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
        skills_by_root.setdefault(resolved_root, []).append(name)
    missing = [path for path in configured_paths if not skills_by_root.get(path)]
    if missing:
        raise error_cls(f"noodle skill discovery missing configured paths: {', '.join(missing)}")
    receipt = {
        "configured_paths": configured_paths,
        "discovered_paths": sorted(skills_by_root),
        "skills_by_path": {path: len(skills_by_root[path]) for path in sorted(skills_by_root)},
        "total_skills": sum(len(items) for items in skills_by_root.values()),
    }
    write_json(root / ".noodle/receipts/runtime/skills.json", {**receipt, "observed_at": int(time.time())})
    return receipt
