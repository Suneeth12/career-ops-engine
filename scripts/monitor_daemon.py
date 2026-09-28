"""Score a list of job URLs and report the high-fit ones. Run it from a scheduler (e.g. daily at 9 AM).

Job URLs come from positional arguments and/or --feeds (one URL per line, # comments allowed).
Each URL must be a single job posting page, not a search or listing page.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.monitor import MonitorScheduler


def read_feeds(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("urls", nargs="*", help="Job posting URLs")
    parser.add_argument("--feeds", help="Text file with one job URL per line")
    parser.add_argument("--threshold", type=float, default=4.0, help="Minimum fit score to report (default 4.0)")
    args = parser.parse_args()

    urls = args.urls + (read_feeds(args.feeds) if args.feeds else [])
    if not urls:
        parser.error("give job URLs as arguments or via --feeds")

    res = MonitorScheduler(urls, min_threshold=args.threshold).run_polling_cycle()
    print(f"Processed {res['total_processed']} job(s); {len(res['matched_jobs'])} at >= {args.threshold}.")
    for m in sorted(res["matched_jobs"], key=lambda m: -m["fit"]["score"]):
        job = m["job"]
        print(f"  [{m['fit']['score']:.2f}] {job['title']} @ {job['company']} | {job['workplace_type']} | {job['source_url']}")
    for e in res["errors"]:
        print(f"  error: {e['source']}: {e['error']}")
    if res["matched_jobs"]:
        print("Next: python scripts/apply_all.py <job_url>")


if __name__ == "__main__":
    main()
