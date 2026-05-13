"""
turn form inputs + scraped rows into a lightweight trip bundle for the ui.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from model_utils import rank_by_similarity

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "data" / "processed" / "travel_dataset.csv"

#rough usd per day for lodging+food+transit; wide ranges on purpose
DAILY_SPEND = {
    "budget": (70, 120),
    "mid": (130, 240),
    "splurge": (260, 520),
    "not sure": (90, 200),
}


def _load_dataset() -> pd.DataFrame:
    if not DATASET.is_file():
        return pd.DataFrame()
    return pd.read_csv(DATASET)


def _rows_for_destination(df: pd.DataFrame, destination: str) -> pd.DataFrame:
    dest = destination.strip().lower()
    if df.empty or not dest:
        return df
    exact = df[df["destination"].str.lower() == dest]
    if not exact.empty:
        return exact.reset_index(drop=True)
    contains = df[df["destination"].str.lower().str.contains(dest, na=False)]
    return contains.reset_index(drop=True) if not contains.empty else df.reset_index(drop=True)


def _row_label(row: pd.Series) -> str:
    sec = str(row.get("section", ""))
    title = str(row.get("title", "") or "").strip()
    if title:
        return f"{sec}: {title}"
    return sec


def _row_blurb(row: pd.Series, max_chars: int = 320) -> str:
    text = str(row.get("description", "") or "").strip()
    text = " ".join(text.split())
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def _ranked_frame(
    df: pd.DataFrame,
    destination: str,
    trip_vibe: str,
    must_see_interests: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    query = " ".join(
        p
        for p in (destination, trip_vibe, must_see_interests)
        if isinstance(p, str) and p.strip()
    ).strip()
    if not query:
        query = destination.strip() or "travel highlights"
    texts: list[str] = []
    for _, row in df.iterrows():
        blob = f"{row.get('section','')} {row.get('title','')} {row.get('description','')}"
        texts.append(str(blob)[:900])
    ranked_idx = [i for i, _ in rank_by_similarity(query, texts)]
    return df.iloc[ranked_idx].reset_index(drop=True)


def _generic_checklist(destination: str) -> list[str]:
    d = destination.strip() or "your destination"
    return [
        f"double-check passport/visa rules for {d}",
        "save offline maps for the areas you will walk",
        "download any transit apps locals actually use",
        "copy hotel address + emergency numbers into your phone",
        "peek at weather the week before and tweak layers",
    ]


def _packing_hints(trip_vibe: str, must_see: str, destination: str) -> list[str]:
    blob = f"{trip_vibe} {must_see} {destination}".lower()
    items = [
        "comfortable walking shoes",
        "reusable water bottle",
        "small daypack",
        "portable charger + cable",
        "copies of bookings and ids (photos are fine)",
    ]
    if any(w in blob for w in ("beach", "island", "swim")):
        items += ["swimsuit", "quick-dry towel", "sunscreen"]
    if any(w in blob for w in ("night", "club", "bar", "rooftop")):
        items += ["one nicer outfit", "light jacket for late nights"]
    if any(w in blob for w in ("temple", "shrine", "mosque", "church")):
        items += ["modest layers / scarf for covered sites"]
    if any(w in blob for w in ("hike", "trail", "mountain")):
        items += ["trail snacks", "hat", "mini first aid"]
    return items


def _budget_block(num_days: int, budget_key: str) -> tuple[str, list[str]]:
    key = (budget_key or "not sure").strip().lower()
    low, high = DAILY_SPEND.get(key, DAILY_SPEND["not sure"])
    total_low = low * num_days
    total_high = high * num_days
    summary = (
        f"very rough ballpark: about ${total_low:,}–${total_high:,} usd total "
        f"({num_days} days, ~${low}–${high}/day). not flight prices."
    )
    lines = [
        f"daily range (lodging+food+local transit vibe): ${low}–${high}",
        f"multiply by {num_days} days → ${total_low:,}–${total_high:,} total window",
        "flights and big tours sit outside this guess",
    ]
    return summary, lines


def get_recommendations(
    destination: str,
    num_days: int,
    trip_vibe: str,
    budget: str,
    must_see_interests: str,
) -> dict:
    #everything the streamlit page needs in one dict so the ui stays dumb
    dest = destination.strip() or "your pick"
    days = max(1, int(num_days))
    vibe = (trip_vibe or "").strip()
    budget_key = (budget or "not sure").strip()
    interests = (must_see_interests or "").strip()

    df = _load_dataset()
    scoped = _rows_for_destination(df, dest)
    ranked = _ranked_frame(scoped, dest, vibe, interests)

    checklist = _generic_checklist(dest)
    if not ranked.empty:
        checklist.append("skim the top matches below and star 2–3 must-dos per day")

    #pull see/do/eat/drink first for daytime ideas; sleep handled separately
    daytime = ranked[ranked["section"].isin(["See", "Do", "Eat", "Drink"])].head(max(8, days * 3))
    picks: list[str] = []
    for _, row in daytime.iterrows():
        label = _row_label(row)
        blurb = _row_blurb(row, 220)
        picks.append(f"{label} — {blurb}" if blurb else label)
    if not picks:
        picks = [
            f"day {i}: wander a central neighborhood, grab one local meal, pick one paid sight"
            for i in range(1, days + 1)
        ]

    itinerary: list[dict[str, object]] = []
    pool = picks[:] if picks else [f"explore {dest} at an easy pace"]
    idx = 0
    for day in range(1, days + 1):
        chunk: list[str] = []
        for _ in range(2):
            if not pool:
                break
            chunk.append(pool[idx % len(pool)])
            idx += 1
        if not chunk:
            chunk = [f"keep day {day} light: one anchor activity + coffee walks"]
        itinerary.append({"day": day, "activities": chunk})

    stays_rows = ranked[ranked["section"] == "Sleep"].head(5)
    stays: list[dict[str, str]] = []
    for _, row in stays_rows.iterrows():
        stays.append({"title": _row_label(row), "note": _row_blurb(row, 280)})
    if not stays:
        stays = [
            {
                "title": "Sleep (no scraped rows yet)",
                "note": f"run scraper + build_dataset, then rerun for {dest} lodging blurbs.",
            }
        ]

    packing = _packing_hints(vibe, interests, dest)
    budget_summary, budget_lines = _budget_block(days, budget_key)

    return {
        "destination": dest,
        "trip_vibe": vibe,
        "budget": budget_key,
        "checklist": checklist,
        "itinerary": itinerary,
        "stays": stays,
        "packing": packing,
        "budget_summary": budget_summary,
        "budget_lines": budget_lines,
    }
