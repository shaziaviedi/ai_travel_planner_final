# Somnia Travel Planner

A course-style travel assistant built with **Streamlit**. You pick a supported city, trip length, vibe, budget tier, and interests. The app returns a **prep checklist**, **day-by-day itinerary ideas**, **places to stay**, and a **rule-based USD budget snapshot**, using **Wikivoyage text** plus optional **OpenStreetMap** lodging data merged into a stay dataset.

This repo is sometimes referred to as the AI Travel Planner project; the live UI title is **Somnia Travel Planner**.

## What the app does

- **Prep and packing**: Checklists and packing lines generated from your destination, length of trip, vibe, and budget.
- **Itinerary**: For each day, ranked **See / Do**, **Eat**, and **Drink** style bullets from guide text (semantic similarity, not a chat LLM).
- **Hotels**: Stay cards from a **sleep** pool built from Wikivoyage sleep rows and, when the pipeline runs, **OSM lodging** merged in `build_dataset.py`. Cards show title, budget band tag, and short facts (for example stars and address) when the data has them.
- **Budget**: Whole-trip USD **ranges** by category (lodging, food, transit, activities) and a total. These are **rough heuristics**, not quotes. Flights and large tours are out of scope.

## How the pipeline fits together

1. **`scraper.py`**  
   Downloads selected English **Wikivoyage** pages and writes `data/raw/wikivoyage_raw.csv` (sections such as See, Do, Eat, Drink, Sleep).

2. **`build_dataset.py`**  
   Cleans and tags rows, writes **`data/processed/travel_dataset.csv`**, and builds **`data/processed/stay_dataset.csv`** by combining sleep-related guide rows with **OpenStreetMap** lodging fetched via **`hotel_source.py`** (Nominatim + Overpass). Use a polite `User-Agent` and Wikimedia [Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use) if you change scraping or redistribution.

3. **`planner.py`**  
   Loads the CSVs, filters by destination, embeds and **ranks** snippets with **`model_utils.py`**, and assembles the plan dict consumed by the UI (itinerary, stays, checklist, packing, budget breakdown).

4. **`app.py`**  
   Streamlit shell: hero, trip **form** (destination, days, vibe, budget, must-see interests), then results in **tabs** (Prep and packing, Itinerary, Hotels, Budget). Optional **debug** toggle adds planner diagnostics.

## Model and ranking

Embeddings use **`sentence-transformers/all-MiniLM-L6-v2`** (Hugging Face) through the `sentence-transformers` package. Vectors are **normalized** so cosine similarity is computed as a **dot product** between the query embedding and each candidate snippet.

## Requirements

See **`requirements.txt`**: Streamlit, pandas, requests, BeautifulSoup, lxml, sentence-transformers, scikit-learn, numpy.

Use a recent **Python 3** (for example 3.11 or 3.12). The first embedding run may download model weights.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Build data after you adjust destinations in **`scraper.py`**:

```bash
python scraper.py
python build_dataset.py
```

`build_dataset` calls the network for OSM stays; expect some runtime and respect API limits.

Start the app:

```bash
streamlit run app.py
```

Open the URL Streamlit prints (often `http://localhost:8501`). Choose a city that exists in **`travel_dataset.csv`**, fill the form, then click **Build my trip**. If a city has no rows, you will see a notice instead of a full itinerary.

## Data on disk

| Path | Meaning |
|------|---------|
| `data/raw/wikivoyage_raw.csv` | Scraper output |
| `data/processed/travel_dataset.csv` | Itinerary pool |
| `data/processed/stay_dataset.csv` | Stay / hotel pool |
| `data/embeddings/` | Optional saved `.npy` embeddings (if you use those helpers) |

**`.gitignore`** excludes `data/raw`, `data/processed`, and `data/embeddings` so large CSVs and caches stay local. Clone a fresh repo and run **`scraper.py`** and **`build_dataset.py`** before expecting results.

## Repository layout

| File | Role |
|------|------|
| `app.py` | Streamlit UI and styles |
| `planner.py` | `get_recommendations`, ranking, itinerary and stay assembly, checklist, packing, budget |
| `model_utils.py` | Load MiniLM, `embed_texts`, `rank_by_similarity` |
| `hotel_source.py` | Nominatim bbox + Overpass queries for lodging-shaped OSM features |
| `build_dataset.py` | Raw Wikivoyage CSV to processed travel + stay datasets |
| `scraper.py` | Wikivoyage pages to raw CSV |
| `assets/fonts/` | Optional local font files used by the hero title in `app.py` |

## Limitations (short)

Guide text quality and section shape **vary by city**. Ranked bullets are **retrieval suggestions**, not verified bookings. Budget numbers are **simple multipliers** from trip length and tier, not live prices. Stays depend on what made it into **`stay_dataset.csv`** and filters in **`planner.py`**.

## Optional next steps

Spot-check relevance per destination, tighten deduplication of near-duplicate lines, or surface source URLs next to each bullet in the UI if you want stronger provenance.
