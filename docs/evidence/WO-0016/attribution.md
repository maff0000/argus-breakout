# WO-0016 AC1 — attribution of all thirteen pairs

Live, read-only (attribute_pairs), one Polygon call per pair, on a scratch copy of the store migrated to schema 6. API key never printed. Verdicts: 13 collapse, 0 omission, 0 neither. No pair is left unattributed and nothing was a stop.

| symbol | ex-date | records | amounts | summed | other source (yfinance) | verdict |
|---|---|---|---|---|---|---|
| CME | 2026-03-10 | 2 | [1.3, 6.15] | 7.450 | 7.45 | collapse |
| COP | 2024-08-12 | 2 | [0.2, 0.58] | 0.780 | 0.78 | collapse |
| DVN | 2024-06-14 | 2 | [0.13, 0.22] | 0.350 | 0.35 | collapse |
| EXE | 2024-05-15 | 2 | [0.14, 0.575] | 0.715 | 0.715 | collapse |
| FANG | 2024-05-14 | 2 | [0.9, 1.07] | 1.970 | 1.97 | collapse |
| FANG | 2024-08-15 | 2 | [0.9, 1.44] | 2.340 | 2.34 | collapse |
| HP | 2024-02-12 | 2 | [0.17, 0.25] | 0.420 | 0.42 | collapse |
| HP | 2024-05-16 | 2 | [0.17, 0.25] | 0.420 | 0.42 | collapse |
| PGR | 2025-01-10 | 2 | [0.1, 4.5] | 4.600 | 4.6 | collapse |
| PGR | 2026-01-02 | 2 | [0.1, 13.5] | 13.600 | 13.6 | collapse |
| WRB | 2024-09-23 | 2 | [0.08, 0.25] | 0.330 | 0.33 | collapse |
| WRB | 2024-12-16 | 2 | [0.08, 0.5] | 0.580 | 0.58 | collapse |
| WRB | 2025-12-15 | 2 | [0.09, 1.0] | 1.090 | 1.09 | collapse |

Record ids (verbatim) are in attribution-output.md. Every id is a real vendor id (none None). The mechanism for all 13 is the same: Polygon returns a regular dividend plus a second record (special/variable component) for one ex-date; the old key (symbol,date,source) kept one. FCX (WO-0015) is not among them: it is a genuine Polygon omission outside the >2x population; the 2D rule handles it on re-materialise.
