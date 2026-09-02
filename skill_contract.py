from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# constraint: ed3c/noodles#290 - one owner for the persisted cycle receipt's path. The producer, the
# constraint: start-time gate, the summary reader, and the earlier-generation retirement must name
# constraint: the same file, or a retirement archives a receipt the gate is not reading.
SCHEDULE_CYCLE_RECEIPT_PATH = ".noodle/schedule-cycle.json"
CONCURRENCY_PROOF_PATH = "policy/concurrency-proof.json"
CONCURRENCY_PROOF_INVARIANTS = ("I1", "I2", "I3", "I4")
AGENT_DOCUMENT = "AGENTS.md"
GUARANTEE_CLASSES = ("P", "L", "R", "N")
# constraint: ed3c/noodles#84 - the publish entrypoint is argv, not a sentence: the exact tokens a
# constraint: cook runs, matched inside a fenced command block, so a copy parked in prose or a dead
# constraint: example cannot stand in for the runnable one.
SCHEDULE_PUBLISH_ENTRYPOINT = ("python3", "skill_contract.py", "publish", ".noodle/orders-next.candidate.json")
# constraint: ed3c/noodles#277 - the summary gate is argv for the same reason as the publish gate.
SCHEDULE_SUMMARY_ENTRYPOINT = ("python3", "skill_contract.py", "summary", ".noodle/schedule-summary.md")
# constraint: ed3c/noodles#277 - the dotted policy pointer the order-construction section must name,
# constraint: resolved against the candidate's own policy/fitness.json by `task_profiles`.
SCHEDULE_TASK_MODEL_POINTER = "required_codex_task_profiles.execute.model"
# constraint: ed3c/noodles#277 - the emitted order field that identifies the order-construction
# constraint: section, so the task-model rule is anchored to structure rather than to a heading name.
SCHEDULE_ORDER_ID_FIELD = "`order_id`"
POLICY_FITNESS_PATH = "policy/fitness.json"
OWNERSHIP_REGISTRY_PATH = "policy/ownership-keys.json"
# constraint: ed3c/noodles#325 - a shorter owned value is not an identity a tracked tree can be
# constraint: scanned for; it matches inside unrelated words and the registry would spend its rows
# constraint: exempting the noise away instead of naming writers.
MIN_OWNED_VALUE_LENGTH = 8
_FENCE_RE = re.compile(r"(?ms)^```[^\n]*\n(?P<body>.*?)^```[ \t]*$")
_HTML_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_SECTION_RE = re.compile(r"(?m)^##[ \t]+\S[^\n]*$")
_ROUTE_BULLET_RE = re.compile(r"(?m)^- `[^`]+` -> ")
_GUARANTEE_CELL_RE = re.compile(r"^([PLRN])(?![A-Za-z0-9])")
_DIAGNOSTIC_BULLET_RE = re.compile(r"^- signal: (?P<signal>.+?); action: (?P<action>.+?); why: (?P<why>.+)$")
# constraint: ed3c/noodles#277 - a receipt shaped only enough for `cycle_summary_lines` to emit one
# constraint: line per required key, so the documented template is compared against the emitter.
_SUMMARY_PROBE_RECEIPT = {
    "frontier": [],
    "winners": [],
    "max_useful_workers": 0,
    "claims": [{"subject": "owner/repo#N", "status": "claimed", "meaning": ""}],
}
EXECUTE_PREFLIGHT_PHRASE = "0. Run `./noodles preflight` before any source edit. Stop if it names a missing capability."
EXECUTE_ENTRYPOINT_PHRASE = "Every execute task enters `poteto-mode` before any matched playbook or leaf skill."
EXECUTE_BYPASS_PHRASE = "Do not bypass `poteto-mode` by entering a leaf skill directly."
EXECUTE_EVIDENCE_PHRASE = "Record the selected P-class route and required physical oracle in the evidence packet."
# constraint: ed3c/noodles#84 - the only surviving route sentence, and it survives as a
# constraint: `feature_contract.VERIFICATION_SKILL_FEATURE` oracle phrase, not as a verify gate.
# constraint: Route target resolution is owned by `runtime_contract.EXECUTE_ROUTE_TRAVERSALS`:
# constraint: `validate_execute_route_bundle_contract` parses each fixture bullet and demands the
# constraint: traversal leaf identity, and `_validate_execute_route_files` reads the pinned playbook
# constraint: bytes, so a missing route target fails through a resolver, never through a sentence.
EXECUTE_VERIFICATION_ROUTE = (
    "- `verification skill work` -> `create-verification-skill` or `maintain-verification-skill`; "
    "oracle `declared feature operation plus deterministic observed-state check`"
)
EXECUTE_VERIFICATION_P_CLASS_PHRASE = (
    "Output from `create-verification-skill` or `maintain-verification-skill` stays P-class until "
    "`./noodles feature verify <feature-id>` runs the declared operation and its oracle checks observed state."
)
# constraint: ed3c/noodles#130 owns these bytes as the stable line-start prefix; ed3c/noodles#84 adds
# constraint: only ownership structure around them, and everything after the prefix stays free text.
EXECUTE_UNSUPPORTED_PHRASE = "Unsupported routes fail closed:"
SCHEDULE_CLAIM_STATUS_MEANINGS = {
    "claimed": "this cycle created the subject's exact execute branch on the provider",
    "claimed_elsewhere": "the subject's exact execute branch already existed, so another executor holds the claim",
    "dependency_changed": "the subject stopped reading back schedulable before its branch was claimed",
    "frontier_changed": "the subject left the winner set between proposal and claim",
    "not_in_winners": "the subject was absent from the winner set this cycle computed; this is not another executor's claim",
    "boundary_conflict": "the subject's declared write boundary intersects an already-admitted active order's boundary, so admitting both concurrently could collide at landing",
    "claimed_boundary_widened": "the subject is already claimed and its write-boundary marker now intersects a concurrently claimed sibling's, so the I3 disjointness proved once at claim time no longer holds for the marker's current bytes; this is not a refused admission and not an ordinary blocker, and only releasing and reclaiming the subject clears it",
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


def _quotable(text: str) -> str:
    """The document minus what it merely parks in an HTML comment. Fences survive here because a
    fenced argv is a runnable artifact; the same argv inside a comment runs nothing."""
    return _HTML_COMMENT_RE.sub("", text)


def _document_body(text: str) -> str:
    """What a Markdown document asserts in its own voice: everything outside fenced examples and
    HTML comments. A phrase parked in either is quoted, not owned."""
    return _FENCE_RE.sub("", _quotable(text))


def _sections(body: str) -> list[str]:
    bounds = [match.start() for match in _SECTION_RE.finditer(body)]
    return [body[start:end] for start, end in zip([0, *bounds], [*bounds, len(body)])]


def _fenced_command_lines(content: str) -> list[str]:
    return [line.strip() for match in _FENCE_RE.finditer(content) for line in match["body"].splitlines() if line.strip()]


def _fenced_entrypoint_errors(
    root: Path, skill_name: str, sections: list[str], command: tuple[str, ...], label: str
) -> tuple[list[str], int | None]:
    """ed3c/noodles#84 shape, generalized by ed3c/noodles#277 to also return the owning section.

    The invariant: the gate a cook runs is argv, not a sentence. Exactly one fenced command in the
    whole document must be these exact tokens, and the script they name must resolve on disk, so a
    copy parked in prose or an HTML comment cannot stand in for the runnable one. The returned index
    is the section that owns the gate, which is what the co-located rules anchor to."""
    argv = list(command)
    matches = [
        index
        for index, section in enumerate(sections)
        for line in _fenced_command_lines(section)
        if line.split() == argv
    ]
    if len(matches) != 1:
        return [
            f"backlog adapter skill {skill_name!r} missing {label}: exactly one "
            f"fenced `{' '.join(argv)}` command is required, found {len(matches)}"
        ], None
    if not (root / argv[1]).is_file():
        return [
            f"backlog adapter skill {skill_name!r} {label} names unresolvable "
            f"entrypoint {argv[1]}"
        ], None
    return [], matches[0]


def _sole_owning_section(sections: list[str], marker: str) -> int | None:
    owners = [index for index, section in enumerate(sections) if marker in _document_body(section)]
    return owners[0] if len(owners) == 1 else None


def schedule_task_model_routing_errors(root: Path, skill_name: str, sections: list[str]) -> list[str]:
    """ed3c/noodles#277 - structural plus resolution control for task-model routing.

    The invariant this gate exists to enforce: the one `execute` stage the scheduler emits takes its
    model from the repository's single committed task-profile source, never from an Agent's own
    choice. Where it holds: the section that constructs the order - identified by the emitted
    `order_id` field it names, not by its heading text - must carry exactly one document-voice line
    naming the policy pointer, and that pointer must resolve in the candidate's own
    `policy/fitness.json` to a complete non-empty profile. Wording is free; the pointer line alone
    parked in an HTML comment, a fenced example, an unrelated section, or a second copy routes
    nothing, because the check is mutual co-location with the `order_id` line, not a fixed section
    identity.

    Non-claim: this cannot detect the pointer line and the `order_id` line relocated together - a
    coordinated move of both anchors into the same unrelated section still names one owner and
    passes. Defeating it that way also relocates the order-construction contract itself, which is a
    materially bigger, more visible edit than rewording one sentence."""
    pointer = f"`{SCHEDULE_TASK_MODEL_POINTER}`"
    naming = [index for index, section in enumerate(sections) for line in _document_body(section).splitlines() if pointer in line]
    if len(naming) != 1:
        return [
            f"backlog adapter skill {skill_name!r} missing task-model routing contract: exactly one "
            f"document line must name {pointer}, found {len(naming)}"
        ]
    owner = _sole_owning_section(sections, SCHEDULE_ORDER_ID_FIELD)
    if owner is None or naming[0] != owner:
        return [
            f"backlog adapter skill {skill_name!r} task-model routing contract is not owned by the "
            f"single section that constructs the order and names {SCHEDULE_ORDER_ID_FIELD}"
        ]
    try:
        task_profiles(root)
    except ValueError as exc:
        return [
            f"backlog adapter skill {skill_name!r} task-model routing contract names "
            f"{SCHEDULE_TASK_MODEL_POINTER}, which does not resolve: {exc}"
        ]
    return []


def schedule_summary_template_errors(skill_name: str, section: str) -> list[str]:
    """ed3c/noodles#277 - behavioral control for the receipt-verbatim summary.

    The invariant this gate exists to enforce: what the Skill tells the cook to write is exactly what
    `validate_cycle_summary` demands of it, so a summary built from this template cannot be rejected
    by the gate that reads it, and a renamed or re-derived field cannot pass as a quote. Where it
    holds: the section that owns the deterministic summary entrypoint, in exactly one fenced
    template. The required key labels are computed from `cycle_summary_lines`, never restated here,
    so relabeling one of the four keys it already reads reds the document. Placeholder wording is
    free.

    Non-claim: `_SUMMARY_PROBE_RECEIPT` is a fixture, not a spec, so it only tracks keys
    `cycle_summary_lines` already reads today. If the emitter starts reading a fifth receipt field,
    the fixture is stale and `cycle_summary_lines` raises `KeyError` on it - caught below and turned
    into a labeled red naming the missing fixture key, so a stale fixture reds the document instead
    of crashing `verify`."""
    try:
        required = [line.partition(":")[0] for line in cycle_summary_lines(_SUMMARY_PROBE_RECEIPT)]
    except KeyError as exc:
        return [
            f"backlog adapter skill {skill_name!r} summary probe fixture is stale: "
            f"cycle_summary_lines now reads {exc}, missing from _SUMMARY_PROBE_RECEIPT"
        ]
    templates = [
        lines
        for match in _FENCE_RE.finditer(section)
        if (lines := [line.strip() for line in match["body"].splitlines() if line.strip()])
        and len(lines) == len(required)
        and [line.partition(":")[0] for line in lines[:-1]] == required[:-1]
        and lines[-1].partition(":")[0]
    ]
    if len(templates) != 1:
        return [
            f"backlog adapter skill {skill_name!r} missing receipt-verbatim summary contract: exactly "
            f"one fenced template must quote the receipt keys {', '.join(required[:-1])} in order, "
            f"then one per-subject status line, found {len(templates)}"
        ]
    if " - " not in templates[0][-1].partition(":")[2]:
        return [
            f"backlog adapter skill {skill_name!r} receipt-verbatim summary contract drops the "
            "per-subject `<status> - <meaning>` shape `cycle_summary_lines` emits"
        ]
    return []


def schedule_starvation_routing_errors(skill_name: str, section: str) -> list[str]:
    """ed3c/noodles#277 - parsed-bullet control for starvation diagnostic routing.

    The invariant this gate exists to enforce: when the scheduler keeps proposing nothing, the
    response is a fixed ordered diagnostic read off the receipt, not a fresh causal story. Where it
    holds: the section that owns the cycle summary, in exactly one document-voice bullet parsed into
    non-empty signal, action and why fields whose action chains at least three `->` separated steps.
    Every field's wording is free; a bullet parked in a comment, a fenced example, or duplicated
    routes nothing.

    Non-claim: `section` here is whichever section the caller already decided owns the summary
    entrypoint (see `validate_backlog_scheduler`'s `summary_owner`); this function does not itself
    re-derive that ownership, so a bullet moved together with the summary entrypoint fence and its
    template into another section is invisible to this check - it inherits the entrypoint's
    co-location boundary rather than adding its own."""
    bullets = [
        match
        for line in _document_body(section).splitlines()
        if (match := _DIAGNOSTIC_BULLET_RE.match(line.strip()))
    ]
    if len(bullets) != 1:
        return [
            f"backlog adapter skill {skill_name!r} missing starvation diagnostic routing contract: "
            f"exactly one document bullet must route signal, action and why, found {len(bullets)}"
        ]
    if bullets[0]["action"].count("->") < 2:
        return [
            f"backlog adapter skill {skill_name!r} starvation diagnostic routing contract names no "
            "ordered diagnostic: its action must chain at least three `->` separated steps"
        ]
    return []


def _selected_values(payload: Any, steps: Sequence[str]) -> set[str]:
    """Walk `steps` through `payload`, `*` meaning every member, and keep the searchable scalars.

    A value shorter than `MIN_OWNED_VALUE_LENGTH` is not an identity a tree can be scanned for - it
    would match inside unrelated words - so it is dropped here rather than producing noise the
    registry would then have to exempt away."""
    values: list[Any] = [payload]
    for step in steps:
        nxt: list[Any] = []
        for value in values:
            if step == "*":
                if isinstance(value, dict):
                    nxt.extend(value.values())
                elif isinstance(value, list):
                    nxt.extend(value)
            elif isinstance(value, dict) and step in value:
                nxt.append(value[step])
        values = nxt
    return {value for value in values if isinstance(value, str) and len(value) >= MIN_OWNED_VALUE_LENGTH}


def validate_ownership_registry(root: Path, tracked_paths: set[str]) -> list[str]:
    """ed3c/noodles#325 - AF-03's one-writer law as a readback over a finite ownership-key registry.

    The system contract's own admission was that repository-wide duplicate-owner detection is not
    mechanically proven "until a finite canonical document set and ownership-key seam exist". This is
    that seam: `policy/ownership-keys.json` maps each registered durable-value class to the ONE path
    that owns it and to the read-only projections admitted to carry a copy. For every class, the
    detector recomputes the owner's current values from the owner document and scans the tracked tree:

    * an occurrence in an unregistered file is a refusal naming the class, the owner and the path;
    * a registered projection is derivation-checked, not string-compared alone - it must still carry
      a value the owner currently holds, so a projection left behind by a pin that moved reds naming
      itself, which is exactly the drift (provider pins copied into the README, since retired) the
      prose law existed to prevent and could not catch.

    Everything is read from the CANDIDATE tree - registry, owner documents, and the scanned files -
    for the reason ed3c/noodles#285, #306 and #315 each paid for: a trusted-side copy of a value the
    candidate legally owns deadlocks every candidate that moves it. Trusted code judges the rule
    here; the candidate carries its own values and its own reviewed registry row.

    Non-claims. Scope is the registry's enumerated classes, never arbitrary prose semantics - the
    contract's caution about prose stands and this seam is its boundary. Occurrence is substring
    containment, so a class whose values are short or word-like is not registrable, which is why
    disclosed counts and state-vocabulary sets are named absent rather than implied present. A
    projection carrying two of a class's values where only one went stale still resolves, so the
    check catches a projection that fell off the owner entirely, not every partial staleness. And
    nothing is auto-rewritten: the detector refuses, atoms and humans cure."""
    path = root / OWNERSHIP_REGISTRY_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{OWNERSHIP_REGISTRY_PATH} is unreadable: {exc}"]
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "classes"} or payload["schema_version"] != 1:
        return [f"{OWNERSHIP_REGISTRY_PATH} must contain exactly schema_version 1 and a classes array"]
    classes = payload["classes"]
    if not isinstance(classes, list) or not classes:
        return [f"{OWNERSHIP_REGISTRY_PATH} classes must be a non-empty array"]
    errors: list[str] = []
    sources: dict[str, str] = {}
    for relative in sorted(tracked_paths):
        try:
            sources[relative] = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    seen: set[str] = set()
    for index, entry in enumerate(classes, start=1):
        label = f"{OWNERSHIP_REGISTRY_PATH} class {index}"
        if not isinstance(entry, dict) or set(entry) != {"id", "owner", "select", "why", "projections"}:
            errors.append(f"{label} must carry exactly id, owner, select, why and projections")
            continue
        label = f"{OWNERSHIP_REGISTRY_PATH} class {entry['id']!r}"
        if entry["id"] in seen:
            errors.append(f"{label} is declared twice")
        seen.add(entry["id"])
        if not isinstance(entry["why"], str) or not entry["why"].strip():
            errors.append(f"{label} carries no written reason for existing")
        owner = str(entry["owner"])
        if owner not in tracked_paths:
            errors.append(f"{label} names owner path {owner!r}, which this tree does not track")
            continue
        select = entry["select"]
        if not isinstance(select, list) or not select or not all(isinstance(step, str) for step in select):
            errors.append(f"{label} select must be a non-empty array of string steps")
            continue
        try:
            owned = _selected_values(json.loads((root / owner).read_text(encoding="utf-8")), select)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{label} owner {owner} is unreadable: {exc}")
            continue
        if not owned:
            errors.append(f"{label} selects no searchable value out of {owner}; the class describes nothing")
            continue
        projections = entry["projections"]
        if not isinstance(projections, list):
            errors.append(f"{label} projections must be an array")
            continue
        admitted: set[str] = set()
        for position, projection in enumerate(projections, start=1):
            if not isinstance(projection, dict) or set(projection) != {"path", "why"}:
                errors.append(f"{label} projection {position} must carry exactly path and why")
                continue
            if not isinstance(projection["why"], str) or not projection["why"].strip():
                errors.append(f"{label} projection {projection['path']!r} carries no written reason")
            relative = str(projection["path"])
            if relative == owner:
                errors.append(f"{label} lists its own owner {owner} as a projection")
                continue
            if relative not in tracked_paths:
                errors.append(f"{label} admits projection {relative!r}, which this tree does not track")
                continue
            admitted.add(relative)
            carried = sorted(value for value in owned if value in sources.get(relative, ""))
            if not carried:
                errors.append(
                    f"{label} admits {relative} as a projection of {owner}, but it carries none of the "
                    f"owner's current values; the pin moved and the projection did not"
                )
        for relative, text in sources.items():
            if relative == owner or relative in admitted:
                continue
            for value in sorted(value for value in owned if value in text):
                errors.append(
                    f"{relative} writes {entry['id']} value {value!r}, which {owner} owns; "
                    f"derive it or admit {relative} as a read-only projection in {OWNERSHIP_REGISTRY_PATH}"
                )
    return errors


def validate_policy_key_consumption(root: Path, tracked_paths: set[str]) -> list[str]:
    """ed3c/noodles#277 - every key the candidate's own fitness policy declares is named by tracked source.

    The invariant this gate exists to enforce: policy is a contract between a file and its readers,
    and a key no reader names is not a weakened contract but a fictional one. Six orphan workflow
    phrase lists sat in `policy/fitness.json` looking like gates until ed3c/noodles#84 read the
    consumers. This reads the CANDIDATE's own policy, not the trusted one, which is what makes an
    added orphan red on the candidate that added it.

    Non-claim: this proves the key name appears literally in some tracked `.py` source. It does not
    claim the consumer reads the value, or reads it correctly - and the match is unscoped, so a
    retirement comment or docstring that names a key only to say it is unused, or a test asserting
    the key must NOT appear, both count as "consumed" the same as a real reader. This gate best
    catches a key nobody has typed anywhere yet; a key already known and described as dead - which
    this repo's own `# constraint:` retirement-comment convention produces at the moment a key is
    retired - can outlive its last real reader undetected until the key itself is deleted."""
    try:
        policy = json.loads((root / POLICY_FITNESS_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{POLICY_FITNESS_PATH} is unreadable: {exc}"]
    if not isinstance(policy, dict):
        return [f"{POLICY_FITNESS_PATH} must be a JSON object"]
    sources: list[str] = []
    for relative in sorted(path for path in tracked_paths if path.endswith(".py")):
        try:
            sources.append((root / relative).read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    named = "\n".join(sources)
    return [
        f"{POLICY_FITNESS_PATH} key {key!r} is consumed by zero tracked .py sources"
        for key in sorted(policy)
        if key not in named
    ]


def execute_route_refusal_errors(skill_name: str, content: str) -> list[str]:
    """ed3c/noodles#84 - bounded structural owner check for the unknown-route refusal.

    The invariant this gate exists to enforce: an execute route outside the admitted fixture set
    fails closed rather than proceeding best-effort. The rule must be exactly one document line, in
    the document's own voice, inside the same `##` section that carries the route fixture bullets;
    the historical sentence moved into a comment, a dead example, or an unrelated section no longer
    satisfies it. Everything after `EXECUTE_UNSUPPORTED_PHRASE` is free text, so the branded
    inventory owned by ed3c/noodles#253 can be replaced without touching this gate. The fixture
    format itself stays owned by `runtime_contract.validate_execute_route_bundle_contract`; the
    bullet pattern here only locates the owning section."""
    body = _document_body(content)
    refusals = [line for line in body.splitlines() if line.startswith(EXECUTE_UNSUPPORTED_PHRASE)]
    if len(refusals) != 1:
        return [
            f"project task skill {skill_name!r} missing unsupported route refusal: exactly one "
            f"document line must start with {EXECUTE_UNSUPPORTED_PHRASE!r}, found {len(refusals)}"
        ]
    if not any(_ROUTE_BULLET_RE.search(section) and refusals[0] in section for section in _sections(body)):
        return [
            f"project task skill {skill_name!r} unsupported route refusal is not owned by the "
            "section that declares the route fixtures"
        ]
    return []


def _guarantee_row_letter(row: list[str]) -> str | None:
    for cell in row[:-2]:
        match = _GUARANTEE_CELL_RE.match(cell)
        if match:
            return match[1]
    return None


def _markdown_tables(body: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for raw in body.splitlines():
        line = raw.strip()
        if len(line) > 1 and line.startswith("|") and line.endswith("|"):
            current.append([cell.strip() for cell in line[1:-1].split("|")])
            continue
        if current:
            tables.append(current)
            current = []
    return tables + ([current] if current else [])


def validate_agent_guarantee_classes(root: Path) -> list[str]:
    """ed3c/noodles#84 - structural replacement for the retired Agent-document phrase grep.

    The invariant that gate existed to enforce: the always-loaded Agent document declares the four
    guarantee classes and what each is allowed to prove. Exact-string membership proved only that
    the bytes appeared somewhere in the file, so the same sentences parked in a comment, a fenced
    example, or a duplicated second section satisfied it. This requires the owning structure
    instead: exactly one table defining each of P/L/R/N once, in the document's own voice, each with
    a non-empty meaning and allowed-authority cell. Wording is free.

    Non-claim: this proves document structure, never that an Agent read or obeyed the table."""
    try:
        body = _document_body((root / AGENT_DOCUMENT).read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"{AGENT_DOCUMENT} is unreadable: {exc}"]
    owning = [
        table
        for table in _markdown_tables(body)
        if {letter for row in table if (letter := _guarantee_row_letter(row))} == set(GUARANTEE_CLASSES)
    ]
    if len(owning) != 1:
        return [
            f"{AGENT_DOCUMENT} must own exactly one guarantee-class table defining "
            f"{'/'.join(GUARANTEE_CLASSES)}; found {len(owning)}"
        ]
    errors: list[str] = []
    seen: list[str] = []
    for row in owning[0]:
        letter = _guarantee_row_letter(row)
        if letter is None:
            continue
        seen.append(letter)
        if not all(cell for cell in row[1:]):
            errors.append(f"{AGENT_DOCUMENT} guarantee class {letter} declares an empty meaning or allowed authority")
    duplicated = sorted({letter for letter in seen if seen.count(letter) > 1})
    if duplicated:
        errors.append(f"{AGENT_DOCUMENT} defines guarantee class {', '.join(duplicated)} more than once")
    return errors


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
    # constraint: ed3c/noodles#277 - the last four schedule sentence locks are gone. Each remaining
    # constraint: contract is decided by structure the document really owns: two fenced argvs, one
    # constraint: policy pointer resolved against the candidate's own policy, one fenced template
    # constraint: compared against `cycle_summary_lines`, and one parsed signal/action/why bullet.
    sections = _sections(_quotable(content))
    errors, _publish_owner = _fenced_entrypoint_errors(
        root, skill_name, sections, SCHEDULE_PUBLISH_ENTRYPOINT, "deterministic publish gate"
    )
    summary_errors, summary_owner = _fenced_entrypoint_errors(
        root, skill_name, sections, SCHEDULE_SUMMARY_ENTRYPOINT, "deterministic summary gate"
    )
    errors.extend(summary_errors)
    errors.extend(schedule_task_model_routing_errors(root, skill_name, sections))
    if summary_owner is None:
        return errors
    errors.extend(schedule_summary_template_errors(skill_name, sections[summary_owner]))
    errors.extend(schedule_starvation_routing_errors(skill_name, sections[summary_owner]))
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
        (EXECUTE_VERIFICATION_P_CLASS_PHRASE, "verification-skill P-class refusal"),
    )
    errors = execute_route_refusal_errors(skill_name, content)
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


def tracked_test_exists(root: Path, identifier: str) -> bool:
    # constraint: ed3c/noodles#100 - resolve `tests.module.Class.test_name` against the tracked
    # constraint: source with ast, not by importing it: verify must stay side-effect free, and the
    # constraint: question is only whether the named control exists in the suite. Resolution walks
    # constraint: same-file base classes, not only the named class's own body: this repo already
    # constraint: shares fixtures by inheritance (tests/test_supervised_ceremony.py's
    # constraint: ControlCheckoutFixture), and a planted-negative moved into a shared base must not
    # constraint: read as absent just because it is not redeclared on the named subclass.
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
    classes = {node.name: node for node in module.body if isinstance(node, ast.ClassDef)}

    def has_method(class_node: ast.ClassDef, method_name: str, seen: set[str]) -> bool:
        if class_node.name in seen:
            return False
        seen.add(class_node.name)
        if any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name
            for item in class_node.body
        ):
            return True
        return any(
            isinstance(base, ast.Name) and base.id in classes and has_method(classes[base.id], method_name, seen)
            for base in class_node.bases
        )

    target = classes.get(parts[2])
    return target is not None and has_method(target, parts[3], set())


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


# constraint: ed3c/noodles#290 - statuses this repository published and has since renamed. The reason
# constraint: is what makes a retirement falsifiable: only a status named here dates a receipt, so an
# constraint: undefined status absent from this table stays a defect of a current-generation receipt
# constraint: and can never be laundered into "written by an earlier generation".
RETIRED_SCHEDULE_CLAIM_STATUSES = {
    "not_frontier": (
        "pre-ed3c/noodles#191 name for the winner-set miss now published as 'not_in_winners'"
    ),
}


def earlier_generation_cycle_receipt(receipt: Any, *, schema_version: int) -> str | None:
    """ed3c/noodles#290 - name what dates this receipt to an earlier generation, or None.

    Two arms, both decided against the current definitions rather than against the receipt's own
    shape: a `schema_version` below the current one, or a claim status this repository retired by
    name. Deliberately narrow - a malformed `winners`, a missing `meaning`, or any other invalid
    shape is also what a broken current-generation receipt looks like, and widening to those would
    make retirement a laundry for exactly the receipts that must keep failing closed.

    Non-claim: naming a receipt earlier-generation says the vocabulary it used is retired. It says
    nothing about whether the generation that wrote it was correct."""
    if not isinstance(receipt, dict):
        return None
    declared = receipt.get("schema_version")
    if isinstance(declared, int) and not isinstance(declared, bool) and declared < schema_version:
        return f"schema_version {declared} predates the current {schema_version}"
    raw_claims = receipt.get("claims")
    claims = raw_claims if isinstance(raw_claims, list) else []
    dated = sorted({
        str(claim.get("status"))
        for claim in claims
        if isinstance(claim, dict) and str(claim.get("status")) in RETIRED_SCHEDULE_CLAIM_STATUSES
    })
    if not dated:
        return None
    return "; ".join(
        f"claim status {status!r} is retired vocabulary: {RETIRED_SCHEDULE_CLAIM_STATUSES[status]}"
        for status in dated
    )


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
    receipt_path = root / SCHEDULE_CYCLE_RECEIPT_PATH
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
