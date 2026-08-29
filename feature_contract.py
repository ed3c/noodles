"""Mandatory repository acceptance plus optional specialized physical feature oracles."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from skill_contract import EXECUTE_VERIFICATION_P_CLASS_PHRASE, EXECUTE_VERIFICATION_ROUTE

EVIDENCE_PATH = ".noodle/feature-evidence.json"
EVIDENCE_FIELDS = ("feature_id", "head", "code_surface", "code_surface_sha256", "operation", "oracle", "observed")
ACCEPTANCE_EVIDENCE_PATH = ".noodle/acceptance-evidence.json"
ACCEPTANCE_EVIDENCE_FIELDS = ("schema_version", "head", "tree", "baseline", "specialized")
BASELINE_CONTRACT_ID = "repository-baseline"
BASELINE_TEST_OPERATION = ("tests/run.sh",)
BASELINE_VERIFY_OPERATION = ("./noodles", "verify", "--json")

# constraint: observed_check reads the declared operation's parsed stdout and raises error_cls on oracle rejection - the one pluggable seam per feature.
ObservedCheck = Callable[..., dict[str, Any]]


def _ok_errors_observed_check(
    root: Path, contract: "FeatureContract", observed_raw: Any, head: str, *, error_cls: type[Exception]
) -> dict[str, Any]:
    if not isinstance(observed_raw, dict) or observed_raw.get("ok") is not True or observed_raw.get("errors"):
        raise error_cls(f"feature {contract.feature_id} oracle rejected observed operation state")
    return {"returncode": 0, "ok": True, "errors": []}


@dataclass(frozen=True)
class FeatureContract:
    feature_id: str
    code_surface: str
    operation: tuple[str, ...]
    oracle_phrases: tuple[str, ...]
    oracle: str
    observed_check: ObservedCheck = _ok_errors_observed_check


VERIFICATION_SKILL_FEATURE = FeatureContract(
    feature_id="verification-skill-oracle",
    code_surface=".agents/skills/execute/SKILL.md",
    operation=("./noodles", "verify", "--json"),
    oracle_phrases=(EXECUTE_VERIFICATION_ROUTE, EXECUTE_VERIFICATION_P_CLASS_PHRASE),
    oracle="code-surface digest and required routing bytes plus exit-zero declared operation reporting ok with zero errors",
)


def _independent_tracked_files_count(root: Path, head: str, *, error_cls: type[Exception]) -> int:
    """Recompute the real regular-file count straight from the git object database at the exact
    candidate head, using a different plumbing command than repository_metrics' own `git ls-files
    --stage` (index/worktree state). A wrong number reported by the CLI cannot fool both paths at once."""
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-z", head], cwd=str(root), text=True, capture_output=True, check=False
    )
    if listing.returncode != 0:
        raise error_cls(f"cannot read back source-tree listing at {head}: {listing.stderr.strip()}")
    count = 0
    for record in listing.stdout.split("\0"):
        if not record:
            continue
        meta, _, _path = record.partition("\t")
        mode = meta.split(" ", 1)[0]
        if mode in {"100644", "100755"}:
            count += 1
    return count


def _metrics_observed_check(
    root: Path, contract: "FeatureContract", observed_raw: Any, head: str, *, error_cls: type[Exception]
) -> dict[str, Any]:
    if not isinstance(observed_raw, dict):
        raise error_cls(f"feature {contract.feature_id} operation produced malformed output: not a JSON object")
    reported = observed_raw.get("tracked_files")
    expected = _independent_tracked_files_count(root, head, error_cls=error_cls)
    if reported != expected:
        raise error_cls(
            f"feature {contract.feature_id} oracle rejected planted wrong metric: "
            f"stdout tracked_files={reported!r} source-tree(head {head})={expected!r}"
        )
    return {"returncode": 0, "ok": True, "errors": [], "oracle_metric": "tracked_files", "oracle_metric_value": expected}


METRICS_CLI_FEATURE = FeatureContract(
    feature_id="metrics-cli-oracle",
    code_surface="noodles.py",
    operation=("./noodles", "metrics", "--json"),
    oracle_phrases=(
        "def repository_metrics(root: Path) -> dict[str, Any]:",
        "def metrics_readback(root: Path, policy_root: Path | None = None) -> dict[str, Any]:",
    ),
    oracle=(
        "code-surface digest and required repository_metrics/metrics_readback routing bytes, exit-zero "
        "declared operation reading the real policy/fitness.json policy surface, plus an independently "
        "recomputed tracked_files count (git ls-tree at the exact candidate head) that must equal the "
        "reported metric"
    ),
    observed_check=_metrics_observed_check,
)
def _independent_workflow_count(root: Path, head: str, *, error_cls: type[Exception]) -> int:
    """Recompute the real .github/workflows/ regular-file count straight from the git object
    database at the exact candidate head, independent of verify_repository's own tracked-entries
    walk. A wrong workflow_count reported by the CLI cannot fool both paths at once."""
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-z", head], cwd=str(root), text=True, capture_output=True, check=False
    )
    if listing.returncode != 0:
        raise error_cls(f"cannot read back source-tree listing at {head}: {listing.stderr.strip()}")
    count = 0
    for record in listing.stdout.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        mode = meta.split(" ", 1)[0]
        if mode in {"100644", "100755"} and path.startswith(".github/workflows/"):
            count += 1
    return count


def _repo_infra_observed_check(
    root: Path, contract: "FeatureContract", observed_raw: Any, head: str, *, error_cls: type[Exception]
) -> dict[str, Any]:
    if not isinstance(observed_raw, dict):
        raise error_cls(f"feature {contract.feature_id} operation produced malformed output: not a JSON object")
    if observed_raw.get("ok") is not True or observed_raw.get("errors"):
        raise error_cls(f"feature {contract.feature_id} oracle rejected observed operation state")
    metrics = observed_raw.get("metrics")
    if not isinstance(metrics, dict):
        raise error_cls(f"feature {contract.feature_id} operation produced malformed output: missing metrics object")
    reported = metrics.get("workflow_count")
    expected = _independent_workflow_count(root, head, error_cls=error_cls)
    if reported != expected:
        raise error_cls(
            f"feature {contract.feature_id} oracle rejected planted wrong metric: "
            f"metrics.workflow_count={reported!r} source-tree(head {head})={expected!r}"
        )
    return {"returncode": 0, "ok": True, "errors": [], "oracle_metric": "workflow_count", "oracle_metric_value": expected}


REPO_INFRA_VERIFY_FEATURE = FeatureContract(
    feature_id="repo-infra-verify-oracle",
    code_surface="noodles.py",
    operation=("./noodles", "verify", "--json"),
    oracle_phrases=(
        "def verify_repository(root: Path, policy_root: Path | None = None) -> dict[str, Any]:",
        "workflow_boundary_errors, _workflow_boundary = github_protection.workflow_boundary_readback(root, sha256_file)",
    ),
    oracle=(
        "code-surface digest and required verify_repository/workflow-boundary routing bytes, exit-zero "
        "declared operation reporting ok with zero errors, plus an independently recomputed "
        ".github/workflows/ tracked-file count (git ls-tree at the exact candidate head) that must equal "
        "the reported metrics.workflow_count"
    ),
    observed_check=_repo_infra_observed_check,
)
ADMITTED_FEATURES = {
    VERIFICATION_SKILL_FEATURE.feature_id: VERIFICATION_SKILL_FEATURE,
    METRICS_CLI_FEATURE.feature_id: METRICS_CLI_FEATURE,
    REPO_INFRA_VERIFY_FEATURE.feature_id: REPO_INFRA_VERIFY_FEATURE,
}


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


def _git_read(root: Path, *args: str, error_cls: type[Exception]) -> str:
    result = subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise error_cls(f"acceptance git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _run_operation(root: Path, operation: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(list(operation), cwd=str(root), text=True, capture_output=True, check=False, env=env)


def _operation_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _require_clean_candidate(root: Path, *, error_cls: type[Exception]) -> None:
    status = _git_read(root, "status", "--porcelain=v1", "--untracked-files=all", error_cls=error_cls)
    if status:
        raise error_cls(f"baseline acceptance requires zero residue; candidate is dirty: {status}")


def verify_acceptance(
    root: Path, feature_id: str | None, *, error_cls: type[Exception]
) -> dict[str, Any]:
    """Run the mandatory repository baseline and then an optional specialized feature oracle."""
    root = Path(root).resolve()
    specialized_contract = resolve_feature(feature_id, error_cls=error_cls) if (feature_id or "").strip() else None
    _require_clean_candidate(root, error_cls=error_cls)
    head = _git_read(root, "rev-parse", "HEAD", error_cls=error_cls)
    tree = _git_read(root, "rev-parse", "HEAD^{tree}", error_cls=error_cls)

    tested = _run_operation(root, BASELINE_TEST_OPERATION)
    if tested.returncode != 0:
        raise error_cls(
            "baseline acceptance operation tests/run.sh failed: "
            + (tested.stderr.strip() or tested.stdout.strip())
        )
    verified = _run_operation(root, BASELINE_VERIFY_OPERATION)
    if verified.returncode != 0:
        raise error_cls(
            "baseline acceptance operation ./noodles verify --json failed: "
            + (verified.stderr.strip() or verified.stdout.strip())
        )
    try:
        verify_observed = json.loads(verified.stdout)
    except json.JSONDecodeError as exc:
        raise error_cls(f"baseline acceptance verify output is unreadable: {exc}") from exc
    if not isinstance(verify_observed, dict) or verify_observed.get("ok") is not True or verify_observed.get("errors"):
        raise error_cls("baseline acceptance verify rejected observed repository state")

    if _git_read(root, "rev-parse", "HEAD", error_cls=error_cls) != head:
        raise error_cls("baseline acceptance operation changed candidate HEAD")
    if _git_read(root, "rev-parse", "HEAD^{tree}", error_cls=error_cls) != tree:
        raise error_cls("baseline acceptance operation changed candidate tree")
    _require_clean_candidate(root, error_cls=error_cls)

    specialized = verify_feature(root, specialized_contract.feature_id, error_cls=error_cls) if specialized_contract else None
    if specialized is not None:
        if _git_read(root, "rev-parse", "HEAD", error_cls=error_cls) != head:
            raise error_cls("specialized acceptance operation changed candidate HEAD")
        if _git_read(root, "rev-parse", "HEAD^{tree}", error_cls=error_cls) != tree:
            raise error_cls("specialized acceptance operation changed candidate tree")
        _require_clean_candidate(root, error_cls=error_cls)
    return {
        "schema_version": 1,
        "head": head,
        "tree": tree,
        "baseline": {
            "contract_id": BASELINE_CONTRACT_ID,
            "operations": [list(BASELINE_TEST_OPERATION), list(BASELINE_VERIFY_OPERATION)],
            "observed": {
                "tests": {
                    "returncode": tested.returncode,
                    "stdout_sha256": _operation_digest(tested.stdout),
                    "stderr_sha256": _operation_digest(tested.stderr),
                },
                "verify": {"returncode": verified.returncode, "ok": True, "errors": []},
            },
        },
        "specialized": specialized,
    }


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
    exact_head = head.stdout.strip()
    operated = subprocess.run(
        list(contract.operation), cwd=str(root), text=True, capture_output=True, check=False
    )
    if operated.returncode != 0:
        raise error_cls(
            f"feature {contract.feature_id} operation {' '.join(contract.operation)} failed: "
            f"{operated.stderr.strip() or operated.stdout.strip()}"
        )
    try:
        observed_raw = json.loads(operated.stdout)
    except json.JSONDecodeError as exc:
        raise error_cls(f"feature {contract.feature_id} operation produced unreadable observed state: {exc}") from exc
    observed = contract.observed_check(root, contract, observed_raw, exact_head, error_cls=error_cls)
    return {
        "feature_id": contract.feature_id,
        "head": exact_head,
        "code_surface": contract.code_surface,
        "code_surface_sha256": digest,
        "operation": list(contract.operation),
        "oracle": contract.oracle,
        "observed": observed,
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
    return _admit_feature_payload(root, contract, evidence, head, error_cls=error_cls)


def _admit_feature_payload(
    root: Path,
    contract: FeatureContract,
    evidence: Any,
    head: str,
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise error_cls("specialized feature evidence must be a JSON object")
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


def admit_acceptance_evidence(
    root: Path, feature_id: str | None, head: str, *, error_cls: type[Exception]
) -> dict[str, Any]:
    """Admit the baseline for every Issue and the specialized oracle only when the Issue declares one."""
    root = Path(root).resolve()
    path = root / ACCEPTANCE_EVIDENCE_PATH
    if not path.is_file():
        suffix = f" --feature {feature_id.strip()}" if (feature_id or "").strip() else ""
        raise error_cls(
            "baseline acceptance verifier was skipped; run "
            f"'./noodles acceptance verify{suffix}' at the exact candidate head"
        )
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise error_cls(f"cannot read acceptance evidence {ACCEPTANCE_EVIDENCE_PATH}: {exc}") from exc
    if not isinstance(evidence, dict):
        raise error_cls(f"acceptance evidence {ACCEPTANCE_EVIDENCE_PATH} must be a JSON object")
    missing = [field for field in ACCEPTANCE_EVIDENCE_FIELDS if field not in evidence]
    if missing:
        raise error_cls(f"acceptance evidence is an agent self-report; missing physical fields: {', '.join(missing)}")
    if evidence["schema_version"] != 1:
        raise error_cls(f"unsupported acceptance evidence schema: {evidence['schema_version']!r}")
    if evidence["head"] != head:
        raise error_cls(f"stale acceptance evidence head {evidence['head']!r} != candidate head {head!r}")
    tree = _git_read(root, "rev-parse", "HEAD^{tree}", error_cls=error_cls)
    if evidence["tree"] != tree:
        raise error_cls(f"stale acceptance evidence tree {evidence['tree']!r} != candidate tree {tree!r}")
    _require_clean_candidate(root, error_cls=error_cls)

    baseline = evidence["baseline"]
    if not isinstance(baseline, dict):
        raise error_cls("baseline acceptance evidence is missing")
    expected_operations = [list(BASELINE_TEST_OPERATION), list(BASELINE_VERIFY_OPERATION)]
    if baseline.get("contract_id") != BASELINE_CONTRACT_ID or baseline.get("operations") != expected_operations:
        raise error_cls("baseline acceptance evidence names no supported repository contract and operations")
    observed = baseline.get("observed")
    if not isinstance(observed, dict):
        raise error_cls("baseline acceptance evidence contains no observed operations")
    tests_observed = observed.get("tests")
    verify_observed = observed.get("verify")
    if not isinstance(tests_observed, dict) or tests_observed.get("returncode") != 0:
        raise error_cls("baseline acceptance evidence records no passing tests/run.sh operation")
    if (
        not isinstance(verify_observed, dict)
        or verify_observed.get("returncode") != 0
        or verify_observed.get("ok") is not True
        or verify_observed.get("errors")
    ):
        raise error_cls("baseline acceptance evidence records no passing ./noodles verify operation")

    specialized_contract = resolve_feature(feature_id, error_cls=error_cls) if (feature_id or "").strip() else None
    specialized = evidence["specialized"]
    if specialized_contract is None:
        if specialized is not None:
            raise error_cls("acceptance evidence contains a specialized oracle not declared by the Issue")
    else:
        _admit_feature_payload(root, specialized_contract, specialized, head, error_cls=error_cls)
    return evidence
