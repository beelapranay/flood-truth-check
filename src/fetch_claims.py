"""Pull public NFIP flood claims from FEMA's OpenFEMA API."""
import requests
import urllib.parse

OPENFEMA_URL = "https://www.fema.gov/api/open/v2/FimaNfipClaims"

SELECT_FIELDS = [
    "id", "dateOfLoss", "yearOfLoss", "latitude", "longitude",
    "ratedFloodZone", "floodZoneCurrent", "elevationCertificateIndicator",
    "baseFloodElevation", "lowestFloorElevation", "lowestAdjacentGrade",
    "elevationDifference", "buildingDamageAmount", "netBuildingPaymentAmount",
    "causeOfDamage", "floodEvent", "state", "reportedZipCode", "countyCode",
    "primaryResidenceIndicator", "waterDepth", "postFIRMConstructionIndicator",
]


def fetch_claims(year_from=2023, limit=300, skip=0):
    """Fetch recent NFIP claims that have a usable location and a stated flood zone."""
    filter_clause = (
        f"yearOfLoss ge {year_from} and latitude ne null and longitude ne null "
        "and (floodZoneCurrent ne null or ratedFloodZone ne null)"
    )
    params = {
        "$filter": filter_clause,
        "$select": ",".join(SELECT_FIELDS),
        "$top": limit,
        "$skip": skip,
        "$format": "json",
        "$orderby": "dateOfLoss desc",
    }
    url = f"{OPENFEMA_URL}?{urllib.parse.urlencode(params)}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("FimaNfipClaims", [])


if __name__ == "__main__":
    claims = fetch_claims(limit=5)
    for c in claims:
        print(c["id"], c["latitude"], c["longitude"], c.get("floodZoneCurrent"), c.get("ratedFloodZone"))
