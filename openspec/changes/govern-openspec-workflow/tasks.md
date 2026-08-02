## 1. Governed schema contract

- [ ] 1.1 RED: add a focused acceptance test under `tests/` that creates a
  temporary change with `--schema governed-spec-driven` and expects the
  `validation` and `review` artifacts, their dependency order, and the apply
  prerequisites and `contextFiles`; run the focused test.
- [ ] 1.2 GREEN/REFACTOR: extend
  `openspec/schemas/governed-spec-driven/schema.yaml` and its templates with
  `validation` and `review`, require both for apply, and describe their boundary
  from canonical execution evidence; rerun the focused test and
  `pnpm exec openspec schema validate governed-spec-driven`.
- [ ] 1.3 Configure `openspec/config.yaml` with context and artifact rules for
  `validation` and `review`, plus governed apply guidance that preserves native
  task selection and requires the implementation-loop handoff; rerun the
  focused schema acceptance test without making the governed schema default.

## 2. Native apply to implementation-loop handoff

- [ ] 2.1 Update `AGENTS.md` and governed-schema apply instructions so native
  `$openspec-apply-change` selects the task and `implementation-loop` then owns
  execution, validation, review, fix rounds, and the `APPROVED` checkbox gate;
  show the exact `AGENTS.md` preview and obtain its required Human Gate before
  editing it.
- [ ] 2.2 Extend `tests/test_implementation_loop_skill.py` and related
  execution-state coverage for the supported `selected → implementing →
  validated → review → approved` path, `NEEDS_FIXES` loop, fresh validation
  evidence, and the rule that only `APPROVED` permits a task checkbox; run the
  focused tests and
  `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`.

## 3. Explicit-schema pilot

- [ ] 3.1 Create a narrow non-product pilot change with
  `pnpm exec openspec new change --schema governed-spec-driven`, create every
  required artifact, and verify `openspec instructions apply` supplies the
  governed context, `validation.md`, `review.md`, and their prerequisites.
- [ ] 3.2 Execute the pilot's one bounded task through native apply followed by
  `implementation-loop`, canonical validation, and independent review; retain
  the resulting evidence and mark its checkbox only after `APPROVED`.
- [ ] 3.3 Review the pilot outcome with the user. If it demonstrates the
  no-wrapper handoff, change `openspec/config.yaml` to make
  `governed-spec-driven` the default; otherwise stop and capture the concrete
  integration gap before considering a wrapper.

## 4. Final verification and handoff

- [ ] 4.1 Run `python3 -m unittest discover -s tests -v`,
  `pnpm exec openspec schema validate governed-spec-driven`,
  `pnpm exec openspec validate --all --strict --no-interactive`, and
  `git diff --check`; record the pilot evidence, manual limitations, and
  wrapper decision before independent whole-change review.
- [ ] 4.2 Run the authorized independent whole-change review through
  `implementation-loop`, resolve any `NEEDS_FIXES`, and retain an `APPROVED`
  report before recommending archive; verify generated native OpenSpec skills
  remain unchanged and no wrapper skill was added.
