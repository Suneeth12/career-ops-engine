"""Ingest a job posting (URL or pasted JD text) into JobPosting JSON."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.scrapers import ScraperError, get_scraper_for_url


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Job URL or pasted JD text")
    parser.add_argument("--out", help="Write the JobPosting JSON here instead of stdout")
    args = parser.parse_args()

    try:
        posting = get_scraper_for_url(args.input).scrape(args.input)
    except ScraperError as e:
        sys.stderr.write(json.dumps({"error": str(e), "status": "FAILED"}) + "\n")
        sys.exit(1)

    output = json.dumps(posting, indent=2, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Ingested job saved to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
