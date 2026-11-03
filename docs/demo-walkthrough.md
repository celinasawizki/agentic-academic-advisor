# Demo walkthrough (≈5 minutes)

Start the API and web app (see README). Students are fictional; programs, courses and sections are real Temple data (bulletin 2026-2027, Spring 2027 class-search snapshot).

1. **Landing** (`/`) — "Your Degree. Your Schedule. Optimized." Click **Explore Demo**.
2. **Demo** (`/demo`) — Lina Haddad: Psychology BA, Entrepreneurship & Innovation Management minor, Data Science: Computational Analytics certificate; interested in I-O Psychology and AI; works Mon/Wed 1–6 PM; prefers Fridays off; 15 credits; F-1. Click **Run the agents**.
3. **Agent workspace** — nine cards move pending → running → complete from persisted execution records. Expand *Degree Requirements* (bulletin sources) and *Course Discovery* (real exclusions: full sections, Japan/Rome-only sections, missing prerequisites, courses not offered in Spring 2027).
4. **Academic dashboard** — every bulletin rule for each program, grouped by the bulletin's headings, with "manual review" rules flagged; GenEd by attribute; PSY 3096 and STAT 2103 flagged graduation-critical.
5. **Schedules** — three CP-SAT strategies over real sections (CRNs, instructors, rooms). Click a course for its explanation: bulletin rule it may satisfy, interest match, why this section, snapshot provenance.
6. Click a **§ swap** button → the manual edit is validated by the same deterministic checks.
7. **Ask for changes:** "I got a job on Tuesdays and Thursdays from 9 to 5" → hard blocks on both days; agents re-run (iteration 2). Every open section of PSY 3096 now collides with one of her jobs: CP-SAT shows the irreducible conflict {Job, Work, graduation-critical PSY 3096} and three verified fixes (change either job, or defer PSY 3096 with the graduation risk explained).
8. **Explanation** → *How was this schedule created?*: agent summaries, constraint classes, and the review agent's checks (snapshot provenance, placement-test prerequisites, F-1 count).
9. **Save draft to TUportal (mock)** → mock draft ID with real CRNs and the notice that nobody is registered.
10. **Priya** (Computer Science BS) shows lecture + lab/recitation sections scheduled together. **Advisor view** (`/advisor`) summarizes all three students.
11. **Build my schedule** — search any of the 435 programs, add courses or upload an audit PDF, and plan.
