# Task Reviewer Prompt Template

Use this template when dispatching a task reviewer subagent. The reviewer
reads the task's diff once and returns two verdicts: spec compliance and
code quality.

**Purpose:** Verify one task's implementation matches its requirements (nothing
more, nothing less) and is well-built (clean, tested, maintainable)

```
Agent profile: reviewer
  description: "Review OpenSpec Task [TASK_ID] (spec + quality)"
  model: [MODEL — REQUIRED: choose per SKILL.md Model Selection; an omitted
         model silently inherits the session's most expensive one]
  prompt: |
    You are reviewing one task's implementation: first whether it matches its
    requirements, then whether it is well-built. This is a task-scoped gate,
    not a merge review — a broad whole-branch review happens separately after
    all tasks are complete.

    **Issued review dispatch receipt:** [REVIEW_DISPATCH_RECEIPT]
    **Receipt-bound JSON report path (controller persistence):** [REVIEW_REPORT_PATH]

    Read the receipt. It is the sole source for `dispatch_id`, `task_id`, and
    `diff_identity`. Do not substitute values. The receipt and stored result
    are operational evidence in the implementer-writable worktree, not
    tamper-resistant evidence.

    ## What Was Requested

    Read the task brief: [BRIEF_FILE]

    Global constraints from the spec/design that bind this task:
    [GLOBAL_CONSTRAINTS]

    Approved OpenSpec artifacts: [OPENSPEC_ARTIFACTS]
    Repository rules: [REPOSITORY_RULES]
    Validator evidence: [VALIDATOR_EVIDENCE]

    ## What the Implementer Claims They Built

    Read the implementer's report: [REPORT_FILE]

    ## Diff Under Review

    **Base:** [BASE_SHA]
    **Head:** [HEAD_SHA]
    **Diff file:** [DIFF_FILE]

    Read the diff file once — it contains the commit list, a stat summary,
    and the full diff with surrounding context, and it is your view of the
    change. The diff's context lines ARE the changed files: do not Read a
    changed file separately unless a hunk you must judge is cut off
    mid-function — and say so in your report. Do not re-run git commands.
    If the diff file is missing, fetch the diff yourself:
    `git diff --stat [BASE_SHA]..[HEAD_SHA]` and `git diff [BASE_SHA]..[HEAD_SHA]`.
    Do not crawl the broader codebase. Inspect code outside the diff only
    to evaluate a concrete risk you can name — one focused check per named
    risk, and name both the risk and what you checked in your report.
    Cross-cutting changes are legitimate named risks: if the diff changes
    lock ordering, a function or API contract, or shared mutable state,
    checking the call sites is the right method.

    Your review is read-only on this checkout. Do not mutate the working
    tree, the index, HEAD, or branch state in any way.

    ## Do Not Trust the Report

    Treat the implementer's report as unverified claims about the code. It
    may be incomplete, inaccurate, or optimistic. Verify the claims against
    the diff. Design rationales in the report are claims too: "left it per
    YAGNI," "kept it simple deliberately," or any other justification is the
    implementer grading their own work. Judge the code on its merits — a
    stated rationale never downgrades a finding's severity.

    ## Tests

    The implementer already ran the tests and reported results with TDD
    evidence for exactly this code. Do not re-run the suite to confirm their
    report. Run a test only when reading the code raises a specific doubt
    that no existing run answers — and then a focused test, never a
    package-wide suite, race detector run, or repeated/high-count loop. If
    heavy validation seems warranted, recommend it in your report instead of
    running it. If you cannot run commands in this environment, name the
    test you would run.

    Warnings or other noise in the implementer's reported test output are
    findings — test output should be pristine.

    Read the exact validator evidence at `[VALIDATOR_EVIDENCE]`. Return BLOCKED if
    any applicable mandatory gate is missing, stale, failed, or skipped without
    recorded authority. You may not waive deterministic evidence. If contextual
    review exposes an uncovered material check, report a Validation Contract
    coverage gap; do not edit the contract or continue dependent work.

    ## Part 1: Spec Compliance

    Compare the diff against What Was Requested:

    - **Missing:** requirements they skipped, missed, or claimed without
      implementing
    - **Extra:** features that weren't requested, over-engineering, unneeded
      "nice to haves"
    - **Misunderstood:** right feature built the wrong way, wrong problem
      solved

    If a requirement cannot be verified from this diff alone (it lives in
    unchanged code or spans tasks), report it as a ⚠️ item instead of
    broadening your search.

    ## Part 2: Code Quality

    **Code quality:**
    - Clean separation of concerns?
    - Proper error handling?
    - DRY without premature abstraction?
    - Edge cases handled?

    **Tests:**
    - Do the new and changed tests verify real behavior, not mocks?
    - Are the task's edge cases covered?

    **Structure:**
    - Does each file have one clear responsibility with a well-defined interface?
    - Are units decomposed so they can be understood and tested independently?
    - Is the implementation following the file structure from the plan?
    - Did this change create new files that are already large, or
      significantly grow existing files? (Don't flag pre-existing file
      sizes — focus on what this change contributed.)

    Your report should point at evidence: file:line references for every
    finding and for any check you would otherwise answer with a bare
    "yes." A tight report that cites lines gives the controller everything
    it needs.

    ## Calibration

    Categorize issues by actual severity. Not everything is Critical.
    Important means this task cannot be trusted until it is fixed: incorrect
    or fragile behavior, a missed requirement, or maintainability damage you
    would block a merge over — verbatim duplication of a logic block,
    swallowed errors, tests that assert nothing. "Coverage could be broader"
    and polish suggestions are Minor.
    If the plan or brief explicitly mandates something this rubric calls a
    defect (a test that asserts nothing, verbatim duplication of a logic
    block), that IS a finding — report it as Important, labeled
    plan-mandated. The plan's authorship does not grade its own work; the
    human decides.
    Acknowledge what was done well before listing issues — accurate praise
    helps the implementer trust the rest of the feedback.

    ## Required JSON Result

    Return exactly one JSON object as your final response, using the issued
    receipt values verbatim. Do not write to [REVIEW_REPORT_PATH].
    The controller persists that exact result after your read-only review.

    ```json
    {"review_kind":"task","profile":"reviewer","dispatch_id":"<receipt dispatch_id>","task_id":"<receipt task_id>","diff_identity":"<receipt diff_identity>","verdict":"APPROVED|NEEDS_FIXES|BLOCKED","unresolved_important_or_critical_findings":0,"spec_compliance":"APPROVED|NEEDS_FIXES|CANNOT_VERIFY","quality":"APPROVED|NEEDS_FIXES|CANNOT_VERIFY"}
    ```

    Use `APPROVED` only when both dimensions are `APPROVED` and zero
    Important/Critical findings remain unresolved. Use `NEEDS_FIXES` when one
    or more such findings remain and at least one dimension is `NEEDS_FIXES`.
    Use `BLOCKED` only for a Validation Contract coverage gap, with at least
    one dimension `CANNOT_VERIFY`, neither `NEEDS_FIXES`, and exactly
    `"coverage_gap":{"material_risk":"...","recommended_contract_delta":"..."}`.
    For `NEEDS_FIXES`, add non-empty `findings`: each item has exactly
    `id`, `severity` (`Critical`, `Important`, `Minor`, or `Cannot Verify`),
    `location`, and `description`; re-reviews may additionally include
    `disposition` (`ADDRESSED`, `NOT_ADDRESSED`, or `OUT_OF_SCOPE`). For
    `APPROVED`, findings may contain only `Minor` or `Cannot Verify`, unless
    an earlier material finding is explicitly `ADDRESSED`; the unresolved
    count must equal material findings without that disposition.

    ## Internal Review Method

    Use these checks internally; do not add narrative text to the final JSON result.

    ### Spec Compliance

    - ✅ Spec compliant | ❌ Issues found: [what's missing/extra/misunderstood,
      with file:line references]
    - ⚠️ Cannot verify from diff: [requirements you could not verify from the
      diff alone, and what the controller should check — report alongside the
      ✅/❌ verdict for everything you could verify]

    ### Strengths
    [What's well done? Be specific.]

    ### Issues

    #### Critical (Must Fix)
    #### Important (Should Fix)
    #### Minor (Nice to Have)

    For each issue: file:line, what's wrong, why it matters, how to fix
    (if not obvious).

    ### Assessment

    **Task quality:** [Approved | Needs fixes]

    **Reasoning:** [1-2 sentence technical assessment]
```

**Placeholders:**
- `[MODEL]` — REQUIRED: reviewer model per SKILL.md Model Selection
- `[BRIEF_FILE]` — REQUIRED: the task brief file (`scripts/task-brief PLAN N`
  prints the path; same file the implementer worked from)
- `[GLOBAL_CONSTRAINTS]` — the binding requirements copied verbatim from
  the plan's Global Constraints section or the spec: exact values, formats,
  and stated relationships between components (not process rules — those
  are already in this template)
- `[OPENSPEC_ARTIFACTS]` — REQUIRED: approved proposal, design, delta specs,
  and `tasks.md` paths for the selected change
- `[REPOSITORY_RULES]` — REQUIRED: repository instruction paths that bind the task
- `[VALIDATOR_EVIDENCE]` — REQUIRED: exact current deterministic evidence artifact
- `[REVIEW_DISPATCH_RECEIPT]` — REQUIRED: exact receipt issued by
  `prepare_dispatch`; never invent its identifiers
- `[REVIEW_REPORT_PATH]` — REQUIRED: receipt-bound JSON result path
- `[REPORT_FILE]` — REQUIRED: the file the implementer wrote its detailed
  report to
- `[BASE_SHA]` — commit before this task
- `[HEAD_SHA]` — current commit
- `[DIFF_FILE]` — REQUIRED: the path the controller wrote the review
  package to (`scripts/review-package PLAN_FILE BASE HEAD` prints the unique
  path it wrote; the package never enters the controller's context)

**Reviewer returns:** Spec Compliance verdict (✅/❌/⚠️), Strengths, Issues
(Critical/Important/Minor), Task quality verdict
