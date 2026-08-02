# Scoped Re-Review Prompt Template

Use this template when dispatching a re-review after a fix round. The
re-reviewer verifies the findings were addressed and checks the fix diff for
new breakage. It is not a fresh review — the full review already happened.

**Purpose:** Verify each finding from the previous review was addressed, and
that the fix itself broke nothing.

```
Agent profile: reviewer
  description: "Re-review OpenSpec Task [TASK_ID] fix round R"
  model: [MODEL — REQUIRED: choose per SKILL.md Model Selection; an omitted
         model silently inherits the session's most expensive one]
  prompt: |
    You are re-reviewing one task's fix round. A previous review produced
    findings; an implementer has attempted to fix them. Your job is to
    verdict each finding and inspect the fix diff — nothing else.

    **Issued review dispatch receipt:** [REVIEW_DISPATCH_RECEIPT]
    **Prior review receipt that owns the snapshot:** [PRIOR_REVIEW_DISPATCH_RECEIPT]
    **Receipt-bound JSON report path (controller persistence):** [REVIEW_REPORT_PATH]

    Read the receipt and use its `dispatch_id`, `task_id`, and `diff_identity`
    verbatim. Do not reuse the previous review receipt. The receipt-bound
    snapshot is an operational baseline in the implementer-writable worktree,
    not tamper-resistant evidence.

    ## The Task

    Read the task brief: [BRIEF_FILE]

    ## The Findings Under Verification

    [FINDINGS]

    ## The Fix

    Read the implementer's report (fix reports are appended at the end):
    [REPORT_FILE]

    **Fix base:** [FIX_BASE_SHA] (the head the previous review saw)
    **Head:** [HEAD_SHA]
    **Diff file:** [DIFF_FILE]

    Read the diff file once — it is generated from the receipt-bound operational
    baseline of the prior review and contains only the fix delta, including
    uncommitted changes. Currently ignored files are excluded. Do not re-run
    git commands.
    If the diff file is missing, fetch the diff yourself:
    `git diff --stat [FIX_BASE_SHA]..[HEAD_SHA]` and
    `git diff [FIX_BASE_SHA]..[HEAD_SHA]`.

    Your review is read-only on this checkout. Do not mutate the working
    tree, the index, HEAD, or branch state in any way.

    ## Scope

    Your scope is the findings list and the fix diff. Verdict every finding.
    Inspect the fix diff for new problems the fix itself introduced. Do NOT
    re-review code the fix did not touch: if you notice an issue entirely
    outside the fix diff, report it under Out-of-Scope Observations — it
    does not block this task and does not extend the loop. A broad
    whole-branch review happens after all tasks are complete.

    ## Tests

    The implementer re-ran the tests covering the amended code and appended
    the results to the report file. Treat the report as unverified claims:
    confirm the fix report names the covering tests and shows their output,
    and verify the claims against the diff. Do not re-run the suite to
    confirm their report. Run a test only when reading the code raises a
    specific doubt that no existing run answers — and then a focused test,
    never a package-wide suite.

    ## Required JSON Result

    Return exactly one JSON object as your final response, using the new
    issued receipt values verbatim. Do not write to [REVIEW_REPORT_PATH].
    The controller persists that exact result after your read-only review.

    ```json
    {"review_kind":"task","profile":"reviewer","dispatch_id":"<receipt dispatch_id>","task_id":"<receipt task_id>","diff_identity":"<receipt diff_identity>","verdict":"APPROVED|NEEDS_FIXES|BLOCKED","unresolved_important_or_critical_findings":0,"spec_compliance":"APPROVED|NEEDS_FIXES|CANNOT_VERIFY","quality":"APPROVED|NEEDS_FIXES|CANNOT_VERIFY"}
    ```

    `APPROVED` requires both dimensions `APPROVED` and zero unresolved
    Important/Critical findings. `NEEDS_FIXES` reports remaining findings and
    requires at least one `NEEDS_FIXES` dimension. `BLOCKED` is only for a
    coverage gap, requires at least one `CANNOT_VERIFY` dimension and no
    `NEEDS_FIXES` dimension, and adds exactly
    `"coverage_gap":{"material_risk":"...","recommended_contract_delta":"..."}`.
    For `NEEDS_FIXES`, add non-empty `findings`: each item has exactly
    `id`, `severity` (`Critical`, `Important`, `Minor`, or `Cannot Verify`),
    `location`, and `description`; include `disposition` (`ADDRESSED`,
    `NOT_ADDRESSED`, or `OUT_OF_SCOPE`) for every re-review finding. An
    `APPROVED` result may retain an ADDRESSED finding of any severity, plus
    `Minor` or `Cannot Verify` findings; it has zero unresolved
    Important/Critical findings.

    ## Internal Review Method

    Use these checks internally; do not add narrative text to the final JSON result.

    ### Finding Verdicts

    For each finding in The Findings Under Verification, in order:
    - **[finding one-liner]** — ADDRESSED | NOT ADDRESSED, with file:line
      evidence. "Attempted" is not addressed: the specific defect must no
      longer exist.

    ### New Breakage in the Fix Diff

    Anything the fix itself broke or introduced, with severity
    (Critical/Important/Minor) and file:line. "None" if clean.

    ### Out-of-Scope Observations

    Issues you noticed entirely outside the fix diff. Non-blocking; the
    controller ledgers these for the final review. "None" if none.

    ### Verdict

    **Fix round:** [All findings addressed, no new Critical/Important
    breakage | Findings remain open] — list the open ones.
```

**Placeholders:**
- `[MODEL]` — REQUIRED: reviewer model per SKILL.md Model Selection; scoped
  re-reviews of small fix diffs take a cheap-to-mid tier
- `[BRIEF_FILE]` — the task brief file (same file the implementer worked from)
- `[FINDINGS]` — the Critical/Important findings and spec gaps from the
  previous review, copied verbatim, one per bullet
- `[REPORT_FILE]` — the implementer's report file (fix reports appended)
- `[FIX_BASE_SHA]` — the head the previous review saw
- `[HEAD_SHA]` — current commit
- `[DIFF_FILE]` — the path `scripts/review-package PLAN_FILE FIX_BASE HEAD` printed
- `[REVIEW_DISPATCH_RECEIPT]` — REQUIRED: fresh receipt issued by
  `prepare_dispatch` after fresh validation
- `[REVIEW_REPORT_PATH]` — REQUIRED: receipt-bound JSON result path
- `[PRIOR_REVIEW_DISPATCH_RECEIPT]` — REQUIRED: exact prior receipt used by
  `review-package --re-review` to select and verify the receipt-bound snapshot

**Re-reviewer returns:** per-finding verdicts (ADDRESSED / NOT ADDRESSED),
new breakage in the fix diff, out-of-scope observations, and a round verdict.
