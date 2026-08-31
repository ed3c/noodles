from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
CONTROL_NOODLE_PROVIDER = "skill-concerns"
CONTROL_NOODLE_SKILL = "control-noodle"
CONTROL_NOODLE_DESTINATION = ".noodle/providers/skill-concerns"
CONTROL_NOODLE_DISCOVERY_ROOT = ".noodle/providers/skill-concerns/skills/control-noodle"
RETIRED_PROVIDER = "matt-engineering"
RETIRED_PROVIDER_DESTINATION = ".noodle/providers/matt-engineering"
RETIRED_PROVIDER_DISCOVERY_ROOT = ".noodle/providers/matt-engineering/skills/engineering"


def validate_admission_policy(provider_name: str, admission: Any) -> list[str]:
    if not isinstance(admission, dict):
        return [f"provider {provider_name} admission must be an object"]
    errors: list[str] = []
    if not admission.get("skill"):
        errors.append(f"provider {provider_name} admission skill is required")
    if not HEX64_RE.fullmatch(str(admission.get("sha256", ""))):
        errors.append(f"provider {provider_name} admission digest must be a 64-hex sha256")
    if not HEX64_RE.fullmatch(str(admission.get("skill_tree_sha256", ""))):
        errors.append(f"provider {provider_name} admission skill-tree digest must be a 64-hex sha256")
    admission_path = str(admission.get("path", ""))
    if not admission_path:
        errors.append(f"provider {provider_name} admission path is required")
    elif Path(admission_path).is_absolute() or ".." in Path(admission_path).parts:
        errors.append(f"provider {provider_name} admission path must stay under the provider checkout")
    subject_files = admission.get("subject_files")
    if not isinstance(subject_files, dict) or not subject_files:
        return errors + [f"provider {provider_name} admission subject_files must be a non-empty object"]
    for subject_path, sha256 in subject_files.items():
        if Path(str(subject_path)).is_absolute() or ".." in Path(str(subject_path)).parts:
            errors.append(f"provider {provider_name} admission subject file path must stay under the provider checkout")
        if not HEX64_RE.fullmatch(str(sha256)):
            errors.append(f"provider {provider_name} admission subject file digest must be a 64-hex sha256")
    return errors


def validate_enabled_provider_names(enabled_names: set[str], cursor_provider: str) -> list[str]:
    expected = {CONTROL_NOODLE_PROVIDER, cursor_provider}
    if enabled_names == expected:
        return []
    return [
        "enabled providers must be exactly "
        f"{CONTROL_NOODLE_PROVIDER} and {cursor_provider}; got {', '.join(sorted(enabled_names)) or '<empty>'}"
    ]


# constraint: ed3c/noodles#174 - a route bundle is a BYTE-PRESERVING CACHE of one route traversal:
# constraint: verbatim concatenation of the exact pinned files, each section addressed by its own
# constraint: sha256 and length-framed so no section body can be read as a boundary. "Compile" means
# constraint: assemble-and-address, never condense; a paraphrased or truncated section fails closed here.
ROUTE_BUNDLE_ROOT = ".noodle/bundles"
ROUTE_BUNDLE_VERSION = "noodles-route-bundle v1"
ROUTE_BUNDLE_HEADER_LINES = 5
SECTION_HEADER_RE = re.compile(
    r"^--- noodles-bundle-section (?P<index>\d+) (?P<path>\S+) sha256=(?P<digest>[0-9a-f]{64}) bytes=(?P<size>\d+) ---$"
)


def route_bundle_path(route: str) -> str:
    return f"{ROUTE_BUNDLE_ROOT}/{route}.md"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _section_header(index: int, relative: str, body: bytes) -> bytes:
    return f"--- noodles-bundle-section {index} {relative} sha256={_sha256(body)} bytes={len(body)} ---\n".encode()


def assemble_route_bundle(
    source_root: Path, *, route: str, provider: str, commit: str, paths: Sequence[str]
) -> bytes:
    chunks = [
        (
            f"{ROUTE_BUNDLE_VERSION}\n"
            f"route: {route}\n"
            f"provider: {provider}\n"
            f"commit: {commit}\n"
            f"sections: {len(paths)}\n"
        ).encode()
    ]
    for index, relative in enumerate(paths):
        body = (source_root / relative).read_bytes()
        chunks.extend((_section_header(index, relative, body), body, b"\n"))
    return b"".join(chunks)


def _parse_route_bundle(payload: bytes) -> tuple[dict[str, str], list[tuple[str, str, bytes]]]:
    parts = payload.split(b"\n", ROUTE_BUNDLE_HEADER_LINES)
    if len(parts) <= ROUTE_BUNDLE_HEADER_LINES:
        raise ValueError("header is truncated")
    header_lines = [line.decode("utf-8", "replace") for line in parts[:ROUTE_BUNDLE_HEADER_LINES]]
    header = {"version": header_lines[0]}
    for line in header_lines[1:]:
        key, separator, value = line.partition(": ")
        if not separator:
            raise ValueError(f"unparseable header line {line!r}")
        header[key] = value
    sections: list[tuple[str, str, bytes]] = []
    cursor = parts[ROUTE_BUNDLE_HEADER_LINES]
    while cursor:
        raw_header, separator, remainder = cursor.partition(b"\n")
        if not separator:
            raise ValueError("section header is unterminated")
        match = SECTION_HEADER_RE.match(raw_header.decode("utf-8", "replace"))
        if match is None:
            raise ValueError(f"unparseable section header {raw_header.decode('utf-8', 'replace')!r}")
        if int(match["index"]) != len(sections):
            raise ValueError(f"section index {match['index']} is out of traversal order")
        size = int(match["size"])
        body = remainder[:size]
        if len(body) != size or remainder[size : size + 1] != b"\n":
            raise ValueError(f"section {match['path']} body is not {size} framed bytes")
        sections.append((match["path"], match["digest"], body))
        cursor = remainder[size + 1 :]
    return header, sections


def check_route_bundle(
    payload: bytes,
    source_root: Path,
    *,
    route: str,
    provider: str,
    commit: str,
    expected_paths: Sequence[str],
) -> dict[str, Any]:
    try:
        header, sections = _parse_route_bundle(payload)
    except ValueError as exc:
        return {"errors": [f"route bundle {route} is unparseable: {exc}"], "bundle_fed_sha256": None, "live_loaded_sha256": None}
    errors = [
        f"route bundle {route} header {key} is {header.get(key)!r}; expected {value!r}"
        for key, value in (
            ("version", ROUTE_BUNDLE_VERSION),
            ("route", route),
            ("provider", provider),
            ("commit", commit),
            ("sections", str(len(expected_paths))),
        )
        if header.get(key) != value
    ]
    traversal = [path for path, _digest, _body in sections]
    if traversal != list(expected_paths):
        return {
            "errors": errors + [f"route bundle {route} traversal is {traversal}; expected {list(expected_paths)}"],
            "bundle_fed_sha256": None,
            "live_loaded_sha256": None,
        }
    live: list[bytes] = []
    for path, digest, body in sections:
        pinned = source_root / path
        if not pinned.is_file():
            errors.append(f"route bundle {route} section {path} has no pinned file at {pinned}")
            continue
        pinned_bytes = pinned.read_bytes()
        live.append(pinned_bytes)
        pinned_digest = _sha256(pinned_bytes)
        if digest != pinned_digest:
            errors.append(f"route bundle {route} section {path} digest {digest} != pinned {pinned_digest}")
        if body != pinned_bytes:
            errors.append(f"route bundle {route} section {path} bytes differ from the pinned file")
    return {
        "errors": errors,
        "bundle_fed_sha256": _sha256(b"".join(body for _path, _digest, body in sections)),
        "live_loaded_sha256": _sha256(b"".join(live)) if len(live) == len(sections) else None,
    }


def validate_skill_config_paths(skill_paths: list[str]) -> list[str]:
    errors: list[str] = []
    if CONTROL_NOODLE_DISCOVERY_ROOT not in skill_paths:
        errors.append(f".noodle.toml skills.paths must include {CONTROL_NOODLE_DISCOVERY_ROOT}")
    if RETIRED_PROVIDER_DISCOVERY_ROOT in skill_paths:
        errors.append(".noodle.toml skills.paths must not retain retired matt-engineering discovery")
    return errors
