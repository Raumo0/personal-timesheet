# Validation Contract Adaptation

`docs/agentic-workflow/validation-contract.md` is the sole deterministic gate
registry. Local orchestration and CI invoke
`tools/agentic_workflow/validate.py`; CI does not duplicate individual gates.

Mandatory missing, stale, failed, or unauthorized-skipped evidence blocks
approval. Changing a gate requires an exact preview and Human Gate. Focused
coverage lives in `tests/test_agentic_validator.py`.
