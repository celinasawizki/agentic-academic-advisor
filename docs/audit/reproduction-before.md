# Reproduction log (before fixes)

Captured against the running API at commit 48d0752.

### Create real student
`POST /api/students` → **200**
```
{"id":"stu-03e0e3ebf7"}
```

### Read real student with NO credentials
`GET /api/students/stu-03e0e3ebf7` → **200**
```
{"id":"stu-03e0e3ebf7","name":"Real Student Test","is_demo":false,"academic_year":"Junior","expected_graduation":"2028-05","catalog_year":null,"planning_term":"202703","program_ids":["psychology-ba"],"campus":"Main","f1_status":"prefer_not","interests_text":"","transcript":[{"course":"PSY 1001","sta
```

### Read real student's plan with NO credentials
`GET /api/plans/plan-c923a7672a` → **200**
```
{"id":"plan-c923a7672a","status":"complete","term_id":"202703","student_id":"stu-03e0e3ebf7","iteration":1,"agents":[{"id":118,"agent":"academic_profile","title":"Academic Profile Agent","responsibility":"Interprets transcript and degree-audit records, separates completed from in-progress work, and 
```

### Modify real student's plan with NO credentials
`POST /api/plans/plan-c923a7672a/modify` → **200**
```
{"applied":["Credit target set to 12"],"assumptions":[],"unclear":[],"mode":"deterministic","rerun":true}
```

### Demo advisor role reviews REAL student's plan
`POST /api/advisor/reviews` → **200**
```
{"ok":true}
```

### Export real student's plan to mock TUportal with NO credentials
`POST /api/integration/tuportal/drafts` → **200**
```
{"draft":{"draft_id":"MOCK-DRAFT-2B26B536","student_id":"stu-03e0e3ebf7","term_id":"202703","crns":["27717","36794","2105","40577","10750","22249"],"environment":"MOCK planning environment (not TUportal)","registered":false},"validation":{"draft_id":"MOCK-DRAFT-2B26B536","valid":true,"mock":true,"me
```

### Validate lecture+lab of 4-credit PHYS 1021 (202703-PHYS1021-003, 202703-PHYS1021-041)
`POST /api/plans/plan-8a2b47dbd9/validate` → **200**
```
{"valid":false,"checks":[{"check":"unique_courses","passed":false,"severity":"error","detail":"Duplicate course in schedule."},{"check":"components","passed":true,"severity":"info","detail":"Every lab/recitation is paired with its course."},{"check":"time_conflicts","passed":true,"severity":"info","
```

Reported credits: **8.0** (expected 4)

### Validate PHYS 1021 lecture WITHOUT its lab (202703-PHYS1021-003)
`POST /api/plans/plan-8a2b47dbd9/validate` → **200**
```
{"valid":false,"checks":[{"check":"unique_courses","passed":true,"severity":"info","detail":"Each course (and course component) appears once."},{"check":"components","passed":true,"severity":"info","detail":"Every lab/recitation is paired with its course."},{"check":"time_conflicts","passed":true,"s
```

Valid without required lab: **False**; failing checks: ['credit_range', 'prereq:PHYS 1021', 'section_provenance', 'requirement_provenance']

### Validate a section unrelated to any requirement (ART 1001 style pick: first non-eligible section id)
`POST /api/plans/plan-8a2b47dbd9/validate` → **200**
```
{"valid":false,"checks":[{"check":"unique_courses","passed":true,"severity":"info","detail":"Each course (and course component) appears once."},{"check":"components","passed":true,"severity":"info","detail":"Every lab/recitation is paired with its course."},{"check":"time_conflicts","passed":true,"s
```

### Two simultaneous modify requests
status codes: **[200, 200]** (both 200 means one change overwrote the other's run)

### Preference persistence
Set credit target 13 on plan plan-c923a7672a; new plan for the same student starts with **15**

### Delete real student with NO credentials
`DELETE /api/students/stu-03e0e3ebf7` → **200**
```
{"deleted":"stu-03e0e3ebf7"}
```

### Rule-level reproductions (python, before fixes)

- PSY 1001 completed with grade **F** → prerequisite status `satisfied` (minimum grade C- in bulletin)
- PSY 1001 completed with grade **D** → prerequisite status `satisfied` (minimum grade C- in bulletin)
- PSY 1001 completed with grade **W** → prerequisite status `satisfied` (minimum grade C- in bulletin)
- Requirement 'PSY 1001' with an **F** on the transcript → `complete`
- Soft penalty of a Mon 8 AM section when the student marked Mon 12–4 PM as *preferred*: `0` (preferred blocks are ignored)
- Snapshot sections with Banner `isSectionLinked`=true: **0** of 8690; variable-credit sections (credits_high set): **2194**; cross-list field stored: **False**
