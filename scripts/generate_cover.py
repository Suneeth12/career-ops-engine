"""Print a tailored 3-paragraph cover letter (optionally save it as .md)."""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.scrapers import load_job
from tools.tailorer import CoverLetterGenerator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Job URL, pasted JD text, or JobPosting .json file")
    parser.add_argument("--out", help="Also save the letter to this .md file")
    parser.add_argument("--profile", help="Candidate profile JSON (default: profile-vault/candidate_profile.json)")
    args = parser.parse_args()

    gen, job = CoverLetterGenerator(args.profile), load_job(args.input)
    print(gen.letter(job))
    if args.out:
        print(f"Saved to {gen.generate(job, args.out)}")


if __name__ == "__main__":
    main()
