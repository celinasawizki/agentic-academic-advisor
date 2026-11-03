# Integrations and their status

| System | Status in MVP | Adapter | What a real integration needs |
|---|---|---|---|
| Temple Degree Audit (sites.temple.edu/degreeaudit) | Not connected. Behind university authentication; no public API. | `adapters/degree_audit.py` — local PDF parser + `TempleDegreeAuditAdapter` stub | Authorized API or export (e.g. via a TUportal test environment). Never scrape or bypass auth. |
| Academic Bulletin | Demo fixtures for Psychology BA, Entrepreneurship minor, CS certificate, GenEd (catalog 2024-2025), marked `demo_unverified`. | `adapters/catalog.py` — `DbCatalogAdapter`, `BulletinIngestionAdapter` stub | Ingest official pages into `ProgramRequirement` with source URL, retrieval time and catalog year; queue ambiguous rules as `needs_review`; human verification before `verified`. |
| Course Search (Banner SSB) | Not connected. Session-based app without a documented open API. Spring 2027 demo sections labeled `demo_fixture`. | `adapters/course_search.py` — `DemoFixtureCourseSearchAdapter`, `TempleBannerCourseSearchAdapter` stub | An authorized endpoint or data export. Section IDs must stay stable; record retrieval time for freshness. |
| TUportal | Mock only. Drafts saved to `integration_status`; nobody is registered. | `adapters/tuportal.py` — `TUportalAdapter` interface, `MockTUportalAdapter` | Test-environment credentials and API docs. Implement `getStudentProfile, getDegreeAudit, getAcademicHistory, getAvailableSections, getRegistrationRestrictions, createDraftSchedule, validateDraftSchedule, getDraftSchedule`. Registration stays a separate, explicitly authorized action. |
| Ambler, Rome, Japan campuses | Shown in onboarding as future; in-person sections at unsupported campuses are excluded by Course Discovery. | `rules.SUPPORTED_CAMPUSES` | Campus-specific section data and rules. |
| Anthropic Claude | Optional (`ANTHROPIC_API_KEY`). | `agents/llm.py` | Institutional data agreement before sending any student education records (`LLM_MAY_RECEIVE_STUDENT_RECORDS`). |

To add a program, add it to `data/demo/programs.json` (or ingest it) with requirements, catalog year and source; set `supported: true`. No code changes are needed.
