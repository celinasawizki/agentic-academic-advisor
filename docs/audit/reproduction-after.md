# Reproduction log (after fixes)

Same scenarios as reproduction-before.md, against the fixed API.

- Read real student, no credentials: `GET /api/students/stu-79daf0fffeb34268a3f4` → **404**
- Read real student, owner token: `GET /api/students/stu-79daf0fffeb34268a3f4` → **200**
- Create plan for real student, no credentials: `POST /api/plans` → **404**
- Read real plan, no credentials: `GET /api/plans/plan-cdaca329482a461d972b` → **404**
- Modify real plan, no credentials: `POST /api/plans/plan-cdaca329482a461d972b/modify` → **404**
- Demo advisor reviews REAL plan: `POST /api/advisor/reviews` → **404**
- Export real plan, no credentials: `POST /api/integration/tuportal/drafts` → **404**
- Export real plan, owner but no approval: `POST /api/integration/tuportal/drafts` → **422**
- Validate PHYS 1021 lecture + lab: credits **4.0** (was 8.0)
- Validate PHYS 1021 lecture only: component warning present **True**
- Two simultaneous modify requests: **[200, 409]** (was [200, 200])
- New plan after setting credit target 13 starts with **13** (was 15)
- Delete real student, no credentials: `DELETE /api/students/stu-79daf0fffeb34268a3f4` → **404**
- Delete real student, owner token: `DELETE /api/students/stu-79daf0fffeb34268a3f4` → **200**
