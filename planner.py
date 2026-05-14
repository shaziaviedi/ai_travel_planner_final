"""
turn form inputs + scraped rows into a lightweight trip bundle for the ui.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from model_utils import embed_texts

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "data" / "processed" / "travel_dataset.csv"
STAY_DATASET = ROOT / "data" / "processed" / "stay_dataset.csv"

#usd/day low/high per category at city multiplier 1.0; sums land in sensible trip bands per tier
_BUDGET_CATEGORY_DAILY_USD: dict[str, dict[str, tuple[int, int]]] = {
    "budget": {
        "lodging": (28, 48),
        "food": (22, 38),
        "transit": (6, 14),
        "activities": (10, 22),
    },
    "mid": {
        "lodging": (52, 95),
        "food": (38, 72),
        "transit": (10, 24),
        "activities": (22, 45),
    },
    "splurge": {
        "lodging": (115, 210),
        "food": (72, 125),
        "transit": (18, 42),
        "activities": (35, 80),
    },
    "not sure": {
        "lodging": (36, 65),
        "food": (28, 52),
        "transit": (8, 18),
        "activities": (12, 30),
    },
}

#rough vs a generic mid-cost baseline; unknown cities fall back to 1.0
CITY_COST_MULTIPLIERS: dict[str, float] = {
    "bangkok": 0.78,
    "cape town": 0.82,
    "bali": 0.72,
    "budapest": 0.75,
    "cairo": 0.68,
    "delhi": 0.62,
    "hanoi": 0.70,
    "ho chi minh city": 0.74,
    "istanbul": 0.76,
    "jakarta": 0.70,
    "kuala lumpur": 0.76,
    "lisbon": 0.88,
    "mexico city": 0.72,
    "phnom penh": 0.70,
    "prague": 0.82,
    "tokyo": 1.28,
    "kyoto": 1.22,
    "osaka": 1.18,
    "singapore": 1.22,
    "london": 1.35,
    "paris": 1.24,
    "zurich": 1.38,
    "new york": 1.32,
    "new york city": 1.32,
    "san francisco": 1.30,
    "los angeles": 1.18,
    "sydney": 1.20,
    "reykjavik": 1.34,
    "seoul": 1.12,
    "hong kong": 1.18,
    "dubai": 1.15,
    "rome": 1.08,
    "barcelona": 1.02,
    "amsterdam": 1.14,
    "berlin": 0.95,
    "vienna": 1.05,
    "copenhagen": 1.22,
    "manila": 0.65,
    "cebu": 0.62,
}

NO_CITY_MSG = (
    "No destination data found for {dest} yet. Try one of the currently supported cities."
)

NO_LODGING_ANY_SOURCE_MSG = (
    "No lodging listings for {dest} in our stay file, live OpenStreetMap lookup, or guide backup yet. "
    "Try another supported city, or run build_dataset.py after refreshing sources."
)

#strip these from descriptions so cards read less like raw wiki maintenance
_META_STRIP_RES = (
    re.compile(r"\[\s*edit\s*\]", re.I),
    re.compile(r"individual listings can be found[^.!?]*[.!?]?", re.I),
    re.compile(r"please add[^.!?]*[.!?]?", re.I),
    re.compile(r"\bsee also\b[^.!?]*[.!?]?", re.I),
    re.compile(r"\bfor more information\b[^.!?]*[.!?]?", re.I),
    re.compile(r"\bwikivoyage\b[^.!?]{0,40}", re.I),
)

#extra words baked into the embed query so each slice of the model hears the right job
SECTION_QUERY_HINTS = {
    "see_do": "sightseeing landmarks viewpoints museums attractions tours experiences things to see and do",
    "eat": "restaurants dining meals food cuisine local eats venues reservations",
    "drink": "bars nightlife drinks cocktails wine beer cafes lounges rooftop pub",
    "sleep": "hotels lodging accommodation rooms booking overnight stay suites hostel resort",
}

FOOD_INTENT = (
    "restaurant",
    "dining",
    "food",
    "eat",
    "meal",
    "cuisine",
    "michelin",
    "chef",
    "fine dining",
    "lunch",
    "dinner",
    "brunch",
    "tasting",
    "bakery",
    "cafe",
    "high end",
    "high-end",
)

STAY_INTENT = ("hotel", "hostel", "stay", "sleep", "lodging", "suite", "resort", "boutique")

LUXURY_ROW = (
    "michelin",
    "fine dining",
    "omakase",
    "tasting menu",
    "sommelier",
    "wine pairing",
    "degustation",
    "exclusive",
    "premium",
    "¥¥¥¥",
    "private room",
    "chef's table",
    "rooftop",
    "skyline",
)

LUXURY_STAY = (
    "luxury",
    "suite",
    "boutique",
    "five star",
    "5 star",
    "five-star",
    "concierge",
    "designer",
    "penthouse",
    "elegant",
    "upscale",
    "exclusive",
    "premium",
    "high-end",
    "high end",
    "opulent",
    "lavish",
    "ritz",
)

#extra lodging phrases for sleep-only keyword boosts (beyond LUXURY_STAY)
SLEEP_SPLURGE_LEXICON: tuple[str, ...] = (
    "grand hotel",
    "five-star",
    "5-star",
    "spa ",
    "rooftop pool",
    "skybar",
    "sky bar",
    "butler",
    "fine linens",
    "palatial",
    "design hotel",
    "private pool",
)
SLEEP_BUDGET_LEXICON: tuple[str, ...] = (
    "budget",
    "affordable",
    "cheap",
    "economical",
    "inexpensive",
    "value",
    "no-frills",
    "no frills",
    "simple stay",
    "basic",
    "backpacker",
    "shared bathroom",
    "dormitory",
    "dorm bed",
)
SLEEP_MID_LEXICON: tuple[str, ...] = (
    "mid-range",
    "mid range",
    "moderate",
    "comfortable",
    "business hotel",
    "three-star",
    "3-star",
    "four-star",
    "4 star",
    "standard",
    "pleasant",
    "contemporary",
    "stylish",
)

#extra sleep-only cues for rule-based ranking by trip budget (title+description+osm tag hints)
SLEEP_RANK_SPLURGE_TERMS: tuple[str, ...] = (
    "luxury",
    "five-star",
    "five star",
    "5-star",
    "5 star",
    "premium",
    "upscale",
    "elegant",
    "suites",
    "suite",
    "resort",
    "boutique",
    "concierge",
    "penthouse",
    "lavish",
    "opulent",
    "michelin",
    "palace",
    "grand hotel",
    "designer",
)
SLEEP_RANK_BUDGET_TERMS: tuple[str, ...] = (
    "hostel",
    "affordable",
    "simple",
    "practical",
    "budget-friendly",
    "budget friendly",
    "backpacker",
    "dorm",
    "dormitory",
    "capsule",
    "guesthouse",
    "guest house",
    "economical",
    "inexpensive",
    "value",
    "no-frills",
    "no frills",
    "cheap",
    "motel",
    "shared bath",
)
SLEEP_RANK_MID_TERMS: tuple[str, ...] = (
    "mid-range",
    "mid range",
    "balanced",
    "moderate",
    "comfortable",
    "business hotel",
    "three-star",
    "3-star",
    "four-star",
    "4-star",
    "4 star",
    "everyday",
    "reliable",
    "standard",
    "contemporary",
    "stylish",
)

#same idea as build_dataset STAY_SIGNALS; lodging has to sound like a place to sleep
LODGING_SIGNALS: tuple[str, ...] = (
    "hotel",
    "hostel",
    "ryokan",
    "inn",
    "motel",
    "lodge",
    "capsule",
    "guesthouse",
    "guest house",
    "b&b",
    "b and b",
    "resort",
    "apartment hotel",
    "lodging",
    "rooms",
    "per night",
    "/night",
    "a night",
)

#wikivoyage row text hints for itinerary ranking by budget tier (see/do/eat/drink only)
SEE_DO_SPLURGE_LEXICON: tuple[str, ...] = (
    "exclusive",
    "vip",
    "private tour",
    "luxury",
    "premium",
    "designer",
    "flagship",
    "spa",
    "wellness",
    "chauffeur",
    "concierge",
    "helicopter",
    "yacht",
    "couture",
    "personal shopper",
    "members club",
    "skip the line",
    "skip-the-line",
    "rooftop",
    "observation deck",
)
SEE_DO_BUDGET_LEXICON: tuple[str, ...] = (
    "free",
    "no charge",
    "no admission",
    "public",
    "park",
    "plaza",
    "promenade",
    "self-guided",
    "walking tour",
    "viewpoint",
    "street art",
    "temple",
    "shrine",
    "market",
    "beach",
    "trail",
    "hike",
    "picnic",
)
SEE_DO_MID_LEXICON: tuple[str, ...] = (
    "museum",
    "gallery",
    "neighborhood",
    "guided tour",
    "ticket",
    "timed entry",
)
EAT_SPLURGE_LEXICON: tuple[str, ...] = (
    "tasting menu",
    "degustation",
    "sommelier",
    "michelin",
    "chef's table",
    "chef table",
    "dress code",
    "wine pairing",
    "omakase",
    "fine dining",
    "course dinner",
    "reservations recommended",
)
EAT_BUDGET_LEXICON: tuple[str, ...] = (
    "street food",
    "food stall",
    "market stall",
    "set menu",
    "lunch special",
    "bakery",
    "counter",
    "hole in the wall",
    "food hall",
    "food court",
    "cheap eats",
    "cafeteria",
)
EAT_MID_LEXICON: tuple[str, ...] = (
    "bistro",
    "brasserie",
    "mid-range",
    "moderate",
    "neighborhood favorite",
    "casual dinner",
    "wine list",
)
DRINK_SPLURGE_LEXICON: tuple[str, ...] = (
    "rooftop",
    "champagne",
    "lounge",
    "speakeasy",
    "craft cocktail",
    "wine bar",
    "sky bar",
    "skybar",
    "terrace",
    "mixologist",
)
DRINK_BUDGET_LEXICON: tuple[str, ...] = (
    "pub",
    "happy hour",
    "draft beer",
    "standing bar",
    "dive bar",
    "local beer",
    "house wine",
    "inexpensive",
)
DRINK_MID_LEXICON: tuple[str, ...] = (
    "wine bar",
    "cocktail bar",
    "neighborhood bar",
    "patio",
    "terrace",
)


def _load_dataset() -> pd.DataFrame:
    if not DATASET.is_file():
        return pd.DataFrame()
    return pd.read_csv(DATASET)


def _load_stay_dataset() -> pd.DataFrame:
    if not STAY_DATASET.is_file():
        return pd.DataFrame()
    return pd.read_csv(STAY_DATASET)


def supported_destinations(df: pd.DataFrame | None = None) -> list[str]:
    #union of travel rows and stay rows so a city with only osm stays still lists
    travel = df if df is not None else _load_dataset()
    stay = _load_stay_dataset()
    parts: list[pd.Series] = []
    if not travel.empty and "destination" in travel.columns:
        parts.append(travel["destination"].astype(str).str.strip())
    if not stay.empty and "destination" in stay.columns:
        parts.append(stay["destination"].astype(str).str.strip())
    if not parts:
        return []
    names = pd.concat(parts, ignore_index=True)
    names = names[names.str.len() > 0]
    return sorted(names.unique().tolist(), key=str.casefold)


list_supported_destinations = supported_destinations


def strict_rows_for_destination(df: pd.DataFrame, destination: str) -> pd.DataFrame:
    #exact city match only; no substring fallback or whole-world pool
    if df.empty or not destination.strip():
        return pd.DataFrame()
    key = destination.strip().casefold()
    mask = df["destination"].astype(str).str.strip().str.casefold() == key
    return df.loc[mask].reset_index(drop=True)


def _enforce_stay_destination(df: pd.DataFrame, display_dest: str) -> pd.DataFrame:
    #last-line guard so live osm or odd csv rows never leak another city into the sleep pool
    if df.empty or not str(display_dest).strip():
        return df
    if "destination" not in df.columns:
        return df
    key = str(display_dest).strip().casefold()
    m = df["destination"].astype(str).str.strip().str.casefold() == key
    return df.loc[m].reset_index(drop=True)


def _canonical_destination_name(scoped: pd.DataFrame) -> str:
    return str(scoped["destination"].iloc[0]).strip()


def _clean_scalar(v: object) -> str:
    #csv quirks sometimes stringify missing cells as "nan"; never surface that in the ui
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if not s or s.casefold() in ("nan", "none", "null", "<na>"):
        return ""
    return s


def _row_text(row: pd.Series, col: str) -> str:
    return _clean_scalar(row.get(col, ""))


def _display_title(row: pd.Series, display_dest: str) -> str:
    #prefer a real listing name; otherwise a short human label instead of blank or "nan"
    t = _row_text(row, "title")
    if t:
        return t
    sec = _row_text(row, "section") or "spot"
    return f"{sec} · {display_dest}"


def _strip_meta_from_description(text: str) -> str:
    s = " ".join(text.split())
    for pat in _META_STRIP_RES:
        s = pat.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_description_for_display(text: str, soft_target: int = 300, hard_max: int = 420) -> str:
    #light polish plus sentence-aware trim so we do not chop mid-thought when we can help it
    s = _strip_meta_from_description(_clean_scalar(text))
    if not s:
        return ""
    if len(s) <= hard_max:
        return s
    chunk = s[:hard_max]
    lo = min(120, max(40, len(chunk) // 4))
    for punct in ".!?":
        pos = chunk.rfind(punct, lo, len(chunk))
        if pos != -1:
            return s[: pos + 1].strip()
    sp = chunk.rfind(" ", max(0, soft_target - 100), len(chunk))
    if sp > 40:
        return s[:sp].strip() + "…"
    return s[:soft_target].strip() + "…"


def _clip(text: str, n: int) -> str:
    #legacy short cut; prefer clean_description_for_display for user-facing blurbs
    text = " ".join(_clean_scalar(text).split())
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _intent_blob(vibe: str, budget: str, interests: str) -> str:
    return f"{vibe} {budget} {interests}".lower()


def _wants_food_focus(vibe: str, interests: str) -> bool:
    return any(k in _intent_blob(vibe, "", interests) for k in FOOD_INTENT)


def _wants_stay_focus(vibe: str, interests: str) -> bool:
    return any(k in _intent_blob(vibe, "", interests) for k in STAY_INTENT)


def _wants_luxury(vibe: str, budget: str, interests: str) -> bool:
    b = _intent_blob(vibe, budget, interests)
    return (
        "fancy" in b
        or "luxury" in b
        or "upscale" in b
        or "splurge" in b
        or (budget or "").strip().casefold() == "splurge"
        or "high end" in b
        or "high-end" in b
        or "fine dining" in b
    )


def _normalized_budget_key(budget: str) -> str:
    k = (budget or "not sure").strip().casefold()
    if k in ("splurge", "budget", "mid", "not sure"):
        return k
    return "not sure"


def _lexicon_hit_count(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for t in terms if t in text)


def _intent_tokens(vibe: str, interests: str) -> list[str]:
    raw = f"{vibe} {interests}".lower()
    out: list[str] = []
    for tok in re.split(r"[^\w\-]+", raw):
        t = tok.strip().casefold()
        if len(t) >= 4 and t not in out:
            out.append(t)
    return out[:24]


def _parse_osm_tags_dict(raw: object) -> dict[str, object]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return {}
    s = str(raw).strip()
    if not s or s.casefold() == "nan":
        return {}
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _osm_stars_numeric(stars_raw: object) -> float | None:
    if stars_raw is None or (isinstance(stars_raw, float) and pd.isna(stars_raw)):
        return None
    s = str(stars_raw).strip()
    if not s:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", s.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _band_from_star_value(v: float) -> str:
    if v >= 4.0:
        return "splurge"
    if v <= 2.0:
        return "budget"
    return "mid"


def _osm_star_band_from_row(row: pd.Series) -> str:
    tags = _parse_osm_tags_dict(row.get("osm_tags"))
    if not tags:
        return "unknown"
    v = _osm_stars_numeric(tags.get("stars"))
    if v is None:
        return "unknown"
    return _band_from_star_value(v)


def _osm_tags_budget_hints(row: pd.Series) -> str:
    #turn a few osm tag keys into plain words for keyword rank + mini lm blob
    tags = _parse_osm_tags_dict(row.get("osm_tags"))
    if not tags:
        return ""
    bits: list[str] = []
    tour = str(tags.get("tourism") or "").replace("_", " ").strip().lower()
    if tour:
        bits.append(tour)
    v = _osm_stars_numeric(tags.get("stars"))
    if v is not None:
        bits.append(f"stars {tags.get('stars')}")
        bb = _band_from_star_value(v)
        if bb == "splurge":
            bits.extend(["five star", "luxury", "premium", "upscale", "elegant"])
        elif bb == "budget":
            bits.extend(["two star", "affordable", "simple", "practical", "budget"])
        else:
            bits.extend(["mid-range", "moderate", "comfortable", "three star", "four star"])
    return " ".join(bits)


def _sleep_row_rank_text(row: pd.Series) -> str:
    t = _row_text(row, "title").lower()
    d = _row_text(row, "description").lower()
    band = str(row.get("estimated_cost_band", "") or "").lower()
    hint = _osm_tags_budget_hints(row).lower()
    return f"{t} {d} {band} {hint}".strip()


def _sleep_cos_weight(budget: str) -> float:
    #sleep gets more keyword weight so budget rules and osm stars can reorder results
    bk = _normalized_budget_key(budget)
    if bk in ("splurge", "budget"):
        return 0.42
    if bk == "mid":
        return 0.46
    return 0.52


def _sleep_query_extra(budget_key: str, vibe: str, interests: str) -> str:
    #tight tail so sleep embeds hear budget tier even when the vibe box is empty
    bk = _normalized_budget_key(budget_key)
    tier: dict[str, str] = {
        "splurge": (
            "luxury hotels five star boutique elegant upscale premium suites "
            "high-end exclusive refined memorable pampered designer concierge"
        ),
        "budget": (
            "hostels guesthouses budget hotels affordable capsule dormitory "
            "economical practical simple value lodging no-frills backpacker friendly"
        ),
        "mid": (
            "mid-range hotels comfortable three-star four-star business hotel "
            "moderate reliable everyday lodging contemporary"
        ),
        "not sure": "mixed hotels hostels boutique stays reasonable lodging",
    }
    bits = [tier.get(bk, tier["not sure"])]
    if (vibe or "").strip():
        bits.append((vibe or "").strip()[:160])
    if (interests or "").strip():
        bits.append((interests or "").strip()[:160])
    return " ".join(bits)


def _itinerary_budget_embed_tail(section_role: str, budget_key: str, vibe: str, interests: str) -> str:
    #extra embed text so see/do/eat/drink pools hear budget tier, not just the hotel tab
    bk = _normalized_budget_key(budget_key)
    if section_role == "see_do":
        if bk == "splurge":
            return (
                "premium exclusive flagship boutiques luxury shopping landmark tours designer galleries "
                "spa wellness memorable elevated experiences private access rooftop views chauffeured"
            )
        if bk == "budget":
            return (
                "free public parks viewpoints self-guided walks street markets outdoor plazas beaches "
                "temple grounds low-cost museums scenic overlooks picnics walking loops light spend"
            )
        if bk == "mid":
            return (
                "balanced mix classic sights timed museum entries neighborhood walking tours "
                "mid-priced attractions one highlight per block sensible pacing"
            )
        return "varied pacing mix of paid and free highlights walking neighborhoods"
    if section_role == "eat":
        if bk == "splurge":
            return (
                "fine dining michelin omakase tasting menu chef table sommelier wine pairing "
                "reservation-only upscale dinner special occasion elegant courses"
            )
        if bk == "budget":
            return (
                "street food stalls markets set menus lunch specials locals counters bakeries "
                "cheap eats hole in the wall food halls commuter spots value"
            )
        if bk == "mid":
            return "mid-range restaurants bistros casual dinner one nicer meal balanced tabs"
        return "varied dining mix casual and sit-down"
    if section_role == "drink":
        if bk == "splurge":
            return (
                "rooftop bars champagne lounges speakeasy craft cocktails wine bars skyline terraces "
                "late night upscale mixology"
            )
        if bk == "budget":
            return (
                "local pubs happy hour neighborhood bars draft beer standing bars inexpensive wine "
                "simple drinks low cover"
            )
        if bk == "mid":
            return "wine bars cocktail bars casual terraces mid-priced drinks neighborhood favorites"
        return "mixed drinks bars nightlife"
    return ""


def _build_embedding_query(
    display_dest: str,
    vibe: str,
    budget: str,
    interests: str,
    section_role: str,
) -> str:
    #stack user words + section hint so mini lm is not guessing blind
    parts = [
        display_dest,
        vibe,
        budget,
        interests,
        SECTION_QUERY_HINTS.get(section_role, ""),
    ]
    if section_role == "eat" and _wants_food_focus(vibe, interests):
        parts.append("fine dining upscale michelin omakase tasting menu chef curated special occasion")
    if section_role == "sleep":
        parts.append(_sleep_query_extra(budget, vibe, interests))
    tail = _itinerary_budget_embed_tail(section_role, budget, vibe, interests)
    if tail.strip():
        parts.append(tail.strip())
    if _wants_luxury(vibe, budget, interests):
        parts.append("splurge premium exclusive memorable high quality")
    return " ".join(p for p in parts if isinstance(p, str) and p.strip()).strip()


_DEBUG_SNIP_LEN = 160
_DEBUG_TOP_K = 8


def _debug_row_snap(row: pd.Series) -> dict[str, str]:
    #tiny row preview for streamlit json without dumping whole wiki blobs
    desc = _row_text(row, "description")
    if len(desc) > _DEBUG_SNIP_LEN:
        desc = desc[: _DEBUG_SNIP_LEN - 1] + "…"
    return {
        "section": _row_text(row, "section") or "-",
        "title": _row_text(row, "title") or "-",
        "description_snippet": desc or "-",
    }


def _debug_top_rows(pool: pd.DataFrame, k: int = _DEBUG_TOP_K) -> list[dict[str, str]]:
    if pool.empty:
        return []
    return [_debug_row_snap(row) for _, row in pool.head(k).iterrows()]


def _debug_hotel_candidate_snap(row: pd.Series) -> dict[str, object]:
    #hotel tab: enough fields to see scrape quality vs map pins before ranking
    base = _debug_row_snap(row)
    base["source_bucket"] = _stay_row_source_bucket(row)
    base["source"] = _row_text(row, "source") or "-"
    base["data_source"] = str(row.get("data_source", "") or "").strip() or "-"
    if "usable_for_stay" in row.index:
        base["usable_for_stay"] = int(pd.to_numeric(row.get("usable_for_stay"), errors="coerce") or 0)
    else:
        base["usable_for_stay"] = None
    band = _row_text(row, "estimated_cost_band")
    base["estimated_cost_band"] = band if band else "-"
    return base


def _debug_hotel_candidates_pre_rank(pool: pd.DataFrame, k: int = _DEBUG_TOP_K) -> list[dict[str, object]]:
    if pool.empty:
        return []
    return [_debug_hotel_candidate_snap(row) for _, row in pool.head(k).iterrows()]


def _debug_hotel_rows_after_ranking(pool: pd.DataFrame, k: int = _DEBUG_TOP_K) -> list[dict[str, object]]:
    if pool.empty:
        return []
    out: list[dict[str, object]] = []
    for _, row in pool.head(k).iterrows():
        d = _debug_hotel_candidate_snap(row)
        if "_sr_cos" in row.index and not (isinstance(row.get("_sr_cos"), float) and pd.isna(row.get("_sr_cos"))):
            d["rank_cos"] = float(row["_sr_cos"])
        if "_sr_boost" in row.index and not (isinstance(row.get("_sr_boost"), float) and pd.isna(row.get("_sr_boost"))):
            d["rank_keyword_boost"] = float(row["_sr_boost"])
        if "_sr_comb" in row.index and not (isinstance(row.get("_sr_comb"), float) and pd.isna(row.get("_sr_comb"))):
            d["rank_combined"] = float(row["_sr_comb"])
        out.append(d)
    return out


def _hotel_filter_stage_counts(sleep_ranked: pd.DataFrame, budget_key: str) -> dict[str, int]:
    #mirrors _build_stays masks so you can tell filtering from ranking from empty pool
    if sleep_ranked.empty:
        return {
            "ranked_pool_rows": 0,
            "after_lodging_shape_filter": 0,
            "after_trip_tier_gate": 0,
            "after_both_filters": 0,
        }
    bk = _normalized_budget_key(budget_key)
    m_lodge = sleep_ranked.apply(_row_sounds_like_lodging, axis=1)
    m_tier = sleep_ranked.apply(lambda r: _stay_passes_tier_gate(r, bk), axis=1)
    both = m_lodge & m_tier
    return {
        "ranked_pool_rows": int(len(sleep_ranked)),
        "after_lodging_shape_filter": int(m_lodge.sum()),
        "after_trip_tier_gate": int(m_tier.sum()),
        "after_both_filters": int(both.sum()),
    }


def _hotel_debug_hint_lines(
    pool_meta: dict[str, object],
    pool_df: pd.DataFrame,
    sleep_ranked: pd.DataFrame,
    stays: list,
    src_counts: dict[str, int],
    filter_counts: dict[str, int],
) -> list[str]:
    #short guesses for whether to look at data, scrape, filters, or rank
    hints: list[str] = []
    n_city = int(pool_meta.get("stay_rows_for_city_all_sections", 0) or 0)
    n_sleep_raw = int(pool_meta.get("stay_sleep_section_rows_raw", 0) or 0)
    n_csv_merge = int(pool_meta.get("stay_csv_merged_pool_rows", 0) or 0)
    n_pool = int(pool_meta.get("lodging_pool_rows_final", 0) or 0)
    n_ranked = int(filter_counts.get("ranked_pool_rows", 0) or 0)
    n_pass = int(filter_counts.get("after_both_filters", 0) or 0)

    if n_city == 0 and n_pool == 0:
        hints.append("likely missing data: stay_dataset has no rows for this exact destination string.")
    elif n_sleep_raw == 0 and n_pool == 0:
        hints.append("no Sleep rows for this city in the stay file — naming or section slice mismatch.")
    elif n_sleep_raw > 0 and n_csv_merge == 0 and n_pool == 0:
        hints.append("sleep rows exist but usable wiki + osm merge is empty before live fetch — gates may be strict or scrape is weak.")
    elif n_sleep_raw > 0 and n_csv_merge == 0 and n_pool > 0 and pool_meta.get("used_live_openstreetmap_fetch"):
        hints.append("csv merge empty; live OpenStreetMap filled the pool — rebuild stay_dataset to cache pins.")

    if pool_meta.get("used_travel_guide_sleep_fallback"):
        hints.append("travel guide Sleep fallback used — stay file + live osm had nothing usable.")

    if n_ranked > 0 and n_pass == 0:
        hints.append("ranked pool has rows but lodging + trip tier filters removed all — focus on filter rules for this budget.")
    elif n_pass > 0 and len(stays) == 0:
        hints.append("rows passed filters but no stay cards returned — title/description may be empty after trim.")
    elif n_pass > 0 and len(stays) > 0:
        hints.append("filters left candidates; ranking + formatting produced visible stays.")

    if src_counts.get("wikivoyage", 0) == 0 and src_counts.get("openstreetmap", 0) > 0 and n_pool > 0:
        hints.append("final pool is map-only (no wikivoyage rows) — wiki sleep may be unusable or absent in the file.")

    seen: set[str] = set()
    out: list[str] = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _ranking_queries(
    display_dest: str,
    vibe: str,
    budget: str,
    interests: str,
) -> dict[str, str]:
    #one embed string per slice; same strings _intent_rank feeds the model
    return {
        "see_do": _build_embedding_query(display_dest, vibe, budget, interests, "see_do"),
        "eat": _build_embedding_query(display_dest, vibe, budget, interests, "eat"),
        "drink": _build_embedding_query(display_dest, vibe, budget, interests, "drink"),
        "sleep": _build_embedding_query(display_dest, vibe, budget, interests, "sleep"),
    }


def _itinerary_cos_weight(budget: str) -> float | None:
    #slightly more keyword weight for day plans when the user picked a clear tier
    bk = _normalized_budget_key(budget)
    if bk == "splurge":
        return 0.56
    if bk == "budget":
        return 0.57
    if bk == "mid":
        return 0.63
    return None


def _keyword_boost(
    row: pd.Series,
    section_role: str,
    vibe: str,
    budget: str,
    interests: str,
) -> float:
    #cheap nudge on top of cosine so price cues move the list without trashing unrelated rows
    bk = _normalized_budget_key(budget)
    if section_role == "sleep":
        text = _sleep_row_rank_text(row)
    else:
        text = f"{_row_text(row, 'title')} {_row_text(row, 'description')}".lower()
    intent = _intent_blob(vibe, budget, interests)
    boost = 0.0
    band = ""
    if "estimated_cost_band" in row.index:
        band = str(row.get("estimated_cost_band", "") or "").lower()

    if _wants_luxury(vibe, budget, interests):
        boost += 0.055 * min(4, sum(1 for w in LUXURY_ROW if w in text))
        if section_role == "eat":
            boost += 0.05 * min(3, sum(1 for w in ("omakase", "michelin", "sommelier", "tasting", "degustation") if w in text))

    if band and section_role != "sleep":
        if bk == "splurge" and band == "splurge":
            boost += 0.18
        if bk == "budget" and band == "budget":
            boost += 0.14
        if bk == "mid" and band == "mid":
            boost += 0.11
        if _wants_luxury(vibe, budget, interests) and band == "splurge":
            boost += 0.08

    if section_role == "eat" and _wants_food_focus(vibe, interests):
        boost += 0.045 * min(
            4,
            sum(1 for w in ("michelin", "omakase", "sommelier", "tasting", "sushi", "chef", "wine pairing") if w in text),
        )

    sec = str(row.get("section", "") or "")
    if section_role == "see_do":
        if bk == "splurge":
            boost += 0.074 * min(9, _lexicon_hit_count(text, SEE_DO_SPLURGE_LEXICON))
            if sec == "Do":
                boost += 0.035 * min(4, sum(1 for w in ("spa", "wellness", "yacht", "helicopter", "vip") if w in text))
        elif bk == "budget":
            boost += 0.078 * min(9, _lexicon_hit_count(text, SEE_DO_BUDGET_LEXICON))
            if any(w in text for w in ("free", "no charge", "no admission")):
                boost += 0.09
        elif bk == "mid":
            boost += 0.055 * min(7, _lexicon_hit_count(text, SEE_DO_MID_LEXICON))
        vhits = sum(1 for tok in _intent_tokens(vibe, interests) if tok in text)
        boost += 0.022 * min(6, vhits)

    if section_role == "eat":
        if bk == "splurge":
            boost += 0.082 * min(9, _lexicon_hit_count(text, EAT_SPLURGE_LEXICON))
            boost += 0.042 * min(4, sum(1 for w in ("michelin", "omakase", "sommelier", "chef") if w in text))
        elif bk == "budget":
            boost += 0.088 * min(9, _lexicon_hit_count(text, EAT_BUDGET_LEXICON))
            if band == "budget":
                boost += 0.11
            if band == "splurge" and "street" not in text and "market" not in text:
                boost -= 0.065
        elif bk == "mid":
            boost += 0.058 * min(7, _lexicon_hit_count(text, EAT_MID_LEXICON))
            if band == "mid":
                boost += 0.09
        vhits_e = sum(1 for tok in _intent_tokens(vibe, interests) if tok in text)
        boost += 0.024 * min(6, vhits_e)

    if section_role == "drink":
        if bk == "splurge":
            boost += 0.092 * min(8, _lexicon_hit_count(text, DRINK_SPLURGE_LEXICON))
        elif bk == "budget":
            boost += 0.085 * min(8, _lexicon_hit_count(text, DRINK_BUDGET_LEXICON))
        elif bk == "mid":
            boost += 0.062 * min(7, _lexicon_hit_count(text, DRINK_MID_LEXICON))
        if any(w in intent for w in ("fancy", "luxury", "splurge", "cocktail", "wine", "rooftop")):
            boost += 0.042 * min(3, sum(1 for w in ("cocktail", "wine", "whisky", "rooftop", "lounge", "champagne") if w in text))

    if section_role == "sleep":
        osm_band = _osm_star_band_from_row(row)
        rs = _lexicon_hit_count(text, SLEEP_RANK_SPLURGE_TERMS)
        rb = _lexicon_hit_count(text, SLEEP_RANK_BUDGET_TERMS)
        rm = _lexicon_hit_count(text, SLEEP_RANK_MID_TERMS)
        ns = _lexicon_hit_count(text, SLEEP_SPLURGE_LEXICON)
        nb = _lexicon_hit_count(text, SLEEP_BUDGET_LEXICON)
        nm = _lexicon_hit_count(text, SLEEP_MID_LEXICON)
        lux_hit = sum(1 for w in LUXURY_STAY if w in text)
        splurge_shape = rs + lux_hit + ns
        budget_shape = rb + nb + sum(1 for w in ("hostel", "capsule", "dorm", "motel") if w in text)
        if band:
            if bk == "splurge" and band == "splurge":
                boost += 0.26
            elif bk == "budget" and band == "budget":
                boost += 0.24
            elif bk == "mid" and band == "mid":
                boost += 0.18
            elif bk == "splurge" and band == "budget":
                boost -= 0.1
            elif bk == "budget" and band == "splurge":
                boost -= 0.14
            elif bk == "mid" and band in ("splurge", "budget"):
                boost += 0.05
        if osm_band != "unknown":
            if bk == osm_band:
                boost += 0.16
            elif bk == "splurge" and osm_band == "budget":
                boost -= 0.12
            elif bk == "budget" and osm_band == "splurge":
                boost -= 0.14
            elif bk == "mid" and osm_band in ("splurge", "budget"):
                boost += 0.04
        if bk == "splurge":
            boost += 0.13 * min(10, splurge_shape)
            boost += 0.07 * min(5, rm)
            if budget_shape >= 2 and splurge_shape < 2:
                boost -= 0.2
            elif "hostel" in text and lux_hit == 0 and band != "splurge" and rs < 2:
                boost -= 0.16
        elif bk == "budget":
            boost += 0.15 * min(12, budget_shape + rb)
            boost += 0.09 * min(6, nb)
            if splurge_shape >= 3 and band != "budget":
                boost -= 0.14
        elif bk == "mid":
            boost += 0.12 * min(10, rm + nm)
            boost += 0.06 * min(5, rb)
            boost += 0.05 * min(5, rs)
            if "hostel" in text and "hotel" not in text and "boutique" not in text and "resort" not in text:
                boost -= 0.07
        else:
            boost += 0.04 * min(10, ns + nm + nb + rs + rb)
        vhits_s = sum(1 for tok in _intent_tokens(vibe, interests) if tok in text)
        boost += 0.028 * min(7, vhits_s)

    return float(max(0.0, min(1.0, boost)))


def _intent_rank(
    df: pd.DataFrame,
    display_dest: str,
    vibe: str,
    budget: str,
    interests: str,
    section_role: str,
    *,
    cos_weight: float | None = None,
    attach_scores: bool = False,
) -> pd.DataFrame:
    #never call the embedder on an empty frame
    if df.empty:
        return df
    q_text = _build_embedding_query(display_dest, vibe, budget, interests, section_role)
    if not q_text:
        q_text = display_dest or "travel"

    texts: list[str] = []
    for _, row in df.iterrows():
        band = _clean_scalar(row.get("estimated_cost_band", "")) if "estimated_cost_band" in row.index else ""
        if section_role == "sleep":
            hint = _osm_tags_budget_hints(row).lower()[:240]
            blob = f"{row.get('section', '')} {_row_text(row, 'title')} {_row_text(row, 'description')} {band} {hint}"
        else:
            blob = f"{row.get('section', '')} {_row_text(row, 'title')} {_row_text(row, 'description')} {band}"
        texts.append(str(blob)[:900])

    q = embed_texts([q_text])
    mat = embed_texts(texts)
    cos = (mat @ q.T).flatten().astype(np.float32)
    boosts = np.array(
        [_keyword_boost(row, section_role, vibe, budget, interests) for _, row in df.iterrows()],
        dtype=np.float32,
    )
    cw = 0.68 if cos_weight is None else float(cos_weight)
    bw = 1.0 - cw
    combined = cw * cos + bw * boosts
    order = np.argsort(-combined)
    out = df.iloc[order].reset_index(drop=True)
    if attach_scores:
        out = out.copy()
        out["_sr_cos"] = cos[order]
        out["_sr_boost"] = boosts[order]
        out["_sr_comb"] = combined[order]
    return out


def _itinerary_pool(
    scoped: pd.DataFrame,
    sections: tuple[str, ...],
    display_dest: str,
    trip_vibe: str,
    budget: str,
    must_see_interests: str,
    section_role: str,
) -> pd.DataFrame:
    pool = scoped[scoped["section"].isin(sections)].copy()
    if "usable_for_itinerary" in pool.columns:
        good = pool[pool["usable_for_itinerary"] == 1]
        if not good.empty:
            pool = good
    return _intent_rank(
        pool,
        display_dest,
        trip_vibe,
        budget,
        must_see_interests,
        section_role,
        cos_weight=_itinerary_cos_weight(budget),
    )


def _sleep_rows_filtered(scoped: pd.DataFrame) -> pd.DataFrame:
    #wikivoyage sleep slice the dataset already marked as stay-usable
    pool = scoped[scoped["section"] == "Sleep"].copy()
    if "usable_for_stay" in pool.columns:
        good = pool[pool["usable_for_stay"] == 1]
        if not good.empty:
            pool = good
    return pool


def _sleep_section_only(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "section" not in df.columns:
        return pd.DataFrame()
    return df[df["section"].astype(str).str.strip() == "Sleep"].copy()


def _usable_stay_eq1(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0).astype(int) == 1


def _subset_usable_else_empty(df: pd.DataFrame) -> pd.DataFrame:
    #wikivoyage: only rows flagged usable; never silently widen to weak prose sleep
    if df.empty:
        return df
    if "usable_for_stay" not in df.columns:
        return df.iloc[0:0].copy()
    good = df.loc[_usable_stay_eq1(df["usable_for_stay"])].copy()
    return good


def _subset_usable_else_all(df: pd.DataFrame) -> pd.DataFrame:
    #openstreetmap backup: prefer usable=1, else keep the pin rows so the tab is not blank
    if df.empty:
        return df
    if "usable_for_stay" not in df.columns:
        return df
    good = df.loc[_usable_stay_eq1(df["usable_for_stay"])].copy()
    return good if not good.empty else df.copy()


def _split_wiki_vs_osm_stays(sleep_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if sleep_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    src = sleep_df.get("source", pd.Series("", index=sleep_df.index)).fillna("").astype(str).str.strip().str.casefold()
    ds = sleep_df.get("data_source", pd.Series("", index=sleep_df.index)).fillna("").astype(str).str.strip().str.casefold()
    is_osm = (src == "openstreetmap") | (src == "osm") | (ds == "osm")
    is_wiki = (src == "wikivoyage") | (~is_osm & (src == "") & (ds != "osm"))
    return sleep_df.loc[is_wiki].copy(), sleep_df.loc[is_osm].copy()


def _stay_row_source_bucket(row: pd.Series) -> str:
    #wikivoyage vs map pins vs legacy travel sleep rows (blank source)
    s = _row_text(row, "source").casefold()
    ds = str(row.get("data_source", "") or "").strip().casefold()
    if ds == "osm" or s in ("openstreetmap", "osm"):
        return "openstreetmap"
    if s == "wikivoyage":
        return "wikivoyage"
    return "travel_guide"


def _count_stay_pool_sources(pool: pd.DataFrame) -> dict[str, int]:
    c = {"wikivoyage": 0, "openstreetmap": 0, "travel_guide": 0}
    if pool.empty:
        return c
    for _, row in pool.iterrows():
        k = _stay_row_source_bucket(row)
        c[k] = c.get(k, 0) + 1
    return c


def _dedupe_stays_prefer_wiki(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    parts = [p for p in (a, b) if p is not None and not p.empty]
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    src_cf = out.get("source", pd.Series("", index=out.index)).astype(str).str.strip().str.casefold()
    out = out.copy()
    out["_sr_rank"] = src_cf.map(lambda x: 0 if x == "wikivoyage" else 1).astype(int)
    out["_sr_tkey"] = out["title"].astype(str).str.strip().str.casefold()
    out = out.sort_values(["_sr_tkey", "_sr_rank"], kind="mergesort")
    out = out.drop_duplicates(subset=["_sr_tkey"], keep="first").drop(columns=["_sr_rank", "_sr_tkey"], errors="ignore")
    return out.reset_index(drop=True)


def _pool_from_stay_csv_slice(sleep_stay: pd.DataFrame) -> pd.DataFrame:
    #good wiki first class; osm fills gaps; same title prefers wiki
    wiki, osm = _split_wiki_vs_osm_stays(sleep_stay)
    wiki_pick = _subset_usable_else_empty(wiki)
    osm_pick = _subset_usable_else_all(osm)
    return _dedupe_stays_prefer_wiki(wiki_pick, osm_pick)


def _live_osm_stay_backup(display_dest: str) -> pd.DataFrame:
    try:
        from hotel_source import fetch_osm_planner_sleep_rows
    except Exception:
        return pd.DataFrame()
    try:
        live = fetch_osm_planner_sleep_rows(display_dest, max_elements=28)
    except Exception:
        return pd.DataFrame()
    if live.empty:
        return live
    live = live.copy()
    if "source" not in live.columns:
        live["source"] = "openstreetmap"
    else:
        s = live["source"].fillna("").astype(str).str.strip()
        live["source"] = s.mask(s == "", "openstreetmap")
    return _enforce_stay_destination(live, display_dest)


def _stay_lodging_pool(
    stay_scoped: pd.DataFrame, scoped: pd.DataFrame, display_dest: str
) -> tuple[pd.DataFrame, str | None, dict[str, object]]:
    #stay_dataset first for this city only; then live osm; then travel sleep from the same scoped slice
    notice: str | None = None
    meta: dict[str, object] = {
        "stay_rows_for_city_all_sections": int(len(stay_scoped)),
        "stay_sleep_section_rows_raw": 0,
        "stay_csv_merged_pool_rows": 0,
        "used_live_openstreetmap_fetch": False,
        "used_travel_guide_sleep_fallback": False,
    }
    sleep_stay = _sleep_section_only(stay_scoped)
    meta["stay_sleep_section_rows_raw"] = int(len(sleep_stay))
    merged = _pool_from_stay_csv_slice(sleep_stay)
    meta["stay_csv_merged_pool_rows"] = int(len(merged))
    if merged.empty:
        merged = _live_osm_stay_backup(display_dest)
        meta["used_live_openstreetmap_fetch"] = bool(not merged.empty)
    if merged.empty:
        travel_sleep = _sleep_rows_filtered(scoped)
        merged = _enforce_stay_destination(travel_sleep, display_dest)
        meta["used_travel_guide_sleep_fallback"] = bool(not merged.empty)
    if merged.empty:
        notice = NO_LODGING_ANY_SOURCE_MSG.format(dest=display_dest)
    meta["lodging_pool_rows_final"] = int(len(merged))
    return merged, notice, meta


def _stay_display_source(row: pd.Series) -> str:
    s = _row_text(row, "source")
    if s:
        return s
    if str(row.get("data_source", "") or "").strip().lower() == "osm":
        return "openstreetmap"
    return "wikivoyage"


def _sleep_pool(
    scoped: pd.DataFrame,
    display_dest: str,
    trip_vibe: str,
    budget: str,
    must_see_interests: str,
    *,
    pool: pd.DataFrame | None = None,
) -> pd.DataFrame:
    #pool= is merged stay rows for this city; else travel sleep only
    pl = pool if pool is not None else _sleep_rows_filtered(scoped)
    return _intent_rank(
        pl,
        display_dest,
        trip_vibe,
        budget,
        must_see_interests,
        "sleep",
        cos_weight=_sleep_cos_weight(budget),
        attach_scores=True,
    )


def _activity_from_row(row: pd.Series, display_dest: str) -> tuple[str, str]:
    #one listing title plus a trimmed blurb for itinerary bullets
    real_title = _row_text(row, "title").strip()
    desc = clean_description_for_display(_row_text(row, "description"), soft_target=200, hard_max=320)
    title = real_title if real_title else _display_title(row, display_dest)
    return title, desc


def _gather_unique_rows(
    pool: pd.DataFrame,
    day_i: int,
    want: int,
    display_dest: str,
) -> list[tuple[str, str]]:
    #walk ranked rows with a day-dependent hop so repeats across days feel less copy-paste
    if pool.empty or want <= 0:
        return []
    n = len(pool)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    base = (day_i * 13) % n
    hop = max(1, min(5, n // max(want, 2)))
    for k in range(min(n * 2, want * 8)):
        idx = (base + k * hop) % n
        row = pool.iloc[idx]
        t, d = _activity_from_row(row, display_dest)
        if not t and not d:
            continue
        key = t.casefold()
        if key in seen:
            continue
        if key:
            seen.add(key)
        out.append((t, d))
        if len(out) >= want:
            break
    return out


def _pair_line(title: str, desc: str) -> str:
    #single human-readable bullet body; title stays plain text for escaping upstream
    t = (title or "").strip()
    d = (
        clean_description_for_display((desc or "").strip(), soft_target=170, hard_max=260)
        if desc
        else ""
    )
    if not t and not d:
        return ""
    if t and d:
        return f"{t}: {d}"
    return t or d


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split(":", 1)[0].strip().casefold() if ":" in line else line.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def _fallback_see_bullets(dest: str, interests: str, budget_key: str) -> list[str]:
    tail = ""
    if interests.strip():
        tail = f" Keep \"{_clip(interests, 72)}\" in mind when you pick the first anchor stop."
    bk = _normalized_budget_key(budget_key)
    if bk == "splurge":
        return [
            f"Line up one headline sight or gallery moment in {dest} before queues peak; save shopping arcades for golden hour.",
            f"Pair architecture with a slow café pause in {dest}; splurge days read better with fewer but richer stops.{tail}",
        ]
    if bk == "budget":
        return [
            f"Thread {dest} with parks, plazas, and self-paced walks—free anchors keep the morning full without a ticket stack.",
            f"Pick one low-cost museum window or viewpoint in {dest}, then let street rhythm carry you until lunch.{tail}",
        ]
    return [
        f"Walk the historic or arts quarter while {dest} is still quiet; queues are gentler before lunch.",
        f"Pick one flagship sight for the morning and leave slack for alleys, markets, or a long coffee.{tail}",
    ]


def _fallback_afternoon(dest: str, budget_key: str) -> list[str]:
    bk = _normalized_budget_key(budget_key)
    if bk == "splurge":
        return [
            f"Keep the middle of the day in {dest} unhurried—spa, flagship retail, or a private-ish tour beats a cross-town sprint.",
            f"Let one tony neighborhood carry the afternoon in {dest}; depth reads more premium than a city-wide skim.",
        ]
    if bk == "budget":
        return [
            f"Stay inside one neighborhood of {dest} for the afternoon so you are not paying time in transit tax.",
            "If legs feel heavy, swap a museum hour for a shady park bench and people watching.",
        ]
    return [
        f"Stay inside one neighborhood of {dest} for the afternoon so you are not paying time in transit tax.",
        "If legs feel heavy, swap a museum hour for a shady park bench and people watching.",
    ]


def _fallback_evening(dest: str, vibe: str, budget_key: str) -> list[str]:
    v = vibe.strip()
    tail = f" You hinted at {v}, so keep the pace kind." if v else ""
    bk = _normalized_budget_key(budget_key)
    if bk == "splurge":
        return [
            f"Ease out of sightseeing before dinner; golden hour makes {dest} read differently on foot.{tail}",
            f"Tonight in {dest}, favor a grown-up lounge, rooftop pour, or tasting flight—let the tab match the tier you chose.",
        ]
    if bk == "budget":
        return [
            f"Ease out of sightseeing before dinner; golden hour makes {dest} read differently on foot.{tail}",
            f"Happy hour corners and neighborhood pubs in {dest} usually beat tourist-strip prices for the same stories.",
        ]
    return [
        f"Ease out of sightseeing before dinner; golden hour makes {dest} read differently on foot.{tail}",
        f"Later, pick a calmer bar, tea room, or hotel lounge within walking distance of your last stop.",
    ]


def _fallback_food(dest: str, budget_key: str, vibe: str) -> list[str]:
    b = (budget_key or "not sure").strip().lower()
    if b == "splurge":
        tier = "Book one standout dinner table; keep lunch casual so the day still breathes."
    elif b == "budget":
        tier = "Markets, lunch specials, and bakeries keep costs honest without feeling like a compromise."
    else:
        tier = "Mix one nicer sit-down with easy lunches so the trip stays grounded."
    vv = f" Let {vibe.strip()} steer cuisine style, not just decor." if vibe.strip() else ""
    return [
        tier + vv,
        f"Ask someone working locally what they eat on a random Tuesday in {dest}; midweek picks stay calmer.",
    ]


def _day_voice(day_n: int, *lines: str) -> str:
    #same trip inputs should not clone identical intros on every day
    if not lines:
        return ""
    return lines[(max(1, int(day_n)) - 1) % len(lines)]


def _optional_note_lines(dest: str, budget_key: str, interests: str, day_n: int) -> list[str]:
    lines: list[str] = []
    bk = _normalized_budget_key(budget_key)
    if interests.strip():
        lines.append(
            f"If \"{_clip(interests, 88)}\" stalls, ask a barista or hotel desk in {dest} for the version locals still like."
        )
    if bk == "budget":
        lines.append("Carry a little cash; small vendors sometimes nudge you off-plan with card minimums.")
        lines.append("Stack free anchors first, then spend only where flavor or access is clearly worth it.")
    elif bk == "splurge":
        lines.append("Lock limited-seat splurges before you pack; walk-in luxury gets picky fast.")
        lines.append(
            f"Build slack between marquee bookings so {dest} still feels like a trip, not a receipt sprint."
        )
    elif bk == "mid":
        lines.append("One paid highlight plus wandering usually beats stacking mid-priced tickets back-to-back.")
    if day_n % 2 == 1:
        lines.append(f"Offline maps back to your stay make late nights in {dest} feel calmer.")
    else:
        lines.append("Leave one thirty-minute hole empty; the best detours rarely show up in ranked lists.")
    return lines[:4]


def _morning_budget_opening(day_n: int, dest: str, budget_key: str) -> str:
    bk = _normalized_budget_key(budget_key)
    if bk == "splurge":
        return _day_voice(
            day_n,
            f"Treat the first hour in {dest} as a small flex: one marquee sight or a polished gallery row before lines thicken.",
            f"Anchor sunrise energy in {dest} with something camera-worthy—signature architecture or a flagship quarter still feels sleepy.",
            f"Let {dest} open with one elevated set piece you actually care about; splurge days read cheap when you stack three back-to-back.",
        )
    if bk == "budget":
        return _day_voice(
            day_n,
            f"Start {dest} on free rails—plazas, waterfront walks, temple grounds—so spend shows up only where flavor is worth it.",
            f"Bank an early win in {dest} without a ticket: markets waking up, street rhythm, window light on public squares.",
            f"Open with self-paced miles in {dest}; cafés, benches, and viewpoint stairs buy atmosphere without grazing your wallet.",
        )
    if bk == "mid":
        return _day_voice(
            day_n,
            f"Ease into {dest} with one anchor sight plus slack; mid-budget trips stay happy when you leave escape hatches open.",
            f"Start practical in {dest}: one timed ticket or museum block, then room for serendipity before prices climb at night.",
        )
    return ""


def _morning_intro(day_n: int, dest: str, vibe: str, interests: str, budget_key: str) -> str:
    #no day-of-week style prefix; the ui already shows which day this is
    opener = _morning_budget_opening(day_n, dest, budget_key)
    v = vibe.strip()
    ins = interests.strip()
    if v:
        core = _day_voice(
            day_n,
            f"You said {v}, so treat the morning as a soft landing before crowds stack up.",
            f"You said {v}; ship one small proof of it before noon so the day has soul early.",
            f"With {v} in mind, keep the first moves gentle so {dest} does not feel like a sprint.",
            f"You named {v}; let the opening hour lean that way while foot traffic is still thin.",
            f"{v} was the brief; give the morning one honest gesture toward it before the noise rises.",
        )
    else:
        core = _day_voice(
            day_n,
            f"Let {dest} wake up around you before the queues get chatty.",
            f"Start while {dest} is still stretching so you steal an hour before the tempo jumps.",
            f"Slide into {dest} while sidewalks are still forgiving and light is kind.",
            f"Give the first hour breathing room so {dest} does not read like a checklist sprint.",
            f"Catch {dest} in a quieter register if you can; afternoons rarely rewind the clock.",
        )
    if ins:
        core += f" Keep \"{_clip(ins, 64)}\" on a sticky note when you aim the first stop."
    if opener:
        return f"{opener} {core}"
    return core


def _afternoon_budget_layer(dest: str, day_n: int, budget_key: str) -> str:
    bk = _normalized_budget_key(budget_key)
    if bk == "splurge":
        return _day_voice(
            day_n,
            f"Afternoon in {dest}: slow retail, spa blocks, or a private-ish experience beat racing cross-town.",
            f"Splurge pacing in {dest} favors depth—one polished neighborhood, fewer taxi hops, longer loitering.",
        )
    if bk == "budget":
        return _day_voice(
            day_n,
            f"Keep the middle of the day in {dest} on public energy—parks, markets, self-guided walks—so tickets stay optional.",
            f"Stretch the afternoon in {dest} with shade, steps, and cheap thrills; buses and plazas often beat pricey hop tours.",
        )
    if bk == "mid":
        return _day_voice(
            day_n,
            f"Balance the afternoon in {dest}: one paid highlight, then neighborhood drift so the tab stays sensible.",
            f"Mid-budget rhythm in {dest}: pair a timed entry with wandering so you never feel locked into spendy hops.",
        )
    return ""


def _afternoon_intro(dest: str, blob: str, day_n: int, budget_key: str) -> str:
    if _nature_heavy(blob):
        base = _day_voice(
            day_n,
            f"Lean into fresh-air loops near {dest}, hydrate, and bail before you feel cooked.",
            f"Stack outdoor pockets early near {dest} while energy is high; save the roof or cafe for later.",
            f"Treat air and shade as gear near {dest}; long sun without breaks makes everything feel harder.",
        )
    elif _cityish(blob):
        base = _day_voice(
            day_n,
            f"Keep transit shallow; one quarter of {dest} is enough canvas for a full day.",
            f"Anchor this afternoon to one neighborhood island in {dest} so backtracking stays rare.",
            f"Prefer one direction through {dest} instead of crisscrossing; diagonal days feel expensive.",
            f"Let one slice of {dest} be enough today; depth reads richer than a city-wide skim.",
        )
    else:
        base = _day_voice(
            day_n,
            f"Trade one indoor block for open space so {dest} still feels airy.",
            f"Swap a boxed hour for a wandering corridor of {dest} so the afternoon keeps texture.",
            f"Balance a head-down hour with something tactile in {dest}; light hands-on time resets momentum.",
        )
    layer = _afternoon_budget_layer(dest, day_n, budget_key)
    if layer:
        return f"{layer} {base}"
    return base


def _evening_intro(dest: str, budget_key: str, wants_lux: bool, day_n: int) -> str:
    bk = (budget_key or "not sure").strip().casefold()
    if wants_lux or bk == "splurge":
        return _day_voice(
            day_n,
            f"In {dest}, let the day taper, then save a little sparkle for where you sip.",
            f"Save one polished hour in {dest} for golden light, then let the night feel unhurried.",
            f"Tonight in {dest}, favor fewer stops with more room between them; luxury likes space.",
        )
    if bk == "budget":
        return _day_voice(
            day_n,
            f"Wind down gently in {dest}; low-key hangs still feel full without a spendy tab.",
            f"Evenings in {dest} reward simple rituals: a walk, a snack window, a calm corner seat.",
            f"Pick a small, repeatable wind-down in {dest} so your wallet and nervous system agree.",
        )
    if bk == "mid":
        return _day_voice(
            day_n,
            f"Tonight in {dest}, aim for one sit-down or craft pour, then keep the route walkable so tabs stay mid-range.",
            f"Trade noise for a slower last lap in {dest} so tomorrow still feels possible.",
            f"Let the last hours in {dest} be mostly on foot; short hops read calmer than one more venue.",
        )
    return _day_voice(
        day_n,
        f"Trade noise for a slower last lap in {dest} so tomorrow still feels possible.",
        f"Let the last hours in {dest} be mostly on foot; short hops read calmer than one more venue.",
        f"Close the loop near where you sleep so {dest} ends as a neighborhood story, not a dash.",
    )


def _food_intro_block(dest: str, budget_key: str, wants_food: bool, vibe: str, day_n: int) -> str:
    b = (budget_key or "not sure").strip().lower()
    if b == "budget":
        core = _day_voice(
            day_n,
            f"Stretch the day in {dest} with midday markets, bakeries, and shared plates.",
            f"Let lunch carry {dest} today: counters, steam, and baker windows beat a stiff prix fixe.",
            f"Thread {dest} with snacks and shared tables so flavor stays high and the bill stays honest.",
        )
    elif b == "splurge":
        core = _day_voice(
            day_n,
            f"Pick one memorable sit-down in {dest} and balance with casual bites.",
            f"Book the marquee table once in {dest}, then let street food and cafes do the heavy lifting.",
            f"Splurge where {dest} truly shines, then coast on simple meals so the trip keeps range.",
        )
    else:
        core = _day_voice(
            day_n,
            f"Mix a nicer dinner with easy lunches in {dest} so you can still wander.",
            f"Alternate anchor meals with light picks in {dest} so taste stays sharp without slowing you down.",
            f"Let {dest} show you two speeds: one slow meal, one grab-and-go rhythm that keeps you moving.",
        )
    if wants_food:
        core += " You signalled food matters, so follow cravings, not only rankings."
    elif vibe.strip():
        core += f" Let {vibe.strip()} nudge cuisine style, not just venue flash."
    return core


def _section_dict(intro: str, bullets: list[str]) -> dict[str, object]:
    return {"intro": intro.strip(), "bullets": [b for b in bullets if b and str(b).strip()]}


def _build_itinerary_days(
    days: int,
    see_do: pd.DataFrame,
    eat: pd.DataFrame,
    drink: pd.DataFrame,
    display_dest: str,
    trip_vibe: str,
    budget: str,
    must_see_interests: str,
) -> list[dict[str, object]]:
    #rule-based day blocks; ranked rows fill bullets, templates cover thin pools without sounding robotic
    vibe = (trip_vibe or "").strip()
    interests = (must_see_interests or "").strip()
    budget_key = (budget or "not sure").strip().lower()
    blob = _intent_blob(vibe, budget_key, interests)
    wants_lux = _wants_luxury(vibe, budget_key, interests)
    wants_food = _wants_food_focus(vibe, interests)

    out: list[dict[str, object]] = []
    for i in range(days):
        day_n = i + 1
        see_rows = _gather_unique_rows(see_do, i, 6, display_dest)
        eat_rows = _gather_unique_rows(eat, i, 4, display_dest)
        drink_rows = _gather_unique_rows(drink, i, 3, display_dest)

        m_pairs = see_rows[0:2]
        m_bullets = _dedupe_lines([_pair_line(t, d) for t, d in m_pairs if _pair_line(t, d)])
        if not m_bullets:
            m_bullets = _fallback_see_bullets(display_dest, interests, budget_key)
        elif len(m_bullets) == 1:
            fb = _fallback_see_bullets(display_dest, interests, budget_key)
            m_bullets.append(fb[1] if len(fb) > 1 else fb[0])
        m_bullets = m_bullets[:3]

        a_pairs = see_rows[2:4] if len(see_rows) >= 3 else see_rows[1:3]
        a_bullets = _dedupe_lines([_pair_line(t, d) for t, d in a_pairs if _pair_line(t, d)])
        if not a_bullets:
            a_bullets = _fallback_afternoon(display_dest, budget_key)
        elif len(a_bullets) == 1:
            fb = _fallback_afternoon(display_dest, budget_key)
            a_bullets.append(fb[1] if len(fb) > 1 else fb[0])
        seen_m = {
            x.split(":", 1)[0].strip().casefold() if ":" in x else x.strip().casefold() for x in m_bullets
        }
        a_bullets = [
            x
            for x in a_bullets
            if (x.split(":", 1)[0].strip().casefold() if ":" in x else x.strip().casefold()) not in seen_m
        ]
        if not a_bullets:
            a_bullets = _fallback_afternoon(display_dest, budget_key)
        a_bullets = a_bullets[:3]

        ev: list[str] = []
        if drink_rows:
            ev.append(_pair_line(*drink_rows[0]))
        if len(drink_rows) > 1:
            ln = _pair_line(*drink_rows[1])
            if ln:
                ev.append(ln)
        if len(ev) < 2 and len(see_rows) > 4:
            ln = _pair_line(*see_rows[4])
            if ln:
                ev.append(ln)
        if len(ev) < 2:
            ev.extend(_fallback_evening(display_dest, vibe, budget_key))
        ev = _dedupe_lines(ev)[:4]

        food_lines = _dedupe_lines([_pair_line(t, d) for t, d in eat_rows[:3] if _pair_line(t, d)])
        if not food_lines:
            food_lines = _fallback_food(display_dest, budget_key, vibe)
        elif len(food_lines) == 1:
            fb = _fallback_food(display_dest, budget_key, vibe)
            food_lines.append(fb[1] if len(fb) > 1 else fb[0])
        food_lines = food_lines[:4]

        notes = _optional_note_lines(display_dest, budget_key, interests, day_n)

        if not see_rows and not eat_rows:
            thin = (
                "Dataset matches are thin for this city slice; treat bullets as guardrails and "
                "swap in fresher picks from locals when you land."
            )
            m_bullets = [thin, *m_bullets][:4]

        out.append(
            {
                "day": day_n,
                "morning_plan": _section_dict(
                    _morning_intro(day_n, display_dest, vibe, interests, budget_key), m_bullets
                ),
                "afternoon_plan": _section_dict(_afternoon_intro(display_dest, blob, day_n, budget_key), a_bullets),
                "evening_plan": _section_dict(_evening_intro(display_dest, budget_key, wants_lux, day_n), ev),
                "food_plan": _section_dict(
                    _food_intro_block(display_dest, budget_key, wants_food, vibe, day_n), food_lines
                ),
                "optional_notes": _section_dict("", notes),
            }
        )
    return out


def _row_sounds_like_lodging(row: pd.Series) -> bool:
    blob = f"{_row_text(row, 'title')} {_row_text(row, 'description')}".casefold()
    return any(sig in blob for sig in LODGING_SIGNALS)


def _splurge_stay_gate(row: pd.Series) -> bool:
    text = f"{_row_text(row, 'title')} {_row_text(row, 'description')}".lower()
    band = str(row.get("estimated_cost_band", "") or "").lower()
    if band == "splurge":
        return True
    if _lexicon_hit_count(text, SLEEP_SPLURGE_LEXICON) >= 1:
        return True
    if sum(1 for w in LUXURY_STAY if w in text) >= 1:
        return True
    return False


def _budget_stay_gate(row: pd.Series) -> bool:
    text = f"{_row_text(row, 'title')} {_row_text(row, 'description')}".lower()
    band = str(row.get("estimated_cost_band", "") or "").lower()
    if band == "budget":
        return True
    if any(w in text for w in ("hostel", "capsule", "dorm", "dormitory", "motel")):
        return True
    if _lexicon_hit_count(text, SLEEP_BUDGET_LEXICON) >= 1:
        return True
    if band == "splurge" and "hostel" not in text and "capsule" not in text:
        return False
    return band in ("mid", "unknown", "")


def _stay_passes_tier_gate(row: pd.Series, bk: str) -> bool:
    if bk == "splurge":
        return _splurge_stay_gate(row)
    if bk == "budget":
        return _budget_stay_gate(row)
    return True


def _stay_budget_alignment_sentence(row: pd.Series, bk: str) -> str | None:
    #plain-language tie to the trip budget tier and osm star hints (rule-based rank echo)
    blob = _sleep_row_rank_text(row)
    band = str(row.get("estimated_cost_band", "") or "").strip().lower()
    osmb = _osm_star_band_from_row(row)
    if bk == "splurge":
        hints: list[str] = []
        if band == "splurge":
            hints.append("the listing tier tag reads splurge")
        if osmb == "splurge":
            hints.append("OpenStreetMap star tags read about four stars or higher")
        rg = _lexicon_hit_count(blob, SLEEP_RANK_SPLURGE_TERMS) + sum(1 for w in LUXURY_STAY if w in blob)
        if rg:
            hints.append("wording carries luxury, boutique, or upscale lodging cues")
        if hints:
            return "Ranked up for your splurge budget because " + "; ".join(hints) + "."
        return None
    if bk == "budget":
        hints = []
        if band == "budget":
            hints.append("the tier tag reads budget")
        if osmb == "budget":
            hints.append("map star tags skew toward simpler or two-star style")
        if _lexicon_hit_count(blob, SLEEP_RANK_BUDGET_TERMS) or any(w in blob for w in ("hostel", "capsule", "dorm")):
            hints.append("language reads affordable, practical, or hostel-style")
        if hints:
            return "Prioritized for your budget tier because " + "; ".join(hints) + "."
        return None
    if bk == "mid":
        hints = []
        if band == "mid":
            hints.append("the tier tag reads mid-range")
        if osmb == "mid":
            hints.append("map star hints sit in a comfortable middle band")
        if _lexicon_hit_count(blob, SLEEP_RANK_MID_TERMS):
            hints.append("copy sounds like balanced everyday lodging")
        if hints:
            return "Fits your moderate budget because " + "; ".join(hints) + "."
        return None
    return None


def _stay_match_reason(row: pd.Series, bk: str, vibe: str, interests: str) -> str:
    parts: list[str] = []
    src = str(row.get("source", "") or "").strip().casefold()
    ds = str(row.get("data_source", "") or "").strip().lower()
    if ds == "osm" or src == "openstreetmap":
        parts.append("OpenStreetMap lodging pin (community map data).")
    elif src == "wikivoyage":
        parts.append("Wikivoyage travel guide listing.")
    blob = _sleep_row_rank_text(row)
    align = _stay_budget_alignment_sentence(row, bk)
    if align:
        parts.append(align)
    luxish = _lexicon_hit_count(blob, SLEEP_SPLURGE_LEXICON) + sum(1 for w in LUXURY_STAY if w in blob)
    if bk == "splurge" and luxish > 0:
        parts.append("Wording leans premium, luxury, or boutique lodging.")
    elif bk == "budget" and (
        _lexicon_hit_count(blob, SLEEP_BUDGET_LEXICON) > 0
        or "hostel" in blob
        or "capsule" in blob
    ):
        parts.append("Reads budget-conscious, hostel-style, or practical on price.")
    elif bk == "mid" and _lexicon_hit_count(blob, SLEEP_MID_LEXICON) > 0:
        parts.append("Sounds like a mid-range or everyday-comfort stay.")
    hits = [t for t in _intent_tokens(vibe, interests) if t in blob][:4]
    if hits:
        parts.append(f"Touches your trip keywords: {', '.join(hits)}.")
    if not parts:
        parts.append("Best fit among the lodging rows we have for this city and your inputs.")
    return " ".join(parts)


_STAY_SUMMARY_SIGNAL: tuple[str, ...] = (
    "breakfast",
    "wifi",
    "wi-fi",
    "metro",
    "station",
    "walk",
    "bus",
    "tram",
    "airport",
    "terrace",
    "rooftop",
    "pool",
    "spa",
    "garden",
    "quiet",
    "dorm",
    "hostel",
    "shared",
    "kitchen",
    "laundry",
    "historic",
    "boutique",
    "ensuite",
    "en-suite",
    "family",
    "parking",
    "elevator",
    "lift",
    "balcony",
    "view",
)

_STAY_GENERIC_OPENERS: tuple[str, ...] = (
    "located in ",
    "situated in ",
    "set in ",
    "conveniently located",
    "conveniently situated",
    "this hotel ",
    "this property ",
    "this hostel ",
    "the hotel ",
    "the property ",
    "the hostel ",
    "welcome to ",
)

_STAY_BOILERPLATE_FRAGMENTS: tuple[str, ...] = (
    "for more information",
    "please visit",
    "visit our website",
    "visit www",
    "check availability",
    "book online",
    "click here",
    "contact us today",
)


def _split_stay_sentences(text: str) -> list[str]:
    #simple split on sentence end; good enough for guide blurbs
    t = " ".join(text.split()).strip()
    if not t:
        return []
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", t) if p.strip()]


def _dedupe_stay_sentences(text: str) -> str:
    #drop repeated sentences so cards are not padded with echo
    parts = _split_stay_sentences(text)
    if not parts:
        return " ".join(text.split()).strip()
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        key = p.casefold().rstrip(".!? ")
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return " ".join(out)


def _strip_stay_generic_openers(text: str) -> str:
    t = " ".join(text.split()).strip()
    if not t:
        return ""
    for _ in range(3):
        low = t.casefold()
        hit = False
        for p in _STAY_GENERIC_OPENERS:
            if low.startswith(p):
                t = t[len(p) :].lstrip(" ,.;—-").strip()
                hit = True
                break
        if not hit:
            break
    return t


def _stay_sentence_is_boilerplate(s: str) -> bool:
    low = s.casefold().strip()
    if len(low) < 18:
        return True
    if any(b in low for b in _STAY_BOILERPLATE_FRAGMENTS):
        return True
    if len(low) < 72 and low.startswith(("located ", "situated ", "set in the", "set in a")):
        return True
    return False


def _stay_pick_summary_sentence(sents: list[str]) -> str:
    #prefer a concrete line over thin location filler
    best = ""
    best_score = -1
    for s in sents:
        s = s.strip()
        if not s or _stay_sentence_is_boilerplate(s):
            continue
        low = s.casefold()
        score = sum(1 for w in _STAY_SUMMARY_SIGNAL if w in low)
        score += min(len(s) // 50, 2)
        if score > best_score or (score == best_score and len(s) > len(best)):
            best_score = score
            best = s
    if best:
        return best.rstrip()
    for s in sents:
        s = s.strip()
        if len(s) >= 18:
            return s.rstrip()
    return ""


def _clip_stay_words(text: str, max_chars: int) -> str:
    t = " ".join(text.split()).strip()
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def _first_stay_sentence(text: str) -> str:
    t = " ".join(text.split()).strip()
    if not t:
        return ""
    for sep in (". ", "? ", "! "):
        i = t.find(sep)
        if i != -1:
            return t[: i + len(sep)].strip()
    return t


def _normalize_stars_field_in_sentence(s: str) -> str:
    #strip junk like plural "s" after a digit (4s) so facts stay numeric for the card ui
    def repl(m: re.Match) -> str:
        prefix, chunk = m.group(1), m.group(2).strip()
        mm = re.search(r"\d+(?:[.,]\d+)?", chunk.replace(",", "."))
        if not mm:
            cleaned = re.sub(r"(?<=\d)s\b", "", chunk, flags=re.I).strip()
            return f"{prefix}{cleaned}"
        v = float(mm.group(0).replace(",", "."))
        v = min(5.0, max(0.0, v))
        if abs(v - round(v)) < 1e-6:
            num = str(int(round(v)))
        else:
            num = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{prefix}{num}"

    return re.sub(r"(?i)(Stars:\s*)([^·]+?)(?=\s*·|\Z)", repl, s)


def polish_stay_description_for_display(text: str) -> str:
    #legacy stay_dataset osm blurbs: drop coords, fix label caps, separate facts for scanning
    s = " ".join(text.split()).strip()
    if not s:
        return ""
    s = re.sub(r"(?i)\s*coordinates\s+about\s+[\d.,]+\s*,\s*[\d.,]+\s*\.?", "", s)
    s = re.sub(r"\s*\.\s*\.", ".", s)
    s = re.sub(r"(?i)\bstars\s+tag\s*:", "Stars:", s)
    s = re.sub(r"(?i)\bbrand\s*:", "Brand:", s)
    s = re.sub(r"(?i)\boperator\s*:", "Operator:", s)
    s = re.sub(r"(?i)\baddress\s+hint\s*:", "Address:", s)
    for pat, rep in (
        (r"^hotel\b", "Hotel"),
        (r"^hostel\b", "Hostel"),
        (r"^motel\b", "Motel"),
        (r"^guest house\b", "Guest House"),
        (r"^guest_house\b", "Guest House"),
        (r"^apartment\b", "Apartment"),
        (r"^chalet\b", "Chalet"),
    ):
        s = re.sub(pat, rep, s, count=1, flags=re.I)
    needle = "(openstreetmap community map)"
    idx = s.casefold().find(needle.casefold())
    if idx != -1:
        close = s.find(")", idx)
        if close != -1:
            head_end = close + 1
            while head_end < len(s) and s[head_end] in " \t":
                head_end += 1
            if head_end < len(s) and s[head_end] == ".":
                head_end += 1
            while head_end < len(s) and s[head_end] == " ":
                head_end += 1
            head, tail = s[:head_end].strip(), s[head_end:].strip()
            if tail:
                tail = re.sub(r"\s*\.\s+", " · ", tail)
                tail = re.sub(r"\s*·\s*·\s*", " · ", tail)
                s = f"{head} {tail}".strip()
    s = _normalize_stars_field_in_sentence(s)
    return re.sub(r"\s{2,}", " ", s).strip()


def _hotel_display_summaries(raw_description: str) -> tuple[str, str]:
    #tight scan line plus a trimmed full blurb; drops echo and thin openers where we can
    raw = _clean_scalar(raw_description)
    if not raw:
        return "", ""
    polished = polish_stay_description_for_display(raw)
    base = _strip_meta_from_description(polished)
    deduped = _dedupe_stay_sentences(base)
    full_description = clean_description_for_display(deduped, soft_target=220, hard_max=340).strip()
    lean = _strip_stay_generic_openers(deduped)
    sents = _split_stay_sentences(lean) or _split_stay_sentences(deduped)
    primary = _stay_pick_summary_sentence(sents)
    if not primary:
        primary = _first_stay_sentence(deduped)
    short_summary = primary.strip()
    if short_summary and short_summary[-1] not in ".!?":
        short_summary += "."
    #at most ~two short lines in the ui
    max_short = 175
    if len(short_summary) < 100:
        for s in sents:
            sc = (s or "").strip()
            if not sc:
                continue
            if sc.casefold().rstrip(".!?") == short_summary.casefold().rstrip(".!?"):
                continue
            if _stay_sentence_is_boilerplate(sc):
                continue
            merged = f"{short_summary.rstrip('.!?')}. {sc}".strip()
            if len(merged) <= max_short + 15:
                short_summary = merged if merged[-1] in ".!?" else merged + "."
                break
    short_summary = _clip_stay_words(short_summary, max_short)
    if not short_summary and full_description:
        short_summary = _clip_stay_words(_first_stay_sentence(full_description), max_short)
    return short_summary.strip(), full_description


def _build_stays(
    sleep_ranked: pd.DataFrame,
    display_dest: str,
    budget_key: str,
    vibe: str,
    interests: str,
    limit: int = 6,
) -> tuple[list[dict[str, str]], str | None]:
    notice: str | None = None
    if sleep_ranked.empty:
        return [], None
    bk = _normalized_budget_key(budget_key)
    mask_lodge = sleep_ranked.apply(_row_sounds_like_lodging, axis=1)
    mask_tier = sleep_ranked.apply(lambda r: _stay_passes_tier_gate(r, bk), axis=1)
    pick = sleep_ranked.loc[mask_lodge & mask_tier].reset_index(drop=True)
    if pick.empty:
        if bk == "splurge":
            notice = (
                f"No listings for {display_dest} clearly read as premium or high-end lodging "
                "for a splurge trip under our filters. Try a dedicated hotel search."
            )
        elif bk == "budget":
            notice = (
                f"No listings here read confidently as budget or hostel-style for {display_dest} "
                "with the current filters. A hostel-focused site may be safer."
            )
        else:
            notice = (
                f"No listings for {display_dest} matched both the lodging-shape and budget filters "
                "we apply before showing picks."
            )
        return [], notice

    rows_out: list[dict[str, str]] = []
    for _, row in pick.iterrows():
        title = _row_text(row, "title")
        raw_desc = _row_text(row, "description")
        short_summary, full_description = _hotel_display_summaries(raw_desc)
        if not title and not short_summary and not full_description:
            continue
        if not title:
            title = _display_title(row, display_dest)
        band = _clean_scalar(row.get("estimated_cost_band", "")) if "estimated_cost_band" in row.index else ""
        if not band:
            band = "unknown"
        src_label = _stay_display_source(row)
        rows_out.append(
            {
                "title": title,
                "short_summary": short_summary,
                "full_description": full_description,
                "short_description": short_summary,
                "description": full_description,
                "source": src_label,
                "estimated_cost_band": band,
                "match_reason": _stay_match_reason(row, bk, vibe, interests),
            }
        )
        if len(rows_out) >= limit:
            break
    if not rows_out:
        return [], (
            f"Stay rows for {display_dest} did not yield readable blurbs after filtering, "
            "so we are not padding the list."
        )
    return rows_out, notice


def _nature_heavy(blob: str) -> bool:
    #trip reads mostly outdoors; skip default city-transit nag
    return any(
        w in blob
        for w in (
            "hike",
            "trail",
            "camping",
            "safari",
            "national park",
            "trek",
            "wildlife",
            "summit",
        )
    )


def _cityish(blob: str) -> bool:
    if any(w in blob for w in ("city", "urban", "metro", "museum", "neighborhood", "food tour", "walkable")):
        return True
    if _nature_heavy(blob) and "city" not in blob:
        return False
    return True


def _tropicalish(destination: str, blob: str) -> bool:
    dest_cf = destination.casefold()
    markers = (
        "bangkok",
        "phuket",
        "bali",
        "singapore",
        "manila",
        "honolulu",
        "miami",
        "cartagena",
        "tulum",
        "phnom penh",
        "ho chi minh",
        "hanoi",
        "kuala lumpur",
        "jakarta",
        "denpasar",
        "cebu",
        "davao",
    )
    if any(m.strip() in dest_cf for m in markers if m.strip()):
        return True
    return any(w in blob for w in ("tropical", "humid", "monsoon", "rainy season", "heat", "beach"))


def build_checklist(destination: str, days: int, vibe: str, budget: str) -> list[str]:
    #small rule engine so the sidebar checklist feels tied to this exact trip
    d = (destination or "").strip() or "your destination"
    n = max(1, int(days))
    v = (vibe or "").strip().lower()
    b = (budget or "not sure").strip().lower()
    blob = f"{v} {b} {d}".casefold()

    items: list[str] = []

    items.append(f"double-check passport/visa rules for {d}")
    items.append(f"peek at weather for {d} the week before and tweak layers")

    if n >= 5:
        items.append("pack enough socks/underlayers for the middle days, or plan one sink-wash evening")
    if n >= 7:
        items.append("for a week-ish run: laundry access, extra tops, or a light detergent sheet beats overpacking")
    if n >= 12:
        items.append("longer trip: schedule a mid-trip reset (laundry, shoe swap, or one chill day)")

    if _cityish(blob):
        items.append("download the local transit app and save offline maps for the neighborhoods you will actually walk")
        items.append("comfortable broken-in walking shoes beat cute new pairs on day three")
    else:
        items.append("save offline maps for trailheads or rural legs where signal drops")

    if _tropicalish(d, blob):
        items.append("heat + sudden rain: breathable clothes, refillable water, tiny umbrella or packable shell")

    if b == "splurge" or any(
        w in blob for w in ("luxury", "fancy", "michelin", "fine dining", "splurge", "high end", "high-end")
    ):
        items.append("splurge-y nights: book a couple dinner slots early and skim dress codes")

    if b == "budget":
        items.append("tight budget days: set a loose daily spend cap and watch foreign atm / card fees")

    if b == "mid":
        items.append("mid budget: mix one splurge meal with casual lunches so the trip still feels balanced")

    items.append("copy hotel address + emergency numbers into your phone (photos of bookings are fine)")

    seen: set[str] = set()
    ordered: list[str] = []
    for line in items:
        if line not in seen:
            seen.add(line)
            ordered.append(line)

    def _cap_first(s: str) -> str:
        t = s.strip()
        if not t:
            return t
        return t[0].upper() + t[1:]

    return [_cap_first(x) for x in ordered]


def packing_list(vibe: str, days: int, destination: str) -> dict[str, list[str]]:
    #rule-based bag split so the ui can show essentials vs trip-specific stacks
    d = (destination or "").strip() or "your destination"
    n = max(1, int(days))
    v = (vibe or "").strip().lower()
    blob = f"{v} {d}".casefold()

    essentials: list[str] = [
        "comfortable walking shoes or sneakers you can actually log miles in",
        "reusable water bottle",
        "small daypack or tote that folds flat in your luggage",
        "copies of bookings and ids (photos on your phone are fine)",
    ]
    trip_specific: list[str] = []

    if n >= 4:
        essentials.append(
            "extra socks + one spare tee so a sweaty day does not wreck the next"
        )
    if n >= 7:
        essentials.append("mid-trip laundry plan: sink detergent sheet or hotel laundry budget")
    if n >= 11:
        essentials.append(
            "mesh laundry bag + one more outfit rotation so long trips stay civil"
        )

    if _tropicalish(d, blob):
        trip_specific += [
            "breathable linen or tech-fabric layers",
            "sunscreen + lip balm with spf",
            "hat or cap for harsh midday sun",
        ]

    if any(
        x in blob
        for x in (
            "fancy",
            "luxury",
            "upscale",
            "splurge",
            "michelin",
            "fine dining",
            "dress code",
            "gala",
            "romantic dinner",
        )
    ):
        trip_specific += [
            "one reservation-ready outfit that fits the nicest place on your list",
            "dress shoes or polished flats you can still walk a few blocks in",
            "compact steamer or hang-in-shower wrinkle reset trick",
        ]

    if any(x in blob for x in ("calm", "slow", "relax", "spa", "quiet", "lazy", "low-key", "gentle", "chill")):
        trip_specific += [
            "book or e-reader for unscheduled hours",
            "eye mask + earplugs if you are protective about sleep",
        ]

    if any(
        x in blob
        for x in (
            "energetic",
            "energy",
            "active",
            "busy days",
            "packed",
            "theme park",
            "nightlife",
            "clubbing",
            "festival",
            "hustle",
        )
    ):
        trip_specific += [
            "second pair of broken-in sneakers or gel insoles",
            "compact crossbody or belt bag so your hands stay free all day",
            "larger power bank + short cable you will actually carry",
        ]

    if any(w in blob for w in ("beach", "island", "swim", "snorkel")):
        trip_specific += ["swimsuit", "quick-dry towel", "dry bag or zip pouch for wet stuff"]
    if any(w in blob for w in ("night", "club", "bar", "rooftop", "cocktail")) and not any(
        x in blob for x in ("fancy", "luxury", "michelin", "fine dining")
    ):
        trip_specific += ["one going-out top or jacket", "light layer for freezing ac vs warm streets"]
    if any(w in blob for w in ("temple", "shrine", "mosque", "church")):
        trip_specific += ["modest layers or scarf for covered sites"]
    if any(w in blob for w in ("hike", "trail", "mountain", "trek")):
        trip_specific += ["trail snacks", "hat with a brim", "mini first aid + blister patches"]

    def _dedupe(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for line in seq:
            if line not in seen:
                seen.add(line)
                out.append(line)
        return out

    def _cap_first_word(s: str) -> str:
        t = s.strip()
        if not t:
            return t
        return t[0].upper() + t[1:]

    return {
        "essentials": [_cap_first_word(x) for x in _dedupe(essentials)],
        "for_this_trip": [_cap_first_word(x) for x in _dedupe(trip_specific)],
    }


def _city_cost_multiplier(destination: str) -> float:
    #exact normalized city name only; anything else uses the neutral baseline
    d = (destination or "").strip().casefold()
    return CITY_COST_MULTIPLIERS.get(d, 1.0)


def _vibe_category_multipliers(vibe: str, interests: str) -> dict[str, float]:
    #small nudges so food-heavy or museum-heavy trips shift the split without apis
    blob = f"{vibe} {interests}".casefold()
    m = {"lodging": 1.0, "food": 1.0, "transit": 1.0, "activities": 1.0}
    if any(w in blob for w in ("michelin", "foodie", "fine dining", "omakase", "wine", "tasting", "brunch")):
        m["food"] *= 1.14
    if any(w in blob for w in ("museum", "galleries", "tours", "tickets", "attractions", "theme park", "shows")):
        m["activities"] *= 1.18
    if any(w in blob for w in ("luxury", "five star", "5 star", "boutique hotel", "spa resort")):
        m["lodging"] *= 1.12
    if any(w in blob for w in ("metro", "subway", "transit", "train hop", "jr pass", "oyster")):
        m["transit"] *= 1.08
    if any(w in blob for w in ("road trip", "taxi", "uber", "drive")):
        m["transit"] *= 1.12
    return m


def _round_money_usd(n: float) -> int:
    return max(0, int(round(n / 10.0) * 10))


def format_usd_range(lo: int, hi: int) -> str:
    #single string shape for ui rows so streamlit always sees consistent money text
    return f"${lo:,}–${hi:,}"


_BUDGET_LABEL_PRETTY = {
    "budget": "Budget trip",
    "mid": "Mid-range trip",
    "splurge": "Splurge trip",
    "not sure": "Flexible budget",
}


def build_budget_breakdown(
    destination: str,
    num_days: int,
    budget_key: str,
    vibe: str,
    interests: str = "",
) -> dict[str, object]:
    #rule-of-thumb category totals in usd for the whole trip; excludes flights
    days = max(1, int(num_days))
    key = (budget_key or "not sure").strip().lower()
    daily = _BUDGET_CATEGORY_DAILY_USD.get(key, _BUDGET_CATEGORY_DAILY_USD["not sure"])
    city_m = _city_cost_multiplier(destination)
    vibe_m = _vibe_category_multipliers(vibe, interests)

    out: dict[str, object] = {}
    sum_lo = 0
    sum_hi = 0
    for cat in ("lodging", "food", "transit", "activities"):
        lo_d, hi_d = daily[cat]
        vm = vibe_m[cat]
        lo_t = lo_d * days * city_m * vm
        hi_t = hi_d * days * city_m * vm
        lo_i, hi_i = _round_money_usd(lo_t), _round_money_usd(hi_t)
        if lo_i > hi_i:
            lo_i, hi_i = hi_i, lo_i
        out[f"{cat}_estimate"] = (lo_i, hi_i)
        sum_lo += lo_i
        sum_hi += hi_i

    out["total_estimate"] = (sum_lo, sum_hi)
    tier = (budget_key or "not sure").strip().lower()
    out["budget_label"] = _BUDGET_LABEL_PRETTY.get(tier, _BUDGET_LABEL_PRETTY["not sure"])
    out["display"] = {
        "lodging": format_usd_range(*(out["lodging_estimate"])),
        "food": format_usd_range(*(out["food_estimate"])),
        "transit": format_usd_range(*(out["transit_estimate"])),
        "activities": format_usd_range(*(out["activities_estimate"])),
        "total": format_usd_range(*(out["total_estimate"])),
    }
    out["summary_sentence"] = _budget_summary_sentence(destination, days, out)
    return out


def _budget_summary_sentence(
    destination: str,
    days: int,
    breakdown: dict[str, object],
) -> str:
    tlo, thi = breakdown["total_estimate"]  # type: ignore[misc]
    d = (destination or "").strip() or "your trip"
    return (
        f"Rough rule-based window for {d} ({days} days): about {format_usd_range(tlo, thi)} USD total "
        f"(lodging, food, local transit, light activities). Flights and big tours sit outside this band."
    )


def _budget_detail_lines(breakdown: dict[str, object]) -> list[str]:
    labels = (
        ("lodging_estimate", "lodging", "lodging"),
        ("food_estimate", "food", "food"),
        ("transit_estimate", "local transit", "transit"),
        ("activities_estimate", "activities & tickets", "activities"),
    )
    lines: list[str] = []
    disp_raw = breakdown.get("display")
    disp = disp_raw if isinstance(disp_raw, dict) else {}
    for k, label, dkey in labels:
        amt = disp.get(dkey)
        if isinstance(amt, str):
            lines.append(f"{label}: {amt}")
            continue
        lo, hi = breakdown[k]  # type: ignore[misc]
        lines.append(f"{label}: {format_usd_range(lo, hi)}")
    return lines


def get_recommendations(
    destination: str,
    num_days: int,
    trip_vibe: str,
    budget: str,
    must_see_interests: str,
    *,
    debug: bool = False,
) -> dict:
    #ranking always happens inside strict_rows_for_destination output, never the whole csv
    #debug=True adds a compact "debug" dict (row previews + embed queries) for streamlit inspection
    raw_dest = (destination or "").strip()
    days = max(1, int(num_days))
    vibe = (trip_vibe or "").strip()
    budget_key = (budget or "not sure").strip()
    interests = (must_see_interests or "").strip()

    df = _load_dataset()
    stay_df = _load_stay_dataset()
    cities = supported_destinations(df)
    scoped = strict_rows_for_destination(df, raw_dest)
    stay_scoped = strict_rows_for_destination(stay_df, raw_dest) if not stay_df.empty else pd.DataFrame()

    if scoped.empty:
        bd = build_budget_breakdown(raw_dest or "your trip", days, budget_key, vibe, interests)
        out = {
            "ok": False,
            "notice": NO_CITY_MSG.format(dest=raw_dest or "that city"),
            "supported_destinations": cities,
            "destination": raw_dest or "unknown",
            "num_days": days,
            "trip_vibe": vibe,
            "budget": budget_key,
            "checklist": build_checklist(raw_dest or "your trip", days, vibe, budget_key),
            "itinerary": [],
            "stays": [],
            "stay_suggestions_notice": None,
            "packing": packing_list(f"{vibe} {interests}".strip(), days, raw_dest),
            "budget_breakdown": bd,
            "budget_summary": bd["summary_sentence"],
            "budget_lines": _budget_detail_lines(bd),
        }
        if debug:
            dq = (raw_dest or "your trip").strip() or "your trip"
            n_stay_city = int(len(stay_scoped)) if not stay_scoped.empty else 0
            n_stay_sleep = int(len(_sleep_section_only(stay_scoped))) if not stay_scoped.empty else 0
            out["debug"] = {
                "scoped_row_count": 0,
                "ranking_queries": _ranking_queries(dq, vibe, budget_key, interests),
                "top_see_do": [],
                "top_eat": [],
                "top_drink": [],
                "top_hotel_rows": [],
                "hotel_debug": {
                    "stay_pipeline_meta": {},
                    "stay_rows_for_city_all_sections": n_stay_city,
                    "stay_sleep_section_rows_raw": n_stay_sleep,
                    "stay_csv_merged_pool_rows": 0,
                    "used_live_openstreetmap_fetch": False,
                    "used_travel_guide_sleep_fallback": False,
                    "lodging_pool_rows_pre_rank": 0,
                    "in_pool_wikivoyage": 0,
                    "in_pool_openstreetmap": 0,
                    "in_pool_travel_guide_sleep": 0,
                    "hotel_debug_hints": [
                        "travel_dataset has no rows for this city — hotel pipeline did not run (fix city name or scrape)."
                    ],
                    "filter_stages": _hotel_filter_stage_counts(pd.DataFrame(), budget_key),
                    "stays_cards_returned": 0,
                    "hotel_candidates_pre_rank": [],
                    "hotel_top_after_ranking": [],
                },
            }
        return out

    display_dest = _canonical_destination_name(scoped)
    stay_scoped_f = _enforce_stay_destination(stay_scoped, display_dest)
    scoped_f = _enforce_stay_destination(scoped, display_dest)

    see_do = _itinerary_pool(
        scoped_f, ("See", "Do"), display_dest, vibe, budget_key, interests, "see_do"
    )
    eat = _itinerary_pool(scoped_f, ("Eat",), display_dest, vibe, budget_key, interests, "eat")
    drink = _itinerary_pool(scoped_f, ("Drink",), display_dest, vibe, budget_key, interests, "drink")

    pool_df, pool_notice, pool_meta = _stay_lodging_pool(stay_scoped_f, scoped_f, display_dest)
    sleep_ranked = (
        _sleep_pool(scoped_f, display_dest, vibe, budget_key, interests, pool=pool_df)
        if not pool_df.empty
        else pd.DataFrame()
    )

    checklist = build_checklist(display_dest, days, vibe, budget_key)

    itinerary = _build_itinerary_days(
        days, see_do, eat, drink, display_dest, vibe, budget_key, interests
    )
    stays, stay_notice = _build_stays(sleep_ranked, display_dest, budget_key, vibe, interests)
    if not stays and pool_notice and stay_notice is None:
        stay_notice = pool_notice

    packing = packing_list(f"{vibe} {interests}".strip(), days, display_dest)
    bd = build_budget_breakdown(display_dest, days, budget_key, vibe, interests)

    out = {
        "ok": True,
        "notice": None,
        "supported_destinations": cities,
        "destination": display_dest,
        "num_days": days,
        "trip_vibe": vibe,
        "budget": budget_key,
        "checklist": checklist,
        "itinerary": itinerary,
        "stays": stays,
        "stay_suggestions_notice": stay_notice,
        "packing": packing,
        "budget_breakdown": bd,
        "budget_summary": bd["summary_sentence"],
        "budget_lines": _budget_detail_lines(bd),
    }
    if debug:
        src_counts = _count_stay_pool_sources(pool_df)
        filter_counts = _hotel_filter_stage_counts(sleep_ranked, budget_key)
        hotel_debug = {
            "stay_pipeline_meta": pool_meta,
            "stay_rows_for_city_all_sections": int(pool_meta.get("stay_rows_for_city_all_sections", 0) or 0),
            "stay_sleep_section_rows_raw": int(pool_meta.get("stay_sleep_section_rows_raw", 0) or 0),
            "stay_csv_merged_pool_rows": int(pool_meta.get("stay_csv_merged_pool_rows", 0) or 0),
            "used_live_openstreetmap_fetch": bool(pool_meta.get("used_live_openstreetmap_fetch")),
            "used_travel_guide_sleep_fallback": bool(pool_meta.get("used_travel_guide_sleep_fallback")),
            "lodging_pool_rows_pre_rank": int(len(pool_df)),
            "in_pool_wikivoyage": int(src_counts.get("wikivoyage", 0)),
            "in_pool_openstreetmap": int(src_counts.get("openstreetmap", 0)),
            "in_pool_travel_guide_sleep": int(src_counts.get("travel_guide", 0)),
            "hotel_debug_hints": _hotel_debug_hint_lines(
                pool_meta, pool_df, sleep_ranked, stays, src_counts, filter_counts
            ),
            "filter_stages": filter_counts,
            "stays_cards_returned": int(len(stays)),
            "hotel_candidates_pre_rank": _debug_hotel_candidates_pre_rank(pool_df),
            "hotel_top_after_ranking": _debug_hotel_rows_after_ranking(sleep_ranked),
        }
        out["debug"] = {
            "scoped_row_count": int(len(scoped_f)),
            "ranking_queries": _ranking_queries(display_dest, vibe, budget_key, interests),
            "top_see_do": _debug_top_rows(see_do),
            "top_eat": _debug_top_rows(eat),
            "top_drink": _debug_top_rows(drink),
            "top_hotel_rows": _debug_top_rows(sleep_ranked),
            "hotel_debug": hotel_debug,
        }
    return out
