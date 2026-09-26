---
schema_version: 1
open_count: 14
waived_count: 0
fixed_count: 0
total_count: 14
last_updated: 2026-09-26T11:01:24.385Z
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
| 5 | 260926-bwk | deviation | src/compliance/workflows/claim_pipeline.py |  | Bundled pre-existing HITL/False-abstention WIP with Task 2 analysis I/O wiring | open |  | 2026-09-26T06:40:46.901Z |  |
| 6 | 07 | unmet-truth | tests/test_config/test_settings.py | 202 | Pre-existing: coverage.other_label is None not False (unrelated to 07-00 stubs) | open |  | 2026-09-26T10:48:48.357Z |  |
| 7 | 07 | unmet-truth | tests/test_config/test_settings.py | 235 | Pre-existing: OcrRetryConfig missing on_missing_signature (unrelated to 07-00 stubs) | open |  | 2026-09-26T10:48:48.458Z |  |
| 8 | 07 | stub | tests/test_llm/test_checker.py |  | Wave 0 xfail stubs for not_authentic/incomplete modes — implemented in 07-01/07-02 | open |  | 2026-09-26T10:49:00.453Z |  |
| 9 | 07 | stub | tests/test_workflows/test_claim_pipeline.py |  | Wave 0 xfail stubs for authenticity/incomplete DENY + suspicious dating UNCERTAIN — implemented in 07-01/07-02 | open |  | 2026-09-26T10:49:00.552Z |  |
| 10 | 07 | stub | tests/test_config/test_settings.py |  | Wave 0 xfail stub for authenticity_prompt/incomplete_prompt — implemented in 07-01 | open |  | 2026-09-26T10:49:00.655Z |  |
| 11 | 07 | unrun-verify | tests/test_config/test_settings.py | 196 | Deselected pre-existing other_label False vs None mismatch during 07-01 verify | open |  | 2026-09-26T10:58:24.614Z |  |
| 12 | 07 | deviation | src/compliance/workflows/claim_pipeline.py |  | Pre-existing mypy errors in claim_pipeline/benford/document left untouched (out of scope) | open |  | 2026-09-26T10:58:24.814Z |  |
| 13 | 07 | unmet-truth | tests/test_config/test_settings.py | 206 | test_analysis_coverage_other_label_is_false expects False; config.yaml has None (pre-existing) | open |  | 2026-09-26T11:01:24.251Z |  |
| 14 | 07 | unrun-verify | src/compliance/ |  | mypy src/compliance reports 7 pre-existing errors; 07-01b made no production changes | open |  | 2026-09-26T11:01:24.385Z |  |

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
  },
  {
    "id": 5,
    "kind": "deviation",
    "phase": "260926-bwk",
    "file": "src/compliance/workflows/claim_pipeline.py",
    "line": null,
    "description": "Bundled pre-existing HITL/False-abstention WIP with Task 2 analysis I/O wiring",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T06:40:46.901Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 6,
    "kind": "unmet-truth",
    "phase": "07",
    "file": "tests/test_config/test_settings.py",
    "line": 202,
    "description": "Pre-existing: coverage.other_label is None not False (unrelated to 07-00 stubs)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T10:48:48.357Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 7,
    "kind": "unmet-truth",
    "phase": "07",
    "file": "tests/test_config/test_settings.py",
    "line": 235,
    "description": "Pre-existing: OcrRetryConfig missing on_missing_signature (unrelated to 07-00 stubs)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T10:48:48.458Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 8,
    "kind": "stub",
    "phase": "07",
    "file": "tests/test_llm/test_checker.py",
    "line": null,
    "description": "Wave 0 xfail stubs for not_authentic/incomplete modes — implemented in 07-01/07-02",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T10:49:00.453Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 9,
    "kind": "stub",
    "phase": "07",
    "file": "tests/test_workflows/test_claim_pipeline.py",
    "line": null,
    "description": "Wave 0 xfail stubs for authenticity/incomplete DENY + suspicious dating UNCERTAIN — implemented in 07-01/07-02",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T10:49:00.552Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 10,
    "kind": "stub",
    "phase": "07",
    "file": "tests/test_config/test_settings.py",
    "line": null,
    "description": "Wave 0 xfail stub for authenticity_prompt/incomplete_prompt — implemented in 07-01",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T10:49:00.655Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 11,
    "kind": "unrun-verify",
    "phase": "07",
    "file": "tests/test_config/test_settings.py",
    "line": 196,
    "description": "Deselected pre-existing other_label False vs None mismatch during 07-01 verify",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T10:58:24.614Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 12,
    "kind": "deviation",
    "phase": "07",
    "file": "src/compliance/workflows/claim_pipeline.py",
    "line": null,
    "description": "Pre-existing mypy errors in claim_pipeline/benford/document left untouched (out of scope)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T10:58:24.814Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 13,
    "kind": "unmet-truth",
    "phase": "07",
    "file": "tests/test_config/test_settings.py",
    "line": 206,
    "description": "test_analysis_coverage_other_label_is_false expects False; config.yaml has None (pre-existing)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T11:01:24.251Z",
    "resolved_at": null,
    "milestone": "v1.0"
  },
  {
    "id": 14,
    "kind": "unrun-verify",
    "phase": "07",
    "file": "src/compliance/",
    "line": null,
    "description": "mypy src/compliance reports 7 pre-existing errors; 07-01b made no production changes",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-09-26T11:01:24.385Z",
    "resolved_at": null,
    "milestone": "v1.0"
  }
]
````
