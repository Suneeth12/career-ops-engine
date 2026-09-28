"""Regression checks for bugs fixed in the 2026-09 audit."""
from tools.common import classify_role, match_skills
from tools.evaluator import FitScorer
from tools.scrapers import get_scraper, get_scraper_for_url
from tools.tailorer import CoverLetterGenerator, LaTeXBuilder
from tools.tracker import ApplicationLogger


def test_skill_matching_is_whole_word():
    overlap, missing = match_skills(["Java", "Go", "FAISS", "Advanced SQL"], ["JavaScript", "MongoDB", "Vector DBs (FAISS)", "SQL"])
    assert overlap == ["FAISS", "Advanced SQL"]
    assert missing == ["Java", "Go"]


def test_role_classification_has_no_substring_false_positives():
    assert classify_role("Mobile Developer") == "sde"          # "bi" in "mobile"
    assert classify_role("Storage Engineer") == "sde"          # "rag" in "storage"
    assert classify_role("International Sales Lead") == "other"  # "intern" in "international"
    assert classify_role("Senior ML Engineer") == "ai"


def test_international_is_not_an_internship():
    job = get_scraper("greenhouse").scrape("company: Acme\ntitle: Engineer\nWork with international clients. Python.")
    assert job["employment_type"] == "full_time"


def test_leverage_does_not_route_to_lever():
    assert get_scraper_for_url("company: Acme\ntitle: Dev\nWe leverage Python.").prefix == "hc"


def test_unknown_skills_are_not_invented_and_score_neutral():
    job = get_scraper("greenhouse").scrape("company: Acme\ntitle: Welder\nMIG and TIG welding.")
    assert job["skills_required"] == []
    fit = FitScorer().evaluate(job)
    assert fit["score"] < 4.0 and fit["recommendation"] != "APPLY"


def test_cover_letter_never_claims_skills_missing_from_profile():
    p1, p2, p3 = CoverLetterGenerator().generate_3_paragraphs(
        {"company": "LegacyCorp", "title": "Developer", "skills_required": ["Cobol", "Fortran", "C++"]})
    text = p1 + p2 + p3
    assert "Cobol" not in text and "Fortran" not in text and "C++" not in text


def test_summary_is_latex_escaped(tmp_path):
    out = LaTeXBuilder().generate_latex_resume(
        {"target_role_title": "AI Engineer", "tailored_summary": "R&D in C# at 100% speed"}, str(tmp_path / "r.tex"))
    tex = open(out, encoding="utf-8").read()
    assert r"R\&D in C\# at 100\% speed" in tex


def test_bullet_clamp_keeps_list_delimiters():
    tex = "\n".join([r"\resumeProjectHeading", r"\resumeItemListStart",
                     r"\resumeItem{a}", r"\resumeItem{b}", r"\resumeItem{c}", r"\resumeItemListEnd"])
    out = LaTeXBuilder._clamp_project_bullets(tex)
    assert r"\resumeItemListStart" in out and r"\resumeItemListEnd" in out
    assert out.count(r"\resumeItem{") == 2


def test_tracker_escapes_pipes_and_does_not_duplicate_rows(tmp_path):
    md = tmp_path / "t.md"
    logger = ApplicationLogger(tracker_md_path=str(md), db_path=str(tmp_path / "t.db"))
    job = {"job_id": "x1", "company": "A | B Corp", "title": "Dev"}
    logger.log(job, {"score": 4.0}, "r.pdf", "c.md")
    logger.log(job, {"score": 4.1}, "r.pdf", "c.md")
    rows = [line for line in md.read_text(encoding="utf-8").splitlines() if "B Corp" in line]
    assert len(rows) == 1 and r"A \| B Corp" in rows[0]
