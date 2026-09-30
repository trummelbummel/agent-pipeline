# Agent test smells

Hunt these with ripgrep first, then confirm in context. Prefer **delete** for S3/S4; **fix** or **add-case** for the rest.

## Smell catalog (verbatim)

Hunt agent smells (fast pass with ripgrep)

* Testing mocks of internals — mocks of private helpers / LangGraph nodes instead of real policy fold
* Asserting implementation, not behavior — call counts, exact prompt strings, private attribute names
* Tautologies — fixture builds the same dict the code returns
* Copy-paste twins — same setup, one field flipped, no named scenario
* Over-specifying LLM text — brittle string equality on explanations
* Missing negative cases — only happy paths for DENY/UNCERTAIN/HITL
* No boundary tests — missing prediction, bad run_manifest, symlink claim id, upload size caps

Delete e.g. Tautologies, copy paste twins or fix agent tells

---

## IDs and actions

| ID | Smell | Default action |
|----|-------|----------------|
| S1 | Testing mocks of internals | fix → call real policy fold / public API; mock only true boundaries (HTTP, chat transport, clock, FS at API edge) |
| S2 | Asserting implementation, not behavior | fix → assert decision, labels, artifacts, status codes; drop call counts / prompt text / `_private` peeks |
| S3 | Tautologies | **delete** (or rewrite so expected value is independent of the code path under test) |
| S4 | Copy-paste twins | **delete** weaker twin, or collapse into `@pytest.mark.parametrize` with **named** scenarios |
| S5 | Over-specifying LLM text | fix → assert structured fields / enums / substrings only when the contract requires wording |
| S6 | Missing negative cases | **add-case** for DENY / UNCERTAIN / HITL (and reject paths) when only APPROVE/happy exists |
| S7 | No boundary tests | **add-case** for missing prediction, bad `run_manifest`, symlink / traversal claim id, upload size caps |

---

## Ripgrep hunts

Run from repo root. Scope with path args when reviewing a subset (`rg … tests/test_policy/`).

### S1 — mocks of internals

```bash
rg -n -e 'patch\(.*(_[a-zA-Z]|nodes?\.|/nodes)' \
      -e 'MagicMock|AsyncMock|unittest\.mock|monkeypatch\.(setattr|setitem)' \
      -e 'patch\.object\([^,]+,\s*[\"'\'']_' \
      tests/
```

Confirm: is the target a **private helper**, LangGraph **node**, or policy **fold** step? → smell.
Is it chat transport / HTTP client / uploaded file at the API boundary? → usually OK (note and skip).

### S2 — implementation not behavior

```bash
rg -n -e 'call_count|assert_called|assert_awaited|call_args|mock_calls' \
      -e 'prompt|system_message|SYSTEM_PROMPT' \
      -e '\._[a-zA-Z]\w*\b' \
      tests/
```

Flag `assert chat_fn.call_count == N`, exact prompt equality, and reads of `_private` attrs. Prefer `decision`, `status_code`, artifact JSON fields.

### S3 — tautologies

```bash
rg -n -e 'assert\s+\w+\s*==\s*\w+' \
      -e 'expected\s*=\s*\{' \
      -e 'return\s*\{[^}]+\}.*=\s*expected|expected\s*=\s*.*return' \
      tests/
```

Manual check: fixture/`expected` dict is built the same way as production (or copied from the function body). If the test cannot fail when the implementation is wrong → **delete**.

### S4 — copy-paste twins

```bash
rg -n -e '^def test_' tests/ | sed 's/.*://' | sort | uniq -c | sort -rn | head
# Then visually / diff nearby test bodies:
rg -n -e '^def test_' -A 40 tests/path/to/file.py
```

Heuristic: two tests share ≥80% of setup lines; differ by one field or one assert; neither has a scenario name in the test name or parametrize `ids=`. → delete one or parametrize with named ids.

### S5 — brittle LLM text

```bash
rg -n -e 'explanation|reason_text|message|rationale' \
      -e 'assert\s+.*==\s*[\"'\''][^\"'\'']{20,}' \
      tests/
```

Flag full-string equality on free-text model output. Keep enums (`DECISION_DENY`), codes, and stable structured keys.

### S6 — missing negatives (DENY / UNCERTAIN / HITL)

```bash
rg -n -e 'DECISION_APPROVE|DECISION_DENY|DECISION_UNCERTAIN|HITL|hitl' tests/
rg -n -e 'def test_.*approv|def test_.*deny|def test_.*uncertain|def test_.*hitl' -i tests/
```

Per decision-producing module under review: if only happy/APPROVE appears, **add** at least one DENY and one UNCERTAIN/HITL (whichever the policy supports).

### S7 — boundary gaps

```bash
rg -n -e 'run_manifest|predicted_answer|symlink|upload|max_.*size|content_length|claim_id' tests/
rg -n -e '\.\./|Path\(|tmp_path' tests/test_api/ tests/test_workflows/
```

When reviewing API / artifacts / evaluation tests, ensure coverage exists (or add) for:
- missing prediction / absent `predicted_answer.json`
- malformed or incomplete `run_manifest`
- symlink or `../` claim id path abuse
- upload size / type caps

Absence of any hits in a package that owns that surface is itself a finding (`add-case`).

---

## Domain notes (this repo)

- Prefer exercising `decision_from_state` / claim pipeline with real checkers and fixtures over patching graph nodes.
- `MagicMock` chat_fn at the LLM **transport** boundary is acceptable; asserting `call_count` as the main oracle is S2.
- Named fixtures like `_base_state(**overrides)` are good when tests assert **different** decisions — not when expected is a mirror of the fixture.
