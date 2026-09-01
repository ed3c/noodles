---
name: Repository-mutating atom
about: One repository-mutating atom carrying the exact noodles Issue contract shape
title: ''
labels: ''
assignees: ''
---

<!-- noodles-role: repository-mutating-atom -->
<!-- noodles-target: ed3c/noodles -->
<!-- noodles-state: ready -->
<!-- noodles-depends-on: none -->
<!-- noodles-requirement: SYSTEM.PURPOSE.001 -->

<!-- The subject marker is the one field only the provider knows, so `noodles adapter sync` derives
     it from the created issue number at intake. Every other marker is authored here: set the
     dependency marker to comma-separated owner/repo#N subjects when this atom has predecessors, and
     rebind the requirement marker to the `### ID` heading in `contracts/system-v1.md` this atom
     actually serves. Repeat the requirement marker to bind more than one. A marker only counts when
     it is here, above the first section: one printed inside a section is documentation. -->

## Physical trigger

<!-- The physical failure or measurement that made this atom necessary. `## Why ...` is also admitted. -->

## Goal

<!-- One sentence: the smallest independently useful atom this Issue admits. -->

## Claim

<!-- What is true after this lands, and nothing wider. -->

## Physical acceptance

- Exact-subject positive and planted-negative controls pass.
- Direct source/provider readback proves only the stated claim.
- `./noodles verify` passes with zero tracked residue.

## Non-case

none

## Non-claims

- No adjacent capability is admitted by prose or inference.
