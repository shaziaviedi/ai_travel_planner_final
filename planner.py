"""
turn form inputs + scraped rows into a lightweight trip bundle for the ui.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from model_utils import embed_texts

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "data" / "processed" / "travel_dataset.csv"

#usd/day low/high per category at city multiplier 1.0 — sums land in sensible trip bands per tier
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

LUXURY_STAY = ("luxury", "suite", "boutique", "five star", "5 star", "concierge", "designer", "penthouse")


def _load_dataset() -> pd.DataFrame:
    if not DATASET.is_file():
        return pd.DataFrame()
    return pd.read_csv(DATASET)


def supported_destinations(df: pd.DataFrame | None = None) -> list[str]:
    #single place to read which cities the csv actually contains
    if df is None:
        df = _load_dataset()
    if df.empty or "destination" not in df.columns:
        return []
    names = df["destination"].astype(str).str.strip()
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


def _canonical_destination_name(scoped: pd.DataFrame) -> str:
    return str(scoped["destination"].iloc[0]).strip()


def _clean_scalar(v: object) -> str:
    #csv quirks sometimes stringify missing cells as "nan"—never surface that in the ui
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
        or "high end" in b
        or "high-end" in b
        or "fine dining" in b
    )


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
    if section_role == "sleep" and (
        _wants_luxury(vibe, budget, interests) or _wants_stay_focus(vibe, interests)
    ):
        parts.append("luxury boutique five star premium suites romantic designer memorable stay")
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
        "section": _row_text(row, "section") or "—",
        "title": _row_text(row, "title") or "—",
        "description_snippet": desc or "—",
    }


def _debug_top_rows(pool: pd.DataFrame, k: int = _DEBUG_TOP_K) -> list[dict[str, str]]:
    if pool.empty:
        return []
    return [_debug_row_snap(row) for _, row in pool.head(k).iterrows()]


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


def _keyword_boost(
    row: pd.Series,
    section_role: str,
    vibe: str,
    budget: str,
    interests: str,
) -> float:
    #cheap nudge on top of cosine so price cues and luxury words actually move the list
    text = f"{_row_text(row, 'title')} {_row_text(row, 'description')}".lower()
    intent = _intent_blob(vibe, budget, interests)
    boost = 0.0

    if _wants_luxury(vibe, budget, interests):
        boost += 0.055 * min(4, sum(1 for w in LUXURY_ROW if w in text))
        if section_role == "eat":
            boost += 0.05 * min(3, sum(1 for w in ("omakase", "michelin", "sommelier", "tasting", "degustation") if w in text))

    if "estimated_cost_band" in row.index:
        band = str(row.get("estimated_cost_band", "") or "").lower()
        if "splurge" in intent and band == "splurge":
            boost += 0.14
        if "budget" in intent and band == "budget":
            boost += 0.06
        if _wants_luxury(vibe, budget, interests) and band == "splurge":
            boost += 0.1

    if section_role == "eat" and _wants_food_focus(vibe, interests):
        boost += 0.045 * min(
            4,
            sum(1 for w in ("michelin", "omakase", "sommelier", "tasting", "sushi", "chef", "wine pairing") if w in text),
        )

    if section_role == "sleep" and _wants_luxury(vibe, budget, interests):
        boost += 0.07 * min(3, sum(1 for w in LUXURY_STAY if w in text))

    if section_role == "drink" and any(w in intent for w in ("fancy", "luxury", "splurge", "cocktail", "wine", "rooftop")):
        boost += 0.04 * min(3, sum(1 for w in ("cocktail", "wine", "whisky", "rooftop", "lounge", "champagne") if w in text))

    return float(min(1.0, boost))


def _intent_rank(
    df: pd.DataFrame,
    display_dest: str,
    vibe: str,
    budget: str,
    interests: str,
    section_role: str,
) -> pd.DataFrame:
    #never call the embedder on an empty frame
    if df.empty:
        return df
    q_text = _build_embedding_query(display_dest, vibe, budget, interests, section_role)
    if not q_text:
        q_text = display_dest or "travel"

    texts: list[str] = []
    for _, row in df.iterrows():
        blob = f"{row.get('section', '')} {_row_text(row, 'title')} {_row_text(row, 'description')}"
        texts.append(str(blob)[:900])

    q = embed_texts([q_text])
    mat = embed_texts(texts)
    cos = (mat @ q.T).flatten().astype(np.float32)
    boosts = np.array(
        [_keyword_boost(row, section_role, vibe, budget, interests) for _, row in df.iterrows()],
        dtype=np.float32,
    )
    #blend keeps embeddings primary but lets splurge+luxury rows jump when the user asks for it
    combined = 0.68 * cos + 0.32 * boosts
    order = np.argsort(-combined)
    return df.iloc[order].reset_index(drop=True)


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
    return _intent_rank(pool, display_dest, trip_vibe, budget, must_see_interests, section_role)


def _sleep_pool(
    scoped: pd.DataFrame,
    display_dest: str,
    trip_vibe: str,
    budget: str,
    must_see_interests: str,
) -> pd.DataFrame:
    pool = scoped[scoped["section"] == "Sleep"].copy()
    if "usable_for_stay" in pool.columns:
        good = pool[pool["usable_for_stay"] == 1]
        if not good.empty:
            pool = good
    return _intent_rank(pool, display_dest, trip_vibe, budget, must_see_interests, "sleep")


def _pick_pair(
    pool: pd.DataFrame,
    day_index: int,
    stride: int,
    display_dest: str,
) -> tuple[str, str]:
    if pool.empty:
        return "", ""
    #stride spreads picks a bit across long weekends without feeling totally random
    n = len(pool)
    for step in range(n):
        j = (day_index * stride + step) % n
        row = pool.iloc[j]
        real_title = _row_text(row, "title")
        desc = clean_description_for_display(_row_text(row, "description"))
        if not real_title and not desc:
            continue
        title = real_title if real_title else _display_title(row, display_dest)
        return title, desc
    return "", ""


def _build_itinerary_days(
    days: int,
    see_do: pd.DataFrame,
    eat: pd.DataFrame,
    drink: pd.DataFrame,
    display_dest: str,
) -> list[dict[str, str]]:
    #different strides keep eat/drink from mirroring see/do every single day
    out: list[dict[str, str]] = []
    for i in range(days):
        mt, md = _pick_pair(see_do, i, 1, display_dest)
        ft, fd = _pick_pair(eat, i, 3, display_dest)
        dt, dd = _pick_pair(drink, i, 2, display_dest)
        if not mt and not ft:
            mt = f"explore {display_dest}"
            md = "no ranked see/do/eat rows left for this city in the dataset; widen the scrape or relax filters."
        if not ft:
            ft = "local meal"
            fd = "pick a busy lunch street or market near where you are staying."
        if not dt and not dd:
            dt = f"evening in {display_dest}"
            dd = "try a calmer bar strip or a hotel lounge when you want to unwind."
        out.append(
            {
                "day": i + 1,
                "main_activity_title": mt,
                "main_activity_description": md,
                "food_title": ft,
                "food_description": fd,
                "drink_title": dt,
                "drink_description": dd,
            }
        )
    return out


def _build_stays(sleep_ranked: pd.DataFrame, display_dest: str, limit: int = 6) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for _, row in sleep_ranked.head(limit * 2).iterrows():
        title = _row_text(row, "title")
        desc = clean_description_for_display(_row_text(row, "description"))
        if not title and not desc:
            continue
        if not title:
            title = _display_title(row, display_dest)
        band = _clean_scalar(row.get("estimated_cost_band", "")) if "estimated_cost_band" in row.index else ""
        if not band:
            band = "unknown"
        rows.append(
            {
                "title": title,
                "description": desc,
                "estimated_cost_band": band,
            }
        )
        if len(rows) >= limit:
            break
    return rows


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
        items.append("longer trip: schedule a mid-trip reset—laundry, shoe swap, or one chill day")

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
    return ordered


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

    return {
        "essentials": _dedupe(essentials),
        "for_this_trip": _dedupe(trip_specific),
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


def build_budget_breakdown(
    destination: str,
    num_days: int,
    budget_key: str,
    vibe: str,
    interests: str = "",
) -> dict[str, tuple[int, int]]:
    #rule-of-thumb category totals in usd for the whole trip; excludes flights
    days = max(1, int(num_days))
    key = (budget_key or "not sure").strip().lower()
    daily = _BUDGET_CATEGORY_DAILY_USD.get(key, _BUDGET_CATEGORY_DAILY_USD["not sure"])
    city_m = _city_cost_multiplier(destination)
    vibe_m = _vibe_category_multipliers(vibe, interests)

    out: dict[str, tuple[int, int]] = {}
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
    return out


def _budget_summary_sentence(
    destination: str,
    days: int,
    breakdown: dict[str, tuple[int, int]],
) -> str:
    tlo, thi = breakdown["total_estimate"]
    d = (destination or "").strip() or "your trip"
    return (
        f"rough rule-based window for {d} ({days} days): about ${tlo:,}–${thi:,} usd total "
        f"(lodging + food + local transit + light activities). excludes flights and big tours."
    )


def _budget_detail_lines(breakdown: dict[str, tuple[int, int]]) -> list[str]:
    labels = (
        ("lodging_estimate", "lodging"),
        ("food_estimate", "food"),
        ("transit_estimate", "local transit"),
        ("activities_estimate", "activities & tickets"),
    )
    lines = []
    for k, label in labels:
        lo, hi = breakdown[k]
        lines.append(f"{label}: about ${lo:,}–${hi:,}")
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
    cities = supported_destinations(df)
    scoped = strict_rows_for_destination(df, raw_dest)

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
            "packing": packing_list(f"{vibe} {interests}".strip(), days, raw_dest),
            "budget_breakdown": bd,
            "budget_summary": _budget_summary_sentence(raw_dest or "your trip", days, bd),
            "budget_lines": _budget_detail_lines(bd),
        }
        if debug:
            dq = (raw_dest or "your trip").strip() or "your trip"
            out["debug"] = {
                "scoped_row_count": 0,
                "ranking_queries": _ranking_queries(dq, vibe, budget_key, interests),
                "top_see_do": [],
                "top_eat": [],
                "top_drink": [],
                "top_hotel_rows": [],
            }
        return out

    display_dest = _canonical_destination_name(scoped)
    see_do = _itinerary_pool(
        scoped, ("See", "Do"), display_dest, vibe, budget_key, interests, "see_do"
    )
    eat = _itinerary_pool(scoped, ("Eat",), display_dest, vibe, budget_key, interests, "eat")
    drink = _itinerary_pool(scoped, ("Drink",), display_dest, vibe, budget_key, interests, "drink")
    sleep_ranked = _sleep_pool(scoped, display_dest, vibe, budget_key, interests)

    checklist = build_checklist(display_dest, days, vibe, budget_key)

    itinerary = _build_itinerary_days(days, see_do, eat, drink, display_dest)
    stays = _build_stays(sleep_ranked, display_dest)
    if not stays:
        stays = []

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
        "packing": packing,
        "budget_breakdown": bd,
        "budget_summary": _budget_summary_sentence(display_dest, days, bd),
        "budget_lines": _budget_detail_lines(bd),
    }
    if debug:
        out["debug"] = {
            "scoped_row_count": int(len(scoped)),
            "ranking_queries": _ranking_queries(display_dest, vibe, budget_key, interests),
            "top_see_do": _debug_top_rows(see_do),
            "top_eat": _debug_top_rows(eat),
            "top_drink": _debug_top_rows(drink),
            "top_hotel_rows": _debug_top_rows(sleep_ranked),
        }
    return out
