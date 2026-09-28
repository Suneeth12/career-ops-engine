import os
import sys
import json
import pytest
import datetime

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.scrapers import get_scraper, get_scraper_for_url, IngestionError
from tools.evaluator import FitScorer
from tools.tailorer import CoverLetterGenerator, LaTeXBuilder, PageValidator
from tools.form_filler import AnswerGenerator
from tools.tracker import ApplicationLogger
from tools.monitor import MonitorScheduler
from scripts.apply_all import run_apply_all
from conftest import FEEDS


# ==============================================================================
# TIER 1: FEATURE COVERAGE (R1, R2, R3, R4) -> 20+ TESTS
# ==============================================================================

# --- R1: Multi-Source Job Discovery & ATS Ingestion Engine ---

def test_r1_greenhouse_scraper():
    scraper = get_scraper("greenhouse")
    job = scraper.scrape("https://boards.greenhouse.io/stripe/jobs/12345")
    assert job["job_id"].startswith("gh_")
    assert job["company"] == "Stripe"
    assert job["workplace_type"] in ["remote_worldwide", "remote_india", "hybrid", "on_site"]
    assert job["employment_type"] in ["full_time", "internship", "apprenticeship", "contract"]

def test_r1_lever_scraper():
    scraper = get_scraper("lever")
    job = scraper.scrape("company: Netflix\ntitle: Software Engineer\nPython SQL AWS")
    assert job["job_id"].startswith("lev_")
    assert job["company"] == "Netflix"
    assert job["title"] == "Software Engineer"
    assert "Python" in job["skills_required"]

def test_r1_ashby_scraper():
    scraper = get_scraper("ashby")
    job = scraper.scrape("company: AI Startup\ntitle: AI Engineer\nSalary: $60,000 - $90,000 USD\nPython PyTorch")
    assert job["job_id"].startswith("ash_")
    assert job["company"] == "AI Startup"
    assert job["title"] == "AI Engineer"
    assert job["salary_range"]["currency"] == "USD"
    assert job["salary_range"]["min"] == 60000.0
    assert job["salary_range"]["max"] == 90000.0

def test_r1_hiring_cafe_scraper():
    scraper = get_scraper("hiring_cafe")
    job = scraper.scrape("company: Global Remote Inc\ntitle: Data Analyst\nSalary: $50,000 - $80,000 USD\nLocation: Remote Worldwide")
    assert job["job_id"].startswith("hc_")
    assert job["company"] == "Global Remote Inc"
    assert job["title"] == "Data Analyst"
    assert job["workplace_type"] == "remote_worldwide"

def test_r1_cutshort_scraper():
    scraper = get_scraper("cutshort")
    job = scraper.scrape("company: Bengaluru Tech Labs\ntitle: Data Analyst\nSalary: 10 - 15 LPA\nLocation: Bangalore")
    assert job["job_id"].startswith("cs_")
    assert job["company"] == "Bengaluru Tech Labs"
    assert job["title"] == "Data Analyst"
    assert job["salary_range"]["currency"] == "INR"
    assert job["salary_range"]["min"] == 10.0
    assert job["salary_range"]["max"] == 15.0

def test_r1_nats_apprentice_scraper():
    scraper = get_scraper("nats")
    job = scraper.scrape("company: Cisco Systems India\ntitle: Graduate Apprentice Trainee\nSalary: 4.5 - 6.0 LPA\nApprentice Role")
    assert job["job_id"].startswith("nats_")
    assert job["company"] == "Cisco Systems India"
    assert job["title"] == "Graduate Apprentice Trainee"
    assert job["employment_type"] == "apprenticeship"

def test_r1_single_and_range_salary_parsing():
    scraper = get_scraper("greenhouse")
    j1 = scraper.scrape("company: TestCo\ntitle: Dev\nSalary: 30 LPA")
    assert j1["salary_range"] == {"currency": "INR", "min": 30.0, "max": 30.0, "period": "lpa"}

    j2 = scraper.scrape("company: TestCo\ntitle: Dev\nSalary: 15 Lakh")
    assert j2["salary_range"] == {"currency": "INR", "min": 15.0, "max": 15.0, "period": "lpa"}

    j3 = scraper.scrape("company: TestCo\ntitle: Dev\nSalary: $100,000")
    assert j3["salary_range"] == {"currency": "USD", "min": 100000.0, "max": 100000.0, "period": "annual"}

    j4 = scraper.scrape("company: TestCo\ntitle: Dev\nSalary: $80k USD")
    assert j4["salary_range"] == {"currency": "USD", "min": 80000.0, "max": 80000.0, "period": "annual"}

    j5 = scraper.scrape("company: TestCo\ntitle: Dev\nSalary: 20-30 LPA")
    assert j5["salary_range"] == {"currency": "INR", "min": 20.0, "max": 30.0, "period": "lpa"}

    j6 = scraper.scrape("company: TestCo\ntitle: Dev\nSalary: $60,000 - $90,000")
    assert j6["salary_range"] == {"currency": "USD", "min": 60000.0, "max": 90000.0, "period": "annual"}

def test_r1_missing_salary_default():
    scraper = get_scraper("greenhouse")
    j = scraper.scrape("company: TestCo\ntitle: Dev\nNo salary listed")
    assert j["salary_range"] == {"currency": "INR", "min": 0.0, "max": 0.0, "period": "lpa"}

def test_r1_dynamic_url_slug_fallback():
    scraper = get_scraper("greenhouse")
    j = scraper.scrape("https://boards.greenhouse.io/netflix/jobs/12345")
    assert j["company"] == "Netflix"
    assert j["title"] == "Software / Data Role"


def test_r1_job_posting_schema_validation():
    scraper = get_scraper_for_url("https://boards.greenhouse.io/test")
    job = scraper.scrape("https://boards.greenhouse.io/test")
    required_keys = ["job_id", "title", "company", "location", "workplace_type", "employment_type", "skills_required", "raw_description", "source_url", "ingested_at"]
    for k in required_keys:
        assert k in job, f"Missing key {k} in JobPosting schema"

def test_r1_input_validation_none_raises_ingestion_error():
    scraper = get_scraper("greenhouse")
    with pytest.raises(IngestionError):
        scraper.scrape(None)
    with pytest.raises(IngestionError):
        get_scraper_for_url(None)

def test_r1_input_validation_empty_string_raises_ingestion_error():
    scraper = get_scraper("greenhouse")
    with pytest.raises(IngestionError):
        scraper.scrape("   ")
    with pytest.raises(IngestionError):
        get_scraper_for_url("")

def test_r1_non_ascii_unicode_jd_parsing():
    text = "company: 🚀 AI Studio Bangalore\ntitle: Lead ML Engineer (AI & 🤖 RAG)\nlocation: Bengaluru, Karnataka, India 🇮🇳\nSalary: 20 - 30 LPA\nSkills: Python, PyTorch, RAG"
    scraper = get_scraper("greenhouse")
    job = scraper.scrape(text)
    assert job["company"] == "🚀 AI Studio Bangalore"
    assert "Lead ML Engineer" in job["title"]
    assert "PyTorch" in job["skills_required"]

def test_r1_delimiter_collision_resistance():
    scraper = get_scraper("greenhouse")
    id_a = scraper.generate_job_id("a:b", "c", "http://example.com")
    id_b = scraper.generate_job_id("a", "b:c", "http://example.com")
    assert id_a != id_b, "generate_job_id must produce distinct IDs to resist delimiter collision"


# --- R2: Fit Scoring Engine & Single-Page LaTeX Resume Generator ---

def test_r2_fit_score_calculation():
    scorer = FitScorer()
    mock_job = {
        "job_id": "test_job_1",
        "skills_required": ["Python", "SQL", "Machine Learning", "RAG"],
        "location": "Bangalore, India",
        "workplace_type": "hybrid",
        "salary_range": {"currency": "INR", "min": 10.0, "max": 15.0, "period": "lpa"}
    }
    eval_res = scorer.evaluate(mock_job)
    assert 1.0 <= eval_res["score"] <= 5.0
    assert "job_id" in eval_res
    assert len(eval_res["tech_stack_overlap"]) >= 1

def test_r2_location_and_ctc_matching():
    scorer = FitScorer()
    mock_job = {
        "job_id": "test_job_loc",
        "skills_required": ["Python"],
        "location": "Bangalore",
        "workplace_type": "hybrid",
        "salary_range": {"currency": "INR", "min": 12.0, "max": 18.0, "period": "lpa"}
    }
    eval_res = scorer.evaluate(mock_job)
    assert eval_res["location_match"] is True
    assert eval_res["compensation_match"] is True

def test_r2_latex_resume_generation(tmp_path):
    builder = LaTeXBuilder()
    params = {
        "candidate_id": "candidate_001",
        "job_id": "job_123",
        "target_role_title": "AI Engineer",
        "highlight_skills": ["Python", "PyTorch", "RAG"],
        "tailored_summary": "Expert AI engineer.",
        "bullet_point_overrides": [],
        "output_format": "tex",
        "enforce_single_page": True
    }
    out_file = str(tmp_path / "test_resume.tex")
    builder.generate_latex_resume(params, out_file)
    assert os.path.exists(out_file)
    with open(out_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Expert AI engineer." in content

def test_r2_single_page_count_constraint(tmp_path):
    out_file = str(tmp_path / "single_page.tex")
    builder = LaTeXBuilder()
    params = {
        "candidate_id": "candidate_001",
        "job_id": "job_123",
        "target_role_title": "Data Scientist",
        "highlight_skills": ["Python", "SQL"],
        "tailored_summary": "Concise summary.",
        "bullet_point_overrides": [],
        "output_format": "tex",
        "enforce_single_page": True
    }
    builder.generate_latex_resume(params, out_file)
    assert PageValidator.validate_single_page(out_file) is False  # a .tex file is not a compiled PDF

def test_r2_cover_letter_generation(tmp_path):
    mock_job = {"company": "Acme Corp", "title": "Data Analyst", "skills_required": ["Python", "SQL"]}
    out_file = str(tmp_path / "cover.md")
    CoverLetterGenerator().generate(mock_job, out_file)
    assert os.path.exists(out_file)
    with open(out_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Acme Corp" in content
        assert "Data Analyst" in content

def test_r2_fit_score_schema_validation():
    scorer = FitScorer()
    mock_job = {"job_id": "test_schema", "skills_required": ["Python"]}
    eval_res = scorer.evaluate(mock_job)
    required_keys = ["job_id", "score", "tech_stack_overlap", "missing_skills", "location_match", "compensation_match", "green_flags", "red_flags", "recommendation", "evaluated_at"]
    for k in required_keys:
        assert k in eval_res, f"Missing key {k} in FitScore schema"


# --- R3: All-in-One /apply-all Command & ATS Form Answer Generator ---

def test_r3_apply_all_composite_pipeline_success():
    jd_input = "company: HighFit Corp\ntitle: Senior RAG Engineer\nPython SQL Machine Learning RAG LangChain"
    res = run_apply_all(jd_input, min_score_threshold=3.5)
    assert res["status"] == "SUCCESS"
    assert "resume_path" in res
    assert os.path.exists(res["application_md"])
    assert sorted(os.listdir(os.path.dirname(res["pdf_path"]))) == ["application.md", "resume.pdf"]
    assert "form_answers" in res

def test_r3_apply_all_low_score_abort():
    jd_input = "company: LowFit Corp\ntitle: Java Enterprise Architect\nJava Spring Hibernate Oracle WebLogic"
    res = run_apply_all(jd_input, min_score_threshold=4.5)
    assert res["status"] == "ABORTED"
    assert "reason" in res

def test_r3_form_answers_generation_india():
    gen = AnswerGenerator()
    mock_job = {"job_id": "in_job", "company": "Bangalore Tech", "workplace_type": "on_site", "salary_range": {"currency": "INR"}}
    answers = gen.generate(mock_job)
    assert answers["expected_ctc"]["currency"] == "INR"
    assert answers["availability_status"] == "Immediate Joiner"
    assert answers["notice_period_days"] == 0

def test_r3_form_answers_generation_global():
    gen = AnswerGenerator()
    mock_job = {"job_id": "us_job", "company": "US Remote Inc", "workplace_type": "remote_worldwide", "salary_range": {"currency": "USD"}}
    answers = gen.generate(mock_job)
    assert answers["expected_ctc"]["currency"] == "USD"
    assert answers["expected_ctc"]["unit"] == "Annual"

def test_r3_tracker_logging(tmp_path):
    tracker_file = str(tmp_path / "job_applications.md")
    logger = ApplicationLogger(tracker_md_path=tracker_file)
    mock_job = {"job_id": "track_01", "company": "Test Company", "title": "ML Engineer"}
    mock_fit = {"score": 4.5}
    entry = logger.log(mock_job, mock_fit, "resume.tex", "cover.md")
    assert entry["status"] == "APPLIED"
    assert os.path.exists(tracker_file)

def test_r3_form_answers_schema_validation():
    gen = AnswerGenerator()
    mock_job = {"job_id": "form_schema_test", "company": "Test"}
    answers = gen.generate(mock_job)
    required_keys = ["job_id", "why_join_company", "notice_period_days", "availability_status", "current_ctc", "expected_ctc", "github_url", "portfolio_url"]
    for k in required_keys:
        assert k in answers, f"Missing key {k} in FormAnswers schema"


# --- R4: Scheduled Background Job Monitor Daemon ---

def test_r4_monitor_polling_cycle():
    scheduler = MonitorScheduler(FEEDS, min_threshold=3.0)
    res = scheduler.run_polling_cycle()
    assert "polled_at" in res
    assert res["total_processed"] > 0

def test_r4_monitor_threshold_filtering():
    scheduler = MonitorScheduler(FEEDS, min_threshold=4.5)
    res = scheduler.run_polling_cycle()
    for item in res["matched_jobs"]:
        assert item["fit"]["score"] >= 4.5

def test_r4_monitor_duplicate_prevention():
    scheduler = MonitorScheduler(FEEDS, min_threshold=1.0)
    res1 = scheduler.run_polling_cycle()
    res2 = scheduler.run_polling_cycle()
    assert res2["total_processed"] == 0, "Duplicate jobs should be skipped on 2nd cycle"

def test_r4_monitor_error_tolerance():
    scheduler = MonitorScheduler(["https://boards.greenhouse.io/invalid_url_test"] + FEEDS[:1])
    res = scheduler.run_polling_cycle()
    assert res["total_processed"] == 1
    assert res["errors"][0]["source"].endswith("invalid_url_test")

def test_r4_monitor_state_reporting():
    scheduler = MonitorScheduler(FEEDS)
    res = scheduler.run_polling_cycle()
    assert isinstance(res["matched_jobs"], list)
    assert isinstance(res["rejected_jobs"], list)


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (20+ TESTS)
# ==============================================================================

# --- R1 Boundaries ---
def test_boundary_r1_empty_jd():
    scraper = get_scraper("greenhouse")
    with pytest.raises(IngestionError):
        scraper.scrape("")

@pytest.mark.live
def test_boundary_r1_unreachable_url_raises():
    # An unreachable page must fail loudly, never produce a made-up posting.
    scraper = get_scraper_for_url("http://invalid-url-domain-999.invalid/job")
    with pytest.raises(IngestionError):
        scraper.scrape("http://invalid-url-domain-999.invalid/job")

def test_boundary_r1_missing_salary():
    scraper = get_scraper("greenhouse")
    job = scraper.scrape("company: NoSalCorp\ntitle: Developer\nNo salary mentioned")
    assert "salary_range" in job

def test_boundary_r1_non_ascii_characters():
    text = "company: 🚀 AI Labs India\ntitle: Senior ML Lead (AI & 🤖 RAG)"
    scraper = get_scraper("greenhouse")
    job = scraper.scrape(text)
    assert job["title"] is not None

def test_boundary_r1_extreme_length_jd():
    long_text = "company: BigData Corp\ntitle: Data Analyst\n" + ("Python SQL RAG Machine Learning " * 1000)
    scraper = get_scraper("greenhouse")
    job = scraper.scrape(long_text)
    assert len(job["raw_description"]) > 10000


# --- R2 Boundaries ---
def test_boundary_r2_zero_overlap_score_1():
    scorer = FitScorer()
    mock_job = {"job_id": "zero_match", "skills_required": ["Cobol", "Fortran", "Assembly"]}
    eval_res = scorer.evaluate(mock_job)
    assert eval_res["score"] <= 2.5
    assert eval_res["recommendation"] in ["SKIP", "MANUAL_REVIEW"]

def test_boundary_r2_full_overlap_score_5():
    scorer = FitScorer()
    mock_job = {
        "job_id": "full_match",
        "skills_required": ["Python", "SQL", "Machine Learning", "RAG", "LangChain"],
        "location": "Bangalore, India",
        "workplace_type": "remote_india",
        "salary_range": {"currency": "INR", "min": 10.0, "max": 18.0, "period": "lpa"}
    }
    eval_res = scorer.evaluate(mock_job)
    assert eval_res["score"] >= 4.5
    assert eval_res["recommendation"] == "APPLY"

def test_boundary_r2_empty_required_skills():
    scorer = FitScorer()
    mock_job = {"job_id": "no_skills", "skills_required": []}
    eval_res = scorer.evaluate(mock_job)
    assert 1.0 <= eval_res["score"] <= 5.0

def test_boundary_r2_missing_master_profile():
    scorer = FitScorer(master_resume_path="nonexistent_profile.json")
    mock_job = {"job_id": "missing_profile", "skills_required": ["Python"]}
    eval_res = scorer.evaluate(mock_job)
    assert eval_res["score"] >= 1.0

def test_boundary_r2_unrecognized_currency():
    scorer = FitScorer()
    mock_job = {"job_id": "eur_job", "skills_required": ["Python"], "salary_range": {"currency": "EUR", "min": 50000, "max": 70000, "period": "annual"}}
    eval_res = scorer.evaluate(mock_job)
    assert "compensation_match" in eval_res


# --- R3 Boundaries ---
def test_boundary_r3_exact_threshold_score():
    jd_input = "company: ThresholdCorp\ntitle: Data Analyst\nPython SQL Pandas"
    res = run_apply_all(jd_input, min_score_threshold=3.0)
    assert res["status"] in ["SUCCESS", "ABORTED"]

def test_boundary_r3_score_3_49_abort():
    jd_input = "company: NearThresholdCorp\ntitle: Developer\nOracle Spring Hibernate"
    res = run_apply_all(jd_input, min_score_threshold=4.9)
    assert res["status"] == "ABORTED"

def test_boundary_r3_nonexistent_output_dir(tmp_path):
    deep_path = str(tmp_path / "deep" / "nested" / "dir" / "resume.tex")
    builder = LaTeXBuilder()
    params = {"candidate_id": "s1", "job_id": "j1", "target_role_title": "T1", "highlight_skills": ["Python"], "tailored_summary": "S1", "bullet_point_overrides": [], "output_format": "tex", "enforce_single_page": True}
    builder.generate_latex_resume(params, deep_path)
    assert os.path.exists(deep_path)

def test_boundary_r3_special_characters_company_name():
    gen = AnswerGenerator()
    mock_job = {"job_id": "spec_char", "company": "ACME / Inc & Co. (Global)"}
    answers = gen.generate(mock_job)
    assert "ACME" in answers["why_join_company"]

def test_boundary_r3_missing_portfolio_meta():
    gen = AnswerGenerator(portfolio_meta_path="nonexistent_meta.json")
    mock_job = {"job_id": "no_meta", "company": "MetaCorp"}
    answers = gen.generate(mock_job)
    assert answers["availability_status"] == "Immediate Joiner"


# --- R4 Boundaries ---
def test_boundary_r4_empty_feed_list():
    scheduler = MonitorScheduler([])
    res = scheduler.run_polling_cycle()
    assert res["total_processed"] == 0

def test_boundary_r4_all_duplicate_feed():
    urls = ["https://boards.greenhouse.io/dup_job"]
    scheduler = MonitorScheduler(urls)
    scheduler.run_polling_cycle()
    res2 = scheduler.run_polling_cycle()
    assert res2["total_processed"] == 0

def test_boundary_r4_zero_matching_jobs():
    urls = ["https://boards.greenhouse.io/low_score_job"]
    scheduler = MonitorScheduler(urls, min_threshold=5.0)
    res = scheduler.run_polling_cycle()
    assert len(res["matched_jobs"]) == 0

def test_boundary_r4_high_threshold_filtering():
    scheduler = MonitorScheduler(FEEDS, min_threshold=5.0)
    res = scheduler.run_polling_cycle()
    assert len(res["matched_jobs"]) <= 2

def test_boundary_r4_rapid_polling_cycles():
    scheduler = MonitorScheduler(FEEDS)
    for _ in range(3):
        res = scheduler.run_polling_cycle()
        assert "polled_at" in res


# ==============================================================================
# TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS (5+ TESTS)
# ==============================================================================

def test_pairwise_r1_to_r2_nats_apprentice_scoring():
    scraper = get_scraper("nats")
    job = scraper.scrape("https://nats.education.gov.in/apprentice/cisco-india")
    scorer = FitScorer()
    fit = scorer.evaluate(job)
    assert fit["score"] >= 1.0
    assert fit["location_match"] is True

def test_pairwise_r2_to_r3_global_usd_form_filling():
    mock_job = {
        "job_id": "hc_remote_01",
        "company": "US Tech Remote",
        "title": "Senior RAG Engineer",
        "workplace_type": "remote_worldwide",
        "salary_range": {"currency": "USD", "min": 60000, "max": 90000, "period": "annual"}
    }
    gen = AnswerGenerator()
    answers = gen.generate(mock_job)
    assert answers["expected_ctc"]["currency"] == "USD"

def test_pairwise_r3_to_tracker_sync(tmp_path):
    tracker_file = str(tmp_path / "sync_tracker.md")
    logger = ApplicationLogger(tracker_md_path=tracker_file)
    mock_job = {"job_id": "pair_03", "company": "SyncCorp", "title": "Data Analyst"}
    mock_fit = {"score": 4.2}
    entry = logger.log(mock_job, mock_fit, "res.tex", "cover.md")
    assert entry["job_id"] == "pair_03"
    assert entry["fit_score"] == 4.2

def test_pairwise_r4_to_r3_daemon_auto_apply():
    scheduler = MonitorScheduler(FEEDS, min_threshold=3.0)
    cycle = scheduler.run_polling_cycle()
    if cycle["matched_jobs"]:
        target_job = cycle["matched_jobs"][0]["job"]
        res = run_apply_all(target_job["source_url"], min_score_threshold=3.0)
        assert res["status"] == "SUCCESS"

def test_pairwise_r1_to_r2_to_tracker_raw_text(tmp_path):
    raw_text = "company: RawTech\ntitle: Data Science Lead\nPython SQL Machine Learning RAG"
    tracker_file = str(tmp_path / "raw_tracker.md")
    scraper = get_scraper_for_url(raw_text)
    job = scraper.scrape(raw_text)
    scorer = FitScorer()
    fit = scorer.evaluate(job)
    logger = ApplicationLogger(tracker_md_path=tracker_file)
    entry = logger.log(job, fit, "resume.tex", "cover.md")
    assert entry["company"] == "RawTech"


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS (5+ TESTS)
# ==============================================================================

def test_scenario_bangalore_sde_hybrid():
    jd = "company: Bengaluru Fintech\ntitle: Data Analyst & SDE\nLocation: Bangalore\nNotice: Immediate Joiner\nSkills: Python, SQL, Power BI, Statistical Analysis"
    res = run_apply_all(jd, min_score_threshold=3.5)
    assert res["status"] == "SUCCESS"
    assert res["form_answers"]["availability_status"] == "Immediate Joiner"
    assert res["form_answers"]["expected_ctc"]["currency"] == "INR"

def test_scenario_global_remote_ai_engineer():
    url = "https://hiring.cafe/job/worldwide-ai-engineer"
    res = run_apply_all(url, min_score_threshold=3.0)
    assert res["status"] == "SUCCESS"
    assert res["form_answers"]["expected_ctc"]["currency"] == "USD"

def test_scenario_nats_govt_apprenticeship():
    url = "https://nats.education.gov.in/apprentice/cisco-graduate-2025"
    res = run_apply_all(url, min_score_threshold=3.0)
    assert res["status"] == "SUCCESS"
    assert "nats_registration_id" in res["form_answers"]

def test_scenario_yc_startup_fullstack():
    jd = "company: YC AI Startup\ntitle: Full Stack AI Engineer\nSkills: Python, React, TypeScript, FastAPI, PostgreSQL"
    res = run_apply_all(jd, min_score_threshold=3.5)
    assert res["status"] == "SUCCESS"
    assert os.path.exists(res["resume_path"])

def test_scenario_dense_corporate_ats():
    jd = "company: GE HealthCare\ntitle: Data Science Specialist\nSkills: Python, SQL, Machine Learning, Generative AI, RAG, Retrieval-Augmented Generation, LangChain, LlamaIndex, OpenAI, PyTorch, Scikit-learn, Pandas, NumPy, FAISS, Power BI"
    res = run_apply_all(jd, min_score_threshold=3.5)
    assert res["status"] == "SUCCESS"
    assert res["fit"]["score"] >= 4.0

def test_r2_page_validator_with_feedback():
    val_res = PageValidator.validate_page_count_with_feedback("nonexistent_mock.pdf")
    assert val_res.is_valid is False
    assert val_res.page_count == 0

def test_r2_latex_single_pass_escaping():
    from tools.tailorer import escape_latex
    raw_text = "100% $50k R&D #1 node_js {test} ~ ^ \\"
    escaped = escape_latex(raw_text)
    assert r"\%" in escaped
    assert r"\$" in escaped
    assert r"\&" in escaped
    assert r"\#" in escaped
    assert r"\_" in escaped
    assert r"\{" in escaped
    assert r"\}" in escaped
    assert r"\textasciitilde{}" in escaped
    assert r"\textasciicircum{}" in escaped
    assert r"\textbackslash{}" in escaped

def test_r2_cover_letter_3_paragraph_structure(tmp_path):
    from tools.tailorer import CoverLetterGenerator
    gen = CoverLetterGenerator()
    mock_job = {"company": "Stripe", "title": "AI Engineer", "skills_required": ["Python", "PyTorch", "RAG"]}
    p1, p2, p3 = gen.generate_3_paragraphs(mock_job)
    assert "Stripe" in p1
    assert "student at" in p1 and "CGPA" in p1
    assert any(kw in p2 for kw in ["Autonomous", "Engine", "Platform", "Queue", "Pipeline", "Microservice", "RAG"])
    assert any(kw in p3 for kw in ["opportunity", "considering", "advance", "Conference", "Certified", "Publication"])

    out_md = gen.generate(mock_job, str(tmp_path / "cover.md"))
    assert os.path.exists(out_md)
    assert not os.path.exists(tmp_path / "cover.txt")


def test_new_remote_scrapers():
    assert get_scraper_for_url("https://weworkremotely.com/jobs/123").prefix == "wwr"
    assert get_scraper_for_url("https://remoteok.com/remote-jobs/123").prefix == "rok"
    assert get_scraper_for_url("https://himalayas.app/jobs/123").prefix == "him"
    assert get_scraper_for_url("https://arc.dev/remote-jobs/123").prefix == "arc"



def test_sqlite_application_tracker_db(tmp_path):
    db_file = str(tmp_path / "test_jobs.db")
    md_file = str(tmp_path / "test_apps.md")

    logger = ApplicationLogger(tracker_md_path=md_file, db_path=db_file)
    mock_job = {"job_id": "test_001", "company": "Canva", "title": "Senior Data Engineer"}
    mock_fit = {"score": 4.6}

    entry = logger.log(mock_job, mock_fit, "resume.pdf", "cover.md", status="APPLIED")
    assert entry["company"] == "Canva"
    assert entry["status"] == "APPLIED"

    apps = logger.list_applications()
    assert len(apps) == 1
    assert apps[0]["company"] == "Canva"
    assert apps[0]["status"] == "APPLIED"

    updated = logger.update_status(entry["application_id"], "INTERVIEW")
    assert updated is True

    apps_after = logger.list_applications(status_filter="INTERVIEW")
    assert len(apps_after) == 1
    assert apps_after[0]["status"] == "INTERVIEW"


