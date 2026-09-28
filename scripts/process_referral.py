"""CLI to process referral alerts from Telegram, WhatsApp, screenshots, or inbox drops.

Usage:
  python scripts/process_referral.py <path-to-text-or-json-file>
  python scripts/process_referral.py --text "Company - Prepzy.ai\nRole - AI Intern..."
  python scripts/process_referral.py --inbox

Outputs:
  profile-vault/applications/<company>-<job_id>/
    - resume.pdf (tailored 1-page PDF)
    - application.md (job summary & fit details)
    - email_draft.md (if email referral)
    - form_responses.md (if Google Form referral)
    - portal_submission.md (if portal link referral)
    - SUBMISSION_CHECKLIST.md (60-second action items)
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import common
from tools.referral_engine import ReferralProcessor, parse_referral_text


def process_single(text: str, threshold: float = 1.0) -> int:
    processor = ReferralProcessor()
    res = processor.process(text, min_score_threshold=threshold)
    if res.get("status") == "SUCCESS":
        print(f"\n[DONE] Successfully processed referral for {res['job']['company']}!")
        print(f"Artifacts ready in: {res['out_dir']}")
        print(f"Resume: {res['pdf_path']}")
        return 0
    elif res.get("status") == "ABORTED":
        print(f"\n[SKIPPED] {res.get('reason')}")
        return 0
    else:
        print(f"\n[FAILED] {res.get('status')}")
        return 1


def process_inbox(inbox_dir: str, threshold: float = 1.0) -> None:
    os.makedirs(inbox_dir, exist_ok=True)
    files = glob.glob(os.path.join(inbox_dir, "*.txt")) + glob.glob(os.path.join(inbox_dir, "*.md"))
    if not files:
        print(f"No text referral files found in {inbox_dir}.")
        print("Drop referral text files into inbox/referrals/ and rerun.")
        return

    print(f"Found {len(files)} referral file(s) in inbox:\n")
    for f in files:
        print(f"--- Processing {os.path.basename(f)} ---")
        try:
            with open(f, "r", encoding="utf-8") as handle:
                text = handle.read()
            process_single(text, threshold)
        except Exception as e:
            print(f"Error processing {f}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_file", nargs="?", help="Path to referral text or json file")
    parser.add_argument("--text", help="Raw referral text string")
    parser.add_argument("--inbox", action="store_true", help="Process all referral files in inbox/referrals/")
    parser.add_argument("--threshold", type=float, default=1.0, help="Minimum fit score threshold (default 1.0)")
    args = parser.parse_args()

    inbox_dir = os.path.join(common.ROOT, "inbox", "referrals")

    if args.inbox:
        process_inbox(inbox_dir, args.threshold)
        sys.exit(0)

    if args.text:
        ret = process_single(args.text, args.threshold)
        sys.exit(ret)

    if args.input_file:
        if not os.path.exists(args.input_file):
            print(f"Error: File not found: {args.input_file}")
            sys.exit(1)
        with open(args.input_file, "r", encoding="utf-8") as handle:
            text = handle.read()
        ret = process_single(text, args.threshold)
        sys.exit(ret)

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
