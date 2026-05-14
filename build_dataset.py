"""
load raw wikivoyage rows, drop junk, tag vibes and what each row is good for, write processed csv.
also merge wikivoyage sleep with openstreetmap lodging into stay_dataset.csv for the planner sleep pool.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd

import hotel_source

ROOT = Path(__file__).resolve().parent
RAW_CSV = ROOT / "data" / "raw" / "wikivoyage_raw.csv"
OUT_CSV = ROOT / "data" / "processed" / "travel_dataset.csv"
STAY_CSV = ROOT / "data" / "processed" / "stay_dataset.csv"
STAY_COVERAGE_CSV = ROOT / "data" / "processed" / "stay_destination_coverage.csv"

#stay export: human-facing columns first, then fields the planner still expects on sleep rows
STAY_WRITE_COLUMNS: tuple[str, ...] = (
    "destination",
    "title",
    "description",
    "estimated_cost_band",
    "vibe_tag",
    "source",
    "usable_for_stay",
    "section",
    "source_url",
    "content_score",
    "likely_place_listing",
    "usable_for_itinerary",
    "source_page_title",
    "page_type",
    "lat",
    "lon",
    "osm_tags",
    "data_source",
)

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


def _sleep_stays_quality_ok(row: pd.Series) -> bool:
    #embedding/score gate on top of scraper heuristics
    t = str(row.get("title", "") or "")
    d = str(row.get("description", "") or "")
    sc = int(row.get("content_score", 0) or 0)
    return bool(_stay_sounds_specific(t, d, sc))


def _usable_for_stay(row: pd.Series) -> bool:
    if str(row.get("section", "") or "") != "Sleep":
        return False
    if int(row.get("likely_place_listing", 0) or 0) != 1:
        return False
    return _sleep_stays_quality_ok(row)


def _osm_places_to_stay_rows(destination: str, places: list[dict]) -> pd.DataFrame:
    #one overpass hit already shaped as dicts; normalize to the same stay columns as wikivoyage sleep
    if not places:
        return pd.DataFrame(columns=list(STAY_WRITE_COLUMNS))
    records: list[dict] = []
    for p in places:
        title = str(p.get("title") or "").strip()
        desc = str(p.get("description") or "").strip()
        band = str(p.get("estimated_cost_band_guess") or "unknown").strip() or "unknown"
        rec = {
            "destination": str(destination).strip(),
            "section": "Sleep",
            "title": title,
            "description": desc,
            "source": "openstreetmap",
            "source_url": str(p.get("osm_browse_url") or "").strip(),
            "likely_place_listing": 1,
            "usable_for_itinerary": 0,
            "source_page_title": "OpenStreetMap",
            "page_type": "overpass",
            "lat": p.get("lat"),
            "lon": p.get("lon"),
            "osm_tags": str(p.get("osm_tags") or "").strip(),
            "data_source": "osm",
            "estimated_cost_band": band,
        }
        records.append(rec)
    mini = pd.DataFrame.from_records(records)
    mini["estimated_cost_band"] = mini.apply(
        lambda r: r["estimated_cost_band"]
        if str(r.get("estimated_cost_band") or "").strip().lower() not in ("", "unknown")
        else infer_cost_band(r),
        axis=1,
    )
    mini["vibe_tag"] = mini.apply(infer_vibe_tag, axis=1)
    mini["content_score"] = mini.apply(content_score, axis=1)
    mini["usable_for_stay"] = mini.apply(_usable_for_stay, axis=1).astype(int)
    return mini.reindex(columns=list(STAY_WRITE_COLUMNS), fill_value="")


def _wikivoyage_sleep_to_stay_rows(df: pd.DataFrame) -> pd.DataFrame:
    #sleep slice from the processed travel table, tagged for provenance
    wiki = df[df["section"].astype(str).str.strip() == "Sleep"].copy()
    if wiki.empty:
        return pd.DataFrame(columns=list(STAY_WRITE_COLUMNS))
    wiki["source"] = "wikivoyage"
    if "data_source" not in wiki.columns:
        wiki["data_source"] = ""
    wiki["data_source"] = wiki["data_source"].fillna("").astype(str)
    for col in ("lat", "lon"):
        if col not in wiki.columns:
            wiki[col] = pd.NA
    out = wiki.reindex(columns=list(STAY_WRITE_COLUMNS))
    return out.fillna("")


def _dedupe_stay_rows(stay: pd.DataFrame) -> pd.DataFrame:
    #same listing title in one city from two feeds: keep wikivoyage
    if stay.empty:
        return stay
    s = stay.copy()
    s["_src_rank"] = s["source"].astype(str).str.strip().str.casefold().map(
        lambda x: 0 if x == "wikivoyage" else 1
    )
    s["_dedupe_key"] = (
        s["destination"].astype(str).str.strip().str.casefold()
        + "\0"
        + s["title"].astype(str).str.strip().str.casefold()
    )
    s = s.sort_values(["_dedupe_key", "_src_rank"], kind="mergesort")
    s = s.drop_duplicates(subset=["_dedupe_key"], keep="first")
    return s.drop(columns=["_dedupe_key", "_src_rank"], errors="ignore")


def build_stay_dataset(travel_df: pd.DataFrame) -> pd.DataFrame:
    #wikivoyage sleep plus osm lodging per destination; network-heavy batch step
    parts: list[pd.DataFrame] = [_wikivoyage_sleep_to_stay_rows(travel_df)]
    dests = sorted(
        {str(x).strip() for x in travel_df["destination"].dropna().astype(str).unique() if str(x).strip()}
    )
    for i, dest in enumerate(dests):
        if i:
            time.sleep(0.35)
        try:
            places = hotel_source.fetch_osm_lodging_places(dest, max_elements=28)
        except Exception:
            places = []
        osm_df = _osm_places_to_stay_rows(dest, places)
        if not osm_df.empty:
            parts.append(osm_df)
    stay = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(STAY_WRITE_COLUMNS))
    stay = _dedupe_stay_rows(stay)
    return stay.reindex(columns=list(STAY_WRITE_COLUMNS), fill_value="")


def _print_stay_summary(stay: pd.DataFrame) -> None:
    if stay.empty:
        print("stay_dataset: (empty)")
        return
    print("\n--- stay rows by destination (top 30 by count) ---")
    by_dest = stay.groupby(stay["destination"].astype(str).str.strip(), dropna=False).size().sort_values(
        ascending=False
    )
    for name, n in by_dest.head(30).items():
        print(f"  {name}: {int(n)}")
    if len(by_dest) > 30:
        print(f"  ... and {len(by_dest) - 30} more destinations")
    print("\n--- stay rows by source ---")
    for src, n in (
        stay.groupby(stay["source"].astype(str).str.strip(), dropna=False).size().sort_values(ascending=False).items()
    ):
        print(f"  {src}: {int(n)}")


def _stay_source_bucket(s: pd.Series) -> str:
    src = str(s.get("source", "") or "").strip().casefold()
    ds = str(s.get("data_source", "") or "").strip().casefold()
    if src == "wikivoyage":
        return "wikivoyage"
    if src in ("openstreetmap", "osm") or ds == "osm":
        return "openstreetmap"
    return "other"


def _stay_destination_coverage_table(stay_df: pd.DataFrame) -> pd.DataFrame:
    #one row per destination for hotel tab health checks
    if stay_df.empty:
        return pd.DataFrame(
            columns=(
                "destination",
                "total_stay_rows",
                "wikivoyage_rows",
                "openstreetmap_rows",
                "other_source_rows",
                "usable_stay_rows",
                "usable_wikivoyage",
                "usable_openstreetmap",
                "hotel_support",
            )
        )
    s = stay_df.copy()
    s["_d"] = s["destination"].astype(str).str.strip()
    s["_b"] = s.apply(_stay_source_bucket, axis=1)
    s["_u"] = pd.to_numeric(s["usable_for_stay"], errors="coerce").fillna(0).astype(int).eq(1)
    rows = []
    for dest, g in s.groupby("_d", sort=True):
        total = int(len(g))
        nw = int((g["_b"] == "wikivoyage").sum())
        no = int((g["_b"] == "openstreetmap").sum())
        nx = int((g["_b"] == "other").sum())
        umask = g["_u"]
        u_all = int(umask.sum())
        uw = int((umask & (g["_b"] == "wikivoyage")).sum())
        uo = int((umask & (g["_b"] == "openstreetmap")).sum())
        tier = _stay_hotel_support_tier(total, u_all, no)
        rows.append(
            {
                "destination": dest,
                "total_stay_rows": total,
                "wikivoyage_rows": nw,
                "openstreetmap_rows": no,
                "other_source_rows": nx,
                "usable_stay_rows": u_all,
                "usable_wikivoyage": uw,
                "usable_openstreetmap": uo,
                "hotel_support": tier,
            }
        )
    out = pd.DataFrame(rows)
    out = out.assign(_sk=out["destination"].astype(str).str.casefold()).sort_values("_sk").drop(columns=["_sk"])
    return out.reset_index(drop=True)


def _stay_hotel_support_tier(total_rows: int, usable_rows: int, osm_rows: int) -> str:
    #quick read for humans: empty vs no usable vs thin vs ok vs rich osm backup
    if total_rows == 0:
        return "empty"
    if usable_rows == 0:
        return "weak_no_usable"
    if usable_rows <= 3:
        return "weak_few_usable"
    if usable_rows >= 18 or (usable_rows >= 10 and osm_rows >= 6):
        return "strong"
    if usable_rows >= 7:
        return "moderate"
    return "thin"


def _print_stay_destination_coverage(cov: pd.DataFrame, csv_path: Path) -> None:
    print("\n--- stay / hotel coverage by destination ---")
    if cov.empty:
        print("(no stay rows; coverage table empty)")
        return
    disp = cov.copy()
    disp["hotel_support"] = disp["hotel_support"].astype(str)
    with pd.option_context("display.max_rows", 200, "display.width", 220, "display.max_columns", 20):
        print(disp.to_string(index=False))
    print(
        "\nhotel_support: empty · weak_no_usable · weak_few_usable · thin · moderate · strong "
        "(usable_for_stay=1 drives weak vs strong; openstreetmap row counts help strong)"
    )
    print(f"\ncoverage csv: {csv_path} ({len(cov)} destinations)")


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


def build_dataset() -> tuple[Path, pd.DataFrame, Path, pd.DataFrame]:
    if not RAW_CSV.is_file():
        raise FileNotFoundError(f"missing raw file: {RAW_CSV} (run scraper.py first)")

    df = pd.read_csv(RAW_CSV)
    for col in ("title", "description", "destination", "section", "source_page_title", "page_type"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).map(clean_ws)
    if "source_page_title" not in df.columns:
        df["source_page_title"] = ""
    if "page_type" not in df.columns:
        df["page_type"] = "main_city_page"
    if "likely_place_listing" in df.columns:
        df["likely_place_listing"] = (
            pd.to_numeric(df["likely_place_listing"], errors="coerce").fillna(0).astype(int).clip(0, 1)
        )
    else:
        df["likely_place_listing"] = 0

    df = _drop_bad_rows(df)

    df["estimated_cost_band"] = df.apply(infer_cost_band, axis=1)
    df["vibe_tag"] = df.apply(infer_vibe_tag, axis=1)
    df["content_score"] = df.apply(content_score, axis=1)
    df["usable_for_itinerary"] = df.apply(_usable_for_itinerary, axis=1).astype(int)
    df["usable_for_stay"] = df.apply(_usable_for_stay, axis=1).astype(int)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    stay_df = build_stay_dataset(df)
    stay_df.to_csv(STAY_CSV, index=False)

    cov = _stay_destination_coverage_table(stay_df)
    STAY_COVERAGE_CSV.parent.mkdir(parents=True, exist_ok=True)
    cov.to_csv(STAY_COVERAGE_CSV, index=False)

    return OUT_CSV, df, STAY_CSV, stay_df


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
    path, out_df, stay_path, stay_df = build_dataset()
    print(f"wrote {path}")
    print(f"wrote {stay_path} rows={len(stay_df)}")
    print(f"wrote {STAY_COVERAGE_CSV}")
    _print_summary(out_df)
    _print_stay_summary(stay_df)
    cov = _stay_destination_coverage_table(stay_df)
    _print_stay_destination_coverage(cov, STAY_COVERAGE_CSV)
