"""Thin client for Mireye's /v1/fetch/batch endpoint."""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.mireye.com/v1"
EXTRA_FIELDS = [
    "fema_flood_zone",
    "flood_zone_subtype",
    "coastal_high_hazard",
    "fema_base_flood_elevation",
]

CREDIT_KEYWORDS = ("credit", "insufficient_funds", "insufficient funds", "quota exceeded", "payment required")


class MireyeCreditsExhausted(Exception):
    """Raised when Mireye reports the account is out of API credits.
    Carries whatever locations were already fetched before it happened."""

    def __init__(self, message, partial_results=None):
        super().__init__(message)
        self.partial_results = partial_results or []


def _api_key():
    key = os.environ.get("MIREYE_API_KEY")
    if not key:
        raise RuntimeError("MIREYE_API_KEY not set (check .env)")
    return key


def _looks_like_credits_exhausted(status_code, text):
    if status_code in (402, 403):
        return True
    lowered = (text or "").lower()
    return any(kw in lowered for kw in CREDIT_KEYWORDS)


def fetch_batch(coords):
    """coords: list of (lat, lng) tuples, max 25. Returns list of per-location
    result dicts (index-aligned with input), each either the raw /v1/fetch
    'fields' dict on success or None on failure."""
    if not coords:
        return []
    if len(coords) > 25:
        raise ValueError("fetch_batch supports at most 25 locations per call")

    locations = [{"lat": lat, "lng": lng} for lat, lng in coords]
    payload = {
        "locations": locations,
        "preset": "flood_risk",
        "fields": EXTRA_FIELDS,
    }
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{BASE_URL}/fetch/batch",
                headers={
                    "Authorization": f"Bearer {_api_key()}",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            if _looks_like_credits_exhausted(resp.status_code, resp.text):
                raise MireyeCreditsExhausted("Mireye API credits have been exhausted.")
            if resp.status_code >= 500:
                last_err = requests.exceptions.HTTPError(f"{resp.status_code} server error")
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except MireyeCreditsExhausted:
            raise
        except requests.exceptions.RequestException as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    else:
        raise last_err

    out = [None] * len(coords)
    for r in data.get("results", []):
        idx = r["index"]
        if r.get("ok"):
            out[idx] = r["fields"]
        else:
            err = r.get("error") or {}
            err_text = f"{err.get('error', '')} {err.get('message', '')}"
            if _looks_like_credits_exhausted(None, err_text):
                raise MireyeCreditsExhausted("Mireye API credits have been exhausted.")
            out[idx] = None
    return out


def fetch_batch_chunked(coords, chunk_size=10):
    """Handles >25 locations by chunking into smaller batches (default 10,
    well under the 25 max, to keep worst-case latency per call down).

    If Mireye reports the account is out of credits partway through, raises
    MireyeCreditsExhausted carrying whatever was already fetched, so the
    caller can still score what it got instead of losing the whole run."""
    results = []
    for i in range(0, len(coords), chunk_size):
        chunk = coords[i:i + chunk_size]
        try:
            results.extend(fetch_batch(chunk))
        except MireyeCreditsExhausted as e:
            e.partial_results = results
            raise
    return results


if __name__ == "__main__":
    res = fetch_batch([(29.7604, -95.3698)])
    import json
    print(json.dumps(res, indent=2, default=str)[:1000])
