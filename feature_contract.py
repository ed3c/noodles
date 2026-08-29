"""One admitted feature contract: an exact feature ID bound to a real code surface, a product entry
operation that must actually run, a deterministic oracle over observed state, and an evidence adapter."""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skill_contract import EXECUTE_VERIFICATION_P_CLASS_PHRASE, EXECUTE_VERIFICATION_ROUTE

EVIDENCE_PATH = ".noodle/feature-evidence.json"
EVIDENCE_FIELDS = ("feature_id", "head", "code_surface", "code_surface_sha256", "operation", "oracle", "observed")


@dataclass(frozen=True)
class FeatureContract:
    feature_id: str
    code_surface: str
    operation: tuple[str, ...]
    oracle_phrases: tuple[str, ...]
    oracle: str


VERIFICATION_SKILL_FEATURE = FeatureContract(
    feature_id="verification-skill-oracle",
    code_surface=".agents/skills/execute/SKILL.md",
    operation=("./noodles", "verify", "--json"),
    oracle_phrases=(EXECUTE_VERIFICATION_ROUTE, EXECUTE_VERIFICATION_P_CLASS_PHRASE),
    oracle="code-surface digest and required routing bytes plus exit-zero declared operation reporting ok with zero errors",
)
ADMITTED_FEATURES = {VERIFICATION_SKILL_FEATURE.feature_id: VERIFICATION_SKILL_FEATURE}


def resolve_feature(feature_id: str | None, *, error_cls: type[Exception]) -> FeatureContract:
    key = (feature_id or "").strip()
    if not key:
        raise error_cls("missing noodles-feature id")
    contract = ADMITTED_FEATURES.get(key)
    if contract is None:
        raise error_cls(f"unadmitted noodles-feature id: {key!r}")
    if not contract.code_surface or not contract.operation or not contract.oracle_phrases:
        raise error_cls(f"feature {key!r} declares no code surface, product operation, and oracle")
    return contract


def _oracle_readback(root: Path, contract: FeatureContract, *, error_cls: type[Exception]) -> str:
    surface = root / contract.code_surface
    if not surface.is_file():
        raise error_cls(f"feature {contract.feature_id} code surface missing: {contract.code_surface}")
    text = surface.read_text(encoding="utf-8")
    for phrase in contract.oracle_phrases:
        if phrase not in text:
            raise error_cls(
                f"feature {contract.feature_id} oracle rejected observed {contract.code_surface}: missing {phrase!r}"
            )
    return hashlib.sha256(surface.read_bytes()).hexdigest()


def verify_feature(root: Path, feature_id: str | None, *, error_cls: type[Exception]) -> dict[str, Any]:
    """Run the declared operation for real and let the oracle check observed state, not a self-report."""
    root = Path(root).resolve()
    contract = resolve_feature(feature_id, error_cls=error_cls)
    digest = _oracle_readback(root, contract, error_cls=error_cls)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(root), text=True, capture_output=True, check=False
    )
    if head.returncode != 0:
        raise error_cls(f"feature {contract.feature_id} cannot read back exact head: {head.stderr.strip()}")
    operated = subprocess.run(
        list(contract.operation), cwd=str(root), text=True, capture_output=True, check=False
    )
    if operated.returncode != 0:
        raise error_cls(
            f"feature {contract.feature_id} operation {' '.join(contract.operation)} failed: "
            f"{operated.stderr.strip() or operated.stdout.strip()}"
        )
    try:
        observed = json.loads(operated.stdout)
    except json.JSONDecodeError as exc:
        raise error_cls(f"feature {contract.feature_id} operation produced unreadable observed state: {exc}") from exc
    if not isinstance(observed, dict) or observed.get("ok") is not True or observed.get("errors"):
        raise error_cls(f"feature {contract.feature_id} oracle rejected observed operation state")
    return {
        "feature_id": contract.feature_id,
        "head": head.stdout.strip(),
        "code_surface": contract.code_surface,
        "code_surface_sha256": digest,
        "operation": list(contract.operation),
        "oracle": contract.oracle,
        "observed": {"returncode": operated.returncode, "ok": True, "errors": []},
    }


def admit_feature_evidence(root: Path, feature_id: str | None, head: str, *, error_cls: type[Exception]) -> dict[str, Any]:
    """Evidence adapter: admit only a packet the verifier produced against this exact head and artifact."""
    root = Path(root).resolve()
    contract = resolve_feature(feature_id, error_cls=error_cls)
    path = root / EVIDENCE_PATH
    if not path.is_file():
        raise error_cls(
            f"feature {contract.feature_id} verifier was skipped; run "
            f"'./noodles feature verify {contract.feature_id}' at the exact candidate head"
        )
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise error_cls(f"cannot read feature evidence {EVIDENCE_PATH}: {exc}") from exc
    if not isinstance(evidence, dict):
        raise error_cls(f"feature evidence {EVIDENCE_PATH} must be a JSON object")
    missing = [field for field in EVIDENCE_FIELDS if field not in evidence]
    if missing:
        raise error_cls(
            f"feature evidence is an agent self-report; missing physical fields: {', '.join(missing)}"
        )
    if evidence["feature_id"] != contract.feature_id:
        raise error_cls(f"feature evidence declares {evidence['feature_id']!r}, not {contract.feature_id!r}")
    if evidence["operation"] != list(contract.operation):
        raise error_cls(f"feature evidence records no declared operation for {contract.feature_id}")
    if evidence["head"] != head:
        raise error_cls(f"stale feature evidence head {evidence['head']!r} != candidate head {head!r}")
    digest = _oracle_readback(root, contract, error_cls=error_cls)
    if evidence["code_surface"] != contract.code_surface or evidence["code_surface_sha256"] != digest:
        raise error_cls(
            f"feature evidence never observed the real artifact {contract.code_surface} at {digest}"
        )
    observed = evidence["observed"]
    if not isinstance(observed, dict) or observed.get("returncode") != 0 or observed.get("ok") is not True:
        raise error_cls(f"feature evidence does not record a passing declared operation for {contract.feature_id}")
    return evidence
