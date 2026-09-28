import datetime
import hashlib
import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import jsonschema

from tools.common import ROOT, contains_term
from .cache import ScraperCache


class ScraperError(Exception):
    """Base exception for scraper operations."""


class IngestionError(ScraperError):
    """Raised when input is invalid, unreachable, or unparseable."""


class SchemaValidationError(ScraperError):
    """Raised when output fails JobPosting JSON Schema validation."""


JOB_POSTING_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "JobPosting",
    "type": "object",
    "properties": {
        "job_id": {"type": "string"},
        "title": {"type": "string"},
        "company": {"type": "string"},
        "location": {"type": "string"},
        "workplace_type": {"type": "string", "enum": ["remote_worldwide", "remote_india", "hybrid", "on_site"]},
        "employment_type": {"type": "string", "enum": ["full_time", "internship", "apprenticeship", "contract"]},
        "salary_range": {
            "type": "object",
            "properties": {
                "currency": {"type": "string", "enum": ["INR", "USD"]},
                "min": {"type": "number"},
                "max": {"type": "number"},
                "period": {"type": "string", "enum": ["lpa", "annual", "monthly"]},
            },
            "required": ["currency", "min", "max", "period"],
        },
        "skills_required": {"type": "array", "items": {"type": "string"}},
        "experience_required_years": {"type": "number"},
        "raw_description": {"type": "string"},
        "source_url": {"type": "string"},
        "ingested_at": {"type": "string"},
    },
    "required": [
        "job_id", "title", "company", "location", "workplace_type",
        "employment_type", "skills_required", "raw_description",
        "source_url", "ingested_at",
    ],
}

KNOWN_SKILLS = [
    "Python", "SQL", "Machine Learning", "Deep Learning", "Generative AI", "RAG",
    "Retrieval-Augmented Generation", "LangChain", "LangGraph", "LlamaIndex", "OpenAI", "LLM", "NLP",
    "Computer Vision", "PyTorch", "TensorFlow", "Hugging Face", "Scikit-learn", "Pandas", "NumPy",
    "FAISS", "Vector Databases", "Power BI", "Power Query", "Tableau", "Excel", "PowerPoint", "Word",
    "Data Analysis", "Statistical Analysis", "Feature Engineering",
    "Model Evaluation", "Spark", "Airflow", "Kafka", "Snowflake", "dbt",
    "JavaScript", "TypeScript", "React", "Node.js", "Tailwind CSS", "FastAPI", "Flask", "Django", "REST APIs",
    "Docker", "Kubernetes", "Terraform", "Linux", "AWS", "GCP", "Azure",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Git", "AI Agents",
    "Quality Engineering", "Test Automation",
    "C++", "C#", "Java", "Kotlin", "Rust", "Spring", "Hibernate", "Oracle",
]

ACRONYMS = {"ai": "AI", "ml": "ML", "rag": "RAG", "sde": "SDE", "nats": "NATS"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _load_env_file() -> None:
    """Loads .env into os.environ without overriding variables already set."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


_load_env_file()


def _fetch_via_firecrawl(url: str, api_key: str) -> str:
    payload = json.dumps({"url": url, "formats": ["markdown", "html"]}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v1/scrape", data=payload, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    d = data.get("data") or {} if data.get("success") else {}
    return d.get("html") or d.get("markdown") or ""


def fetch_url_content(url: str) -> str:
    """Fetches page content (Firecrawl API if FIRECRAWL_API_KEY is set, else plain HTTP).
    Raises IngestionError on failure; never returns placeholder content."""
    cache_key = f"html:{url}"
    cached = ScraperCache.get(cache_key)
    if cached:
        return cached

    content = ""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if api_key and api_key != "your_firecrawl_api_key_here":
        try:
            content = _fetch_via_firecrawl(url, api_key)
        except (OSError, ValueError):
            content = ""

    if len(content) <= 100:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
        except (OSError, ValueError) as e:
            raise IngestionError(f"Could not fetch {url}: {e}") from e

    if len(content) <= 100:
        raise IngestionError(f"Fetched page is empty or too short: {url}")
    ScraperCache.set(cache_key, content)
    return content


def format_slug(slug: str) -> str:
    if not slug:
        return ""
    words = re.sub(r"-\d+$", "", slug).replace("-", " ").replace("_", " ").split()
    return " ".join(ACRONYMS.get(w.lower(), w.capitalize()) for w in words)


def extract_slug_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort (company, title) from well-known job board URL shapes."""
    if not url or not isinstance(url, str):
        return None, None
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None, None

    def title_at(i: int) -> Optional[str]:
        return format_slug(parts[i]) if len(parts) > i and not parts[i].isdigit() else None

    if "greenhouse.io" in netloc:
        return format_slug(parts[0]), (title_at(2) if len(parts) > 2 and parts[1] in ("jobs", "job") else None)
    if "lever.co" in netloc or "ashbyhq.com" in netloc:
        return format_slug(parts[0]), title_at(1)
    if any(d in netloc for d in ("hiring.cafe", "cutshort.io", "instahyre.com")):
        return None, format_slug(parts[1] if parts[0] in ("job", "jobs") and len(parts) > 1 else parts[0])
    if "nats.education.gov.in" in netloc:
        return format_slug(parts[1] if len(parts) > 1 else parts[0]), None
    if parts[0].isdigit() or parts[0] in ("job", "jobs"):
        return None, None
    return format_slug(parts[0]), title_at(1)


class BaseScraper:
    """Parses a job posting from a URL (fetched) or raw JD text into the JobPosting schema.
    Board-specific behaviour is just a job_id prefix and a placeholder source URL for pasted text."""

    def __init__(self, prefix: str = "fc", default_url: str = "https://local.mock/job"):
        self.prefix = prefix
        self.default_url = default_url

    def validate_input(self, source_input: Any) -> str:
        if source_input is None:
            raise IngestionError("Input cannot be None.")
        if not isinstance(source_input, str):
            raise IngestionError(f"Input must be a string, got {type(source_input).__name__}.")
        cleaned = source_input.strip()
        if not cleaned:
            raise IngestionError("Input string cannot be empty or whitespace only.")
        return cleaned

    def validate_schema(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            jsonschema.validate(instance=data, schema=JOB_POSTING_SCHEMA)
            return data
        except jsonschema.ValidationError as e:
            raise SchemaValidationError(f"JobPosting schema validation failed: {e.message}") from e

    def generate_job_id(self, company: str, title: str, source_url: str) -> str:
        """12-char MD5 over a JSON array, so field delimiters cannot collide."""
        serialized = json.dumps([company.strip().lower(), title.strip().lower(), source_url.strip().lower()])
        return hashlib.md5(serialized.encode("utf-8")).hexdigest()[:12]

    def scrape(self, source_input: str) -> Dict[str, Any]:
        text = self.validate_input(source_input)
        if text.startswith(("http://", "https://")):
            return self.build_posting(fetch_url_content(text), text, url_known=True)
        return self.build_posting(text, self.default_url, url_known=False)

    def build_posting(self, raw_text: str, source_url: str, url_known: bool, job_id: Optional[str] = None,
                      company: Optional[str] = None, title: Optional[str] = None,
                      location: Optional[str] = None) -> Dict[str, Any]:
        co, ti, loc = self.extract_company_title_location(raw_text, source_url if url_known else None)
        company, title, location = company or co, title or ti, location or loc
        employment_type = self.parse_employment_type(raw_text)
        if self.prefix == "nats" and employment_type == "full_time":
            employment_type = "apprenticeship"
        return self.validate_schema({
            "job_id": f"{self.prefix}_{job_id or self.generate_job_id(company, title, source_url)}",
            "title": title,
            "company": company,
            "location": location,
            "workplace_type": self.parse_workplace_type(raw_text, location),
            "employment_type": employment_type,
            "salary_range": self.parse_salary_range(raw_text),
            "skills_required": self.extract_skills_from_text(f"{title} {raw_text}"),
            "experience_required_years": self.parse_experience_years(raw_text),
            "raw_description": raw_text,
            "source_url": source_url,
            "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

    def extract_skills_from_text(self, text: str) -> List[str]:
        """Known skills mentioned in the JD. Returns [] when none are recognised (never guesses)."""
        return [s for s in KNOWN_SKILLS if contains_term(s, text)]

    def parse_workplace_type(self, text: str, location: str) -> str:
        combined = f"{text} {location}".lower()
        if any(k in combined for k in ["remote worldwide", "worldwide remote", "global remote", "work from anywhere"]):
            return "remote_worldwide"
        if any(k in combined for k in ["remote india", "remote (india)", "work from home india", "remote in india"]):
            return "remote_india"
        if "hybrid" in combined:
            return "hybrid"
        if "remote" in combined:
            return "remote_worldwide" if ("usd" in combined or "worldwide" in combined or "$" in combined) else "remote_india"
        return "on_site"

    def parse_employment_type(self, text: str) -> str:
        if re.search(r"\binterns?(?:hip)?s?\b", text, re.IGNORECASE):
            return "internship"
        if re.search(r"\b(?:apprentice(?:ship)?s?|nats)\b", text, re.IGNORECASE):
            return "apprenticeship"
        if re.search(r"\b(?:contract|freelance)\b", text, re.IGNORECASE):
            return "contract"
        return "full_time"

    def parse_salary_range(self, text: str) -> Dict[str, Any]:
        default_salary = {"currency": "INR", "min": 0.0, "max": 0.0, "period": "lpa"}
        if not text:
            return default_salary

        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:LPA|Lakhs?)", text, re.IGNORECASE)
        if m:
            v1, v2 = float(m.group(1)), float(m.group(2))
            return {"currency": "INR", "min": min(v1, v2), "max": max(v1, v2), "period": "lpa"}
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:LPA|Lakhs?)", text, re.IGNORECASE)
        if m:
            v = float(m.group(1))
            return {"currency": "INR", "min": v, "max": v, "period": "lpa"}

        # Monthly stipend/salary (e.g., "60,000 - 80,000/month", "30,000/month", "₹20,000 - 25,000/month")
        m_mo = re.search(r"(?:₹|rs\.?|inr)?\s*(\d{1,3}(?:,\d{3})+|\d{4,6})\s*(?:-|to)\s*(?:₹|rs\.?|inr)?\s*(\d{1,3}(?:,\d{3})+|\d{4,6})\s*(?:/(?:mo|month)|per\s*month|\bmonthly\b)", text, re.IGNORECASE)
        if m_mo:
            v1 = float(m_mo.group(1).replace(",", ""))
            v2 = float(m_mo.group(2).replace(",", ""))
            return {"currency": "INR", "min": min(v1, v2), "max": max(v1, v2), "period": "monthly"}
        m_mo_s = re.search(r"(?:₹|rs\.?|inr)?\s*(\d{1,3}(?:,\d{3})+|\d{4,6})\s*(?:/(?:mo|month)|per\s*month|\bmonthly\b)", text, re.IGNORECASE)
        if m_mo_s:
            v = float(m_mo_s.group(1).replace(",", ""))
            return {"currency": "INR", "min": v, "max": v, "period": "monthly"}

        def usd(val: str) -> float:
            cleaned = val.replace("$", "").replace(",", "").strip().lower()
            if cleaned.endswith("k"):
                return float(cleaned[:-1]) * 1000.0
            v = float(cleaned)
            return v * 1000.0 if v < 1000 else v

        amount = r"(\d{2,3}(?:,\d{3})?|\d{1,3}k)"
        lower = text.lower()
        m = re.search(r"\$?\s*" + amount + r"\s*(?:-|to)\s*\$?" + amount, text, re.IGNORECASE)
        if m and ("$" in text or "usd" in lower or "annual" in lower):
            v1, v2 = usd(m.group(1)), usd(m.group(2))
            return {"currency": "USD", "min": min(v1, v2), "max": max(v1, v2), "period": "annual"}
        m = re.search(r"\$?\s*" + amount, text, re.IGNORECASE)
        if m and ("$" in text or "usd" in lower):
            v = usd(m.group(1))
            if v >= 1000.0:
                return {"currency": "USD", "min": v, "max": v, "period": "annual"}
        return default_salary

    def parse_experience_years(self, text: str) -> float:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+|-|\s*to\s*\d+)?\s*(?:years?|yrs?)\s*(?:of\s*)?experience", text, re.IGNORECASE)
        return float(m.group(1)) if m else 0.0

    def extract_company_title_location(self, text: str, source_url: Optional[str] = None) -> Tuple[str, str, str]:
        found: Dict[str, Optional[str]] = {}
        # 1. Explicit headers (e.g. "Company: X", "Company - X", "Role: Y", "Role - Y", "Location - Z").
        field_patterns = {
            "company": r"(?:company|organization|org)\s*[:\-–—]\s*([^\n<]+)",
            "title": r"(?:title|role|position|job role)\s*[:\-–—]\s*([^\n<]+)",
            "location": r"(?:location|loc|place|city)\s*[:\-–—]\s*([^\n<]+)",
        }
        for field, pat in field_patterns.items():
            m = re.search(rf"^{pat}", text, re.IGNORECASE | re.MULTILINE) or re.search(rf"{pat}", text, re.IGNORECASE)
            found[field] = m.group(1).strip() if m else None
        company, title, location = found["company"], found["title"], found["location"]

        # 2. HTML: JSON-LD, OpenGraph, <h1>/<title>, class hints.
        if "<" in text and ">" in text:
            for jld_str in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text, re.DOTALL | re.IGNORECASE):
                try:
                    ld = json.loads(jld_str.strip())
                except ValueError:
                    continue
                if not isinstance(ld, dict) or ld.get("@type") != "JobPosting":
                    continue
                title = title or (str(ld["title"]).strip() if ld.get("title") else None)
                org = ld.get("hiringOrganization")
                if not company and isinstance(org, dict) and org.get("name"):
                    company = str(org["name"]).strip()
                job_loc = ld.get("jobLocation")
                addr = job_loc.get("address") if isinstance(job_loc, dict) else None
                if not location and isinstance(addr, dict):
                    parts = [str(addr[k]).strip() for k in ("addressLocality", "addressRegion", "addressCountry") if addr.get(k)]
                    location = ", ".join(parts) or None

            if not company or not title:
                m_og = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', text, re.IGNORECASE)
                if m_og:
                    # e.g. "Sales Manager at IDFC First Bank — Indore, Madhya Pradesh, IN"
                    og = m_og.group(1).strip()
                    m = re.search(r"\bat\s+([^\—\|\-]+)", og, re.IGNORECASE)
                    company = company or (m.group(1).strip() if m else None)
                    m = re.search(r"^([^\—\|\-]+?)\s+at\b", og, re.IGNORECASE)
                    title = title or (m.group(1).strip() if m else None)
                    m = re.search(r"[\—\|]\s*([^\—\|]+)$", og)
                    location = location or (m.group(1).strip() if m else None)

            if not title:
                m_h1 = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.IGNORECASE | re.DOTALL)
                m_t = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
                if m_h1:
                    title = re.sub(r"<[^>]+>", "", m_h1.group(1)).strip()
                elif m_t:
                    t_raw = re.sub(r"<[^>]+>", "", m_t.group(1)).strip()
                    title = re.split(r"\s+at\s+|-|\|", t_raw, flags=re.IGNORECASE)[0].strip()
            if not company:
                m = re.search(r'class=["\']company[^"\'\n]*["\']>([^<#\n]+)', text, re.IGNORECASE)
                company = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else None
            if not location:
                m = re.search(r'class=["\']location[^"\'\n]*["\']>([^<#\n]+)', text, re.IGNORECASE)
                location = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else None

        # 3. URL slug.
        url_target = source_url
        if not url_target:
            m = re.search(r"https?://[^\s<\"']+", text)
            url_target = m.group(0) if m else None
        junk_company = ("unknown company", "a sustainable pace")
        if url_target:
            slug_co, slug_ti = extract_slug_from_url(url_target)
            if slug_co and (not company or company.lower() in junk_company):
                company = slug_co
            title = title or slug_ti

        # 4. "hiring at X" heuristic.
        if not company or company.lower() in junk_company:
            m = re.search(r"\bhiring at\s+([A-Z0-9][A-Za-z0-9\s&\.\-\_]+)", text, re.IGNORECASE)
            if m:
                company = m.group(1).strip()

        return company or "Unknown Company", title or "Software / Data Role", location or "Remote / Flexible"
