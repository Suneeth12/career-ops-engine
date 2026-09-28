"""Log, list, and update job applications (SQLite + job_applications.md)."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.evaluator import FitScorer
from tools.scrapers import load_job
from tools.tracker import ApplicationLogger


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="Job URL, pasted JD text, or JobPosting .json file to log")
    parser.add_argument("--resume", help="Resume file submitted (required when logging)")
    parser.add_argument("--cover", default="", help="Cover letter file submitted")
    parser.add_argument("--list", action="store_true", help="List logged applications")
    parser.add_argument("--status-filter", help="Only list this status (APPLIED, INTERVIEW, REJECTED, OFFER)")
    parser.add_argument("--update", help="Application ID or job ID whose status to change")
    parser.add_argument("--status", help="New status for --update")
    args = parser.parse_args()
    logger = ApplicationLogger()

    if args.update:
        if not args.status:
            parser.error("--update requires --status")
        found = logger.update_status(args.update, args.status)
        print(f"Updated '{args.update}' -> {args.status.upper()}" if found else f"Not found: '{args.update}'")
        sys.exit(0 if found else 1)

    if args.list or args.status_filter:
        apps = logger.list_applications(args.status_filter)
        print(f"{len(apps)} application(s) in {logger.db_path}")
        for a in apps:
            print(f"  [{a['status']}] {a['role']} @ {a['company']} | score {a['fit_score']:.2f} | "
                  f"applied {a['date_applied']} | follow-up {a['follow_up_date']} | {a['application_id']}")
        return

    if not args.input or not args.resume:
        parser.error("logging needs a job input and --resume (or use --list / --update)")
    posting = load_job(args.input)
    entry = logger.log(posting, FitScorer().evaluate(posting), args.resume, args.cover)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
