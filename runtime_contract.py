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

from issue_contract import SUBJECT_RE
from provider_contract import (
    CONTROL_NOODLE_DESTINATION,
    CONTROL_NOODLE_DISCOVERY_ROOT,
    CONTROL_NOODLE_PROVIDER,
    CONTROL_NOODLE_SKILL,
    RETIRED_PROVIDER,
    RETIRED_PROVIDER_DESTINATION,
    RETIRED_PROVIDER_DISCOVERY_ROOT,
    ROUTE_BUNDLE_ROOT,
    assemble_route_bundle,
    check_route_bundle,
    route_bundle_path,
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
# constraint: ed3c/noodles#174 monitor finding 13 - CURSOR_PSTACK_NATIVE_ROOT and the route-traversal
# constraint: paths below must agree on where the native pstack skill tree lives; NATIVE_SUBPATH is the
# constraint: single source (provider-checkout-relative) and NATIVE_ROOT derives from it, so a moved
# constraint: pinned layout only needs one edit instead of two hand-kept-in-sync literals.
CURSOR_PSTACK_NATIVE_SUBPATH = "pstack/skills"
CURSOR_PSTACK_NATIVE_ROOT = f"{CURSOR_PSTACK_DESTINATION}/{CURSOR_PSTACK_NATIVE_SUBPATH}"
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
_ROUTE_ENTRYPOINT = f"{CURSOR_PSTACK_NATIVE_SUBPATH}/poteto-mode/SKILL.md"
# constraint: ed3c/noodles#174 - the deterministic prefix of each immutable execute route fixture, in
# constraint: traversal order, addressed relative to the pinned cursor-pstack checkout. Every route
# constraint: starts at the poteto-mode entrypoint because no execute task may enter a leaf directly.
EXECUTE_ROUTE_TRAVERSALS: dict[str, tuple[str, ...]] = {
    "investigation": (
        _ROUTE_ENTRYPOINT,
        f"{CURSOR_PSTACK_NATIVE_SUBPATH}/poteto-mode/playbooks/investigation.md",
    ),
    "function-boundary-feature-work": (
        _ROUTE_ENTRYPOINT,
        f"{CURSOR_PSTACK_NATIVE_SUBPATH}/architect/SKILL.md",
        f"{CURSOR_PSTACK_NATIVE_SUBPATH}/poteto-mode/playbooks/feature.md",
    ),
    "long-multi-phase-work": (
        _ROUTE_ENTRYPOINT,
        f"{CURSOR_PSTACK_NATIVE_SUBPATH}/show-me-your-work/SKILL.md",
        f"{CURSOR_PSTACK_NATIVE_SUBPATH}/poteto-mode/playbooks/multi-phase-plan.md",
    ),
    "verification-skill-work": (
        _ROUTE_ENTRYPOINT,
        f"{CURSOR_PSTACK_NATIVE_SUBPATH}/create-verification-skill/SKILL.md",
        f"{CURSOR_PSTACK_NATIVE_SUBPATH}/maintain-verification-skill/SKILL.md",
    ),
    "cli-control": (
        _ROUTE_ENTRYPOINT,
        f"{CURSOR_PSTACK_COMPAT_SOURCE_ROOT}/control-cli/SKILL.md",
    ),
    "pre-commit-cleanup": (
        _ROUTE_ENTRYPOINT,
        f"{CURSOR_PSTACK_COMPAT_SOURCE_ROOT}/deslop/SKILL.md",
    ),
}
EXECUTE_ROUTE_BUNDLE_PHRASE = (
    "Read the pinned route bundle for the selected route before the live files. A bundle is a "
    "byte-preserving cache of the same pinned bytes in the same traversal order, never a substitute "
    "for the routing decision and never a summary. If a bundle is absent, stale, or fails its digest "
    "chain, load the pinned files live; every other pinned skill stays reachable only that way."
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


def _route_bundle_skills() -> set[str]:
    # constraint: ed3c/noodles#174 monitor finding 11 - only native-rooted SKILL.md leaves count as
    # constraint: "bundled" here; CURSOR_PSTACK_REQUIRED_NATIVE_SKILLS is a native-namespace set, so a
    # constraint: compat skill (cursor-team-kit/skills/<name>) that ever shared a basename with a
    # constraint: required native skill must never subtract that native skill from the live-only
    # constraint: complement below - the two namespaces are distinct skills at distinct paths.
    native_prefix = f"{CURSOR_PSTACK_NATIVE_SUBPATH}/"
    return {
        Path(path).parent.name
        for paths in EXECUTE_ROUTE_TRAVERSALS.values()
        for path in paths
        if path.endswith("/SKILL.md") and path.startswith(native_prefix)
    }


def live_only_native_skills() -> tuple[str, ...]:
    """Pinned native skills no bundle covers: the cache-not-cage complement that stays reachable
    only by normal live loading."""
    return tuple(sorted(set(CURSOR_PSTACK_REQUIRED_NATIVE_SKILLS) - _route_bundle_skills()))


def materialize_route_bundles(root: Path, providers: list[dict[str, Any]], *, error_cls: type[Exception]) -> dict[str, Any] | None:
    destination = _cursor_provider_destination(root, providers)
    if destination is None:
        return None
    commit = git(destination, "rev-parse", "HEAD", error_cls=error_cls)
    (root / ROUTE_BUNDLE_ROOT).mkdir(parents=True, exist_ok=True)
    bundles: dict[str, Any] = {}
    for route, paths in EXECUTE_ROUTE_TRAVERSALS.items():
        try:
            payload = assemble_route_bundle(
                destination, route=route, provider=CURSOR_PSTACK_PROVIDER, commit=commit, paths=paths
            )
        except OSError as exc:
            raise error_cls(f"route bundle {route} missing pinned traversal bytes: {exc}") from exc
        target = root / route_bundle_path(route)
        current = target.read_bytes() if target.is_file() else None
        # constraint: the payload embeds the pin commit and every section digest, so byte-equality is
        # constraint: exactly "the pin did not change"; an unchanged pin never rewrites the bundle.
        if current != payload:
            target.write_bytes(payload)
        bundles[route] = {
            "path": route_bundle_path(route),
            "sections": len(paths),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "status": "unchanged" if current == payload else "written",
        }
    return {
        "route_bundle_commit": commit,
        "route_bundles": bundles,
        "live_only_skills": list(live_only_native_skills()),
    }


def validate_route_bundles(root: Path, providers: list[dict[str, Any]], *, error_cls: type[Exception]) -> dict[str, Any] | None:
    destination = _cursor_provider_destination(root, providers)
    if destination is None:
        return None
    commit = git(destination, "rev-parse", "HEAD", error_cls=error_cls)
    bundles: dict[str, Any] = {}
    for route, paths in EXECUTE_ROUTE_TRAVERSALS.items():
        target = root / route_bundle_path(route)
        if not target.is_file():
            raise error_cls(f"route bundle missing: {route_bundle_path(route)}")
        payload = target.read_bytes()
        result = check_route_bundle(
            payload,
            destination,
            route=route,
            provider=CURSOR_PSTACK_PROVIDER,
            commit=commit,
            expected_paths=paths,
        )
        if result["errors"]:
            raise error_cls("; ".join(result["errors"]))
        if result["bundle_fed_sha256"] != result["live_loaded_sha256"]:
            raise error_cls(
                f"route bundle {route} bundle-fed stream {result['bundle_fed_sha256']} "
                f"!= live-loaded stream {result['live_loaded_sha256']}"
            )
        bundles[route] = {
            "path": route_bundle_path(route),
            "sections": len(paths),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bundle_fed_sha256": result["bundle_fed_sha256"],
            "live_loaded_sha256": result["live_loaded_sha256"],
        }
    live_only = live_only_native_skills()
    for skill in live_only:
        if not (destination / CURSOR_PSTACK_NATIVE_SUBPATH / skill / "SKILL.md").is_file():
            raise error_cls(f"out-of-bundle skill {skill!r} is not live-loadable from the pinned checkout")
    return {"route_bundle_commit": commit, "route_bundles": bundles, "live_only_skills": list(live_only)}


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
    execute = required_skill_paths.get("execute")
    if execute is None:
        raise error_cls("missing required skill readback for execute")
    routing = Path(execute["resolved_path"]).read_text(encoding="utf-8")
    if EXECUTE_ROUTE_BUNDLE_PHRASE not in routing:
        raise error_cls("execute routing contract does not point cooks at the pinned route bundles")
    for route in EXECUTE_ROUTE_TRAVERSALS:
        if route_bundle_path(route) not in routing:
            raise error_cls(f"execute routing contract does not name route bundle {route_bundle_path(route)}")


# constraint: ed3c/noodles#174 monitor finding 7 - a route's traversal (data, above) must keep naming
# constraint: the same leaf skill(s) as its own "Immutable route fixtures" bullet in the committed
# constraint: SKILL.md (prose), or a bundle could silently assemble the wrong skill's bytes under the
# constraint: right route name. Parsed from the real bullet text rather than a second hardcoded mapping,
# constraint: so the two can only agree by construction, not by two authors remembering to match.
_ROUTE_FIXTURE_BULLET_RE = re.compile(r"^- `(?P<label>[^`]+)` -> (?P<rhs>.+?); oracle ", re.M)


def _route_fixture_bullets(routing: str) -> dict[str, str]:
    return {
        match["label"].strip().lower().replace(" ", "-"): match["rhs"]
        for match in _ROUTE_FIXTURE_BULLET_RE.finditer(routing)
    }


def _route_traversal_leaf_identity(path: str) -> str:
    leaf = Path(path)
    return leaf.parent.name if path.endswith("/SKILL.md") else leaf.stem


def validate_execute_route_bundle_contract(root: Path) -> list[str]:
    """monitor findings 7 and 8 - static, provider-checkout-free check of the committed execute
    SKILL.md text, reachable from verify_repository (./noodles verify, the gate that runs on every
    PR head) without a live noodle binary or a materialized provider checkout - unlike
    _validate_execute_route_files above, which only runs through skill_discovery_check and therefore
    never ran in CI."""
    skill_file = root / PROJECT_SKILLS_ROOT / "execute" / "SKILL.md"
    if not skill_file.is_file():
        return [f"execute skill missing at {skill_file}"]
    routing = skill_file.read_text(encoding="utf-8")
    errors: list[str] = []
    if EXECUTE_ROUTE_BUNDLE_PHRASE not in routing:
        errors.append("execute routing contract does not point cooks at the pinned route bundles")
    bullets = _route_fixture_bullets(routing)
    for route, paths in EXECUTE_ROUTE_TRAVERSALS.items():
        bundle_path = route_bundle_path(route)
        if bundle_path not in routing:
            errors.append(f"execute routing contract does not name route bundle {bundle_path}")
        bullet = bullets.get(route)
        if bullet is None:
            errors.append(f"execute routing contract has no immutable-route-fixture bullet for route {route!r}")
            continue
        for leaf_path in paths[1:]:
            # constraint: paths[0] is the shared poteto-mode entrypoint, common to every route and
            # constraint: not itself named per-route in the fixture bullets.
            identity = _route_traversal_leaf_identity(leaf_path)
            if identity not in bullet:
                errors.append(
                    f"execute routing contract fixture for route {route!r} does not name {identity!r} "
                    f"(traversal leaf {leaf_path!r})"
                )
    return errors


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


def noodle_project_root(root: Path, *, error_cls: type[Exception]) -> Path:
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
    project = noodle_project_root(root.resolve(), error_cls=error_cls)
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
    project = noodle_project_root(root.resolve(), error_cls=error_cls)
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
    project = noodle_project_root(root.resolve(), error_cls=error_cls)
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
    project = noodle_project_root(root.resolve(), error_cls=error_cls)
    binary = resolve_locked_runtime_binary(root, error_cls=error_cls)
    result = run(
        [str(binary), "worktree", "exec", worktree_name, *command],
        cwd=project,
        error_cls=error_cls,
    )
    return result.stdout.strip()


def blocking_handoff_readback(
    root: Path,
    subject: str,
    pr_number: int,
    head: str,
    session_id: str,
    *,
    error_cls: type[Exception],
) -> dict[str, Any] | None:
    context = validate_handoff_session(root, subject, session_id, error_cls=error_cls)
    existing = [
        item for item in context["events"]
        if item.get("type") == "stage_message"
        and isinstance(item.get("payload"), dict)
        and item["payload"].get("issue_subject") == subject
    ]
    if len(existing) > 1:
        raise error_cls("execute handoff has duplicate blocking stage messages")
    if not existing:
        return None
    event = existing[0]
    if event["payload"].get("pr_number") != pr_number or event["payload"].get("head_sha") != head:
        raise error_cls("execute handoff stage message PR or head drifted")
    run_id = int(event["payload"].get("workflow_run_id") or 0)
    baseline_attempt = int(event["payload"].get("baseline_run_attempt") or 0)
    message = f"Provider handoff ready: {subject} PR #{pr_number} exact head {head} verify run {run_id} after attempt {baseline_attempt}; park until trusted provider landing readback."
    stage_messages = [item for item in context["events"] if item.get("type") == "stage_message"]
    if event.get("session_id") != session_id or event["payload"].get("blocking") is not True:
        raise error_cls("execute handoff stage message is not blocking for the exact session")
    if (
        run_id <= 0
        or baseline_attempt <= 0
        or event["payload"].get("message") != message
        or not stage_messages
        or stage_messages[-1] is not event
    ):
        raise error_cls("execute handoff stage message direct readback failed")
    return {
        "session_id": session_id,
        "head": head,
        "message": message,
        "blocking": True,
        "verification_rerun": {
            "workflow_run_id": run_id,
            "head_sha": head,
            "baseline_run_attempt": baseline_attempt,
        },
    }


def handoff_rerun_intent_readback(
    root: Path,
    subject: str,
    pr_number: int,
    head: str,
    session_id: str,
    *,
    error_cls: type[Exception],
) -> dict[str, Any] | None:
    context = validate_handoff_session(root, subject, session_id, error_cls=error_cls)
    existing = [item for item in context["events"] if item.get("type") == "handoff_verify_rerun_intent"]
    if len(existing) > 1:
        raise error_cls("execute handoff has duplicate verify rerun intents")
    if not existing:
        return None
    event = existing[0]
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise error_cls("execute handoff verify rerun intent payload is invalid")
    if (
        event.get("session_id") != session_id
        or payload.get("issue_subject") != subject
        or payload.get("pr_number") != pr_number
        or payload.get("head_sha") != head
    ):
        raise error_cls("execute handoff verify rerun intent subject, PR, or head drifted")
    run_id = int(payload.get("workflow_run_id") or 0)
    baseline_attempt = int(payload.get("baseline_run_attempt") or 0)
    if run_id <= 0 or baseline_attempt <= 0:
        raise error_cls("execute handoff verify rerun intent run identity is invalid")
    return {
        "issue_subject": subject,
        "pr_number": pr_number,
        "head_sha": head,
        "workflow_run_id": run_id,
        "baseline_run_attempt": baseline_attempt,
    }


def emit_handoff_rerun_intent(
    root: Path,
    subject: str,
    pr_number: int,
    head: str,
    workflow_run_id: int,
    baseline_run_attempt: int,
    session_id: str,
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    existing = handoff_rerun_intent_readback(
        root, subject, pr_number, head, session_id, error_cls=error_cls
    )
    expected = {
        "issue_subject": subject,
        "pr_number": pr_number,
        "head_sha": head,
        "workflow_run_id": workflow_run_id,
        "baseline_run_attempt": baseline_run_attempt,
    }
    if existing is not None:
        if existing != expected:
            raise error_cls("execute handoff verify rerun intent run identity drifted")
        return existing
    emit_session_event(
        root,
        session_id,
        "handoff_verify_rerun_intent",
        expected,
        error_cls=error_cls,
    )
    observed = handoff_rerun_intent_readback(
        root, subject, pr_number, head, session_id, error_cls=error_cls
    )
    if observed != expected:
        raise error_cls("execute handoff verify rerun intent direct readback failed")
    return observed


def emit_blocking_handoff(
    root: Path,
    subject: str,
    pr_number: int,
    head: str,
    workflow_run_id: int,
    baseline_run_attempt: int,
    session_id: str,
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    existing = blocking_handoff_readback(root, subject, pr_number, head, session_id, error_cls=error_cls)
    if existing is not None:
        if existing["verification_rerun"]["workflow_run_id"] != workflow_run_id:
            raise error_cls("execute handoff stage message workflow run id drifted")
        if existing["verification_rerun"]["baseline_run_attempt"] != baseline_run_attempt:
            raise error_cls("execute handoff stage message baseline run attempt drifted")
        return existing
    context = validate_handoff_session(root, subject, session_id, error_cls=error_cls)
    message = f"Provider handoff ready: {subject} PR #{pr_number} exact head {head} verify run {workflow_run_id} after attempt {baseline_run_attempt}; park until trusted provider landing readback."
    payload = {
        "message": message,
        "blocking": True,
        "issue_subject": subject,
        "pr_number": pr_number,
        "head_sha": head,
        "workflow_run_id": workflow_run_id,
        "baseline_run_attempt": baseline_run_attempt,
    }

    def matching(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            item for item in events
            if item.get("type") == "stage_message"
            and isinstance(item.get("payload"), dict)
            and item["payload"].get("message") == message
            and item["payload"].get("workflow_run_id") == workflow_run_id
            and item["payload"].get("baseline_run_attempt") == baseline_run_attempt
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
    receipt = blocking_handoff_readback(root, subject, pr_number, head, session_id, error_cls=error_cls)
    if (
        receipt is None
        or receipt["verification_rerun"]["workflow_run_id"] != workflow_run_id
        or receipt["verification_rerun"]["baseline_run_attempt"] != baseline_run_attempt
    ):
        raise error_cls("execute handoff stage message direct readback failed")
    return receipt


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
    bundle_receipt = validate_route_bundles(root, providers, error_cls=error_cls)
    if bundle_receipt is not None:
        for receipt in receipts:
            if receipt["name"] == CURSOR_PSTACK_PROVIDER:
                receipt.update(bundle_receipt)
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
    bundle_materialization = materialize_route_bundles(root, providers, error_cls=error_cls)
    receipts = provider_check(root, error_cls=error_cls)
    if bundle_materialization is not None:
        statuses = {route: item["status"] for route, item in bundle_materialization["route_bundles"].items()}
        for receipt in receipts:
            if receipt["name"] == CURSOR_PSTACK_PROVIDER:
                receipt["route_bundle_status"] = statuses
                break
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


# constraint: input and output schemas are declared separately - a future bundle/manifest shape
# constraint: change bumps SKILL_EVAL_OUTPUT_SCHEMA without forcing every caller-authored lane index
# constraint: (checked against SKILL_EVAL_LANE_INDEX_SCHEMA) to be rewritten, and vice versa.
SKILL_EVAL_LANE_INDEX_SCHEMA = 1
SKILL_EVAL_OUTPUT_SCHEMA = 1
SKILL_EVAL_MANIFEST_NAME = "skill-eval-sweep-manifest.json"
SKILL_EVAL_LANDED_OUTCOME = "landed"
SKILL_EVAL_LANE_TEXT_FIELDS = ("subject", "outcome", "completed_at", "verify_receipt", "merge_receipt")
# constraint: the packaged-byte secret gate. Only the three GitHub credential families this atom
# constraint: declares, each with a body floor so the bare word "ghp_" in a transcript is not a FATAL.
SKILL_EVAL_SECRET_RE = re.compile(rb"(ghs_|ghp_|github_pat_)[A-Za-z0-9_]{16,}")


def _skill_eval_text(value: Any, *, field: str, where: str, error_cls: type[Exception]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_cls(f"skill-eval lane index {where}: {field} must be one non-empty string")
    return value


def _skill_eval_digest(value: Any, *, field: str, where: str, error_cls: type[Exception]) -> str:
    text = _skill_eval_text(value, field=field, where=where, error_cls=error_cls)
    if not HEX64_RE.fullmatch(text):
        raise error_cls(f"skill-eval lane index {where}: {field} must be one sha256 digest, got {text!r}")
    return text


def _skill_eval_archive_reference(entry: Any, where: str, *, error_cls: type[Exception]) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise error_cls(f"skill-eval lane index {where}: each archive reference must be one object")
    size = entry.get("bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise error_cls(f"skill-eval lane index {where}: bytes must be one non-negative integer, got {size!r}")
    return {
        "path": _skill_eval_text(entry.get("path"), field="path", where=where, error_cls=error_cls),
        "sha256": _skill_eval_digest(entry.get("sha256"), field="sha256", where=where, error_cls=error_cls),
        "bytes": size,
    }


def _skill_eval_lane(raw: Any, position: int, *, error_cls: type[Exception]) -> dict[str, Any]:
    where = f"lane[{position}]"
    if not isinstance(raw, dict):
        raise error_cls(f"skill-eval lane index {where}: each lane must be one object")
    lane = {
        field: _skill_eval_text(raw.get(field), field=field, where=where, error_cls=error_cls)
        for field in SKILL_EVAL_LANE_TEXT_FIELDS
    }
    if not SUBJECT_RE.fullmatch(lane["subject"]):
        raise error_cls(f"skill-eval lane index {where}: subject {lane['subject']!r} is not one exact owner/repo#N subject")
    pr = raw.get("pr")
    if not isinstance(pr, int) or isinstance(pr, bool) or pr <= 0:
        raise error_cls(f"skill-eval lane index {where}: pr must be one positive integer, got {pr!r}")
    skills = raw.get("skills")
    if not isinstance(skills, dict) or not skills:
        raise error_cls(f"skill-eval lane index {where}: skills must be one non-empty executing-skill digest map")
    archives = raw.get("archives")
    if not isinstance(archives, list) or not archives:
        raise error_cls(f"skill-eval lane index {where}: archives must be one non-empty list of session-archive references")
    return {
        **lane,
        "pr": pr,
        "skills": {
            str(name): _skill_eval_digest(digest, field=f"skills[{name}]", where=where, error_cls=error_cls)
            for name, digest in sorted(skills.items())
        },
        "archives": sorted(
            (
                _skill_eval_archive_reference(entry, f"{where}.archives[{index}]", error_cls=error_cls)
                for index, entry in enumerate(archives)
            ),
            key=lambda item: item["path"],
        ),
    }


def _skill_eval_lane_index(path: Path, *, error_cls: type[Exception]) -> list[dict[str, Any]]:
    payload = load_json(path, error_cls=error_cls)
    if not isinstance(payload, dict) or payload.get("schema_version") != SKILL_EVAL_LANE_INDEX_SCHEMA:
        raise error_cls(f"skill-eval lane index {path} must declare schema_version {SKILL_EVAL_LANE_INDEX_SCHEMA}")
    raw_lanes = payload.get("lanes")
    if not isinstance(raw_lanes, list) or not raw_lanes:
        raise error_cls(f"skill-eval lane index {path} carries no lanes")
    lanes = [_skill_eval_lane(raw, position, error_cls=error_cls) for position, raw in enumerate(raw_lanes)]
    seen: set[str] = set()
    for lane in lanes:
        if lane["subject"] in seen:
            raise error_cls(f"skill-eval lane index {path} repeats subject {lane['subject']}")
        seen.add(lane["subject"])
    return sorted(lanes, key=lambda lane: lane["subject"])


def _skill_eval_selection(
    lanes: Sequence[dict[str, Any]],
    sample: Sequence[str],
    since: str,
    until: str,
    *,
    error_cls: type[Exception],
) -> list[tuple[dict[str, Any], list[str]]]:
    """Deterministic selection from the caller's explicit inputs only.

    The window bounds and the sample list are caller arguments; nothing here reads a clock, a random
    source, or live repository state, so the same index plus the same arguments always selects the
    same lanes in the same order. A sample subject the window does not carry is a caller
    contradiction and fails closed instead of silently shrinking the sweep."""
    window = [
        lane
        for lane in lanes
        if (not since or lane["completed_at"] >= since) and (not until or lane["completed_at"] <= until)
    ]
    requested = sorted({subject for subject in sample if subject.strip()})
    available = {lane["subject"] for lane in window}
    absent = [subject for subject in requested if subject not in available]
    if absent:
        raise error_cls(
            f"skill-eval sample subjects absent from the caller's window {since or '-'}..{until or '-'}: {', '.join(absent)}"
        )
    selected: list[tuple[dict[str, Any], list[str]]] = []
    for lane in window:
        reasons = []
        if lane["outcome"] != SKILL_EVAL_LANDED_OUTCOME:
            reasons.append(f"outcome:{lane['outcome']}")
        if lane["subject"] in requested:
            reasons.append("sample")
        if reasons:
            selected.append((lane, reasons))
    if not selected:
        raise error_cls("skill-eval sweep selected no lane; an empty selection is never a successful sweep")
    return selected


def _skill_eval_secret_scan(label: str, payload: bytes, *, error_cls: type[Exception]) -> None:
    # constraint: report the credential family and the byte offset, never the matched bytes - a
    # constraint: diagnostic echoing the token would re-leak it into the trail this gate protects.
    match = SKILL_EVAL_SECRET_RE.search(payload)
    if match:
        raise error_cls(
            f"skill-eval secret scan rejected {label}: {match.group(1).decode('ascii')} token pattern at byte offset {match.start()}"
        )


def _skill_eval_archive_bytes(
    archive_root: Path, subject: str, archive: dict[str, Any], *, error_cls: type[Exception]
) -> bytes:
    relative = Path(archive["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise error_cls(f"skill-eval archive reference for {subject} escapes the archive root: {archive['path']}")
    resolved = archive_root / relative
    if not resolved.is_file():
        raise error_cls(
            f"skill-eval archive missing for {subject}: {archive['path']} is not a file under {archive_root}"
        )
    data = resolved.read_bytes()
    if len(data) < archive["bytes"]:
        raise error_cls(
            f"skill-eval archive truncated for {subject}: {archive['path']} declares {archive['bytes']} bytes, read {len(data)}"
        )
    observed = hashlib.sha256(data).hexdigest()
    if observed != archive["sha256"]:
        raise error_cls(
            f"skill-eval archive digest mismatch for {subject}: {archive['path']} declares {archive['sha256']}, read {observed}"
        )
    _skill_eval_secret_scan(f"archive {archive['path']} of {subject}", data, error_cls=error_cls)
    return data


def sweep_skill_eval(
    index_path: Path,
    archive_root: Path,
    out_dir: Path,
    *,
    sample: Sequence[str] = (),
    since: str = "",
    until: str = "",
    error_cls: type[Exception],
) -> dict[str, Any]:
    """Package one evidence bundle per selected lane and emit the sweep manifest.

    Custody only. Every session-archive reference is re-verified by digest against the bytes on disk
    at package time and every packaged byte is token-scanned, so a missing, truncated, or tampered
    archive and a leaked credential each become a FATAL instead of a quietly thinner bundle. No
    verdict is produced: the behavioral judge that reads this output is agent-side and N-class, and
    no scheduling, verification, or landing path reads anything written here."""
    # constraint: resolve before anything derives from it - the manifest's archive_root field is
    # constraint: packaged evidence, so two callers pointing at the same directory through a
    # constraint: different spelling (relative, trailing slash, `.` segment) must not fork the digest.
    archive_root = archive_root.resolve()
    if not archive_root.is_dir():
        raise error_cls(f"skill-eval archive root is not a directory: {archive_root}")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise error_cls(f"skill-eval sweep output directory is not empty: {out_dir}")
    lanes = _skill_eval_lane_index(index_path, error_cls=error_cls)
    packaged: list[tuple[Path, bytes, dict[str, Any]]] = []
    for lane, reasons in _skill_eval_selection(lanes, sample, since, until, error_cls=error_cls):
        repository, _, number = lane["subject"].partition("#")
        bundle_name = f"{repository.replace('/', '-')}-{number}.json"
        for archive in lane["archives"]:
            _skill_eval_archive_bytes(archive_root, lane["subject"], archive, error_cls=error_cls)
        payload = (
            json.dumps(
                {
                    "schema_version": SKILL_EVAL_OUTPUT_SCHEMA,
                    "subject": lane["subject"],
                    "pr": lane["pr"],
                    "outcome": lane["outcome"],
                    "completed_at": lane["completed_at"],
                    "selected_by": reasons,
                    "verify_receipt": lane["verify_receipt"],
                    "merge_receipt": lane["merge_receipt"],
                    "skill_digests": lane["skills"],
                    "archives": lane["archives"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        _skill_eval_secret_scan(f"bundle {bundle_name}", payload, error_cls=error_cls)
        packaged.append((
            out_dir / bundle_name,
            payload,
            {
                "subject": lane["subject"],
                "pr": lane["pr"],
                "selected_by": reasons,
                "verify_receipt": lane["verify_receipt"],
                "merge_receipt": lane["merge_receipt"],
                "skill_digests": lane["skills"],
                "archive_sha256": [archive["sha256"] for archive in lane["archives"]],
                "bundle_path": bundle_name,
                "bundle_sha256": hashlib.sha256(payload).hexdigest(),
            },
        ))
    manifest = {
        "schema_version": SKILL_EVAL_OUTPUT_SCHEMA,
        "lane_index_sha256": sha256_file(index_path),
        "archive_root": str(archive_root),
        "selection": {
            "sample": sorted({subject for subject in sample if subject.strip()}),
            "since": since,
            "until": until,
        },
        "lane_count": len(packaged),
        "lanes": [entry for _path, _payload, entry in packaged],
    }
    manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _skill_eval_secret_scan(SKILL_EVAL_MANIFEST_NAME, manifest_payload, error_cls=error_cls)
    # constraint: nothing reaches the filesystem until every selected lane has passed digest
    # constraint: re-verification and the token scan, so a FATAL sweep leaves no half-written bundle.
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, payload, _entry in packaged:
        path.write_bytes(payload)
    (out_dir / SKILL_EVAL_MANIFEST_NAME).write_bytes(manifest_payload)
    return manifest
