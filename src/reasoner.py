"""LLM reasoning layer: reviews each rule-flagged claim and makes the actual
judgment call — escalate or dismiss, with a rationale in its own words —
instead of the fixed threshold being the last word.

Uses Claude Haiku 4.5 with structured outputs. The system prompt is frozen
and identical across every call in a run, so it's marked for prompt caching:
the first call in a run pays the cache-write premium, every claim after that
(within the same run, and the next run within the TTL) reads it near-free.
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

SYSTEM_PROMPT = """You review candidate anomalies in NFIP (National Flood Insurance Program) claims for an insurance SIU / FEMA audit triage agent.

## Where you fit in the pipeline

A separate rule-based step has already compared each claim's stated flood risk against Mireye's independently sourced physical terrain data (elevation from USGS, flood zone and floodplain status from FEMA's NFHL, wetland proximity from USFWS NWI, coastal distance from NOAA). That step flags a claim only when at least two independent signals disagree with the claim's story. Your job is not to redo that check — it's already done and the signals are given to you as fact. Your job is to look at the specific numbers behind those signals and decide, as a human reviewer would, whether this specific claim is actually worth a person's time, and to say why in plain language a reviewer can act on.

The signals you may see, and what each one means when it fires:

- A claim rated in a high-risk FEMA flood zone (A, AE, AH, AO, AR, A99, V, VE) whose point does not sit inside any FEMA-mapped floodplain today.
- A claim rated in a high-risk zone with no wetlands intersecting or within 500 meters.
- A claim rated in a coastal high-hazard zone (V or VE — wave action risk) more than 8 km from the nearest coastline.
- A claim rated in a high-risk zone sitting on terrain over 30 meters in elevation, with no floodplain and no coast within 5 km — physically atypical for that rating.
- A claim rated in a low-risk zone (X, B, C, D) whose point sits inside a FEMA-mapped floodplain today — the reverse case, a possibly underpriced risk.
- A claim rated low-risk whose point intersects a mapped wetland.
- Whether an elevation certificate is on file for the claim. About 91% of NFIP claims nationally have none, so its absence alone means nothing — it only matters as a note on top of a real signal, because it means no paperwork exists to independently resolve the contradiction either.

## What you're being handed for each claim

The claim's rated flood zone, its net building payout, which of the signals above fired and their specific numbers (elevation in meters, distance to coast in meters, wetland counts, etc.), and the exact Mireye source and confidence level behind each number.

## What "worth escalating" means here

A genuine physical contradiction that a human reviewer could act on: the terrain plainly does not support the claim's risk classification, or plainly does support more risk than a low-risk rating implies. Weigh the actual magnitude of the numbers, not just how many signals fired — three signals that are each barely over their threshold can be weaker than one signal that is wildly off (an elevation reading 200 meters up with the nearest coast 40 km away, for instance, is a strong contradiction on its own merits, regardless of how many boxes it checked). Also weigh confidence: a "medium" confidence Mireye field is less conclusive than "high". Remember that all locations are rounded to roughly a 7-mile box for privacy — a contradiction has to be large enough to survive that fuzziness, not a close call that the rounding alone could explain.

A claim's payout size changes the *urgency* of escalating, not whether the underlying classification problem is real. A $0 or small payout means there's little money to recover right now, so a financial-recovery reviewer has less reason to rush — but the buyer for this tool is as much a data-quality and audit function (FEMA's own program office, or an insurer's compliance team) as it is fraud recovery, and a real classification error is still worth a note even at $0 payout, just with a lower-urgency recommended action. Don't let payout size override a genuine terrain contradiction into "no action" — say the contradiction is real and low-urgency, rather than dismissing it as if it doesn't matter.

## Worked examples

**Example 1 — escalate, high confidence.** Input: zone AE, payout $196,036, no elevation certificate, signals: "not within a mapped floodplain" and "atypical terrain, elevation 178.4m with no coast or floodplain within range", citations: elevation 178.4m (USGS_3DEP_COG, high confidence), within_floodplain_polygon=false (FEMA_NFHL, high confidence), coast_distance_m=61,200 (NOAA_CUSP, high confidence).
Output: `{"decision": "escalate", "confidence": "high", "rationale": "This claim is rated AE, FEMA's high-risk floodplain zone, but it sits at 178 meters of elevation, 61 km from the nearest coast, and Mireye's live FEMA lookup confirms the point isn't in a mapped floodplain at all. That's not a borderline case the 7-mile location rounding could explain away — a location that high and that far inland has no plausible path to an AE rating. Both figures come from high-confidence sources.", "recommended_action": "Refer to underwriting for a re-rate review of the AE classification; no elevation certificate exists to resolve this independently."}`

**Example 2 — dismiss, but note the issue rather than wave it away, because payout is $0.** Input: zone AE, payout $0, no elevation certificate, signals: "not within a mapped floodplain" and "atypical terrain, elevation 134.0m", citations: elevation 134.0m (USGS_3DEP_COG, high confidence), within_floodplain_polygon=false (FEMA_NFHL, high confidence).
Output: `{"decision": "dismiss", "confidence": "medium", "rationale": "The terrain contradiction here is real and well-supported: rated AE, but Mireye shows 134m elevation with no mapped floodplain nearby. However, the claim paid $0, so there's no money at stake for a fraud reviewer today. That doesn't make the classification error unimportant, just lower urgency.", "recommended_action": "Log for a batch data-quality review rather than an immediate referral; verify why an AE-rated property with no floodplain nexus generated a claim at all."}`

**Example 3 — dismiss, genuinely ambiguous.** Input: zone A, payout $8,400, elevation certificate on file, signals: "not within a mapped floodplain" and "no wetlands within 500m", citations: within_floodplain_polygon=false (FEMA_NFHL, medium confidence), intersects_wetland=false (USFWS_NWI, high confidence).
Output: `{"decision": "dismiss", "confidence": "low", "rationale": "Two signals fired, but the floodplain reading itself is only medium confidence, and this is a small claim with an elevation certificate already on file to independently verify it. The contradiction is plausible but not strong enough, given the location rounding, to be confident it isn't just a boundary effect.", "recommended_action": "No referral needed; the existing elevation certificate already gives a reviewer a way to check this if it comes up elsewhere."}`

## Rules for your answer

- Cite only the specific numbers and fields you were actually given. Never invent a fact, a distance, or a source that wasn't in the input.
- If the case is genuinely ambiguous, say so plainly in your rationale and reflect that honestly in your confidence level — don't manufacture false certainty in either direction.
- Write the rationale like you're briefing a colleague who has the same data in front of them but hasn't drawn a conclusion yet: state the contradiction, not the checklist. Do not just restate the rule-based reasons verbatim.
- `decision` is "escalate" only when the case is genuinely worth a reviewer's time; otherwise "dismiss".
- `confidence` reflects how sure you are in your own decision, not the confidence field of any single Mireye value.
- `recommended_action` is one concrete next step for a reviewer, e.g. "refer to SIU for manual site check", "flag for underwriting re-rate review", "monitor only, low priority", or "likely explained by the 7-mile location rounding — no action".
"""


class ClaimJudgment(BaseModel):
    decision: Literal["escalate", "dismiss"]
    confidence: Literal["low", "medium", "high"]
    rationale: str
    recommended_action: str


def _client():
    return anthropic.Anthropic()


def _build_user_message(claim: dict, rule_result: dict) -> str:
    lines = [
        f"Rated flood zone: {rule_result['claim_zone']}",
        f"Net building payout: ${rule_result['payout']:,.0f}",
        f"Elevation certificate on file: {'yes' if claim.get('elevationCertificateIndicator') else 'no'}",
        "",
        "Rule-triggered signals:",
    ]
    for r in rule_result["reasons"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("Mireye citations behind those signals:")
    for c in rule_result["citations"]:
        lines.append(
            f"- {c['field']} = {c['value']} ({c['source']}, {c['confidence']} confidence, "
            f"fetched {c['fetched_at']})"
        )
    return "\n".join(lines)


def reason_about_claim(claim: dict, rule_result: dict) -> Optional[dict]:
    """Calls Claude to judge one claim. Returns a dict with decision/confidence/
    rationale/recommended_action/usage, or None if the call failed (caller
    should fall back to the rule-based reasons alone)."""
    try:
        client = _client()
        response = client.messages.parse(
            model=MODEL,
            max_tokens=512,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _build_user_message(claim, rule_result)}],
            output_format=ClaimJudgment,
        )
        judgment = response.parsed_output
        return {
            "decision": judgment.decision,
            "confidence": judgment.confidence,
            "rationale": judgment.rationale,
            "recommended_action": judgment.recommended_action,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
                "cache_read_input_tokens": response.usage.cache_read_input_tokens,
            },
        }
    except Exception as e:
        return {"error": str(e)}


def reason_about_claims(scored_claims, claims_by_id, max_workers=4):
    """Mutates each scored claim dict in place, adding an 'llm' key.
    Returns aggregate usage totals across the batch."""
    totals = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "failed": 0, "sample_errors": []}

    def _run(s):
        claim = claims_by_id.get(s["claim_id"], {})
        return s, reason_about_claim(claim, s)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_run, s) for s in scored_claims]
        for fut in as_completed(futures):
            s, result = fut.result()
            if result is None or "error" in (result or {}):
                totals["failed"] += 1
                s["llm"] = None
                if result and "error" in result and len(totals["sample_errors"]) < 3:
                    totals["sample_errors"].append(result["error"])
            else:
                s["llm"] = {k: v for k, v in result.items() if k != "usage"}
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                    totals[k] += result["usage"][k]

    return totals


if __name__ == "__main__":
    import json

    data = json.load(open("output/report_run.json"))
    sample = data["scored_claims"][:3]
    claims_by_id = data["claims_by_id"]
    totals = reason_about_claims(sample, claims_by_id)
    for s in sample:
        print(f"\nclaim {s['claim_id'][:8]} — rule score {s['score']}")
        print(json.dumps(s["llm"], indent=2))
    print("\ntotals:", totals)
