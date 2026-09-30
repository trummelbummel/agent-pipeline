---
name: test-review
description: >
  Reviews pytest files for agent-written test smells and runs mutation/sabotage
  spot-checks. Tracks open fixes in .gsd/test_fixes.md, classifies each via the
  classify-tasks skill (simple vs complex), deletes tautologies and copy-paste
  twins, fixes other agent tells, then mutates critical assertions (always
  reverts). Use after GSD tasks that touch tests, when the user invokes
  /test-review, or when test quality review is requested.
---

<objective>
Hunt agent smells in tests (fast ripgrep pass), record confirmed fixes in
`.gsd/test_fixes.md`, classify each entry with `classify-tasks`, delete or fix
the worst offenders (steering first when complex), then sabotage 5–10 critical
lines to prove the suite catches regressions. Always restore the working tree
after mutation. Prefer behavior over implementation; prefer real policy fold
over mocked internals.
</objective>

<quick_start>
1. Scope: changed `tests/**/*.py` from git diff, or paths the user names, or all of `tests/`.
2. Read [references/smells.md](references/smells.md) and run the ripgrep hunt.
3. Append confirmed hits as tasks to `.gsd/test_fixes.md` (see [references/test_fixes_format.md](references/test_fixes_format.md)).
4. Classify every open / newly added task with `.claude/skills/classify-tasks` (load its `SKILL.md` + `references/classification-rules.md`). Steer on complex before remediating.
5. Triage → **delete** tautologies / copy-paste twins; **fix** other agent tells; mark tasks done in `test_fixes.md`.
6. Read [references/mutation.md](references/mutation.md). Mutate 5–10 critical lines, score, **revert**. Append weak-pass follow-ups to `test_fixes.md` and re-classify them.
7. Print findings + mutation scorecard + classification summary. Touched tests green; sabotage gone.
</quick_start>

<workflow>
<step name="scope">
Determine which test files to review:
- After a GSD task / verify: every `tests/**/*.py` touched in the diff (plus siblings in the same package if a fixture/conftest changed).
- Standalone: user-specified paths, else uncommitted test changes, else all of `tests/`.
- Exclude `__pycache__`, `.tox`, `.venv`, fixture binary blobs, and `docling_fakes.py` unless the user asks.

Also read `.gsd/test_fixes.md` if it exists — open `[ ]` tasks in scope are in play this run (re-classify if missing Verdict).
</step>

<step name="smell-hunt">
Read [references/smells.md](references/smells.md). Run the listed `rg` hunts from the repo root against the scoped files (or `tests/` if broad).

For each hit, classify by smell ID (S1–S7). Open the file and confirm the hit is real — discard false positives (e.g. mocking a true system boundary like HTTP/chat transport is OK; mocking a private helper / LangGraph node is not).

Record: `file:line`, smell ID, one-line evidence, proposed action (`delete` | `fix` | `add-case` | `skip`).
</step>

<step name="track-test-fixes">
Persist confirmed hits (and in-scope open backlog items) to **`.gsd/test_fixes.md`**.

Read [references/test_fixes_format.md](references/test_fixes_format.md). If the file is missing, create it from that template.

For each new confirmed smell (skip `skip` / false positives):
1. Assign the next `TF-NNN` id (monotonic; never reuse).
2. Append a row to the **Task Classification** table (Verdict/Signals blank until classify).
3. Append a detail section: smell ID, files, proposed action, Work, Done when.

Do not duplicate an open task for the same `file` + smell + evidence. Update the existing entry instead.
</step>

<step name="classify">
**Required.** Classify every task that is open (`[ ]`) or newly added and still missing a Verdict.

1. Read `.claude/skills/classify-tasks/SKILL.md` and `.claude/skills/classify-tasks/references/classification-rules.md`.
2. Treat each `TF-*` entry as a classify-tasks task: title, Work/description, Files, Done when → `verify` / expectedOutput.
3. Apply the same decision tree (high-weight any → complex; 2+ medium → complex; else simple).
4. Write Verdict + Signals (+ Risk) into the classification table and the detail section.
5. Print the classify-tasks table for these TF tasks.
6. For each **complex** task: run classify-tasks `steer-complex` (ask 1–3 steering questions, wait, record answers under **Steering** in the detail section) **before** remediating that task.
7. Simple tasks proceed without pause.
</step>

<step name="remediate">
Apply fixes in priority order, simple first, then steered complex:

1. **Delete** — Tautologies (S3) and copy-paste twins (S4). Prefer deleting the weak twin over merging unless a named parametrized scenario is clearly better.
2. **Fix** — Mocks of internals (S1), asserting implementation (S2), over-specifying LLM text (S5). Rewrite to assert observable decisions / public outcomes against real policy fold where feasible.
3. **Add** — Missing negative cases (S6) and boundary tests (S7) when the gap is in-scope for the files under review. Keep additions minimal: one focused case per gap, not a second suite.

After each task is done: mark `[x]` in `.gsd/test_fixes.md`, note resolution (commit hash if available), keep the classification Verdict.

Do not expand production code. Do not mock private helpers / graph nodes to “make the rewrite easy.” If a real-fold rewrite is blocked on missing seams, leave the task `[ ]`, note the blocker under **Steering** / Notes, and continue.
</step>

<step name="mutation">
Read [references/mutation.md](references/mutation.md). This step is **mandatory** and **highest signal**.

1. From remediated (or confirmed-strong) tests, pick **5–10 critical lines** — assertions or fixture values that gate DENY / APPROVE / UNCERTAIN / HITL, path validation, upload caps, or prediction I/O.
2. For each pick: invert the input or flip the expected outcome so a correct test **must fail**.
3. Run only the affected test(s). Record: `file:line`, mutation, **FAIL (good)** or **PASS (weak test)**.
4. **Immediately revert** every sabotage (restore file contents). Confirm `git diff` / file contents match pre-mutation for those lines.
5. For any **PASS (weak)** result: append a new `TF-*` to `.gsd/test_fixes.md`, run the **classify** step on it, strengthen or replace when simple (or after steering if complex), then optionally re-mutate once. Never leave sabotaged code in the tree.

If a mutation cannot be reverted cleanly, stop and restore from git before continuing.
</step>

<step name="verify">
Re-run the tests touched by remediation (and any packages involved in mutation). All must be green with sabotage reverted.
Confirm `.gsd/test_fixes.md` classification table matches detail sections (every open/new row has Verdict + Signals).
</step>

<step name="report">
Print:

```
## Test Review

### Classification (.gsd/test_fixes.md)
| Task | Title | Verdict | Signals | Risk |
|------|-------|---------|---------|------|

### Smells this run
| File | Line | Smell | TF | Action | Notes |
|------|------|-------|----|--------|-------|

### Mutations
| File | Line | Mutation | Result | Follow-up |
|------|------|----------|--------|-----------|

Summary: X deleted / Y fixed / Z cases added / M mutations (G good-fail, W weak-pass).
Backlog: A open / B done in .gsd/test_fixes.md. Working tree clean of sabotage: yes/no.
```
</step>
</workflow>

<anti_patterns>
- Do not leave inverted assertions or sabotaged fixtures in the tree — revert is non-negotiable.
- Do not remediate complex TF tasks without classify-tasks steering recorded in `test_fixes.md`.
- Do not skip writing `.gsd/test_fixes.md` because fixes were applied in-session — track then mark done.
- Do not invent a parallel classification scheme — reuse classify-tasks rules only.
- Do not “fix” smells by adding more mocks of private helpers or LangGraph nodes.
- Do not treat `assert chat_fn.call_count == N` as behavior coverage.
- Do not keep tautologies because “they document the shape.”
- Do not merge copy-paste twins into a mega-test that still only covers happy paths.
- Do not assert full LLM explanation strings when a decision enum / structured field suffices.
- Do not skip the mutation pass when the smell hunt finds nothing — still sabotage 5 critical lines.
</anti_patterns>

<success_criteria>
- Confirmed smells and weak-mutation follow-ups are tracked in `.gsd/test_fixes.md` with TF ids.
- Every open/new TF task has a classify-tasks Verdict + Signals; complex ones have Steering before work.
- Tautologies and copy-paste twins deleted or replaced with named scenarios.
- Other agent tells fixed toward behavior + real policy fold (or left open with blocker noted).
- 5–10 mutations run; weak passes tracked/classified; all sabotage reverted.
- Touched tests green; report table printed.
</success_criteria>
