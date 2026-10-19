# WO-0010 — Operator checks

Run by the Delivery Controller on dell-debian (execution host) against the final head. No real credential appears
below; dummy credential files contain the documented fake `AKIAIOSFODNN7EXAMPLE`. No host/port/key value is involved.

```
host=dell-debian cwd=/srv/argus-breakout-wt/WO-0010 head=57b0817447c220e31c90c11ae25f529e82ef59e7
$ git check-ignore -q polygon.txt  (AC1)
exit=0  (0 = ignored)
$ git check-ignore -v polygon.txt
.gitignore:41:/*.txt	polygon.txt
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
--- AC8 (AMD-0007): governance docs never ignored; .env and polygon.txt still ignored
git check-ignore -q docs/amendments/AMD-0099-secret-test.md  exit=1
git check-ignore -q docs/work-orders/WO-0099-token-test.md  exit=1
git check-ignore -q .env  exit=0
git check-ignore -q polygon.txt  exit=0
(AMD-0099 and WO-0099 paths do not exist; expected exits: 1 1 0 0)
```
