# Mutation / sabotage spot-checks

Test Mutation / sabotage spot-checks (highest signal)

Pick 5–10 critical lines invert the input and see if check still succeeds.
After your check revert back to the original state.

---

## Protocol

1. **Choose targets** — Prefer assertions (or fixture values feeding them) that gate:
   - `DECISION_DENY` / `DECISION_APPROVE` / `DECISION_UNCERTAIN` / HITL
   - claim path / id validation (symlink, `..`, unknown id)
   - upload size / type rejection
   - presence/shape of `predicted_answer` / `run_manifest`
   - policy fold outcomes from checker flags (not mock call counts)

2. **Invert one line at a time** — Examples:
   - Expected `DECISION_DENY` → `DECISION_APPROVE`
   - `identity_check=True` → `False` (or drop the flag that should force DENY)
   - Valid claim id → `../etc/passwd` or a symlink path **without** updating the expect-reject assert
   - Cap `max_upload_bytes` expect 413 → expect 200
   - `assert result.decision == X` → `==` the opposite enum

3. **Run narrowly**
   ```bash
   pytest path/to/test_file.py::test_name -q
   ```

4. **Score**
   | Result | Meaning | Follow-up |
   |--------|---------|-----------|
   | FAIL | Good — test caught the sabotage | Revert; keep test |
   | PASS | Weak — test does not encode the behavior | Revert; strengthen or replace; optional re-mutate |

5. **Revert (mandatory)**
   - Restore each sabotaged file before the next mutation (or after the batch if you tracked every edit).
   - Prefer `git checkout -- <file>` when the file had no intentional remediation edits yet; otherwise manually undo only the sabotage lines so remediation edits stay.
   - Confirm no sabotage remains: re-read the inverted lines; working tree must match intended post-remediation state.

6. **Never commit sabotage.** Never end the skill with red tests caused by leftover inversions.

## Selection tips

- Spread across files when possible (pipeline, policy decision, API uploads).
- Skip tautologies you already deleted — mutate the replacements or remaining strong tests.
- One mutation = one hypothesis (“if the decision flip, this assert must fail”).
- Cap at 10. Quality over volume.

## Recording template

```
| File | Line | Mutation | Result | Follow-up |
|------|------|----------|--------|-----------|
| tests/…/test_decision.py | 42 | DENY→APPROVE expect | FAIL (good) | — |
| tests/…/test_uploads.py | 88 | size cap expect 200 | PASS (weak) | assert status==413 |
```

Working tree clean of sabotage: **yes**
