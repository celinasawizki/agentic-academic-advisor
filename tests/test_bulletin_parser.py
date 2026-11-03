from app.ingest.bulletin import parse_course_blocks, parse_prereqs, parse_requirement_tables, program_type

TABLE = """<h2>Major Requirements</h2>
<table class="sc_courselist"><tbody>
<tr class="even areaheader firstrow"><td colspan="2"><span class="courselistcomment areaheader">Introductory Courses</span></td><td></td></tr>
<tr class="odd"><td class="codecol"><a href="/search/?P=PSY%201001" class="bubblelink code">PSY 1001</a></td><td>Introduction to Psychology</td><td class="hourscol">3</td></tr>
<tr class="orclass odd"><td class="codecol"><div style="margin-left:20px;" class="blockindent">or <a href="/search/?P=PSY%201901" class="bubblelink code">PSY 1901</a></div></td><td>Honors</td><td class="hourscol"></td></tr>
<tr class="even"><td class="codecol"><a class="bubblelink code">CHEM 1031</a>&amp; <a class="bubblelink code">CHEM 1033</a></td><td>General Chemistry I and Lab</td><td class="hourscol">4</td></tr>
<tr class="odd areaheader"><td colspan="2"><span class="courselistcomment areaheader">Foundations</span></td><td></td></tr>
<tr class="even"><td colspan="2" class="codecol"><span class="courselistcomment">Select two of the following:</span></td><td class="hourscol">6</td></tr>
<tr class="odd"><td class="codecol"><a class="bubblelink code">PSY 2201</a></td><td>A</td><td></td></tr>
<tr class="even"><td class="codecol"><a class="bubblelink code">PSY 2301</a></td><td>B</td><td></td></tr>
<tr class="odd"><td class="codecol"><a class="bubblelink code">PSY 2401</a></td><td>C</td><td></td></tr>
<tr class="even"><td colspan="2" class="codecol"><span class="courselistcomment">Select 9 credits from the following:</span></td><td class="hourscol">9</td></tr>
<tr class="odd"><td class="codecol"><a class="bubblelink code">SGM 3002</a></td><td>A</td><td></td></tr>
<tr class="odd"><td colspan="2" class="codecol"><span class="courselistcomment">Two electives chosen from the menu of the General Business Studies minor</span></td><td class="hourscol">6</td></tr>
<tr class="listsum"><td colspan="2">Total Credit Hours</td><td class="hourscol">22</td></tr>
</tbody></table>"""


def test_parse_requirement_table():
    reqs = parse_requirement_tables(TABLE)
    intro, bundle, select, credits, manual = reqs
    assert intro.options == [["PSY 1001"], ["PSY 1901"]] and intro.group == "Introductory Courses"
    assert bundle.options == [["CHEM 1031", "CHEM 1033"]]
    assert select.kind == "count" and select.needed == 2 and len(select.options) == 3 and select.group == "Foundations"
    assert credits.kind == "credits" and credits.needed == 9
    assert manual.kind == "manual" and manual.needs_review


def test_alternate_path_tables_are_not_added_as_requirements():
    html = TABLE.replace("<h2>Major Requirements</h2>", "<li><strong>Seven course alternate prerequisites for the minor:</strong>")
    assert all(r.kind == "note" for r in parse_requirement_tables(html))


def test_parse_prereqs_to_and_of_or_groups():
    groups, _ = parse_prereqs("Minimum grade of C- in (PSY 1001, PSY 1901, or PSY 1996), (PSY 1003 or STAT 2103), and any 2000-level PSY course.")
    assert groups == [["PSY 1001", "PSY 1901", "PSY 1996"], ["PSY 1003", "STAT 2103"]]
    groups, notes = parse_prereqs("Minimum grade of C- in (MATH 0701, 'Y' in MC3, or 'Y' in MC6T)")
    assert groups == [["MATH 0701", "@OTHER"]] and notes


def test_parse_course_block():
    page = """<div class="courseblock"><p class="courseblocktitle"><strong>PSY 3096.  Conducting Psychological Research.  3   Credit Hours.</strong></p>
    <div class="courseblockdesc"><div class="courseblockheaddiv">Research methods.</div><p class="courseblockpart"><strong>Course Attributes:</strong> WI</p>
    <p class="courseblockpart"><strong>Pre-requisites:</strong> Minimum grade of C- in <a class="bubblelink code">PSY 1001</a>.</p></div></div>"""
    [c] = parse_course_blocks(page)
    assert c["code"] == "PSY 3096" and c["credits"] == 3 and c["attributes"] == ["WI"] and c["prereqs"] == [["PSY 1001"]]


def test_program_type_from_slug():
    assert program_type("psychology-ba") == "major" and program_type("psychology-minor") == "minor"
    assert program_type("forensic-psychology-certificate") == "certificate" and program_type("general-education") is None


def test_and_between_parenthesized_groups():
    text = ("Minimum grade of C- in ( ECON 1101 , ECON 1901 , ECON 1102 , or ECON 1902 ) and ( STAT 1001 , 'Y' in STA2, "
            "STAT 1102 , MATH 1041 , or 'Y' in MATW)")
    groups, _ = parse_prereqs(text)
    assert groups == [["ECON 1101", "ECON 1901", "ECON 1102", "ECON 1902"], ["STAT 1001", "@OTHER", "STAT 1102", "MATH 1041"]]


def test_grade_and_concurrency_annotations_are_ignored():
    text = ("Minimum grade of C- in ( CIS 1068 or CIS 1073), CIS 1166 , and ( MATH 1041 , ( MATH 1031 and MATH 1022 ), "
            "MATH 1042 (may be taken concurrently), or 'Y' in MATW)")
    groups, _ = parse_prereqs(text)
    assert ["CIS 1068", "CIS 1073"] in groups and ["CIS 1166"] in groups
    assert all("@OTHER" not in g or "MATH 1041" in g for g in groups)


def test_select_rule_written_as_section_header():
    html = """<table class="sc_courselist"><tbody>
    <tr class="odd areaheader"><td colspan="2"><span class="areaheader">Chemistry Sequence</span></td></tr>
    <tr class="even areaheader"><td colspan="2"><span class="areaheader">Select one Chemistry Lab Science A:</span></td></tr>
    <tr class="odd"><td class="codecol"><a class="bubblelink code">CHEM 1031</a></td><td>Gen Chem I</td></tr>
    <tr class="even"><td class="codecol"><a class="bubblelink code">CHEM 1951</a></td><td>Honors Gen Chem I</td></tr>
    </tbody></table>"""
    [r] = parse_requirement_tables(html)
    assert r.kind == "count" and r.needed == 1 and r.options == [["CHEM 1031"], ["CHEM 1951"]] and r.group == "Chemistry Sequence"
