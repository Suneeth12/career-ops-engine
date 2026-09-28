"""/apply-all: ingest -> score -> tailor resume -> cover letter -> form answers -> track.

Writes profile-vault/applications/<company>-<job_id>/ with exactly two files:
  resume.pdf      the tailored one-page resume
  application.md  job summary, fit score, cover letter and form answers
The LaTeX source stays in profile-vault/cache/tex/<job_id>/ (git-ignored) for manual edits.
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from typing import Any, Dict

from tools import common
from tools.evaluator import FitScorer
from tools.form_filler import AnswerGenerator
from tools.scrapers import load_job
from tools.tailorer import CoverLetterGenerator, LaTeXBuilder, PageValidator
from tools.tracker import ApplicationLogger


def _answer_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(str(value.get(k, "")) for k in ("amount", "currency", "unit")).strip()
    return str(value)


def render_application_md(job: Dict[str, Any], fit: Dict[str, Any], letter: str, answers: Dict[str, Any]) -> str:
    lines = [
        f"# {job['title']} — {job['company']}",
        "",
        f"- **Source:** {job['source_url']}",
        f"- **Location:** {job['location']} ({job['workplace_type']}, {job['employment_type']})",
        f"- **Fit:** {fit['score']:.2f} / 5.0 — {fit['recommendation']}",
        f"- **Matched skills:** {', '.join(fit['tech_stack_overlap']) or '—'}",
        f"- **Missing skills:** {', '.join(fit['missing_skills']) or '—'}",
        f"- **Generated:** {datetime.date.today().isoformat()} · resume: `resume.pdf`",
        "",
        "## Cover letter",
        "",
        letter,
        "## Form answers",
        "",
    ]
    for key, value in answers.items():
        if key == "job_id" or value in ("", None):
            continue
        lines.append(f"**{key.replace('_', ' ').capitalize()}:** {_answer_text(value)}  ")
    return "\n".join(lines) + "\n"


def run_apply_all(input_source: str, min_score_threshold: float = 3.5) -> Dict[str, Any]:
    print("\n[1/6] Ingesting job posting...")
    job = load_job(input_source)
    print(f"    {job['title']} @ {job['company']} ({job['source_url']})")

    print("[2/6] Scoring fit...")
    fit = FitScorer().evaluate(job)
    score = fit["score"]
    print(f"    {score:.2f} / 5.0 -> {fit['recommendation']}")
    if score < min_score_threshold:
        print(f"    ABORTED: score below threshold {min_score_threshold}.")
        return {"status": "ABORTED", "reason": f"Fit score {score:.2f} < threshold {min_score_threshold}", "job": job, "fit": fit}

    out_dir = os.path.join(common.APPLICATIONS_DIR, f"{common.slugify(job['company'])}-{job['job_id']}")
    print("[3/6] Tailoring and compiling resume...")
    builder = LaTeXBuilder()
    tex_path = builder.generate_latex_resume(builder.build_customization_params(job, fit),
                                             os.path.join(common.CACHE_DIR, "tex", job["job_id"], "resume.tex"))
    pdf_path = builder.compile_pdf(tex_path, output_dir=out_dir)
    pages = PageValidator.get_page_count(pdf_path)
    print(f"    {pdf_path} ({pages} page{'s' if pages != 1 else ''})")

    print("[4/6] Writing cover letter...")
    letter = CoverLetterGenerator().letter(job)
    print("[5/6] Generating form answers...")
    answers = AnswerGenerator().generate(job)
    app_md = os.path.join(out_dir, "application.md")
    with open(app_md, "w", encoding="utf-8") as f:
        f.write(render_application_md(job, fit, letter, answers))
    print(f"    {app_md}")

    result = {"job": job, "fit": fit, "resume_path": tex_path, "pdf_path": pdf_path,
              "application_md": app_md, "form_answers": answers}
    if pages != 1:
        print(f"    NOT LOGGED: resume is {pages} pages; trim {tex_path} and re-run.")
        return {"status": "PAGE_OVERFLOW", **result}

    print("[6/6] Logging to tracker...")
    entry = ApplicationLogger().log(job, fit, pdf_path, app_md, status="READY_TO_APPLY")
    print(f"    {entry['application_id']} -> {entry['status']}")
    return {"status": "SUCCESS", "tracker_entry": entry, **result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="Job URL, pasted JD text, or JobPosting .json file")
    parser.add_argument("--threshold", type=float, default=3.5, help="Minimum fit score to continue (default 3.5)")
    args = parser.parse_args()
    res = run_apply_all(args.input, args.threshold)
    sys.exit(0 if res["status"] in ("SUCCESS", "ABORTED") else 1)


if __name__ == "__main__":
    main()
