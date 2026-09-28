import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.scrapers import get_scraper_for_url, OracleHCMScraper
from tools import common
from tools.tailorer import LaTeXBuilder, PageValidator, CoverLetterGenerator
from tools.evaluator import FitScorer

def test_oracle_hcm_routing():
    url = "https://jobs.hexaware.com/#en/sites/CX_1/job/605215?"
    scraper = get_scraper_for_url(url)
    assert isinstance(scraper, OracleHCMScraper)

def test_oracle_hcm_mock():
    scraper = OracleHCMScraper()
    job = scraper.scrape("https://local.mock/job")
    assert job["job_id"].startswith("ora_")
    assert "company" in job
    assert "title" in job
    assert "skills_required" in job
    assert isinstance(job["skills_required"], list)

@pytest.mark.live
def test_oracle_hcm_live_hexaware():
    url = "https://jobs.hexaware.com/#en/sites/CX_1/job/605215?"
    scraper = OracleHCMScraper()
    job = scraper.scrape(url)
    assert job["job_id"] == "ora_605215"
    assert job["title"] == "Gen AI Developer Associate"
    assert job["company"] == "Hexaware Technologies"
    assert "Python" in job["skills_required"]
    assert "Generative AI" in job["skills_required"]

def test_genai_role_template_and_summary():
    builder = LaTeXBuilder()
    template = builder.get_template_for_job("Gen AI Developer Associate")
    assert "resume_ai_genai_engineering.tex" in template

    posting = {
        "job_id": "ora_605215",
        "title": "Gen AI Developer Associate",
        "company": "Hexaware Technologies",
        "skills_required": ["Python", "Generative AI", "PyTorch", "NLP"]
    }
    params = builder.build_customization_params(posting, {"tech_stack_overlap": ["Python", "Generative AI"]})
    assert "Gen AI Engineer" in params["tailored_summary"]
    assert "student at" in params["tailored_summary"] and "CGPA:" in params["tailored_summary"]

def test_genai_cover_letter():
    gen = CoverLetterGenerator()
    posting = {
        "job_id": "ora_605215",
        "title": "Gen AI Developer Associate",
        "company": "Hexaware Technologies",
        "skills_required": ["Python", "Generative AI", "PyTorch", "NLP"]
    }
    p1, p2, p3 = gen.generate_3_paragraphs(posting)
    assert "Gen AI Developer Associate" in p1
    assert any(kw in p2 for kw in ["RAG", "Generative AI", "Intelligence", "Engineering", "Python"])
    assert any(kw in p3 for kw in ["Certified", "Oracle", "AWS", "opportunity", "consideration"])

def test_every_real_application_is_one_pdf_page():
    """Guards the real vault: each application folder holds resume.pdf (exactly 1 page) and nothing but application.md."""
    apps = os.path.join(common.VAULT, "applications")  # common.APPLICATIONS_DIR is redirected to tmp by conftest
    for name in os.listdir(apps):
        folder = os.path.join(apps, name)
        if not os.path.isdir(folder):
            continue
        assert set(os.listdir(folder)) <= {"resume.pdf", "application.md"}, f"extra files in {name}"
        val = PageValidator.validate_page_count_with_feedback(os.path.join(folder, "resume.pdf"))
        assert val.is_valid, f"{name}: {val.feedback}"
    assert PageValidator.validate_single_page(os.path.join(common.VAULT, "resume.pdf"))
