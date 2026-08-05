# Flood claim truth-check agent

A submission for the Mireye Build Challenge, 2026.

Most NFIP flood claims can't be checked against the document meant to verify them; 91% are missing an elevation certificate. This agent pulls real claims from FEMA's public data, checks each one's stated flood risk against Mireye's cited terrain and flood facts, and flags the ones where the story and the ground don't match.

## Requirements

- Python 3.10+
- A Mireye API key

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add your key to a `.env` file in the project root:

```
MIREYE_API_KEY=your-key-here
```

## Running it from the command line

```bash
python3 main.py 2023 200
```

The two arguments are the earliest claim year and how many claims to pull (both optional, default to 2023 and 300). This writes `output/results.json` (every flagged claim, scored and cited) and `output/report.md` (a ranked, readable version of the same thing).

## Running the web UI

```bash
uvicorn app:app --reload --port 8010
```

Then open `http://127.0.0.1:8010`. Set a sample size, hit run, and watch it pull claims, call Mireye, and score them live. Run history persists to `output/runs/`, so you can compare runs or re-open an old one without rerunning it.

## How it's put together

```
main.py              CLI entry point
app.py                FastAPI backend for the web UI
src/
  fetch_claims.py      pulls claims from FEMA's OpenFEMA API
  mireye_client.py     batched calls to Mireye's /v1/fetch/batch
  pipeline.py          wires the above together, shared by the CLI and the API
  analyze.py           the scoring logic: what counts as a contradiction
  report.py            renders the CLI's markdown report
static/                the web UI (plain HTML/JS, no build step)
```

## Data sources

- Claims: [FEMA OpenFEMA, NFIP Redacted Claims](https://www.fema.gov/openfema-data-page/nfip-redacted-claims-v3) (public, no key needed)
- Ground truth: [Mireye API](https://docs.mireye.ai), `flood_risk` preset
