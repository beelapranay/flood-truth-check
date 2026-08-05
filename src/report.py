"""Turn scored claims into a human-readable ranked referral report."""


def render_report(scored_claims, claims_by_id, total_scanned, top_n=30):
    ranked = sorted(scored_claims, key=lambda x: x["priority"], reverse=True)[:top_n]

    lines = []
    lines.append("# Flood Claim Truth-Check — Referral Report\n")
    lines.append(
        f"Scanned **{total_scanned}** recent NFIP claims. "
        f"**{len(scored_claims)}** showed a contradiction between their stated "
        f"flood-risk story and Mireye's cited terrain/flood data. "
        f"Top **{len(ranked)}** shown below, ranked by priority "
        "(contradiction severity x payout size).\n"
    )

    for i, s in enumerate(ranked, 1):
        claim = claims_by_id.get(s["claim_id"], {})
        lat, lng = claim.get("latitude"), claim.get("longitude")
        event = claim.get("floodEvent") or "unspecified event"
        state = claim.get("state", "?")
        date = claim.get("dateOfLoss", "")[:10]
        payout = s["payout"]

        lines.append(f"## {i}. Claim `{s['claim_id']}` — priority {s['priority']}\n")
        lines.append(
            f"- Location (rounded to ~0.1°): {lat}, {lng} ({state})\n"
            f"- Date of loss: {date} — {event}\n"
            f"- Rated flood zone: {s['claim_zone']}\n"
            f"- Net building payout: ${payout:,.0f}\n"
        )
        lines.append("**Why flagged:**")
        for r in s["reasons"]:
            lines.append(f"- {r}")
        lines.append("\n**Mireye citations:**")
        for c in s["citations"]:
            lines.append(
                f"- `{c['field']}` = {c['value']} — {c['source']} "
                f"({c['confidence']} confidence, fetched {c['fetched_at']}) "
                f"[source]({c['source_url']})"
            )
        lines.append("")

    return "\n".join(lines)
