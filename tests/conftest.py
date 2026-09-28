import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import common
from tools.scrapers import IngestionError, ScraperCache, base
from tools.scrapers.base import extract_slug_from_url

# Job URLs whose fake pages are defined in fake_fetch below.
FEEDS = [
    "https://hiring.cafe/job/101-remote-ai",
    "https://boards.greenhouse.io/job/202-data-analyst",
    "https://nats.education.gov.in/apprentice/303-cisco",
]


def fake_fetch(url: str) -> str:
    """Offline stand-in for fetch_url_content: a small job page derived from the URL."""
    u = url.lower()
    if "invalid_url_test" in u:
        raise IngestionError(f"Could not fetch {url}: simulated network failure")
    company, title = extract_slug_from_url(url)
    company, title = company or "Target Employer", title or "Software / Data Role"
    location, salary, skills = "Remote Worldwide", "$60,000 - $90,000 USD", "Python, RAG, SQL, Machine Learning"
    if "low_score" in u or "cobol" in u:
        company, title, location, salary, skills = "LegacyCorp", "Cobol Developer", "Ohio, USA", "40,000 - 50,000 USD", "Cobol, Fortran, Assembly"
    elif "stripe" in u:
        company, title, salary, skills = "Stripe", "Senior Software Engineer", "$120,000 - $160,000 USD", "Python, React, AWS, SQL"
    elif "202-data-analyst" in u:
        company, title, location, salary, skills = "TechCorp", "Data Analyst", "Bangalore, India", "8 - 12 LPA", "Python, Java, Docker, Oracle, SQL"
    elif "303-cisco" in u or "nats" in u:
        company, title, location, salary, skills = "Cisco Systems", "Graduate Apprentice Trainee", "Bangalore, India", "4.5 - 6.0 LPA", "Python, SQL, Machine Learning, C++, Java"
    elif "remote-ai" in u or "worldwide" in u:
        company, title, salary, skills = "Global AI", "Senior RAG Engineer", "$60,000 - $95,000 USD", "Python, SQL, Machine Learning, RAG, LangChain"
    return (f"<html><head><title>{title} at {company}</title></head><body><h1>{title}</h1>"
            f"<div class='company'>{company}</div><div class='location'>{location}</div>"
            f"<p>Salary: {salary}. Skills: {skills}.</p><p>Source URL: {url}</p></body></html>")


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch, request):
    """Keeps tests away from the real tracker, database, applications folder and caches."""
    monkeypatch.setattr(common, "APPLICATIONS_DIR", str(tmp_path / "applications"))
    monkeypatch.setattr(common, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(common, "TRACKER_MD", str(tmp_path / "job_applications.md"))
    monkeypatch.setattr(ScraperCache, "dir", str(tmp_path / "scraper_cache"))
    monkeypatch.setattr(ScraperCache, "_mem", {})
    if not request.node.get_closest_marker("live"):
        monkeypatch.setattr(base, "fetch_url_content", fake_fetch)
