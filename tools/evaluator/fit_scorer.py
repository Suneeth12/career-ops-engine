import datetime
import re
from typing import Any, Dict, List, Optional

from tools.common import PROFILE_PATH, contains_term, load_json, match_skills
from .matcher import BM25ResumeMatcher

ACTION_VERBS = ["Architected", "Engineered", "Implemented", "Developed", "Fine-tuned",
                "Benchmarked", "Trained", "Authored", "Deployed", "Built"]


class FitScorer:
    """Scores candidate fit (1.0-5.0) against a JobPosting: skill overlap, location,
    compensation, flags, a recommendation, and supporting ATS heuristics."""

    def __init__(self, master_resume_path: Optional[str] = None) -> None:
        self.candidate_profile = load_json(master_resume_path or PROFILE_PATH)
        self.candidate_skills = self.candidate_profile.get("skills", [])

    def evaluate(self, job_data: Optional[Dict[str, Any]] = None,
                 candidate_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        posting = job_data or {}
        profile = candidate_profile if candidate_profile and "skills" in candidate_profile else self.candidate_profile
        req_skills = posting.get("skills_required") or []
        overlap, missing = match_skills(req_skills, profile.get("skills", []))

        # No recognised skills in the JD means "unknown", not "perfect match".
        ratio = len(overlap) / len(req_skills) if req_skills else 0.5
        score = 1.0 + ratio * 4.0

        loc = str(posting.get("location") or "").lower()
        location_match = (posting.get("workplace_type") in ("remote_worldwide", "remote_india")
                          or any(k in loc for k in ("bangalore", "bengaluru", "india")))

        sal = posting.get("salary_range") or {}
        currency, min_sal, max_sal = sal.get("currency", "INR"), sal.get("min", 0.0), sal.get("max", 0.0)
        period = sal.get("period", "lpa")
        has_salary = min_sal > 0.0 or max_sal > 0.0
        if not has_salary:
            compensation_match = True
        elif currency == "INR":
            compensation_match = (max_sal >= 15000.0) if period == "monthly" else (max_sal >= 5.0)
        elif currency == "USD":
            compensation_match = (max_sal >= 2000.0) if period == "monthly" else (max_sal >= 30000.0)
        else:
            compensation_match = True

        score += 0.2 if location_match else -0.5
        if compensation_match and has_salary:
            score += 0.2
        score = round(max(1.0, min(5.0, score)), 2)

        green_flags: List[str] = []
        red_flags: List[str] = []
        if len(overlap) >= 3:
            green_flags.append(f"Strong skill alignment on {len(overlap)} core technologies ({', '.join(overlap[:3])}).")
        if location_match:
            green_flags.append("Location policy matches candidate availability.")
        else:
            red_flags.append("On-site role outside primary preference location.")
        if has_salary:
            (green_flags if compensation_match else red_flags).append(
                "Compensation range matches candidate expectations." if compensation_match
                else "Compensation below candidate minimum expectation.")
        if missing:
            red_flags.append(f"Gap in required skills: {', '.join(missing[:3])}.")
        if not req_skills:
            red_flags.append("No recognised skills in the job description; review manually.")

        recommendation = "APPLY" if score >= 4.0 else "MANUAL_REVIEW" if score >= 3.0 else "SKIP"

        return {
            "job_id": posting.get("job_id", "unknown_job"),
            "score": score,
            "tech_stack_overlap": overlap,
            "missing_skills": missing,
            "location_match": location_match,
            "compensation_match": compensation_match,
            "green_flags": green_flags or ["Valid tech stack profile."],
            "red_flags": red_flags or ["None."],
            "recommendation": recommendation,
            "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            **self._ats_heuristics(posting, profile, overlap, missing),
        }

    def _ats_heuristics(self, posting: Dict[str, Any], profile: Dict[str, Any],
                        overlap: List[str], missing: List[str]) -> Dict[str, Any]:
        """Keyword density, weighted section scores, a HackerRank-style rubric, X-Y-Z metric audit
        and BM25 similarity. Heuristics derived from the profile's structure, not hard-coded facts."""
        summary = str(profile.get("summary") or "")
        texts: List[str] = [summary]
        for p in profile.get("projects") or []:
            texts += [str(p.get("name") or ""), str(p.get("description") or "")]
            texts += [str(x) for x in (p.get("bullets") or []) + (p.get("tech_stack") or [])]
        for e in profile.get("experience") or []:
            texts += [str(e.get("title") or ""), str(e.get("company") or "")] + [str(h) for h in e.get("highlights") or []]
        education = profile.get("education") or []
        for ed in education:
            texts += [str(ed.get(k) or "") for k in ("institution", "degree", "cgpa", "location")]
        publications = profile.get("publications") or []
        for pub in publications:
            texts += [str(pub.get(k) or "") for k in ("title", "venue", "description")]
        texts += [str(c) for c in profile.get("certifications") or []] + [str(s) for s in profile.get("skills") or []]
        all_text = " ".join(texts)
        lower = all_text.lower()
        total_words = max(1, len(re.findall(r"\b[A-Za-z0-9\+\#\.\_]+\b", lower)))

        title = str(posting.get("title") or "")
        jd = f"{title} {posting.get('raw_description') or ''} {' '.join(posting.get('skills_required') or [])}"
        bm25 = BM25ResumeMatcher().match(jd, all_text)

        density = {}
        for term in set(overlap + ["python", "sql", "fastapi", "docker", "aws", "rag"]):
            count = len(re.findall(r"(?<![\w+#])" + re.escape(term.lower()) + r"(?![\w+#])", lower))
            pct = round(count / total_words * 100.0, 2)
            density[term] = {"count": count, "density_pct": pct,
                             "status": "optimal" if 1.0 <= pct <= 4.5 else "over_dense" if pct > 4.5 else "sparse"}

        total_req = max(1, len(overlap) + len(missing))
        skills_score = len(overlap) / total_req * 100.0
        strong_projects = any(contains_term(k, lower) for k in ("rag", "fastapi", "etl", "pipeline", "docker"))
        proj_score = 90.0 if strong_projects else 75.0
        title_kws = [w for w in re.split(r"\W+", title.lower()) if len(w) > 2]
        summary_score = min(100.0, 70.0 + 10.0 * sum(1 for kw in title_kws if kw in summary.lower()))
        has_grades = any(ed.get("cgpa") for ed in education)
        edu_score = 95.0 if has_grades or publications else 80.0
        composite = round(0.35 * skills_score + 0.40 * proj_score + 0.15 * summary_score + 0.10 * edu_score, 1)

        has_github = bool(profile.get("github_url")) or "github" in lower
        hr_os = 35 if has_github and publications else 25
        hr_proj = 30 if any(contains_term(k, lower) for k in ("rag", "fastapi", "lora", "transformer", "yolo")) else 20
        hr_exp = 25 if profile.get("experience") or has_grades else 15
        hr_skills = min(10, int(len(overlap) / total_req * 10))
        hr_total = hr_os + hr_proj + hr_exp + hr_skills

        metrics = re.findall(r"(?:\$\d+|\b\d+(?:,\d+)*(?:\.\d+)?(?:%|x|ms|\+)?)", all_text)
        verbs = [v for v in ACTION_VERBS if v.lower() in lower]

        return {
            "ats_score": composite,
            "keyword_density": density,
            "section_semantic_weights": {
                "skills_weight_pct": 35, "skills_score": round(skills_score, 1),
                "projects_weight_pct": 40, "projects_score": proj_score,
                "summary_weight_pct": 15, "summary_score": summary_score,
                "education_weight_pct": 10, "education_score": edu_score,
                "composite_score": composite,
            },
            "hackerrank_rubric": {
                "open_source_research": hr_os, "projects_complexity": hr_proj,
                "academic_experience": hr_exp, "technical_skills": hr_skills,
                "total_score": hr_total, "rating": "HIGH FIT" if hr_total >= 80 else "MODERATE FIT",
            },
            "google_xyz_metrics": {
                "quantified_metrics_detected": sorted(set(metrics)),
                "metric_count": len(metrics),
                "action_verbs_detected": verbs,
                "compliance_status": "PASS" if len(metrics) >= 5 else "NEEDS_TUNING",
            },
            "bm25_match": bm25,
        }
