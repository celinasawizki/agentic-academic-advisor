# Auth & Privacy
File: `apps/api/app/core/auth.py` (pluggable `AuthProvider`; `TempleSSOProvider` stub).

| Principal | Can see |
|---|---|
| Anonymous | Fictional demo students |
| Real student (token) | Own records only |
| Demo advisor (`X-Demo-Role: advisor`) | Fictional students only |

- Tokens stored as SHA-256 hashes; denials return **404** so IDs can't be probed; IDs 80 bits.
- Consent before processing; uploads PDF ≤5 MB, parsed in memory, never stored/logged.
- `DELETE /api/students/{id}` removes plans, agent logs, options, validations.
- Not FERPA-reviewed; browser localStorage token is a stand-in for SSO.

Related: [[ADR-002 Record separation with 404 denials]].
