---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-09-25T15:23:03.729Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 04 | stub | tests/test_workflows/test_claim_pipeline.py |  | 7 xfail Wave 0 Nyquist stubs — ClaimPipeline implemented in 04-02/04-03 | open |  | 2026-09-25T15:23:03.729Z |  |

````json
[
  {
    "id": 1,
    "kind": "stub",
    "phase": "04",
    "file": "tests/test_workflows/test_claim_pipeline.py",
    "line": null,
    "description": "7 xfail Wave 0 Nyquist stubs — ClaimPipeline implemented in 04-02/04-03",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-25T15:23:03.729Z",
    "resolved_at": null,
    "milestone": "v1.0"
  }
]
````
