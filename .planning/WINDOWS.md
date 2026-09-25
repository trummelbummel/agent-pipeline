---
schema_version: 1
open_count: 4
waived_count: 0
fixed_count: 0
total_count: 4
last_updated: 2026-09-25T16:52:14.404Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 04 | stub | tests/test_workflows/test_claim_pipeline.py |  | 7 xfail Wave 0 Nyquist stubs — ClaimPipeline implemented in 04-02/04-03 | open |  | 2026-09-25T15:23:03.729Z |  |
| 2 | 04 | stub | tests/test_workflows/test_claim_pipeline.py |  | PE/missed routing xfail stubs deferred to 04-03 | open |  | 2026-09-25T15:28:36.541Z |  |
| 3 | 04 | stub | src/compliance/workflows/claim_pipeline.py |  | PE/missed coverage routes to END until 04-03 | open |  | 2026-09-25T15:28:36.644Z |  |
| 4 | 05 | deviation | src/compliance/workflows/claim_pipeline.py |  | Rule 2: input_root for caller-supplied claim folders in analyze_claim | open |  | 2026-09-25T16:52:14.404Z |  |

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
  },
  {
    "id": 2,
    "kind": "stub",
    "phase": "04",
    "file": "tests/test_workflows/test_claim_pipeline.py",
    "line": null,
    "description": "PE/missed routing xfail stubs deferred to 04-03",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-25T15:28:36.541Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 3,
    "kind": "stub",
    "phase": "04",
    "file": "src/compliance/workflows/claim_pipeline.py",
    "line": null,
    "description": "PE/missed coverage routes to END until 04-03",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-25T15:28:36.644Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 4,
    "kind": "deviation",
    "phase": "05",
    "file": "src/compliance/workflows/claim_pipeline.py",
    "line": null,
    "description": "Rule 2: input_root for caller-supplied claim folders in analyze_claim",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-25T16:52:14.404Z",
    "resolved_at": null,
    "milestone": "v1.0"
  }
]
````
