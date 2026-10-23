# WO-0017 AC1 — raw-payload attribution of TEL 2024-11-22 and SKYD 2026-09-15

Fetched 2026-10-22 through the audited code at 3551139 (`argus diagnose dividends --raw`, and the same raw accessor for the SKYD tickers). One Polygon call per ticker-date; the key is never printed. Payloads are verbatim: the question is what the vendor actually sent.

## TEL 2024-11-22

Stored: polygon 1.3 (the sum of two records), yfinance 0.65, ratio 2x, prior_close 150.52.

```
rows=5
symbol	date	source	n_rows_stored	stored_amount	note
TEL	2024-11-22	polygon	1	1.3	normalised polygon=1.3 yfinance=0.65 ratio=2x prior_close=150.5200 adj_close_err_pct=0.432 suspect=False
TEL	2024-11-22	yfinance	1	0.65	normalised polygon=1.3 yfinance=0.65 ratio=2x prior_close=150.5200 adj_close_err_pct=0.432 suspect=False
TEL	2024-11-22	polygon_raw	2	0.65	record 1/2 declaration_date=2024-03-13 frequency=4 verbatim: {"cash_amount": 0.65, "currency": "USD", "declaration_date": "2024-03-13", "dividend_type": "CD", "ex_dividend_date": "2024-11-22", "frequency": 4, "id": "E89b4ac9e4c8a74626d9ea08f59bf9b3e20c7fc900cf32ef2dadaf5e321ca942d", "pay_date": "2024-12-06", "record_date": "2024-11-22", "ticker": "TEL"}
TEL	2024-11-22	polygon_raw	2	0.65	record 2/2 declaration_date=2024-03-13 frequency=4 verbatim: {"cash_amount": 0.65, "currency": "USD", "declaration_date": "2024-03-13", "dividend_type": "CD", "ex_dividend_date": "2024-11-22", "frequency": 4, "id": "E0db7c55e9207d0d053fbf9370917fe59c0c4dfee0d5af8de4026cfa31983cb74", "pay_date": "2024-12-06", "record_date": "2024-11-22", "ticker": "TEL"}
TEL	2024-11-22	polygon_raw_summary	2	1.3	n_records_returned=2; cash_amounts=[0.65, 0.65]; dividend_type=["CD", "CD"]; frequency=[4, 4]; declaration_date=["2024-03-13", "2024-03-13"]; response_status=OK; response_count=None; next_url_present=False; stored_polygon_amount=1.3; stored_equals=equals_sum_of_records
```

Two records, **identical in amount (0.65), declaration_date (2024-03-13), frequency (4), dividend_type (CD), pay_date and record_date; only the id differs**. That is one quarterly dividend delivered twice. Verdict: **DUPLICATE**. yfinance's 0.65 is right, and Polygon's stored 1.3 was the doubled sum that WO-0016's key change exposed. The WO-0017 dedupe collapses it to 0.65.

## SKYD 2026-09-15

Polygon indexes the pre-rename ticker PSKY; SKYD is the canonical symbol (operator rename PSKY to SKYD).

```
TICKER PSKY status OK count 1 next_url False
{"cash_amount": 0.05, "currency": "USD", "declaration_date": "2026-07-21", "dividend_type": "CD", "ex_dividend_date": "2026-09-15", "frequency": 4, "id": "E5f2e16aeffb728ecfbe8fae826f9cf959bb15a6262aab312c89182a1b22f6121", "pay_date": "2026-10-01", "record_date": "2026-09-15", "ticker": "PSKY"}
TICKER SKYD status OK count 0 next_url False
```

Under PSKY: **one record, 0.05** (declared 2026-07-21, frequency 4). Under SKYD: **zero records**. The store holds, for this ex-date, polygon PSKY 0.05, yfinance PSKY 0.05 and yfinance SKYD 0.05 (yfinance stores the one dividend under both tickers of the renamed company). Verdict: **DUPLICATE, on the yfinance side, across the two tickers of one renamed company**: yfinance's 0.10 is the same 0.05 counted once per ticker, and Polygon's 0.05 is correct (one record). It is not an omission and not a second genuine dividend. Whether the WO-0017 dedupe collapses it depends on the two yfinance rows landing in one canonical group; AC3 in `operator-checks.md` reports what the live materialise does.

## DVN 2024-09-13 (AC1, added by AMD-0031 section 3)

Verbatim payload (ticker DVN, ex-dividend date 2024-09-13; status OK, 2 records, no next_url):

```
TICKER DVN status OK count 2 next_url False
{"cash_amount": 0.22, "currency": "USD", "declaration_date": "2024-08-06", "dividend_type": "SC", "ex_dividend_date": "2024-09-13", "frequency": 4, "id": "Pe3c430b21d4818e8b6db8c079a0b6bd4b9e3b7843eca5b937be3158674c5cf23", "pay_date": "2024-09-30", "record_date": "2024-09-13", "ticker": "DVN"}
{"cash_amount": 0.22, "currency": "USD", "declaration_date": "2024-08-06", "dividend_type": "CD", "ex_dividend_date": "2024-09-13", "frequency": 4, "id": "Eb19fea597c46e0d6b0411fb962cec49a96020fd42743cb04ea9dcadcfac23adf", "pay_date": "2024-09-30", "record_date": "2024-09-13", "ticker": "DVN"}
```

| | record 1 | record 2 |
|---|---|---|
| cash_amount | 0.22 | 0.22 |
| declaration_date | 2024-08-06 | 2024-08-06 |
| frequency | 4 | 4 |
| dividend_type | CD (id begins E) | SC (id begins P) |
| pay_date | 2024-09-30 | 2024-09-30 |

**Verdict: genuine second dividend.** Fixed (CD) plus variable/special (SC) of the same size; yfinance
carries 0.44, the sum. The two records are identical in amount, declaration date and frequency, so
the AMD-0031 key cannot separate them from TEL's duplicate and the cross-source total does
(materialise warning: `resolution=genuine (matches_sum) yfinance=0.4400 if_one=0.2200 if_all=0.4400`).

**Observation for the Architect (not acted on).** AMD-0031 states that no payload field can separate
TEL from DVN. In these two payloads one does: `dividend_type` is CD and CD for TEL's two records
(duplicate) and SC and CD for DVN's (genuine), and the stored `vendor_id` carries the same signal in
its first character (E for the CD records, P for DVN's SC record). Two cases do not make a rule and
`dividend_type` is not stored in `dividends`; the cross-source rule resolves both correctly and is
what is implemented. Whether `dividend_type` should be carried is a decision for the Architect.
