"""Job board registry and URL/text router."""
import json
import os
import re
from typing import Any, Dict
from urllib.parse import urlparse

from .base import (BaseScraper, IngestionError, ScraperError, SchemaValidationError,
                   fetch_url_content)
from .cache import ScraperCache
from .oracle_hcm import OracleHCMScraper

# (name, job_id prefix, URL domains, pasted-text keywords, placeholder source URL for pasted text)
BOARDS = [
    ("greenhouse", "gh", ["greenhouse.io"], ["greenhouse"], "https://boards.greenhouse.io/job"),
    ("lever", "lev", ["lever.co"], ["lever.co"], "https://jobs.lever.co/job"),
    ("ashby", "ash", ["ashbyhq.com"], ["ashby", "ashbyhq"], "https://jobs.ashbyhq.com/job"),
    ("hiring_cafe", "hc", ["hiring.cafe"], ["hiring.cafe"], "https://hiring.cafe/job"),
    ("cutshort", "cs", ["cutshort.io"], ["cutshort"], "https://cutshort.io/job"),
    ("instahyre", "ih", ["instahyre.com"], ["instahyre"], "https://www.instahyre.com/job"),
    ("wellfound", "wf", ["wellfound.com", "angel.co"], ["wellfound", "angellist"], "https://wellfound.com/jobs"),
    ("unstop", "us", ["unstop.com", "dare2compete.com"], ["unstop", "dare2compete"], "https://unstop.com/jobs"),
    ("oneremotejobs", "orj", ["oneremotejobs.com"], ["oneremotejobs"], "https://oneremotejobs.com/job"),
    ("weworkremotely", "wwr", ["weworkremotely.com"], ["weworkremotely"], "https://weworkremotely.com/job"),
    ("remoteok", "rok", ["remoteok.com", "remoteok.io"], ["remoteok"], "https://remoteok.com/job"),
    ("himalayas", "him", ["himalayas.app"], ["himalayas.app"], "https://himalayas.app/jobs"),
    ("arcdev", "arc", ["arc.dev"], ["arc.dev", "arcdev"], "https://arc.dev/remote-jobs"),
    ("nats", "nats", ["nats.education.gov.in"], ["nats"], "https://nats.education.gov.in/apprentice"),
]
ORACLE_DOMAINS = ("hexaware.com", "oraclecloud.com")


def get_scraper(board: str) -> BaseScraper:
    """Scraper for a board name from BOARDS (or 'oracle_hcm' / 'generic')."""
    if board == "oracle_hcm":
        return OracleHCMScraper()
    for name, prefix, _, _, default_url in BOARDS:
        if name == board:
            return BaseScraper(prefix, default_url)
    return BaseScraper()


def get_scraper_for_url(url_or_text: str) -> BaseScraper:
    """Routes a URL (by domain) or pasted JD text (by whole-word keyword) to a scraper."""
    cleaned = BaseScraper().validate_input(url_or_text)
    lower = cleaned.lower()
    if lower.startswith(("http://", "https://")):
        netloc = urlparse(lower).netloc
        if any(d in netloc for d in ORACLE_DOMAINS):
            return OracleHCMScraper()
        for name, _, domains, _, _ in BOARDS:
            if any(d in netloc for d in domains):
                return get_scraper(name)
        return BaseScraper()

    if re.search(r"\b(?:hexaware|oraclecloud)\b", lower):
        return OracleHCMScraper()
    for name, _, _, keywords, _ in BOARDS:
        if any(re.search(r"\b" + re.escape(k) + r"\b", lower) for k in keywords):
            return get_scraper(name)
    return get_scraper("hiring_cafe")


def load_job(source: str) -> Dict[str, Any]:
    """A saved JobPosting .json file, or a URL / pasted JD text to scrape."""
    if source.endswith(".json") and os.path.exists(source):
        with open(source, "r", encoding="utf-8") as f:
            return json.load(f)
    return get_scraper_for_url(source).scrape(source)


__all__ = [
    "BOARDS", "BaseScraper", "IngestionError", "OracleHCMScraper", "ScraperCache", "ScraperError",
    "SchemaValidationError", "fetch_url_content", "get_scraper", "get_scraper_for_url", "load_job",
]
