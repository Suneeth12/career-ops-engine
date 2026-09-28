"""Fast-Apply: Single-command end-to-end application pipeline.

Accepts any input (URL, referral text, JSON path, or text file) and produces:
  1. Fit evaluation (1.0 - 5.0 score + ATS heuristics)
  2. Tailored single-page LaTeX resume compiled to PDF via Tectonic
  3. Tailored cover letter + channel-specific submission package (Email, Form, Portal)
  4. SQLite + Markdown tracking
  5. Instant copy to conversation artifact directory if specified

Usage:
  rtk python scripts/fast_apply.py "<url_or_pasted_text>"
  rtk python scripts/fast_apply.py --text "Company - ABC\nRole - ML Engineer..."
  rtk python scripts/fast_apply.py path/to/job.json
  rtk python scripts/fast_apply.py "<input>" --artifact-dir "C:/path/to/brain"
"""
import argparse
import json
import os
import shutil
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import common
from tools.evaluator import FitScorer
from tools.form_filler import AnswerGenerator
from tools.referral_engine import ReferralProcessor, parse_referral_text
from tools.scrapers import get_scraper_for_url, load_job
from tools.tailorer import CoverLetterGenerator, LaTeXBuilder, PageValidator
from tools.tracker import ApplicationLogger


def is_referral_style_text(text: str) -> bool:
    """Detects if text looks like a Telegram/WhatsApp referral alert."""
    lower = text.lower()
    return any(k in lower for k in ("company -", "company:", "role -", "role:", "batch -", "batch:"))


def run_fast_apply(source: str, threshold: float = 3.0, artifact_dir: str = None) -> Dict[str, Any]:
    cleaned = (source or "").strip()
    if not cleaned:
        raise ValueError("Input source cannot be empty.")

    # 1. Detect input type & Ingest
    print("\n[1/5] Ingesting Job Details...")
    if os.path.exists(cleaned) and cleaned.endswith(".json"):
        with open(cleaned, "r", encoding="utf-8") as f:
            job = json.load(f)
    elif os.path.exists(cleaned):
        with open(cleaned, "r", encoding="utf-8") as f:
            content = f.read()
        job = parse_referral_text(content) if is_referral_style_text(content) else get_scraper_for_url(content).scrape(content)
    elif cleaned.startswith(("http://", "https://")):
        job = load_job(cleaned)
    elif is_referral_style_text(cleaned):
        job = parse_referral_text(cleaned)
    else:
        job = get_scraper_for_url(cleaned).scrape(cleaned)

    print(f"    Target: {job.get('title')} @ {job.get('company')} ({job.get('location')})")

    # 2. Evaluate Candidate Fit
    print("[2/5] Scoring Fit & ATS Match...")
    fit = FitScorer().evaluate(job)
    score = fit["score"]
    print(f"    Fit Score: {score:.2f} / 5.0 -> {fit['recommendation']}")
    print(f"    Matched Skills: {', '.join(fit['tech_stack_overlap']) or 'None'}")

    if score < threshold:
        print(f"    ABORTED: Score {score:.2f} < threshold {threshold}.")
        return {"status": "ABORTED", "reason": f"Score {score:.2f} < threshold {threshold}", "job": job, "fit": fit}

    # 3. Tailor & Compile Single-Page Resume
    print("[3/5] Tailoring & Compiling 1-Page Resume...")
    builder = LaTeXBuilder()
    params = builder.build_customization_params(job, fit)
    cache_tex = os.path.join(common.CACHE_DIR, "tex", job["job_id"], "resume.tex")
    tex_path = builder.generate_latex_resume(params, cache_tex)

    folder_slug = f"{common.slugify(job['company'])}-{job['job_id']}"
    out_dir = os.path.join(common.APPLICATIONS_DIR, folder_slug)
    os.makedirs(out_dir, exist_ok=True)

    pdf_path = builder.compile_pdf(tex_path, output_dir=out_dir)
    pages = PageValidator.get_page_count(pdf_path)
    print(f"    Compiled: {pdf_path} ({pages} page{'s' if pages != 1 else ''})")

    # 4. Generate Application Package
    print("[4/5] Generating Application Package...")
    letter = CoverLetterGenerator().letter(job)
    answers = AnswerGenerator().generate(job)
    app_md = os.path.join(out_dir, "application.md")

    # Use ReferralProcessor helpers if referral channel is identified
    channel_text = ""
    checklist_text = ""
    if "application_channel" in job:
        rp = ReferralProcessor()
        checklist_text = rp._build_submission_checklist_text(job, fit, pdf_path, out_dir)
        channel = job["application_channel"]
        if channel == "EMAIL":
            channel_text = rp._build_email_draft_text(job, fit)
        elif channel == "GOOGLE_FORM":
            channel_text = rp._build_form_responses_text(job, fit)
        elif channel == "CAREER_LINK":
            channel_text = rp._build_portal_submission_text(job, fit)
        else:
            channel_text = rp._build_email_draft_text(job, fit)

        content = rp._render_master_app_md(job, fit, letter, answers, checklist_text, channel_text)
    else:
        from scripts.apply_all import render_application_md
        content = render_application_md(job, fit, letter, answers)

    with open(app_md, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"    Application: {app_md}")

    # Optional: copy directly to conversation artifact directory
    artifact_copy = None
    if artifact_dir and os.path.isdir(artifact_dir):
        co_slug = common.slugify(job["company"])
        artifact_copy = os.path.join(artifact_dir, f"{co_slug}_resume.pdf")
        shutil.copyfile(pdf_path, artifact_copy)
        print(f"    Artifact Copy: {artifact_copy}")

    # 5. Log Application
    print("[5/5] Logging Application...")
    entry = ApplicationLogger().log(job, fit, pdf_path, app_md, status="READY_TO_APPLY")
    print(f"    Logged: {entry['application_id']} -> READY_TO_APPLY")

    return {
        "status": "SUCCESS" if pages == 1 else "PAGE_OVERFLOW",
        "job": job,
        "fit": fit,
        "pdf_path": pdf_path,
        "tex_path": tex_path,
        "application_md": app_md,
        "artifact_pdf": artifact_copy,
        "pages": pages,
        "tracker_entry": entry,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", help="URL, file path, or JD text")
    parser.add_argument("--text", help="Raw JD or referral text")
    parser.add_argument("--file", help="Path to JD file (.txt, .md, .json)")
    parser.add_argument("--threshold", type=float, default=3.0, help="Minimum fit score (default: 3.0)")
    parser.add_argument("--artifact-dir", help="Directory to copy final resume.pdf for direct user access")
    args = parser.parse_args()

    target_source = args.text or args.file or args.input
    if not target_source:
        parser.print_help()
        sys.exit(1)

    res = run_fast_apply(target_source, threshold=args.threshold, artifact_dir=args.artifact_dir)
    if res.get("status") == "SUCCESS":
        print("\n========================================================")
        print("                 FAST APPLY COMPLETE                    ")
        print("========================================================")
        print(f"Role       : {res['job'].get('title')} @ {res['job'].get('company')}")
        print(f"Score      : {res['fit'].get('score'):.2f} / 5.0 ({res['fit'].get('recommendation')})")
        print(f"Resume PDF : {res['pdf_path']} (1 page)")
        print(f"LaTeX TeX  : {res['tex_path']}")
        print(f"Package    : {res['application_md']}")
        if res.get("artifact_pdf"):
            print(f"Artifact   : {res['artifact_pdf']}")
        print("========================================================\n")
        sys.exit(0)
    elif res.get("status") == "PAGE_OVERFLOW":
        print(f"\n[WARNING] PDF spilled to {res.get('pages')} pages. Review {res.get('tex_path')}.")
        sys.exit(2)
    else:
        print(f"\n[ABORTED] {res.get('reason')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
