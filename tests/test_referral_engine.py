"""Tests for Telegram/Channel Referral Processing Engine."""
import os
import pytest

from tools.referral_engine import ReferralProcessor, parse_referral_text
from tools.tailorer import PageValidator


def test_parse_referral_email_channel():
    text = """Company - Prepzy.ai
Role - AI Intern
Batch - 2025/2026/2027
Stipend - 20,000 - 25,000/month
Location - Mohali (On-site)
We're looking for Python, RAG, LangChain, FastAPI.
How to Apply:
Send your CV + GitHub + LinkedIn to puneet.sharma@globuslearn.com
Subject: Application – AI Intern"""

    job = parse_referral_text(text)
    assert job["company"] == "Prepzy.ai"
    assert job["title"] == "AI Intern"
    assert job["batch_eligible"] is True
    assert job["salary_range"]["period"] == "monthly"
    assert job["salary_range"]["min"] == 20000.0
    assert job["salary_range"]["max"] == 25000.0
    assert job["application_channel"] == "EMAIL"
    assert job["apply_target"] == "puneet.sharma@globuslearn.com"
    assert "AI Intern" in (job["email_subject_hint"] or "")
    assert "Python" in job["skills_required"]
    assert "FastAPI" in job["skills_required"]


def test_parse_referral_google_form_channel():
    text = """Company - DAITA
Role - Software Engineering Intern
Batch - 2025/2026/2027
Stipend - 60,000 - 80,000/month
Location - Bangalore
JD: https://drive.google.com/file/d/1ztMFAaMISbqYmhMmM2AG4f973ITTeS5X/view
How to Apply:
Apply Link - https://docs.google.com/forms/d/e/1FAIpQLSdK_StfmHl2ugG1hvTl0plrd9Eo9EweDYH3btWVb-u9kdDdQg/viewform"""

    job = parse_referral_text(text)
    assert job["company"] == "DAITA"
    assert job["title"] == "Software Engineering Intern"
    assert job["batch_eligible"] is True
    assert job["salary_range"]["period"] == "monthly"
    assert job["salary_range"]["min"] == 60000.0
    assert job["salary_range"]["max"] == 80000.0
    assert job["application_channel"] == "GOOGLE_FORM"
    assert "docs.google.com/forms" in job["apply_target"]
    assert job["jd_url"] is not None


def test_parse_referral_career_link():
    text = """Company - Outbox Labs
Role - Founder's Office Intern
Batch - 2025/2026/2027
Stipend - 30,000/month
Location - Bangalore
How to Apply:
https://outbox.vc/careers/founders-office-internship-with-ppo-295953"""

    job = parse_referral_text(text)
    assert job["company"] == "Outbox Labs"
    assert job["title"] == "Founder's Office Intern"
    assert job["batch_eligible"] is True
    assert job["salary_range"]["period"] == "monthly"
    assert job["salary_range"]["min"] == 30000.0
    assert job["application_channel"] == "CAREER_LINK"
    assert "outbox.vc" in job["apply_target"]


def test_dp_world_sdet_classification():
    text = """Company - DP World
Role - SDET I
Batch - 2022/2023/2024/2025
Salary - 60,000 - 90,000/month
Location - Bangalore / Hyderabad / Gurgaon
Notice Period: Immediate to Serving Notice Period Only
How to Apply:
share your resume at sudha.rangavajhula@dpworld.com"""

    job = parse_referral_text(text)
    assert job["company"] == "DP World"
    assert job["title"] == "SDET I"
    assert job["application_channel"] == "EMAIL"
    assert job["apply_target"] == "sudha.rangavajhula@dpworld.com"
    assert job["salary_range"]["period"] == "monthly"


def test_referral_processor_generates_valid_single_page_package(tmp_path, monkeypatch):
    from tools import common
    # Route applications to tmp_path to isolate test writes
    monkeypatch.setattr(common, "APPLICATIONS_DIR", str(tmp_path / "apps"))
    monkeypatch.setattr(common, "DB_PATH", str(tmp_path / "test_jobs.db"))
    monkeypatch.setattr(common, "TRACKER_MD", str(tmp_path / "test_tracker.md"))

    text = """Company - Prepzy.ai
Role - AI Intern
Batch - 2025/2026/2027
Stipend - 20,000 - 25,000/month
Location - Mohali (On-site)
We're looking for hands-on experience with Python, ML/DL, NLP, RAG, LangChain, FastAPI.
How to Apply:
Send your CV + GitHub + LinkedIn to puneet.sharma@globuslearn.com
Subject: Application – AI Intern"""

    processor = ReferralProcessor()
    res = processor.process(text, min_score_threshold=2.0)

    assert res["status"] == "SUCCESS"
    assert os.path.exists(res["pdf_path"])
    assert PageValidator.get_page_count(res["pdf_path"]) == 1
    assert os.path.exists(res["deliverables"]["application_md"])
    assert set(os.listdir(res["out_dir"])) <= {"resume.pdf", "application.md"}

    app_content = open(res["deliverables"]["application_md"], encoding="utf-8").read()
    assert "puneet.sharma@globuslearn.com" in app_content
    assert "Application – AI Intern" in app_content
    assert "⚡ 60-Second Submission Checklist" in app_content
