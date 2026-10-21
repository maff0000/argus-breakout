# WO-0013 — AMD-0019 §2H: the second logger in `store.py`

## What `_stdlog` was
`_stdlog = logging.getLogger(__name__)` in `argus/data/store.py`, added by the WO-0007 merge resolution beside the structlog `log`. It had **one** call site: a WARNING when a read-write `connect()` repaired a relocated store's views (`"store relocated: recorded %r, now %r; views recreated"`).

## Did it pass the redaction processor?
**No.** `argus/logging.py` configures structlog with a `PrintLoggerFactory` and a JSON renderer plus the redaction processor, and installs **no stdlib handler**. A stdlib record with no handler goes to Python's last-resort handler: plain text on **stderr**, outside the JSON channel and outside redaction. (The line carried directory paths, not secrets, so nothing leaked; but the channel was the wrong one and would have bypassed redaction for any future call.)

## Did anything require it?
No. No test used `caplog`; no other module read it.

## What was done
Removed `_stdlog` and `import logging` from `store.py`; the one message now goes through the structlog channel as `log.warning("store_relocated", recorded=..., current=..., action="views_recreated")`. A test (`test_store_has_a_single_logging_channel`) asserts `_stdlog` is gone. `import logging` remains only in `argus/logging.py`, the configuration module. Auditor confirmed. One structured JSON channel to stdout (PID §8.3, CI-7).
