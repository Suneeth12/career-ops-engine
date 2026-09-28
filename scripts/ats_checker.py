"""Parse a resume PDF the way an ATS would and audit it against candidate_profile.json."""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from pdfminer.high_level import extract_text

from tools.common import PROFILE_PATH, contains_term, load_json
from tools.tailorer import PageValidator


def analyze_pdf_ats(pdf_path: str, profile_path: str = PROFILE_PATH) -> dict:
    candidate = load_json(profile_path)
    edu = (candidate.get("education") or [{}])[0]
    cgpa = str(edu.get("cgpa", "")).split("/")[0].strip()
    inst = str(edu.get("institution", "")).split("-")[0].strip()

    pages = PageValidator.get_page_count(pdf_path)
    print(f"[1] Pages: {pages} -> {'PASS' if pages == 1 else 'FAIL'}")

    text = extract_text(pdf_path)
    print(f"[2] Extracted {len(text)} characters. Sample: {text[:160].strip()!r}")

    keywords = sorted(set(candidate.get("skills", []) + [k for k in (cgpa, inst, "GitHub") if k]))
    found = [k for k in keywords if contains_term(k, text)]
    missing = [k for k in keywords if k not in found]
    match = len(found) / len(keywords) * 100 if keywords else 0.0
    print(f"[3] Profile keyword match: {match:.1f}% ({len(found)}/{len(keywords)})")
    if missing:
        print(f"    Missing: {', '.join(missing[:15])}")

    lower = text.lower()
    rubric = {
        "open_source_research": 35 if "github.com" in lower and ("paper" in lower or "conference" in lower) else 25,
        "projects_complexity": 30 if any(contains_term(p, lower) for p in ("rag", "fastapi", "dashboard", "pipeline")) else 20,
        "academic_experience": 25 if cgpa and cgpa in text and inst.lower() in lower else 15,
        "technical_skills": 10 if match >= 70.0 else 7,
    }
    total = sum(rubric.values())
    print(f"[4] HackerRank-style rubric: {total}/100 ({'HIGH FIT' if total >= 80 else 'MODERATE FIT'}) {rubric}")

    metrics = re.findall(r"(?:\$\d+|\b\d+(?:,\d+)*(?:\.\d+)?(?:%|x|ms|\+)?)", text)
    target = max(3, sum(len(p.get("bullets", [])) for p in candidate.get("projects", [])))
    print(f"[5] Quantified metrics: {len(metrics)} (target >= {target}) -> {'PASS' if len(metrics) >= target else 'ADD MORE NUMBERS'}")
    return {"pages": pages, "keyword_match_pct": match, "missing_keywords": missing, "rubric": rubric, "metric_count": len(metrics)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="Resume PDF to audit")
    analyze_pdf_ats(parser.parse_args().pdf)
