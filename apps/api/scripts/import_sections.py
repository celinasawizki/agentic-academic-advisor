"""One-time snapshot of a term's sections from Temple's public class search
(Banner 9 Student Registration SSB, no login). Rate limited to 1 request/second.
Run only with permission; the result is committed as data/temple/sections-<term>.json
so the app never contacts Temple at runtime.

    python -m scripts.import_sections 202703     (from apps/api)
"""

import html as htmllib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.sections import modality  # noqa: E402
from scripts.http_cache import PoliteClient  # noqa: E402

SSB = "https://prd-xereg.temple.edu/StudentRegistrationSsb/ssb"
OUT = Path(__file__).resolve().parents[3] / "data" / "temple"
DAY_KEYS = [("monday", "M"), ("tuesday", "T"), ("wednesday", "W"), ("thursday", "R"), ("friday", "F"), ("saturday", "S"), ("sunday", "U")]
PAGE = 500


def hhmm(t: str | None) -> str | None:
    return f"{t[:2]}:{t[2:]}" if t and len(t) == 4 else None


def slim(x: dict) -> dict:
    meetings = []
    for mf in x.get("meetingsFaculty") or []:
        mt = mf.get("meetingTime") or {}
        days = "".join(code for key, code in DAY_KEYS if mt.get(key))
        start, end = hhmm(mt.get("beginTime")), hhmm(mt.get("endTime"))
        if days and start and end:
            meetings.append({"days": days, "start": start, "end": end, "type": mt.get("meetingTypeDescription"),
                             "building": mt.get("buildingDescription"), "room": mt.get("room")})
    primary = [f["displayName"] for f in x.get("faculty") or [] if f.get("primaryIndicator")]
    return {
        "id": f"{x['term']}-{x['subject']}{x['courseNumber']}-{x['sequenceNumber']}",
        "crn": x["courseReferenceNumber"], "course": f"{x['subject']} {x['courseNumber']}", "section": x["sequenceNumber"],
        "title": htmllib.unescape(x.get("courseTitle") or ""), "credits": x.get("creditHourLow") or x.get("creditHours"),
        "credits_high": x.get("creditHourHigh"), "campus": htmllib.unescape(x.get("campusDescription") or ""),
        "modality": modality(x.get("instructionalMethod"), x.get("instructionalMethodDescription")),
        "instructional_method": x.get("instructionalMethodDescription"), "schedule_type": x.get("scheduleTypeDescription"),
        "instructor": ", ".join(primary) or "Staff", "seats_available": x.get("seatsAvailable"),
        "max_enrollment": x.get("maximumEnrollment"), "wait_count": x.get("waitCount"), "open": x.get("openSection"),
        "linked": bool(x.get("isSectionLinked")), "link_identifier": x.get("linkIdentifier"), "part_of_term": x.get("partOfTerm"),
        "attributes": [a.get("code") for a in x.get("sectionAttributes") or [] if a.get("code")], "meetings": meetings,
    }


def main(term: str) -> None:
    http = PoliteClient(delay=1.0)
    c = http.raw()
    http.throttle()
    terms = c.get(f"{SSB}/classSearch/getTerms", params={"searchTerm": "", "offset": 1, "max": 20}).json()
    term_desc = next((t["description"] for t in terms if t["code"] == term), None)
    if not term_desc:
        sys.exit(f"Term {term} not published in class search")
    http.throttle()
    subjects = c.get(f"{SSB}/classSearch/get_subject", params={"searchTerm": "", "term": term, "offset": 1, "max": 1000}).json()
    print(f"{term_desc}: {len(subjects)} subjects")
    http.throttle()
    c.get(f"{SSB}/term/termSelection", params={"mode": "search"})
    http.throttle()
    c.post(f"{SSB}/term/search", params={"mode": "search"}, data={"term": term, "studyPath": "", "studyPathText": "", "startDatepicker": "", "endDatepicker": ""})

    sections = []
    for i, subj in enumerate(subjects, 1):
        offset = 0
        while True:
            http.throttle()
            c.post(f"{SSB}/classSearch/resetDataForm")
            http.throttle()
            r = c.get(f"{SSB}/searchResults/searchResults", params={
                "txt_subject": subj["code"], "txt_term": term, "startDatepicker": "", "endDatepicker": "",
                "pageOffset": offset, "pageMaxSize": PAGE, "sortColumn": "subjectDescription", "sortDirection": "asc"})
            if r.status_code != 200:
                time.sleep(10)
                continue
            body = r.json()
            data = body.get("data") or []
            sections += [slim(x) for x in data]
            offset += PAGE
            if offset >= (body.get("totalCount") or 0) or not data:
                break
        if i % 20 == 0:
            print(f"  {i}/{len(subjects)} subjects, {len(sections)} sections")

    meta = {"source": "Temple University public class search (Banner SSB)", "url": f"{SSB}/classSearch/classSearch",
            "term": term, "term_description": term_desc, "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notice": "Point-in-time snapshot. Seats, times and instructors change; verify in TUportal before registering."}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"sections-{term}.json").write_text(json.dumps({"_meta": meta, "sections": sections}, indent=0))
    print(f"Wrote {len(sections)} sections to {OUT / f'sections-{term}.json'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "202703")
