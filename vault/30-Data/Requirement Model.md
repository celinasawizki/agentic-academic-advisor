# Requirement Model
Rule kinds: `count` (take N of options; option = list taken together, e.g. lecture+lab), `credits`, `patterns` (ranges / GenEd attributes), `manual` (unparsed prose — never guessed), `note` (reference only).

Reliability: **VERIFIED** (only from `verifications.json`) · **PENDING_VERIFICATION** (parser default) · **AMBIGUOUS** (prose, needs-review layout, catalog-year mismatch) · **UNAVAILABLE** / **BLOCKED** (set by [[Course Discovery Agent]]).

≈490 rules are manual/AMBIGUOUS. Parser: `apps/api/app/ingest/bulletin.py`. See [[ADR-004 Never guess requirements]].
