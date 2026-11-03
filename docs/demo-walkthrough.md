# Demo walkthrough (≈5 minutes)

Start the API and web app (see README). All data is fictional / demo.

1. **Landing** (`/`) — "Your Degree. Your Schedule. Optimized." Click **Explore Demo**.
2. **Demo** (`/demo`) — Lina Haddad: Psychology major, Entrepreneurship minor, CS certificate, interested in I-O Psychology and AI, works Mon/Wed 1–6 PM, prefers Fridays off, 15 credits, Main Campus, F-1. Click **Run the agents**.
3. **Agent workspace** — nine cards move pending → running → complete from persisted execution records. Expand *Course Discovery* to see each exclusion (Ambler section, PSY 4996 missing PSY 2201). Expand *Degree Requirements* to see sources marked `demo_unverified`.
4. **Academic dashboard** — progress per program (in-progress shown separately), interest themes and top matches with reasons, PSY 2201 flagged graduation-critical.
5. **Schedules** — banner: *"We couldn't find a schedule that satisfies all your preferences."* CP-SAT's irreducible conflict set: *Prefer Fridays off* + *Work* + *graduation-critical PSY 2201*. Resolution options, each re-solved:
   - Give up Fridays off for this term (Graduation Priority option, PSY 2201 Friday 9 AM).
   - Change the hard work block (requires explicit input).
   - Defer PSY 2201 (keeps preferences; graduation risk explained; no approved alternative exists for a required course).
   Compare the three options (credits, degree progress, interest alignment, preferences met, F-1 count, review status).
6. Click a course block → explanation panel: requirement (pending verification), interest reason, schedule fit, why this section beat the others, CRN and data source.
7. Click a **§ swap** button on a course → manual edit is validated by the same deterministic checks (try PSY 2201 §001 to see the hard-availability failure).
8. **Ask for changes:** "Give me Fridays off" → parsed into a *hard* Friday block; agents re-run (iteration 2). Graduation Priority becomes infeasible and the solver explains why; the other strategies avoid Friday. Try "I got a job on Tuesdays" (assumed 9–5, flagged) and "I want to take 18 credits instead".
9. **Explanation** → *How was this schedule created?*: agent summaries, constraint classes, and the review agent's checks.
10. **Save draft to TUportal (mock)** → mock draft ID and CRNs, with the notice that nobody is registered.
11. **Advisor view** (`/advisor`) — caseload summary, unresolved requirements, conflicts, review status; approve or request changes.
