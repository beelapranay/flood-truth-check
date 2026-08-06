"""Core pipeline logic, shared by the CLI (main.py) and the web API (app.py)."""
import time

from src.fetch_claims import fetch_claims
from src.mireye_client import fetch_batch_chunked, MireyeCreditsExhausted
from src.analyze import score_claim
from src.reasoner import reason_about_claims


def run_pipeline(year_from=2023, limit=300, progress=None):
    """Runs the full pipeline and returns a dict with the scored claims,
    the source claims (keyed by id), and summary stats.

    progress: optional callable(str) invoked with human-readable status
    updates, useful for streaming progress to a UI.
    """
    def emit(msg):
        if progress:
            progress(msg)

    started_at = time.time()

    emit(f"Fetching up to {limit} NFIP claims from {year_from} onward...")
    claims = fetch_claims(year_from=year_from, limit=limit)
    emit(f"Got {len(claims)} claims.")

    claims_by_id = {c["id"]: c for c in claims}

    coord_to_claims = {}
    for c in claims:
        key = (c["latitude"], c["longitude"])
        coord_to_claims.setdefault(key, []).append(c["id"])

    unique_coords = list(coord_to_claims.keys())
    emit(f"{len(unique_coords)} unique locations after dedup — calling Mireye...")

    credits_exhausted = False
    try:
        mireye_results = fetch_batch_chunked(unique_coords)
    except MireyeCreditsExhausted as e:
        credits_exhausted = True
        mireye_results = e.partial_results + [None] * (len(unique_coords) - len(e.partial_results))
        emit(
            f"Mireye API credits ran out after {len(e.partial_results)} of "
            f"{len(unique_coords)} locations — scoring what was fetched so far."
        )

    coord_to_fields = dict(zip(unique_coords, mireye_results))

    emit("Scoring claims against Mireye's cited ground truth...")
    scored = []
    for c in claims:
        key = (c["latitude"], c["longitude"])
        fields = coord_to_fields.get(key)
        result = score_claim(c, fields)
        if result:
            scored.append(result)

    scored.sort(key=lambda x: x["priority"], reverse=True)

    llm_usage = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "failed": 0}
    if scored:
        emit(f"Asking the agent to review {len(scored)} flagged claims...")
        llm_usage = reason_about_claims(scored, claims_by_id)
        reviewed = len(scored) - llm_usage["failed"]
        emit(f"Agent reviewed {reviewed} of {len(scored)} claims ({llm_usage['failed']} review calls failed).")
        if llm_usage.get("sample_errors"):
            emit(f"Sample review error: {llm_usage['sample_errors'][0]}")

    elapsed = round(time.time() - started_at, 1)
    emit(f"Done in {elapsed}s — {len(scored)} of {len(claims)} claims flagged.")

    return {
        "params": {"year_from": year_from, "limit": limit},
        "total_scanned": len(claims),
        "unique_locations": len(unique_coords),
        "flagged_count": len(scored),
        "elapsed_seconds": elapsed,
        "scored_claims": scored,
        "claims_by_id": claims_by_id,
        "credits_exhausted": credits_exhausted,
        "llm_usage": llm_usage,
    }
