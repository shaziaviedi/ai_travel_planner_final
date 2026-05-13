"""
load raw wikivoyage rows, drop junk, tag vibes and what each row is good for, write processed csv.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_CSV = ROOT / "data" / "raw" / "wikivoyage_raw.csv"
OUT_CSV = ROOT / "data" / "processed" / "travel_dataset.csv"

#splurge-ish words win first so a row is not called "budget" just because it says "not expensive"
SPLURGE_HINTS = (
    "splurge",
    "luxury",
    "luxurious",
    "fancy",
    "upscale",
    "premium",
    "expensive",
    "high-end",
    "high end",
    "fine dining",
    "michelin",
    "starred",
    "award-winning",
    "tasting menu",
    "degustation",
    "sommelier",
    "wine pairing",
    "exclusive",
    "elegant",
    "designer",
    "rooftop",
    "penthouse",
    "concierge",
    "champagne",
    "caviar",
    "private dining",
    "vip",
    "world-class",
    "five-star",
    "five star",
    "5-star",
    "5 star",
    "¥¥¥¥",
    "$$$$",
    "omakase",
    "chef's table",
    "dress code",
    "members only",
)
MID_HINTS = (
    "mid-range",
    "mid range",
    "moderate",
    "reasonable",
    "mid-priced",
    "mid priced",
    "average price",
    "standard room",
    "comfortable",
    "typical",
    "¥¥¥",
    "$$$",
)
BUDGET_HINTS = (
    "budget",
    "cheap",
    "inexpensive",
    "affordable",
    "low price",
    "economy",
    "hostel",
    "dorm",
    "capsule hotel",
    "street food",
    "conveyor belt sushi",
    "standing-only",
    "¥500",
    "¥¥",
    "free admission",
    "no cover",
    "100-yen",
)

#first match wins; put narrower vibes before broad ones like food or stay
VIBE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "luxury",
        (
            "luxury",
            "luxurious",
            "fancy",
            "upscale",
            "premium",
            "expensive",
            "fine dining",
            "michelin",
            "tasting menu",
            "sommelier",
            "wine pairing",
            "degustation",
            "exclusive",
            "elegant",
            "designer",
            "rooftop",
            "penthouse",
            "concierge",
            "champagne",
            "caviar",
            "private dining",
            "omakase",
            "award-winning",
            "five-star",
            "five star",
            "5-star",
            "vip",
            "dress code",
            "chef's table",
        ),
    ),
    (
        "culture",
        (
            "temple",
            "shrine",
            "mosque",
            "cathedral",
            "church",
            "museum",
            "gallery",
            "opera",
            "ballet",
            "symphony",
            "orchestra",
            "heritage",
            "historic",
            "history",
            "unesco",
            "exhibit",
            "castle",
            "palace",
            "traditional",
            "ceremony",
            "folk",
            "craft",
            "workshop",
            "architecture tour",
            "walking tour",
            "cultural",
        ),
    ),
    (
        "energetic",
        (
            "festival",
            "carnival",
            "parade",
            "fireworks",
            "marathon",
            "stadium",
            "concert",
            "live show",
            "crowded",
            "packed",
            "high energy",
            "all-night",
            "all night",
            "neon",
            "dance floor",
            "rave",
            "block party",
            "street party",
        ),
    ),
    (
        "nightlife",
        (
            "nightclub",
            "night club",
            "nightlife",
            "clubbing",
            "after hours",
            "late-night",
            "late night",
            "izakaya",
            "karaoke",
            "live music",
            "dj ",
            "bar crawl",
            "pub crawl",
        ),
    ),
    (
        "calm",
        (
            "quiet",
            "tranquil",
            "peaceful",
            "serene",
            "zen",
            "meditation",
            "slow stroll",
            "gentle walk",
            "tea house",
            "tea room",
            "onsen",
            "spa",
            "garden stroll",
            "riverside",
            "hideaway",
            "secluded",
            "low-key",
            "low key",
            "intimate setting",
            "mindfulness",
            "reading room",
        ),
    ),
    (
        "food",
        (
            "restaurant",
            "sushi",
            "ramen",
            "street food",
            "food hall",
            "yakitori",
            "bbq",
            "bakery",
            "cafe",
            "café",
            "bistro",
            "brunch",
            "dim sum",
            "hawker",
        ),
    ),
    (
        "nature",
        (
            "park",
            "garden",
            "hike",
            "trail",
            "beach",
            "waterfront",
            "scenic",
            "viewpoint",
            "forest",
            "lake",
            "island hop",
            "wildlife",
            "botanical",
        ),
    ),
    (
        "shopping",
        (
            "shopping",
            "mall",
            "market",
            "boutique",
            "department store",
            "souvenir",
            "arcade",
            "duty-free",
        ),
    ),
    (
        "stay",
        (
            "hotel",
            "hostel",
            "ryokan",
            "guesthouse",
            "capsule",
            "lodging",
            "accommodation",
            "resort",
            "inn",
        ),
    ),
)

BAD_SUBSTRINGS = (
    "please add",
    "individual listings can be found",
    "individual listings",
    "listing can be found",
    "listings are in",
    "see the district",
    "see the city",
    "for up-to-date listings",
    "this article is",
    "help wikivoyage",
    "wikivoyage is not",
    "template:",
    "may be found in",
    "more information on",
    "redirected from",
    "we should",
    "stub",
)

GENERIC_TITLES = frozenset(
    {
        "budget",
        "mid-range",
        "mid range",
        "splurge",
        "see",
        "do",
        "eat",
        "drink",
        "sleep",
        "get in",
        "get around",
        "understand",
        "stay safe",
        "connect",
        "cope",
        "go next",
        "other districts",
        "learn",
        "work",
        "buy",
        "districts",
    }
)

#sleep row needs some lodging signal to count as a real place to stay
STAY_SIGNALS = (
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

GUIDE_OPENERS = re.compile(
    r"^(visitors\s+|the\s+city\s+|one\s+of\s+|there\s+are\s+|you\s+can\s+|if\s+you\s+)",
    re.I,
)


def clean_ws(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def blob(row: pd.Series) -> str:
    t = "" if pd.isna(row.get("title")) else str(row["title"])
    d = "" if pd.isna(row.get("description")) else str(row["description"])
    return f"{t} {d}".lower()


def infer_cost_band(row: pd.Series) -> str:
    #cheap substring scan; order is splurge then budget then mid
    text = blob(row)
    if any(h in text for h in SPLURGE_HINTS):
        return "splurge"
    if any(h in text for h in BUDGET_HINTS):
        return "budget"
    if any(h in text for h in MID_HINTS):
        return "mid"
    return "unknown"


def infer_vibe_tag(row: pd.Series) -> str:
    #first keyword hit wins; reorder VIBE_RULES if two labels fight too often
    text = blob(row)
    for tag, words in VIBE_RULES:
        if any(w in text for w in words):
            return tag
    return "general"


def _is_generic_title(title: str) -> bool:
    t = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    return t in GENERIC_TITLES or len(t) <= 1


def _has_bad_substring(text: str) -> bool:
    t = text.lower()
    return any(b in t for b in BAD_SUBSTRINGS)


def _looks_like_guide_rail(title: str, desc: str) -> bool:
    #long meandering intro with a vague title is almost never a single bookable thing
    if len(desc) > 950 and len(title) < 25:
        return True
    if len(desc) > 700 and GUIDE_OPENERS.match(desc.strip()):
        return True
    if len(desc) > 1100:
        return True
    return False


def _useless_title(title: str) -> bool:
    if not title or len(title.strip()) < 2:
        return True
    if len(title) > 140:
        return True
    if _is_generic_title(title):
        return True
    #sentence-like titles are usually prose, not a venue name
    if title.count(".") >= 2 or (title.count(",") >= 3 and len(title) > 90):
        return True
    return False


def content_score(row: pd.Series) -> int:
    t = str(row.get("title", "") or "")
    d = str(row.get("description", "") or "")
    sec = str(row.get("section", "") or "")
    lt, ld = len(t), len(d)
    score = 42
    if lt < 3:
        return 0
    if 4 <= lt <= 72:
        score += 14
    if 25 <= ld <= 520:
        score += 18
    if ld < 18:
        score -= 28
    if ld > 1300:
        score -= 22
    if 130 <= ld <= 900:
        score += 6
    blob = f"{t} {d}".lower()
    if any(x in blob for x in ("¥", " usd", "$", "tel", "phone", "+81", "+65", "www.", ".com", " station", " min ", " walk")):
        score += 12
    if sec in ("Eat", "Drink") and any(x in blob for x in ("open", "closed", "daily", ":00", " am", " pm")):
        score += 5
    if _is_generic_title(t):
        score -= 25
    if GUIDE_OPENERS.match(d.strip()) and ld > 260:
        score -= 18
    if lt > 95:
        score -= 10
    return int(max(0, min(100, score)))


def _stay_sounds_specific(title: str, desc: str, score: int) -> bool:
    if score < 46:
        return False
    blob = f"{title} {desc}".lower()
    if not any(s in blob for s in STAY_SIGNALS):
        return False
    if _is_generic_title(title) and len(desc) < 100:
        return False
    if len(title) > 88:
        return False
    return True


def _usable_for_itinerary(row: pd.Series) -> bool:
    sec = str(row.get("section", "") or "")
    if sec not in ("See", "Do", "Eat", "Drink"):
        return False
    if not bool(row.get("content_score", 0) >= 52):
        return False
    t = str(row.get("title", "") or "")
    d = str(row.get("description", "") or "")
    if len(d) < 22:
        return False
    if _looks_like_guide_rail(t, d):
        return False
    return True


def _usable_for_stay(row: pd.Series) -> bool:
    if str(row.get("section", "") or "") != "Sleep":
        return False
    t = str(row.get("title", "") or "")
    d = str(row.get("description", "") or "")
    sc = int(row.get("content_score", 0) or 0)
    return bool(_stay_sounds_specific(t, d, sc))


def _drop_bad_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    t = df["title"].astype(str).str.strip()
    d = df["description"].astype(str).str.strip()
    mask = (
        t.map(lambda x: not _useless_title(x))
        & ~t.str.lower().map(_has_bad_substring)
        & ~d.str.lower().map(_has_bad_substring)
        & ~pd.Series([_looks_like_guide_rail(a, b) for a, b in zip(t, d)], index=df.index)
    )
    return df.loc[mask].reset_index(drop=True)


def build_dataset() -> tuple[Path, pd.DataFrame]:
    if not RAW_CSV.is_file():
        raise FileNotFoundError(f"missing raw file: {RAW_CSV} (run scraper.py first)")

    df = pd.read_csv(RAW_CSV)
    for col in ("title", "description", "destination", "section"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).map(clean_ws)

    df = _drop_bad_rows(df)

    df["estimated_cost_band"] = df.apply(infer_cost_band, axis=1)
    df["vibe_tag"] = df.apply(infer_vibe_tag, axis=1)
    df["content_score"] = df.apply(content_score, axis=1)
    df["usable_for_itinerary"] = df.apply(_usable_for_itinerary, axis=1).astype(int)
    df["usable_for_stay"] = df.apply(_usable_for_stay, axis=1).astype(int)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    return OUT_CSV, df


def _print_summary(df: pd.DataFrame) -> None:
    n = len(df)
    print(f"rows kept: {n}")
    if n == 0:
        print("(nothing left after filters; loosen rules or rescrape)")
        return
    print("by destination:")
    for dest, c in df["destination"].value_counts().sort_index().items():
        print(f"  {dest}: {c}")
    print("by section:")
    for sec, c in df["section"].value_counts().sort_index().items():
        print(f"  {sec}: {c}")
    hi = int(df["usable_for_itinerary"].sum()) if "usable_for_itinerary" in df.columns else 0
    st = int(df["usable_for_stay"].sum()) if "usable_for_stay" in df.columns else 0
    print(f"usable_for_itinerary=1: {hi}  usable_for_stay=1: {st}")


if __name__ == "__main__":
    path, out_df = build_dataset()
    print(f"wrote {path}")
    _print_summary(out_df)
