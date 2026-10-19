# AMD-NNNN — <title>

| Field | Value |
|---|---|
| **Status** | Draft \| Approved \| Applied |
| **Amends** | `PID.md` §… and/or `docs/pids/PID-ARGUS-NNNN-<slug>.md` §… |
| **Related ADR** | ADR-NNNN \| none |
| **Raised by** | Architect \| Delivery Controller (returned WO-NNNN) \| Human |
| **Affects Work Orders** | WO-NNNN (status at time of amendment), … \| none open |

## 1. Problem
What was found to be wrong, missing, ambiguous or contradictory, with the
evidence (file, line, failing test, returned.md reference).

## 2. Change
Exact before/after text for every affected PID section. Quote the current
text; give the replacement text. No paraphrase.

## 3. Consequences
- Work Orders that must be re-based, re-scoped or cancelled, by id.
- New Work Orders required, by title (the Architect authors them separately).
- Evidence or ADRs that must be updated.

## 4. Application
When Approved, the Architect applies §2 to the PID text in the same commit
and tags each changed section `(AMD-NNNN)`. Status → Applied.

## 5. Approval
```
Approved by: <Architect>
Date (UTC):  YYYY-MM-DD
Commit:      <sha>
```
