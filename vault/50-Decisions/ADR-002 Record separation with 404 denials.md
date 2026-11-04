# ADR-002 Record separation with 404 denials
**Status:** accepted (audit, Nov 2026 — fixes B1, B2)
**Decision:** Three principal classes (anonymous/fictional, real owner-token, demo advisor → fictional only) behind `AuthProvider`. Denials return 404 so IDs can't be probed. Tokens hashed.
**Consequences:** Temple SSO plugs into `TempleSSOProvider`; localStorage token is a prototype stand-in. See [[Auth & Privacy]].
