"""Flood Claim Truth-Check Agent — CLI entry point.

1. Pull recent NFIP claims from FEMA's public OpenFEMA API.
2. Enrich each unique claim location with Mireye's cited terrain/flood facts.
3. Score each claim for contradictions between its stated flood-risk story
   and the physical reality Mireye reports.
4. Write a ranked referral report.
"""
import json
import os
import sys

from src.pipeline import run_pipeline
from src.report import render_report


def main(year_from=2023, limit=300, top_n=30):
    result = run_pipeline(year_from=year_from, limit=limit, progress=print)

    os.makedirs("output", exist_ok=True)
    with open("output/results.json", "w") as f:
        json.dump(result["scored_claims"], f, indent=2, default=str)

    report_md = render_report(
        result["scored_claims"],
        result["claims_by_id"],
        total_scanned=result["total_scanned"],
        top_n=top_n,
    )
    with open("output/report.md", "w") as f:
        f.write(report_md)

    print(f"Wrote output/results.json ({result['flagged_count']} flagged claims)")
    print(f"Wrote output/report.md (top {min(top_n, result['flagged_count'])})")


if __name__ == "__main__":
    year_from = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    main(year_from=year_from, limit=limit)
