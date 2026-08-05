"""Contradiction scoring: does a claim's stated flood-risk story match Mireye's
independently-sourced terrain/flood facts for that location?"""

SFHA_ZONES = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}
COASTAL_ZONES = {"V", "VE"}
LOW_RISK_ZONES = {"X", "B", "C", "D"}


def _val(fields, name):
    """Pull a field's value out of a Mireye fields dict, or None if absent/failed."""
    entry = fields.get(name) if fields else None
    if not entry or entry.get("status") != "ok":
        return None
    return entry.get("value")


def _citation(fields, name):
    entry = fields.get(name) if fields else None
    if not entry:
        return None
    return {
        "field": name,
        "value": entry.get("value"),
        "source": entry.get("source"),
        "source_url": entry.get("source_url"),
        "fetched_at": entry.get("fetched_at"),
        "confidence": entry.get("confidence"),
    }


def score_claim(claim, mireye_fields):
    """Returns None if the claim can't be scored (no Mireye data), else a dict
    with score, priority, reasons (plain-English), and citations (Mireye provenance)."""
    if not mireye_fields:
        return None

    claim_zone = (claim.get("floodZoneCurrent") or claim.get("ratedFloodZone") or "").strip().upper()
    # normalize e.g. "AE1" -> "AE", strip trailing digits some FEMA fields carry
    base_zone = "".join(ch for ch in claim_zone if ch.isalpha())

    elevation = _val(mireye_fields, "elevation")
    coast_distance_m = _val(mireye_fields, "coast_distance_m")
    in_floodplain = _val(mireye_fields, "within_floodplain_polygon")
    intersects_wetland = _val(mireye_fields, "intersects_wetland")
    wetlands_500m = _val(mireye_fields, "wetlands_within_500m_count")
    fema_zone_now = _val(mireye_fields, "fema_flood_zone")

    used_fields = set()
    score = 0
    reasons = []

    if base_zone in SFHA_ZONES:
        # Claim asserts meaningful flood risk. Check whether the physical
        # terrain around this (rounded) location plausibly supports that.
        if in_floodplain is False:
            score += 25
            used_fields.add("within_floodplain_polygon")
            reasons.append(
                f"Claim is rated {claim_zone} (a high-risk FEMA flood zone), but Mireye's "
                "current FEMA NFHL lookup for this location shows it is NOT within a mapped floodplain."
            )
        if intersects_wetland is False and (wetlands_500m or 0) == 0:
            score += 15
            used_fields.update({"intersects_wetland", "wetlands_within_500m_count"})
            reasons.append("No wetlands intersect or lie within 500m of this location (USFWS NWI).")
        if base_zone in COASTAL_ZONES and coast_distance_m is not None and coast_distance_m > 8000:
            score += 30
            used_fields.add("coast_distance_m")
            reasons.append(
                f"Zone {claim_zone} is a coastal high-hazard zone (wave action risk), but the "
                f"nearest coastline is {coast_distance_m / 1000:.1f} km away per NOAA."
            )
        if elevation is not None and elevation > 30 and (coast_distance_m or 0) > 5000 and in_floodplain is False:
            score += 20
            used_fields.add("elevation")
            reasons.append(
                f"Ground elevation here is {elevation:.1f}m (USGS) with no nearby coast or "
                f"mapped floodplain — atypical terrain for a {claim_zone}-rated property."
            )
    elif base_zone in LOW_RISK_ZONES:
        # Reverse check: is this actually a live, mapped floodplain today,
        # despite being rated/priced as low-risk?
        if in_floodplain is True:
            score += 40
            used_fields.add("within_floodplain_polygon")
            reasons.append(
                f"Claim is rated {claim_zone} (low-risk), but Mireye's current FEMA NFHL lookup "
                "shows this location IS within a mapped floodplain today."
            )
        if intersects_wetland is True:
            score += 15
            used_fields.add("intersects_wetland")
            reasons.append("This low-risk-rated location intersects a mapped wetland (USFWS NWI).")

    if len(reasons) < 2:
        return None  # require at least 2 independent physical signals to agree
        # before flagging — a single signal is too easily explained by the
        # ~7-mile coordinate rounding alone; missing-certificate alone (true
        # for ~91% of claims) was never a signal either

    if not claim.get("elevationCertificateIndicator"):
        score += 10
        reasons.append(
            "No elevation certificate on file for this claim either — so FEMA's own "
            "records can't independently confirm or refute this contradiction."
        )

    payout = claim.get("netBuildingPaymentAmount") or claim.get("buildingDamageAmount") or 0
    payout = payout or 0
    priority = score * (1 + min(payout, 200000) / 200000)

    citations = [c for f in used_fields if (c := _citation(mireye_fields, f))]
    if fema_zone_now:
        c = _citation(mireye_fields, "fema_flood_zone")
        if c:
            citations.append(c)

    return {
        "claim_id": claim.get("id"),
        "score": score,
        "priority": round(priority, 1),
        "reasons": reasons,
        "citations": citations,
        "claim_zone": claim_zone,
        "payout": payout,
    }
