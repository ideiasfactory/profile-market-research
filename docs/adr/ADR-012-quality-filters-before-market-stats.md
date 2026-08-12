# ADR-012 — Quality Filters Before Market Stats

Decision: before market statistics, observations pass seniority compatibility checks, salary-period sanitization, absolute BRL plausibility bounds, and post-normalization exclusion of implausible values (`app.compensation.services.quality`). Outliers are then marked with IQR fences when the usable sample has `N >= 5` (`app.compensation.services.statistics`).

Reason: noisy pages and seniority mismatches distort percentiles more than missing data; filtering early keeps the Python compensation engine auditable and conservative.
