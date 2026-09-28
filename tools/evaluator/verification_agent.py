import os
import sqlite3
from typing import Any, Dict, Optional

from tools import common
from tools.evaluator.fit_scorer import FitScorer
from tools.form_filler import AnswerGenerator
from tools.scrapers import get_scraper_for_url
from tools.tailorer import PageValidator

REQUIRED_FORM_FIELDS = [
    "search_motivation", "measurable_outcome_past_12m", "job_search_timeline",
    "working_hours_and_timezone", "reason_for_leaving", "base_compensation_usd",
    "github_url", "portfolio_url",
]


class ApplicationVerifier:
    """7-point audit of an application package: ingestion, scoring, profile facts,
    form answers, single-page PDF, SQLite log and Markdown tracker."""

    def verify_application_package(self, input_source: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
        report: Dict[str, Any] = {"input_source": input_source, "passed": True, "checklist": {}, "errors": [], "warnings": []}
        check = report["checklist"]

        def fail(step: str, msg: str) -> None:
            check[step] = f"FAIL: {msg}"
            report["errors"].append(f"{step}: {msg}")
            report["passed"] = False

        try:
            job = get_scraper_for_url(input_source).scrape(input_source)
        except Exception as e:
            fail("1_job_ingestion", str(e))
            return report
        missing = [k for k in ("job_id", "company", "title", "workplace_type", "source_url") if not job.get(k)]
        if missing:
            fail("1_job_ingestion", f"Missing keys {missing}")
        else:
            check["1_job_ingestion"] = f"PASS: Ingested '{job['title']}' @ '{job['company']}'"

        try:
            score = FitScorer().evaluate(job)["score"]
            if 1.0 <= score <= 5.0:
                check["2_fit_scoring"] = f"PASS: Score = {score:.2f} / 5.0"
            else:
                fail("2_fit_scoring", f"Invalid score {score}")
        except Exception as e:
            fail("2_fit_scoring", str(e))

        profile = common.load_json(common.PROFILE_PATH)
        absent = [k for k in ("full_name", "email", "phone", "education", "skills") if not profile.get(k)]
        if absent:
            check["3_candidate_facts"] = f"WARN: candidate_profile.json missing {absent}"
            report["warnings"].append(f"Candidate profile is missing {absent}.")
        else:
            check["3_candidate_facts"] = f"PASS: Candidate profile complete ({profile['full_name']})"

        try:
            answers = AnswerGenerator().generate(job)
            empty = [f for f in REQUIRED_FORM_FIELDS if not answers.get(f)]
            if empty:
                fail("4_form_answers", f"Empty form fields {empty}")
            else:
                named = job["company"].lower() in answers["why_join_company"].lower()
                check["4_form_answers"] = f"PASS: {len(REQUIRED_FORM_FIELDS)} required fields generated (company named: {named})"
        except Exception as e:
            fail("4_form_answers", str(e))

        if pdf_path:
            pages = PageValidator.get_page_count(pdf_path)
            if pages == 1:
                check["5_pdf_constraint"] = f"PASS: single-page PDF at {os.path.basename(pdf_path)}"
            else:
                fail("5_pdf_constraint", f"{pdf_path} has {pages} pages (expected 1)")
        else:
            check["5_pdf_constraint"] = "SKIP: no PDF path provided."

        if os.path.exists(common.DB_PATH):
            try:
                with sqlite3.connect(common.DB_PATH, timeout=30.0) as conn:
                    count = conn.execute("SELECT COUNT(*) FROM applications WHERE job_id = ?", (job["job_id"],)).fetchone()[0]
                check["6_sqlite_db"] = (f"PASS: job_id '{job['job_id']}' in jobs.db" if count
                                        else f"WARN: job_id '{job['job_id']}' not in jobs.db")
            except sqlite3.Error as e:
                check["6_sqlite_db"] = f"WARN: {e}"
        else:
            check["6_sqlite_db"] = "WARN: jobs.db does not exist yet."

        if os.path.exists(common.TRACKER_MD):
            with open(common.TRACKER_MD, "r", encoding="utf-8") as f:
                md = f.read()
            check["7_markdown_log"] = ("PASS: entry found in job_applications.md" if job["job_id"] in md or job["company"] in md
                                       else f"WARN: no entry for '{job['company']}' in job_applications.md")
        else:
            check["7_markdown_log"] = "WARN: job_applications.md does not exist yet."

        return report
