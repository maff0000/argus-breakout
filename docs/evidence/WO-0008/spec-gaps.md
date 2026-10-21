# WO-0008 — Spec gaps and residuals

1. **Scale facts, measured (WO §8):** IBKR daily volume is in shares; IV/HV series are decimals (0.13 = 13%); `formatDate=2` epoch converts to the correct exchange date.
2. **Paper-port guard in practice:** the project `.env` port is not an allowlisted paper port. The guard works as designed; the nightly job (WO-0009) needs `IB_PORT` set to the paper-gateway port, which is the PO's configuration change, not the chain's. The host also exposes a second gateway on loopback that serves the live port; nothing here touches it.
3. **Priority-flag resolution rule:** the Implementer treats a flag as resolved once `reconcile_log` holds a `close` row for that symbol and the flagged date. Reasonable, not in the WO text; keeps a flag from being re-sampled forever. Flag for ratification.
4. **Sliding-window pacer** (50 requests per 10 minutes) replaces the WO's `RateLimiter` (a token bucket permits ~55). Within the pacing intent; flagged.
5. **`tests/fakes/__init__.py`** (empty) is outside §2; needed for imports. Clerical.
6. **Qualify call:** each history request also issues `qualifyContracts` (a contract lookup, not an account/order call). It counts against IBKR pacing separately; the nightly budget is 20 + 13×2 = 46 history requests: inside the 50-per-10-minutes limit with 4 to spare, so any growth in the sample or the ETF list makes the pacer sleep.
7. **Audit observation:** `test_cli_disconnects_on_provider_error` is weak (accepts exit 1 or 2).
