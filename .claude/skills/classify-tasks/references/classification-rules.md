# Task Classification Rules

Classify each task as **simple** or **complex** based on the signals below.
A task is **complex** if it triggers **any high-weight signal**. A task is
**simple** if it triggers only low-weight signals or none at all.

## Decision Tree

```
For each task:
  1. Check HIGH-WEIGHT signals → any match? → COMPLEX
  2. Check MEDIUM-WEIGHT signals → 2+ matches? → COMPLEX
  3. Otherwise → SIMPLE
```

---

## High-Weight Signals (any one → complex)

### H1: Cross-file architectural change
The task modifies contracts, interfaces, or data flow across 3+ files that import
each other. The agent can't see all callers and may break hidden coupling.

**Detect:** task.files spans 3+ modules with import relationships, or description
mentions "refactor," "restructure," "move," or "split" across module boundaries.

### H2: Concurrency, race conditions, or shared mutable state
The task involves threading, async coordination, locks, queues, or any shared
mutable state across processes. LLMs guess at correctness here instead of reasoning
through interleavings.

**Detect:** description mentions threads, async, locks, semaphores, queues,
workers, parallel, atomic, race condition, or the files use `threading`,
`asyncio`, `multiprocessing`, `concurrent.futures`.

### H3: Security-sensitive code
Auth flows, session management, secrets handling, input sanitization for injection
prevention, cryptographic operations, or permission checks. The cost of a subtle
bug is too high for autonomous execution.

**Detect:** description mentions auth, login, session, token, secret, credential,
encrypt, decrypt, hash, sanitize, escape, CSRF, CORS, or files touch auth/security
modules.

### H4: Subtle correctness requirements
Numerical stability, off-by-one in non-trivial index logic, floating-point
comparison, boundary conditions in algorithms, or correctness proofs. The LLM
sounds equally confident on correct and incorrect code.

**Detect:** description involves algorithm implementation, mathematical computation,
coordinate systems, pagination boundary logic, or custom data structure operations.

### H5: Vague or underspecified requirements
The task description leaves significant design decisions to the implementer.
The LLM fills gaps with assumptions and often doesn't flag that it did.

**Detect:** description uses words like "appropriate," "as needed," "handle
gracefully," "improve," or "clean up" without specifying concrete behavior.
Missing acceptance criteria. No `verify` or `expectedOutput` defined.

### H6: Niche, internal, or undocumented APIs
The task depends on APIs that aren't well-represented in training data: internal
company SDKs, very new libraries (< 6 months old), or APIs with version-specific
breaking changes. The LLM may hallucinate function signatures.

**Detect:** imports from internal packages, references to APIs not in major
public packages, or description mentions specific version requirements for
uncommon libraries.

### H7: Performance tuning without profiling data
The task asks to "optimize," "speed up," or "reduce memory" without providing
profiling output, benchmarks, or specific bottleneck identification. The LLM
guesses the bottleneck instead of measuring.

**Detect:** description says "optimize," "performance," "speed up," "slow,"
"memory," "bottleneck" without referencing profiling data or benchmarks.

---

## Medium-Weight Signals (2+ → complex)

### M1: State-dependent debugging
The task involves fixing a bug that depends on runtime state, environment
configuration, flaky tests, or is "only reproducible on X." The LLM needs
to run the code, see logs, and iterate.

**Detect:** description mentions "flaky," "intermittent," "works locally,"
"only in production," "environment-specific," or requires runtime debugging.

### M2: Large blast radius
The task touches shared infrastructure code (database migrations, CI config,
deployment scripts, shared utilities imported by 5+ modules). A mistake
propagates widely.

**Detect:** files include migration files, CI/CD configs, Dockerfiles,
shared utility modules, or framework middleware.

### M3: Non-obvious domain logic
The task implements business rules that require domain knowledge not present
in the codebase — compliance rules, financial calculations, medical logic,
legal requirements. The LLM can't verify correctness against the domain.

**Detect:** description references domain-specific rules, regulations,
formulas, or business processes that aren't documented in the codebase.

### M4: Long-lived session or multi-step workflow
The task is part of a chain where earlier decisions constrain later ones,
and the LLM may forget constraints or reintroduce bugs it already fixed
within a long session.

**Detect:** task depends on 3+ prior tasks in sequence, or description
references state built up across multiple prior steps.

---

## Low-Weight Signals (safe for autonomous execution)

### L1: Boilerplate and glue code
CRUD endpoints, data classes, CLI argument parsing, config loading, format
conversion. Common patterns with low ambiguity.

### L2: Standard library/framework usage
pandas, spaCy, SQL, regex, FastAPI routes, Django models, Flask blueprints,
pytest fixtures. Well-documented, well-represented in training data.

### L3: Single-file refactoring
Rename, extract function, add type hints, linter fixes, DRY cleanup — all
within one file. No cross-file impact.

### L4: Tests for clear behavior
Writing unit tests when the function's contract is already defined.
Edge case enumeration from a clear spec.

### L5: Documentation and explanation
Docstrings, README updates, commit messages, code comments, summarizing
a module or diff.

### L6: Translation between formats
Language-to-language, framework-to-framework, pseudocode-to-code, or
format conversion (JSON ↔ YAML ↔ CSV).

### L7: Reading errors and suggesting fixes
Stack trace analysis, common error patterns, dependency conflicts.

### L8: First drafts of scripts
One-off data wrangling, plotting, automation scripts. Quick iteration
expected.
