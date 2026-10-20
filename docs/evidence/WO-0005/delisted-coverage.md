# WO-0005 — Delisted-history coverage (AC1b, AMD-0015 §2B; accepted residual R5)

Free-source limitation, recorded as a named figure beside the aggregate it affects (CI-8 / DESIGN §6.1): bars for *delisted historical members* are incomplete, so any composite built from `bars_raw` must carry `n_members_with_bars` with `n_members`.

| Cohort | Requested | Written | Unavailable | Coverage |
|---|---|---|---|---|
| Current members + ETFs (AC1a, gate ≥ 99%) | 518 | 518 | 0 | **100.0%** |
| Historical-only members (AC1b, no threshold) | 237 | 110 | **127** | **46.4%** |

Source: `argus ingest bootstrap --start 2015-01-01`, yfinance, run on 2026-10-20 (see `operator-checks.md`). yfinance answers "possibly delisted; no timezone found" / 404 for these tickers.
Three of the 127 are mapped renames whose history yfinance serves only under the new ticker (BK→BNY, FI→FISV, MMC→MRSH; AMD-0014/AMD-0016 §2D — the rename-aware bars lookup is WO-0007's job and will turn these three into covered members).

Unavailable symbols (127):
`ABC,ABMD,ADS,AET,ALXN,ANDV,ANSS,ANTM,ARG,ATVI,AVP,BCR,BK,BLL,BRCM,BXLT,CA,CBS,CDAY,CELG,CERN,CFN,CMA,CMCSK,COG,COL,COV,CPGX,CTL,CTLT,CTRA,CTXS,CVC,CXO,DAY,DFS,DISCA,DISCK,DISH,DNR,DRE,DWDP,ENDP,ESRX,ESV,ETFC,EVHC,FBHS,FDO,FI,FL,FLIR,FLT,FRC,FTR,GGP,GMCR,GPS,HBI,HCBK,HES,HFC,HOLX,HRS,HSP,IPG,JEC,JNPR,JOY,JWN,K,KORS,KRFT,KSU,LLTC,LM,LO,LVLT,MJN,MMC,MRO,MWV,MXIM,MYL,NBL,NLOK,NLSN,PBCT,PDCO,PEAK,PETM,PKI,PXD,QEP,RAI,RE,RHT,RTN,SCG,SEE,SIAL,SIVB,SNI,SRCL,STJ,SWN,SWY,SYMC,TGNA,TIF,TMK,TSS,TWC,TWTR,TWX,UTX,VAR,VIAB,VIAC,WBA,WCG,WFM,WIN,WLTW,WRK,XEC,XLNX`

Consequence for downstream work (DESIGN §6.1, AMD-0015 §2B): the equal-weight composite is computed over members *with bars*; `n_members_with_bars` is stored beside `n_members` for every date; a date under 95% coverage is flagged and excluded from the PID-ARGUS-0004 lead-time study unless explicitly included.
