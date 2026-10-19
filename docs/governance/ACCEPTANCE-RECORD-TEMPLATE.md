# Architect Acceptance — WO-NNNN

```
WORK ORDER:        WO-NNNN — <title>
PARENT PID:        PID-ARGUS-NNNN
BASE SHA:          <sha>
AUDITED SHA:       <sha>   (must equal the PR branch head at merge)
PR:                #NN  <url>
AUDIT VERDICT:     GREEN | PRODUCT_RED | …   (docs/evidence/WO-NNNN/audit.md)
ACCEPTANCE:        ACCEPTED | REJECTED
PR COMMENT:        <url of the "ARCHITECT ACCEPTANCE: WO-NNNN @ <sha> — …" comment>
DATE (UTC):        YYYY-MM-DD
ARCHITECT:         <name>
```

## Checks performed by the Architect
- [ ] Every acceptance criterion in the Work Order has a corresponding test
      or operator check with recorded output in `docs/evidence/WO-NNNN/`.
- [ ] Auditor dispatch prompt is filed verbatim and contains no diff-specific
      hints (DELIVERY-CHAIN §7).
- [ ] Audit verdict is GREEN, or RED findings were resolved by a follow-up
      Work Order and re-audited.
- [ ] Diff stays within the Work Order's scope; no excluded path touched.
- [ ] No secrets, hostnames, ports, account identifiers or gateway details
      in the diff (public repository).
- [ ] At least one Auditor finding or AC was spot-checked directly against
      the artefact by the Architect: `<which, and result>`.

## Notes
<reasons for REJECTED, or observations for the Delivery Controller>
