# WO-0015 dividend mechanism (AC1, AC2)

Run on a scratch copy of the store (WO-0014 re-materialised), read-only. One live Polygon call per --raw invocation.

## AC1 — PGR 2026-01-02 (verbatim, key never printed)
~~~
PGR	2026-01-02	polygon_raw	record 1/2 verbatim: {"cash_amount": 0.1, "currency": "USD", "declaration_date": "2025-12-08", "dividend_type": "CD", "ex_dividend_date": "2026-01-02", "frequency": 4, "id": "E4c0de545f3b1e8ad834cd6523691f749e15a899b0adf7809d4b85b19018c2e0b", "pay_date": "2026-01-08", "record_date": "2026-01-02", "ticker": "PGR"}
PGR	2026-01-02	polygon_raw	record 2/2 verbatim: {"cash_amount": 13.5, "currency": "USD", "declaration_date": "2025-12-05", "dividend_type": "CD", "ex_dividend_date": "2026-01-02", "frequency": 1, "id": "E28292ad85a329679827a20a8465fd6fb0ef85e3b957c927c2e7177c596c335fa", "pay_date": "2026-01-08", "record_date": "2026-01-02", "ticker": "PGR"}
PGR	2026-01-02	polygon_raw_summary	n_records_returned=2; cash_amounts=[0.1, 13.5]; dividend_type=["CD", "CD"]; frequency=[4, 1]; response_status=OK; response_count=None; next_url_present=False; stored_polygon_amount=0.1; stored_equals=equals_one_record
~~~

Polygon returns TWO records for one ex-date: a quarterly 0.10 (frequency 4) and an annual special 13.50 (frequency 1). The store holds ONE polygon row (0.10, equals_one_record); yfinance holds 13.60 = the SUM. Collapse CONFIRMED for PGR: the primary key (symbol,date,source) keeps one record and the other is lost.

## AC1 — FCX 2026-07-15 (a quarterly ex-date)
~~~
FCX	2026-07-15	polygon_raw	record 1/1 verbatim: {"cash_amount": 0.075, "currency": "USD", "declaration_date": "2026-06-24", "dividend_type": "CD", "ex_dividend_date": "2026-07-15", "frequency": 4, "id": "Ebcf40fbc63dce9b48996dfce92871dbd804c417448cf938fd0781493e3c4669a", "pay_date": "2026-08-03", "record_date": "2026-07-15", "ticker": "FCX"}
FCX	2026-07-15	polygon_raw_summary	n_records_returned=1; cash_amounts=[0.075]; dividend_type=["CD"]; frequency=[4]; response_status=OK; response_count=None; next_url_present=False; stored_polygon_amount=0.075; stored_equals=equals_the_single_record
~~~

Polygon returns ONE record (0.075); stored equals it. yfinance stores 0.15 for every FCX quarter. NO collapse for FCX: Polygon itself does not carry the second 0.075 (the performance-based component). The FCX disagreement is an upstream Polygon completeness gap, not the PGR mechanism. The hypothesis "same-ex-date records collapse" is therefore CONFIRMED for PGR and REFUTED for FCX; two distinct mechanisms.

## AC2 — population of >2x disagreements (full store)
26 rows = 13 (symbol, ex_date) pairs, file dividends-population-output.tsv: CME 2026-03-10; COP 2024-08-12; DVN 2024-06-14; EXE 2024-05-15; FANG 2024-05-14, 2024-08-15; HP 2024-02-12, 2024-05-16; PGR 2025-01-10, 2026-01-02; WRB 2024-09-23, 2024-12-16, 2025-12-15. adj_close_err_pct ranges 0.43% to 5.93% (PGR 2026-01-02 is the max). Only PGR 2026-01-02 was fetched raw, so the mechanism is established for that pair only; the other 12 pairs are not yet attributed to the PGR mechanism or to a Polygon completeness gap (the FCX type). FCX is not in the population (exactly 2.0x, not above).
