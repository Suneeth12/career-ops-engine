"""Shared paths, profile loading, skill matching and role classification."""
import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.join(ROOT, "profile-vault")
PROFILE_PATH = os.path.join(VAULT, "candidate_profile.json")
if not os.path.exists(PROFILE_PATH):
    _example = os.path.join(VAULT, "candidate_profile.example.json")
    if os.path.exists(_example):
        PROFILE_PATH = _example
META_PATH = os.path.join(VAULT, "portfolio_meta.json")
TEMPLATES_DIR = os.path.join(VAULT, "templates")
CACHE_DIR = os.path.join(VAULT, "cache")  # git-ignored: fetched pages, LaTeX sources, compiled PDFs
APPLICATIONS_DIR = os.path.join(VAULT, "applications")
DB_PATH = os.path.join(VAULT, "jobs.db")
TRACKER_MD = os.path.join(VAULT, "job_applications.md")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40] or "job"


def load_json(path: Optional[str], default: Any = None) -> Any:
    """Reads a JSON file, returning `default` ({} if None) when missing or unreadable."""
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {} if default is None else default


SKILL_ALIASES: List[List[str]] = [
    ["rag", "retrieval-augmented generation", "retrieval augmented generation"],
    ["ml", "machine learning"],
    ["ai", "artificial intelligence"],
    ["genai", "gen ai", "generative ai"],
    ["js", "javascript"],
    ["ts", "typescript"],
    ["py", "python"],
    ["dl", "deep learning"],
    ["nlp", "natural language processing"],
    ["cv", "computer vision"],
    ["pytorch", "torch"],
    ["tensorflow", "tf"],
    ["scikit-learn", "sklearn"],
    ["llm", "llms", "large language models"],
    ["vector dbs (faiss)", "vector databases", "faiss", "vector db", "vector dbs"],
    ["agentic workflows", "ai agents", "agents"],
    ["restful apis", "rest apis", "rest api"],
    ["langchain", "langgraph"],
    ["model evaluation", "quality engineering", "test automation"],
    ["power bi", "power query", "dax"],
    ["excel", "advanced excel", "spreadsheets", "pivot tables"],
    ["data analysis", "data analytics", "business analytics"],
    ["data science", "data scientist", "ds"],
    ["statistics", "probability", "statistical analysis", "probability & statistics"],
    ["sql", "mysql", "postgresql", "relational databases", "databases"],
    ["apis", "restful apis", "rest apis", "rest api", "fastapi", "flask"],
    ["feature engineering", "data preprocessing"],
    ["supervised learning", "unsupervised learning", "machine learning"],
    ["git", "github", "version control"],
]


def _aliases(skill: str) -> set:
    s = skill.lower().strip()
    out = {s}
    for group in SKILL_ALIASES:
        if s in group:
            out.update(group)
    return out


def contains_term(term: str, text: str) -> bool:
    """Whole-word/phrase match that also works for terms like 'C++' or 'C#'."""
    return re.search(r"(?<![\w+#])" + re.escape(term.lower()) + r"(?![\w+#])", text.lower()) is not None


def skill_matches(required: str, candidate_skills: Iterable[str]) -> bool:
    req = _aliases(required)
    for cand in candidate_skills:
        if req & _aliases(cand) or any(contains_term(r, cand) for r in req) or contains_term(cand, required):
            return True
    return False


def match_skills(required: Iterable[str], candidate_skills: Iterable[str]) -> Tuple[List[str], List[str]]:
    """Splits required skills into (overlap, missing) against the candidate's skills."""
    cand = list(candidate_skills)
    overlap, missing = [], []
    for r in required or []:
        (overlap if skill_matches(r, cand) else missing).append(r)
    return overlap, missing


def claimable_skills(job_skills: Iterable[str], profile: Dict[str, Any], limit: int = 4) -> List[str]:
    """Job skills the candidate actually has; falls back to the candidate's own top skills.
    Never returns a skill that is not backed by the profile."""
    overlap, _ = match_skills(job_skills or [], profile.get("skills", []))
    return (overlap or profile.get("skills", []))[:limit]


# Pass 1: the job's own role noun ("... Data Engineer", "Data Analyst", "ML Engineer") decides.
ROLE_NOUNS = [
    ("sdet", r"sdet(?: \w+)?|qa engineer|quality engineer(?:ing)?|test engineer|automation engineer"),
    ("founders_office", r"founder'?s? office(?: intern)?|chief of staff|strategy (?:&|and) ops|entrepreneur in residence|eir"),
    ("product_management", r"product manager|apm|associate product manager|product lead|product owner"),
    ("data_engineering", r"(?:data|analytics|etl|big data) engineer(?:ing)?"),
    ("data_analytics", r"(?:data|business|bi|mis|product|reporting) analyst|analytics|bi developer"),
    ("ai", r"data scien(?:ce|tist)|(?:gen ?ai|ai|ml|machine learning|llm|nlp|deep learning|computer vision|prompt) "
           r"(?:engineer|developer|scientist|researcher|trainee|intern|associate|specialist)"),
]
# Pass 2: domain keywords anywhere in the title, in priority order.
ROLE_KEYWORDS = [
    ("sdet", r"sdet|qa|test automation|automation test|quality engineering"),
    ("founders_office", r"founder'?s? office|chief of staff|generalist"),
    ("product_management", r"product management|product manager|apm"),
    ("ai", r"gen ?ai|generative|ai|ml|machine learning|llms?|rag|nlp|prompt|deep learning|computer vision"),
    ("data_engineering", r"etl|pipelines?|spark|databricks|airflow|dbt"),
    ("data_analytics", r"analyst|bi|power bi|tableau|sql|mis|database"),
    ("sde", r"sde|software|developer|backend|full ?stack|engineer|intern"),
]


def classify_role(title: Optional[str]) -> str:
    """Maps a job title to 'ai', 'data_engineering', 'data_analytics', 'sde' or 'other'.
    'AI Data Engineer' -> data_engineering (the role noun wins over the domain keyword)."""
    t = (title or "").lower()
    for patterns in (ROLE_NOUNS, ROLE_KEYWORDS):
        for role, pattern in patterns:
            if re.search(r"\b(?:" + pattern + r")\b", t):
                return role
    return "other"


if __name__ == "__main__":
    assert skill_matches("FAISS", ["Vector DBs (FAISS)"])
    assert not skill_matches("Java", ["JavaScript"])
    assert not skill_matches("C++", ["Python", "C#"])
    assert skill_matches("Retrieval-Augmented Generation", ["RAG"])
    assert skill_matches("Advanced SQL", ["SQL"])
    assert not skill_matches("GitHub Actions", ["Git"])
    assert classify_role("Mobile Developer") == "sde"
    assert classify_role("Storage Engineer") == "sde"
    assert classify_role("International Sales") == "other"
    assert classify_role("Gen AI Developer Associate") == "ai"
    assert classify_role("Data Analyst & SDE") == "data_analytics"
    assert classify_role("AI Data Engineer") == "data_engineering"
    assert classify_role("Analytics Engineer") == "data_engineering"
    assert classify_role("Data Scientist") == "ai"
    assert classify_role("Senior RAG Engineer") == "ai"
    assert classify_role("Power BI Developer") == "data_analytics"
    print("ok")
