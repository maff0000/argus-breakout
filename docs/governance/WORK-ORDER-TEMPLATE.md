# WO-NNNN — <title>

| Field | Value |
|---|---|
| **Status** | Draft \| Approved \| In Progress \| Implemented \| Audited (GREEN/RED) \| PR Open \| Accepted \| Merged \| Closed \| Returned to Architect |
| **Parent PID** | `docs/pids/PID-ARGUS-NNNN-<slug>.md` — sections §x, §y |
| **Applicable Amendments** | none \| AMD-NNNN, … |
| **Base SHA** | `<40-hex>` (`main` at approval; see DELIVERY-CHAIN §6.3) |
| **Branch** | `wo/NNNN-<slug>` |
| **Depends on** | WO-…, … (must be Closed) \| none |
| **Parallel group** | P0-A … (Work Orders in the same group are independent and may run concurrently) |
| **Presentation target** | FUNCTIONAL_ONLY \| PRODUCT_USABLE \| PRESENTATION_POLISHED (inherits PID §5 unless stated) |
| **PR** | #… (DC fills) |
| **Evidence** | `docs/evidence/WO-NNNN/` |

## 1. Objective
One paragraph. What exists after this Work Order that did not before.

## 2. Scope (exhaustive)
Files to create or change, with the behaviour each must have. Signatures,
schemas, CLI commands and config keys stated exactly. The Implementer must
not need to guess.

```
<path>            <create|modify>  <what>
```

## 3. Exclusions
What the **Implementer** must not build or touch, even if it seems helpful.
Name paths. These never restrict the Delivery Controller's clerical and
evidence writes (DELIVERY-CHAIN §6.4, AMD-0010).

## 4. Design constraints
Architecture the Implementer works within (from the PID/ADRs): libraries
allowed, patterns required, error-handling and logging rules, security
rules, UTC canonical, configuration only via environment.

## 5. Required tests
All tests run with `pytest -q` **offline, with no `.env` and no network**.
Live checks are marked `@pytest.mark.live` and skipped by default.

| Test | Proves | Capable of failing because… |
|---|---|---|
| `tests/test_x.py::test_y` | … | … |

## 6. Acceptance criteria
Numbered, observable, each mapped to a test or an operator check the
Delivery Controller performs and records.

- **AC1** — …  (test: …)
- **AC2** — …  (operator check: …)

## 7. Evidence the Delivery Controller must file
- `docs/evidence/WO-NNNN/tests.md` — exact commands run and output summary
- `docs/evidence/WO-NNNN/auditor-prompt.md` — Auditor dispatch prompt, verbatim
- `docs/evidence/WO-NNNN/audit.md` — Auditor verdict block, verbatim
- `docs/evidence/WO-NNNN/acceptance.md` — Architect acceptance record
- Operator-check outputs named in §6

## 8. Implementer notes
Reading order; gotchas; what "done" looks like from the Implementer's seat.

## 9. Approval
```
Approved by: <Architect>
Date (UTC):  YYYY-MM-DD
Commit:      <sha of the commit that set Status=Approved>
```

## 10. Delivery log (DC appends)
```
YYYY-MM-DDTHH:MMZ  <state>  <sha/PR/note>
```
