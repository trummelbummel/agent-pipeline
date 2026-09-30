# `.gsd/test_fixes.md` format

Persistent backlog for test-review findings. Mirror the shape of `.gsd/review_backlog.md`.
Classify every task with `.claude/skills/classify-tasks` before remediating.

## File location

`.gsd/test_fixes.md` (create if missing)

## Header template

```markdown
# Test Review — Fix Backlog

Source: `/test-review` smell hunt + mutation weak-passes
Classified: via `/classify-tasks` rules (`.claude/skills/classify-tasks`)

Legend: ✅ simple (autonomous) · ⚠️ complex (needs steering before execution)

Status: `[ ]` open · `[x]` done

---

## Task Classification

| Task | Title | Verdict | Signals | Risk |
|------|-------|---------|---------|------|

**Summary: X simple / Y complex out of Z total tasks** (update on each classify pass)

---
```

## Detail section template (one per TF-NNN)

```markdown
### [ ] TF-001: Short title (S2) ⚠️

**Smell:** S2 — Asserting implementation, not behavior
**Action:** fix
**Files:** `tests/test_workflows/test_claim_pipeline.py`
**Verdict:** complex — H5, M3
**Risk:** call_count oracle masks wrong DENY path

**Work**

- Replace `assert chat_fn.call_count == N` with assertions on `decision` / artifacts.
- Keep chat_fn mock only as transport boundary.

**Done when**

- Named test(s) assert decision enums / public fields; no call_count as primary oracle.
- `pytest tests/test_workflows/test_claim_pipeline.py -q` green.

**Steering**

- (required when Verdict is complex — record Q&A from classify-tasks steer-complex)

**Resolution**

- (fill when `[x]`: what changed; optional commit hash)
```

## Rules

1. **IDs:** `TF-001`, `TF-002`, … monotonic. Never reuse. Mutation follow-ups get new ids.
2. **Dedup:** same file + smell + evidence → update existing open row; do not clone.
3. **Classify before remediate:** blank Verdict is not allowed once Work starts.
4. **Simple vs complex:** only classify-tasks `references/classification-rules.md` — no ad-hoc labels.
5. **Done:** flip `[ ]` → `[x]`, keep Verdict emoji in the heading, fill **Resolution**.
6. **Summary line:** recount simple/complex after each classify pass (open + done rows).
