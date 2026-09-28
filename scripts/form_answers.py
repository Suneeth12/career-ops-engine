"""Generate ATS application-form answers for a job posting."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.form_filler import AnswerGenerator
from tools.scrapers import load_job


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Job URL, pasted JD text, or JobPosting .json file")
    parser.add_argument("--out", help="Write the answers JSON here instead of stdout")
    args = parser.parse_args()

    output = json.dumps(AnswerGenerator().generate(load_job(args.input)), indent=2, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Form answers saved to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
