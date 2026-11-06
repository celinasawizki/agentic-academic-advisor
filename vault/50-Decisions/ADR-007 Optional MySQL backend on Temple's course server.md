# ADR-007 Optional MySQL backend on Temple's course server

**Date:** 2026-11-05 · **Status:** accepted

## Context
The instructor provided an account on `dataanalytics.temple.edu` (MySQL 8.0, strict SQL mode). The account starts empty and may create a fixed set of databases. The app had only ever run on SQLite.

## Decision
`DATABASE_URL` selects the backend. SQLite stays the default so the project runs anywhere; MySQL is used through `mysql+pymysql://…`. Credentials live only in the gitignored `.env`.

## Consequences
- `app.models.DateTime` stores naive UTC with microseconds on MySQL (its DATETIME drops the timezone and, by default, fractions of a second, which made `created_at` ordering tie) and always returns aware UTC.
- Strict mode exposed values SQLite had silently accepted: `schedule_options.review_status` held `checks_passed_with_warnings` in a 20-character column (widened to 40), and `total_credits` was an Integer column receiving fractional credits (now Float).
- The additive migration quotes identifiers with the dialect's quoting (MySQL rejects `"col"`).
- Remote connections use `pool_pre_ping` and `pool_recycle` because the server closes idle connections.
- `TEST_DATABASE_URL` runs the suite against MySQL (172/172 passed); the default suite stays on SQLite.
- Anyone with the account sees the same students and plans: fictional data only unless agreed.
