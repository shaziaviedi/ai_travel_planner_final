"""
load scraped wikivoyage rows, slap on a couple heuristic tags, write a tidy csv.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW_CSV = ROOT / "data" / "raw" / "wikivoyage_raw.csv"
OUT_CSV = ROOT / "data" / "processed" / "travel_dataset.csv"

#splurge-ish words win first so we do not label a fancy place "budget" just because it says "not cheap"
SPLURGE_HINTS = (
    "splurge",
    "luxury",
    "upscale",
    "michelin",
    "fine dining",
    "expensive",
    "high-end",
    "high end",
    "¥¥¥¥",
    "five-star",
    "five star",
    "$$$$",
)
MID_HINTS = (
    "mid-range",
    "mid range",
    "moderate",
    "reasonable",
    "¥¥¥",
)
BUDGET_HINTS = (
    "budget",
    "cheap",
    "inexpensive",
    "affordable",
    "hostel",
    "dorm",
    "capsule hotel",
    "street food",
    "conveyor belt sushi",
    "¥500",
    "¥¥",
    "free admission",
    "no cover",
)

#order matters: first match becomes the vibe we store
VIBE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nightlife", ("nightclub", "night club", "nightlife", "izakaya", "karaoke", "live music", "dj ")),
    ("food", ("restaurant", "sushi", "ramen", "street food", "food hall", "yakitori", "bbq", "bakery")),
    ("culture", ("temple", "shrine", "museum", "gallery", "castle", "palace", "heritage", "exhibit")),
    ("nature", ("park", "garden", "hike", "trail", "beach", "waterfront", "scenic", "viewpoint")),
    ("shopping", ("shopping", "mall", "market", "boutique", "department store", "souvenir")),
    ("stay", ("hotel", "hostel", "ryokan", "guesthouse", "capsule", "lodging", "accommodation")),
)


def blob(row: pd.Series) -> str:
    #mash title + description once; everything is case-insensitive
    title = "" if pd.isna(row.get("title")) else str(row["title"])
    desc = "" if pd.isna(row.get("description")) else str(row["description"])
    return f"{title} {desc}".lower()


def infer_cost_band(row: pd.Series) -> str:
    text = blob(row)
    if any(h in text for h in SPLURGE_HINTS):
        return "splurge"
    if any(h in text for h in BUDGET_HINTS):
        return "budget"
    if any(h in text for h in MID_HINTS):
        return "mid"
    return "unknown"


def infer_vibe_tag(row: pd.Series) -> str:
    text = blob(row)
    for tag, words in VIBE_RULES:
        if any(w in text for w in words):
            return tag
    return "general"


def build_dataset() -> tuple[Path, int]:
    if not RAW_CSV.is_file():
        raise FileNotFoundError(f"missing raw file: {RAW_CSV} (run scraper.py first)")

    df = pd.read_csv(RAW_CSV)
    #light cleanup so csv is nicer to eyeball later
    for col in ("title", "description"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    df["estimated_cost_band"] = df.apply(infer_cost_band, axis=1)
    df["vibe_tag"] = df.apply(infer_vibe_tag, axis=1)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    n = len(df)
    df.to_csv(OUT_CSV, index=False)
    return OUT_CSV, n


if __name__ == "__main__":
    path, n = build_dataset()
    print(f"wrote {path} ({n} rows)")
