# WO-0005 — Operator checks (live, host-run)

Live run of `argus ingest bootstrap --start 2015-01-01` at head `abdb1a2` (the code under audit at the time; `2c5a8a2` changes only the exit-code expression, which the live run did not exercise because no symbol was skipped on a fresh store).
The store was seeded with WO-0003's real `universe refresh` output (no scaffold). Nothing secret is involved (yfinance needs no key).

## AC1 — **NOT MET** (needs an Architect ruling)
Requested = `symbols` ∪ historical `membership` = **755** symbols (518 in `symbols` + 237 historical-only).
```
symbols=628 rows=1743171 skipped=0 failed=127     wall=333.5s    exit code 1
```
628 / 755 = **83.2%** written, against the AC1 target of ≥ 98%. All 127 failures are historical-only members (none is in `symbols`; 0 current members or ETFs failed): delisted, acquired or renamed names for which yfinance holds no data under that ticker
("possibly delisted; no timezone found"). Three are mapped renames (BK, FI, MMC — yfinance serves their history only under the new ticker; AMD-0014). The failed list:
`ABC,ABMD,ADS,AET,ALXN,ANDV,ANSS,ANTM,ARG,ATVI,AVP,BCR,BK,BLL,BRCM,BXLT,CA,CBS,CDAY,CELG,CERN,CFN,CMA,CMCSK,COG,COL,COV,CPGX,CTL,CTLT,CTRA,CTXS,CVC,CXO,DAY,DFS,DISCA,DISCK,DISH,DNR,DRE,DWDP,ENDP,ESRX,ESV,ETFC,EVHC,FBHS,FDO,FI,FL,FLIR,FLT,FRC,FTR,GGP,GMCR,GPS,HBI,HCBK,HES,HFC,HOLX,HRS,HSP,IPG,JEC,JNPR,JOY,JWN,K,KORS,KRFT,KSU,LLTC,LM,LO,LVLT,MJN,MMC,MRO,MWV,MXIM,MYL,NBL,NLOK,NLSN,PBCT,PDCO,PEAK,PETM,PKI,PXD,QEP,RAI,RE,RHT,RTN,SCG,SEE,SIAL,SIVB,SNI,SRCL,STJ,SWN,SWY,SYMC,TGNA,TIF,TMK,TSS,TWC,TWTR,TWX,UTX,VAR,VIAB,VIAC,WBA,WCG,WFM,WIN,WLTW,WRK,XEC,XLNX`
This is a data-availability limit of the source (survivorship), not an implementation defect (fault isolation worked: the run completed, listed them, and wrote 628 symbols / 1,743,171 rows). The spec as written ("≥ 98% of symbols in `symbols` ∪ historical `membership`") cannot be met from yfinance.
**Ruling needed**: restrict the AC1 denominator (e.g. current members + ETFs + historical members with data), name a second source for delisted names, or accept an explicit failed-list ceiling.

## AC2 — met, with exceptions listed
Every active symbol (current members and ETFs) has ≥ 2,400 `bars_raw[source='yfinance']` rows for 2015-01-01…2024-12-31 **except 47**, every one of which listed/IPO'd/was spun off after 2015-01-10 (first bar date shown), i.e. the reason the WO names:
```
AC2 exceptions (symbol, rows 2015-2024, first bar, last bar): 47
first bar after 2015-01-10 or none: 47
others (listed from the start but <2400 rows): []
KHC 2390 2015-07-06
PYPL 2390 2015-07-06
LITE 2377 2015-07-23
P 2325 2015-10-06
XLRE 2323 2015-10-08
HPE 2316 2015-10-19
XYZ 2293 2015-11-19
TWLO 2145 2016-06-23
FTV 2138 2016-07-05
DELL 2107 2016-08-17
VST 2073 2016-10-05
HWM 2054 2016-11-01
INVH 1992 2017-02-01
CVNA 1932 2017-04-28
IR 1922 2017-05-12
VICI 1761 2018-01-02
XLC 1645 2018-06-19
BE 1620 2018-07-25
VRT 1614 2018-08-02
MRNA 1526 2018-12-07
FOXA 1463 2019-03-12
FOX 1462 2019-03-13
DOW 1457 2019-03-20
UBER 1421 2019-05-10
CRWD 1399 2019-06-12
DDOG 1330 2019-09-19
CARR 1205 2020-03-19
OTIS 1205 2020-03-19
PLTR 1070 2020-09-30
DASH 1021 2020-12-09
ABNB 1020 2020-12-10
EXE 979 2021-02-10
COIN 936 2021-04-14
APP 935 2021-04-15
HOOD 862 2021-07-29
CEG 742 2022-01-19
GEHC 513 2022-12-15
KVUE 418 2023-05-04
VLTO 313 2023-10-04
RDDT 197 2024-03-21
SOLV 194 2024-03-26
GEV 193 2024-03-27
SNDK 0 2025-02-13
Q 0 2025-10-27
FDXF 0 2026-05-27
HONA 0 2026-06-15
VYLR 0 2026-10-01
```
(Count line: 47 exceptions; 0 "listed from the start but short".)

## AC3 — met
`splits` rows with `source='yfinance'`: **207**; `dividends` rows with `source='yfinance'`: **20,843**. Same-date split + dividend retained (join on symbol, date, source): **3** — XRX 2017-01-03 (ratio 1.518, cash 2.98), DHR 2016-07-05 (1.319, 24.56), DXC 2015-11-30 (1.7412, 9.083045).

## AC4 — tests (see `tests.md`, `audit.md`)
