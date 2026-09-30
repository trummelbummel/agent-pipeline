---
name: classify-tasks
description: >
  Classifies GSD plan tasks or .gsd/test_fixes.md entries as simple or complex.
  Simple tasks proceed autonomously. Complex tasks pause for human steering before execution.
  Use after gsd_plan_slice or gsd_plan_milestone completes, after /test-review writes
  test_fixes.md, or when the user invokes /classify-tasks.
---

<objective>
Read tasks from a GSD plan or from `.gsd/test_fixes.md` and classify each as **simple**
or **complex**. Simple tasks are ones an LLM can reliably execute autonomously. Complex
tasks carry risk of silent wrong answers, hidden coupling, or architectural judgment
calls — they need human steering before the agent proceeds.

The classification is based on empirical LLM capability boundaries, not task size.
</objective>

<quick_start>
1. Locate the task source: user-specified plan / `.gsd/test_fixes.md`, else the most recent slice PLAN (or milestone ROADMAP), else open TF-* rows in `.gsd/test_fixes.md` if that file was just updated.
2. Read each task's title, description, files, verify, and expectedOutput fields (for TF-*: Work, Files, Done when).
3. Classify each task using the decision tree in [references/classification-rules.md](references/classification-rules.md).
4. Print the classification table. If the source is `.gsd/test_fixes.md`, write Verdict / Signals / Risk back into that file.
5. For any task classified as **complex**, pause and present the task to the user with the risk factors identified, asking for steering direction before execution begins. Record steering under **Steering** when updating `test_fixes.md`.
</quick_start>

<workflow>
<step name="locate-plan">
Find the active task source to classify:
- If the user points at a milestone/slice plan or at `.gsd/test_fixes.md`, read that file.
- Else if `/test-review` just wrote/updated `.gsd/test_fixes.md` with unclassified TF-* rows, use that file.
- Otherwise, find the most recently modified `*-PLAN.md` or use `gsd_milestone_status` to identify the current in-progress slice.
- Read the file fully to extract all tasks (for `test_fixes.md`: every open `[ ]` row and any row missing Verdict).
</step>

<step name="extract-tasks">
For each task in the plan, extract:
- Task ID and title
- Description (what it does)
- Files it touches
- Verification criteria
- Expected output
- Dependencies on other tasks
- `requiredWorkflowTools` (browser, mac, etc.)

For each `TF-*` entry in `.gsd/test_fixes.md`, map:
- Task ID / title ← heading (`TF-NNN: …`)
- Description ← **Work** (+ smell / action)
- Files ← **Files**
- Verification / expectedOutput ← **Done when**
- Dependencies / tools ← note if present; else empty
</step>

<step name="classify">
Apply the classification rules from [references/classification-rules.md](references/classification-rules.md) to each task.

For each task, walk the **complexity signals** checklist. A task is **complex** if it triggers
one or more high-weight signals. A task with zero signals or only low-weight signals is **simple**.

Record the verdict and the triggering signals for each task.
</step>

<step name="report">
Print a classification table:

```
## Task Classification

| Task | Title | Verdict | Signals | Risk |
|------|-------|---------|---------|------|

Legend: ✅ simple (autonomous)  ⚠️ complex (needs steering)
```

Summary line: `X simple / Y complex out of Z total tasks`
</step>

<step name="steer-complex">
For each **complex** task, present the user with:

1. **What the task asks** — one-sentence summary.
2. **Why it's flagged** — the specific complexity signals that triggered.
3. **What could go wrong** — concrete failure modes if the agent proceeds without guidance.
4. **Steering questions** — what the agent needs to know to execute safely:
   - Architecture or design constraints the agent can't see?
   - Preferred approach among alternatives?
   - External context (team conventions, scale, runtime environment)?
   - Acceptance bar — how will the human know it's right?

Use `ask_user_questions` for structured input. Ask 1-3 focused questions per complex task.
Wait for the user's response before proceeding. Record the steering answers as task context
for the execution phase. When the source is `.gsd/test_fixes.md`, write answers under that
task's **Steering** section and refresh its classification-table row.
</step>

<step name="persist-test-fixes">
When the source is `.gsd/test_fixes.md`: after classify (and any steering), update the
**Task Classification** table and each detail section with Verdict, Signals, Risk, and
the Summary line (`X simple / Y complex out of Z total tasks`). Do not leave blank Verdicts
on rows that were in scope for this run.
</step>
</workflow>

<anti_patterns>
- Do not classify based on estimated LOC or time alone — a 200-line CRUD endpoint is simple; a 5-line concurrency fix is complex.
- Do not assume "uses common library" means simple if the task involves subtle correctness (e.g., pandas + race conditions).
- Do not skip classification for tasks that "look small."
- Do not fabricate steering answers — always ask the human.
- Do not block on simple tasks — let them proceed autonomously.
- Do not invent a second rubric for TF-* test fixes — same classification-rules.md as plan tasks.
</anti_patterns>

<success_criteria>
- Every in-scope task (plan or `.gsd/test_fixes.md`) has a classification verdict with cited signals.
- Simple tasks have zero high-weight complexity signals.
- Complex tasks are presented to the user with specific risk factors and steering questions.
- No complex task proceeds to execution without human steering input recorded.
- The classification table is printed before any execution begins.
- When classifying test fixes, `.gsd/test_fixes.md` is updated in place (table + detail + summary).
</success_criteria>
