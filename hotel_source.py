"""
overpass + nominatim helpers for lodging-shaped osm objects; complements wikivoyage sleep rows.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import pandas as pd
import requests

#osmf policy: always send a descriptive user-agent
USER_AGENT = "AITravelPlannerStudent/0.1 (course project; contact via repo maintainer)"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"


def nominatim_bbox(destination: str, timeout: float = 18.0) -> tuple[float, float, float, float] | None:
    #returns south, west, north, east for overpass (south lat, west lon, north lat, east lon)
    params = {
        "q": destination,
        "format": "json",
        "limit": 1,
    }
    r = requests.get(
        NOMINATIM,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    bb = data[0].get("boundingbox")
    if not bb or len(bb) != 4:
        return None
    south, north, west, east = (float(x) for x in bb)
    if south >= north or west >= east:
        return None
    return south, west, north, east


def _stars_to_band(stars_raw: object) -> str:
    if stars_raw is None or (isinstance(stars_raw, float) and pd.isna(stars_raw)):
        return "unknown"
    s = str(stars_raw).strip()
    if not s:
        return "unknown"
    m = re.search(r"(\d+(?:[.,]\d+)?)", s.replace(",", "."))
    if not m:
        return "unknown"
    try:
        v = float(m.group(1))
    except ValueError:
        return "unknown"
    if v >= 4.0:
        return "splurge"
    if v <= 2.0:
        return "budget"
    return "mid"


def _stars_display_from_tags(stars_raw: object) -> str:
    #card line should be digits only (no trailing "s" from messy osm tags)
    raw = str(stars_raw or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"(?<=\d)s\b", "", raw, flags=re.I).strip()
    m = re.search(r"\d+(?:[.,]\d+)?", raw.replace(",", "."))
    if not m:
        return raw
    v = float(m.group(0).replace(",", "."))
    v = min(5.0, max(0.0, v))
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _build_description(destination: str, tags: dict[str, Any]) -> str:
    #only stars + address for consistent cards; planner/ui strip any legacy lead text
    parts: list[str] = []
    if tags.get("stars"):
        sn = _stars_display_from_tags(tags.get("stars"))
        if sn:
            parts.append(f"Stars: {sn}")
    addr_parts = [
        str(tags.get(k) or "").strip()
        for k in ("addr:housenumber", "addr:street", "addr:city")
        if tags.get(k) and str(tags.get(k) or "").strip()
    ]
    if addr_parts:
        parts.append(f"Address: {', '.join(addr_parts)}")
    if not parts:
        return ""
    return " · ".join(parts)


def _compact_osm_tags(tags: dict[str, Any]) -> str:
    keep = (
        "name",
        "name:en",
        "tourism",
        "stars",
        "rooms",
        "beds",
        "brand",
        "operator",
        "website",
        "phone",
        "addr:city",
        "addr:street",
        "addr:housenumber",
        "opening_hours",
    )
    sub = {k: tags[k] for k in keep if k in tags and str(tags[k]).strip()}
    return json.dumps(sub, ensure_ascii=False)[:900]


def fetch_osm_lodging_places(destination: str, max_elements: int = 28) -> list[dict[str, Any]]:
    """
    pull hotel-like osm objects inside a nominatim bbox; returns plain dicts for inspection or csv.
    keys: destination, title, description, lat, lon, source, osm_tags
    """
    dest = (destination or "").strip()
    if not dest:
        return []
    time.sleep(1.0)
    bbox = nominatim_bbox(dest)
    if bbox is None:
        return []
    south, west, north, east = bbox
    #separate tourism filters read clearer than one big regex in overpass
    q = f"""[out:json][timeout:25];
(
  nwr["tourism"="hotel"]({south},{west},{north},{east});
  nwr["tourism"="hostel"]({south},{west},{north},{east});
  nwr["tourism"="guest_house"]({south},{west},{north},{east});
  nwr["tourism"="motel"]({south},{west},{north},{east});
  nwr["tourism"="chalet"]({south},{west},{north},{east});
  nwr["tourism"="apartment"]({south},{west},{north},{east});
);
out center tags {max(1, max_elements)};
"""
    r = requests.post(
        OVERPASS,
        data={"data": q},
        headers={"User-Agent": USER_AGENT},
        timeout=55.0,
    )
    r.raise_for_status()
    payload = r.json()
    elements = payload.get("elements") or []
    out: list[dict[str, Any]] = []
    for el in elements:
        if el.get("type") not in ("node", "way", "relation"):
            continue
        tags = el.get("tags") or {}
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        title = (
            str(tags.get("name") or tags.get("name:en") or tags.get("brand") or "").strip()
            or f"Unnamed {tags.get('tourism', 'hotel')}"
        )
        if len(title) > 140:
            title = title[:137] + "…"
        oid = el.get("id")
        typ = el.get("type", "node")
        browse = f"https://www.openstreetmap.org/{typ}/{oid}" if oid else ""
        desc = _build_description(dest, tags)
        out.append(
            {
                "destination": dest,
                "title": title,
                "description": desc,
                "lat": float(lat),
                "lon": float(lon),
                "source": "openstreetmap",
                "osm_tags": _compact_osm_tags(tags),
                "osm_browse_url": browse,
                "estimated_cost_band_guess": _stars_to_band(tags.get("stars")),
            }
        )
        if len(out) >= max_elements:
            break
    return out


def fetch_osm_planner_sleep_rows(destination: str, max_elements: int = 26) -> pd.DataFrame:
    #shape rows so they can concat with the processed wikivoyage sleep slice
    rows = fetch_osm_lodging_places(destination, max_elements=max_elements)
    if not rows:
        return pd.DataFrame()
    records: list[dict[str, Any]] = []
    for r in rows:
        band = str(r.get("estimated_cost_band_guess") or "unknown")
        browse = str(r.get("osm_browse_url") or "").strip()
        if not browse:
            browse = f"https://www.openstreetmap.org/?mlat={r['lat']}&mlon={r['lon']}#map=16/{r['lat']}/{r['lon']}"
        records.append(
            {
                "destination": r["destination"],
                "source_page_title": "OpenStreetMap",
                "page_type": "overpass",
                "section": "Sleep",
                "title": r["title"],
                "description": r["description"],
                "source_url": browse,
                "estimated_cost_band": band,
                "vibe_tag": "general",
                "usable_for_itinerary": 0,
                "usable_for_stay": 1,
                "likely_place_listing": 1,
                "content_score": 58,
                "data_source": "osm",
                "lat": r["lat"],
                "lon": r["lon"],
                "osm_tags": r["osm_tags"],
            }
        )
    return pd.DataFrame.from_records(records)
