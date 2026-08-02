## Context

This pilot uses the candidate schema explicitly while the repository default
remains `spec-driven`.

## Goals / Non-Goals

Prove the native-apply to implementation-loop handoff for one non-product
task. Do not add a wrapper, change profiles, or change product behavior.

## Decisions

Native apply selects the pilot task; implementation-loop validation and an
independent reviewer provide the approval evidence before its checkbox changes.

## Risks / Trade-offs

Manual orchestration may reveal an integration gap. If it does, stop before
making the candidate schema the default.

## Migration Plan

Retain pilot evidence locally; do not change the default until the user reviews
the outcome.
