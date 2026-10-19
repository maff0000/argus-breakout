# WO-0010 — Operator checks

Run by the Delivery Controller on dell-debian (execution host) against the final head. No real credential appears
below; dummy credential files contain the documented fake `AKIAIOSFODNN7EXAMPLE`. No host/port/key value is involved.

```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0010 head=7a0cf85556be311f050de0aa36449ee06e60c2d1
$ git check-ignore -q polygon.txt  (AC1)
exit=0  (0 = ignored)
$ git check-ignore -v polygon.txt
.gitignore:42:*.txt	polygon.txt
$ git check-ignore -q .env.example  (AC2)
exit=1  (1 = NOT ignored)
$ git ls-files .env.example
.env.example
--- AC3: dummy polygon.txt with fake key; git add -A must stage nothing
$ git status --porcelain
(end; empty above = nothing staged)
--- AC4: clean branch scans
gitleaks detect rc=0
gitleaks protect --staged rc=0
--- AC5: force-stage dummy; protect must fail naming argus-bare-key-file
gitleaks protect --staged rc=1
RuleID:      argus-bare-key-file
File:        polygon.txt
$ git status --porcelain (after cleanup)
(end)
--- spot-check of auditor finding 2 (empty file): scratch clone, force-stage empty polygon.txt
empty polygon.txt staged: gitleaks protect rc=0 (0 = NOT flagged, confirming finding 2)
--- AC8 (AMD-0007/0008): four commands
AC8 docs/amendments/AMD-0099-secret-test.md expected=1 actual=1 OK
AC8 docs/work-orders/WO-0099-token-test.md expected=1 actual=1 OK
AC8 .env expected=0 actual=0 OK
AC8 polygon.txt expected=0 actual=0 OK
--- AC9 (AMD-0008): exposure matrix, row for row (0 = ignored, 1 = not ignored)
AC9 .env expected=0 actual=0 OK
AC9 .env.local expected=0 actual=0 OK
AC9 secret.key expected=0 actual=0 OK
AC9 id.pem expected=0 actual=0 OK
AC9 polygon.txt expected=0 actual=0 OK
AC9 docs/x/polygon.txt expected=0 actual=0 OK
AC9 deep/a/b/fmp.txt expected=0 actual=0 OK
AC9 docs/x/.env expected=0 actual=0 OK
AC9 docs/secret.key expected=0 actual=0 OK
AC9 docs/id.pem expected=0 actual=0 OK
AC9 docs/credentials.json expected=0 actual=0 OK
AC9 sub/secret.md expected=0 actual=0 OK
AC9 docs/amendments/AMD-0011-secret-rotation.md expected=1 actual=1 OK
AC9 docs/work-orders/WO-0099-token-test.md expected=1 actual=1 OK
AC9 docs/runbook/OPERATIONS.md expected=1 actual=1 OK
AC9 docs/README.md expected=1 actual=1 OK
AC9 README.md expected=1 actual=1 OK
AC9 PID.md expected=1 actual=1 OK
AC9 .env.example expected=1 actual=1 OK
AC9 mismatches: 0
```
