import os
import sys
import time
import json
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.scrapers import ScraperCache, get_scraper_for_url
from tools.evaluator import FitScorer, BM25ResumeMatcher
from tools.tailorer import LaTeXBuilder, PageValidator
from scripts.apply_all import run_apply_all


def test_scraper_cache_hit_and_normalization():
    url = "https://boards.greenhouse.io/test/jobs/12345?utm_source=linkedin&ref=tracker"
    ScraperCache.clear()
    
    # Verify cache miss initially
    assert ScraperCache.get(url) is None
    
    sample_data = {"job_id": "test_123", "title": "Software Engineer"}
    ScraperCache.set(url, sample_data)
    
    # Verify cache hit with tracking params stripped
    clean_url = "https://boards.greenhouse.io/test/jobs/12345"
    cached = ScraperCache.get(clean_url)
    assert cached is not None
    assert cached["job_id"] == "test_123"


def test_bm25_resume_matcher_accuracy_and_speed():
    matcher = BM25ResumeMatcher()
    jd = "Seeking a Senior AI Engineer experienced in Python, Machine Learning, RAG, PyTorch, and FastAPI microservices."
    resume = "AI Engineer with hands-on expertise in Python, PyTorch, RAG architectures, FastAPI Docker microservices, and Machine Learning."
    
    t0 = time.perf_counter()
    result = matcher.match(jd, resume)
    elapsed = time.perf_counter() - t0
    
    # Sub-millisecond execution requirement
    assert elapsed < 0.05, f"Matcher took too long: {elapsed:.4f}s"
    assert result["overall_ats_match_pct"] > 60.0
    assert result["cosine_similarity"] > 0.50
    assert "python" in [k.lower() for k in result["matched_keywords"]]
    assert "rag" in [k.lower() for k in result["matched_keywords"]]


def test_fit_scorer_2026_ats_standards():
    scorer = FitScorer()
    posting = {
        "job_id": "job_ats_test",
        "title": "Generative AI Developer",
        "company": "NextGen AI",
        "location": "Bangalore, India",
        "workplace_type": "hybrid",
        "employment_type": "full_time",
        "skills_required": ["Python", "Generative AI", "PyTorch", "FastAPI"],
        "raw_description": "Architect RAG workflows, fine-tune models, and deploy scalable FastAPI microservices.",
        "source_url": "https://example.com/job",
        "ingested_at": "2026-09-12T12:00:00Z"
    }
    
    res = scorer.evaluate(posting)
    assert "ats_score" in res
    assert res["ats_score"] >= 75.0
    
    # Verify keyword density analysis
    assert "keyword_density" in res
    assert "python" in res["keyword_density"]
    assert res["keyword_density"]["python"]["status"] in ["optimal", "sparse", "over_dense"]
    
    # Verify section semantic weights (35% skills, 40% projects, 15% summary, 10% education)
    assert "section_semantic_weights" in res
    weights = res["section_semantic_weights"]
    assert weights["skills_weight_pct"] == 35
    assert weights["projects_weight_pct"] == 40
    assert weights["summary_weight_pct"] == 15
    assert weights["education_weight_pct"] == 10
    
    # Verify HackerRank Rubric (Max 100)
    assert "hackerrank_rubric" in res
    hr = res["hackerrank_rubric"]
    assert hr["total_score"] >= 75
    assert hr["open_source_research"] in [25, 35]
    assert hr["projects_complexity"] in [20, 30]
    
    # Verify Google X-Y-Z Quantified Metrics Audit
    assert "google_xyz_metrics" in res
    xyz = res["google_xyz_metrics"]
    assert xyz["compliance_status"] == "PASS"
    assert len(xyz["action_verbs_detected"]) >= 3


def test_latex_builder_dynamic_space_budgeter_and_caching(tmp_path):
    builder = LaTeXBuilder()
    params = {
        "target_role_title": "Senior AI & RAG Engineer",
        "tailored_summary": "AI Engineer specializing in RAG architectures, LLM fine-tuning, and scalable FastAPI microservices at National Institute of Technology.",
        "highlight_skills": ["Python", "PyTorch", "FastAPI", "Docker", "AWS"]
    }
    
    test_tex_out = str(tmp_path / "test_space_budgeter.tex")
    out_tex = builder.generate_latex_resume(params, test_tex_out)
    
    with open(out_tex, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verify calibrated itemsep injected
    assert "itemsep=0.8pt" in content or "itemsep=1.0pt" in content or "itemsep=1.2pt" in content
    
    # Verify Tectonic compilation and first-pass single-page constraint (/Count 1)
    pdf_path = builder.compile_pdf(out_tex)
    assert os.path.exists(pdf_path)
    assert PageValidator.get_page_count(pdf_path) == 1
    
    # Verify sub-second artifact caching on repeated call
    t0 = time.perf_counter()
    cached_pdf = builder.compile_pdf(out_tex)
    t1 = time.perf_counter()
    assert (t1 - t0) < 0.20, f"Artifact cache hit was not sub-second: {t1 - t0:.4f}s"
    assert cached_pdf == pdf_path


def test_unified_pipeline_sub_second_execution():
    # Verify end-to-end pipeline speed using in-memory /apply-all
    url = "https://boards.greenhouse.io/job/sample"
    
    # Warm up cache
    run_apply_all(url)
    
    # Measure sub-second execution on cached pipeline
    t0 = time.perf_counter()
    res = run_apply_all(url)
    elapsed = time.perf_counter() - t0
    
    assert res["status"] == "SUCCESS"
    assert "pdf_path" in res
    assert os.path.exists(res["pdf_path"])
    assert PageValidator.get_page_count(res["pdf_path"]) == 1
    assert elapsed < 1.0, f"End-to-end pipeline exceeded 1.0s target: {elapsed:.4f}s"


def test_new_scrapers_schema_validation_execution():
    from tools.scrapers import get_scraper
    raw_input = "company: RemoteTech\ntitle: Full Stack Developer\nskills: Python, SQL, React\nLocation: Remote Worldwide"

    for board in ["remoteok", "arcdev", "himalayas", "weworkremotely", "oneremotejobs"]:
        scraper = get_scraper(board)
        job = scraper.scrape(raw_input)
        assert job["workplace_type"] in ["remote_worldwide", "remote_india", "hybrid", "on_site"]
        assert job["company"] == "RemoteTech"
        assert "Python" in job["skills_required"]


def test_normalize_cache_key_with_fragments_and_query_order():
    from tools.scrapers.cache import normalize_cache_key

    # Query param order normalization
    k1 = normalize_cache_key("https://example.com/job?b=2&a=1")
    k2 = normalize_cache_key("https://example.com/job?a=1&b=2")
    assert k1 == k2

    # Fragment preservation (prevent collision across different jobs on SPA portals)
    k_hex1 = normalize_cache_key("https://jobs.hexaware.com/#en/sites/CX_1/job/605215?")
    k_hex2 = normalize_cache_key("https://jobs.hexaware.com/#en/sites/CX_1/job/999999?")
    assert k_hex1 != k_hex2


def test_bm25_matcher_none_and_empty_guards():
    matcher = BM25ResumeMatcher()
    r1 = matcher.match(None, None)
    assert r1["bm25_normalized_pct"] == 0.0
    assert r1["cosine_similarity_pct"] == 0.0
    assert r1["overall_ats_match_pct"] == 0.0

    r2 = matcher.match("", "")
    assert r2["bm25_normalized_pct"] == 0.0
    assert r2["cosine_similarity_pct"] == 0.0


def test_fit_scorer_none_fields_and_full_profile():
    scorer = FitScorer()
    res = scorer.evaluate({"job_id": "test_none", "title": None, "raw_description": None, "skills_required": None})
    assert res["score"] >= 1.0
    assert res["section_semantic_weights"]["education_score"] == 95.0
    assert res["hackerrank_rubric"]["academic_experience"] == 25
    assert res["hackerrank_rubric"]["open_source_research"] == 35


def test_verify_application_cli_out_file(tmp_path):
    import subprocess
    report_file = str(tmp_path / "verification_report.json")
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "verify_application.py"))
    cmd = [sys.executable, script, "company: FastCorp\ntitle: AI Engineer\nPython RAG", "--out", report_file]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert os.path.exists(report_file)
    assert os.path.getsize(report_file) > 0
    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["passed"] is True
    assert "checklist" in data

