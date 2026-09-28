"""7-point verification of an application package."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.evaluator.verification_agent import ApplicationVerifier


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Job URL or pasted JD text")
    parser.add_argument("--pdf", help="Compiled resume PDF to check for the single-page constraint")
    parser.add_argument("--out", help="Also write the JSON report here")
    args = parser.parse_args()

    results = ApplicationVerifier().verify_application_package(args.input, pdf_path=args.pdf)
    print(f"Input : {results['input_source'][:80]}")
    print(f"Result: {'PASS' if results['passed'] else 'FAIL'}")
    for step, msg in results["checklist"].items():
        print(f"  {step:<18} {msg}")
    for err in results["errors"]:
        print(f"  error: {err}")
    for warn in results["warnings"]:
        print(f"  warning: {warn}")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Report saved to {args.out}")
    sys.exit(0 if results["passed"] else 1)


if __name__ == "__main__":
    main()
