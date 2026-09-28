"""Tailor the single-page LaTeX resume to a job posting and optionally compile it."""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools import common
from tools.evaluator import FitScorer
from tools.scrapers import load_job
from tools.tailorer import LaTeXBuilder, PageValidator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Job URL, pasted JD text, or JobPosting .json file")
    parser.add_argument("--profile", help="Candidate profile JSON (default: profile-vault/candidate_profile.json)")
    parser.add_argument("--out", default=os.path.join(common.CACHE_DIR, "tex", "tailored", "resume.tex"), help="Output .tex path (PDF is written next to it)")
    parser.add_argument("--compile", action="store_true", help="Compile to PDF with Tectonic and check it is one page")
    args = parser.parse_args()

    posting = load_job(args.input)
    fit = FitScorer(args.profile).evaluate(posting)
    print(f"Fit: {fit['score']:.2f} / 5.0 ({fit['recommendation']})")

    builder = LaTeXBuilder(args.profile)
    tex = builder.generate_latex_resume(builder.build_customization_params(posting, fit), args.out)
    print(f"Resume: {tex}")
    if not args.compile:
        return

    result = PageValidator.validate_page_count_with_feedback(builder.compile_pdf(tex))
    print(f"Single page: {'PASS' if result.is_valid else 'FAIL'} - {result.feedback}")
    for tip in result.tuning_guidance:
        print(f"  - {tip}")
    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    main()
