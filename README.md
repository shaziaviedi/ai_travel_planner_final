# AI Travel Planner

## Overview

**AI Travel Planner** is a small end-to-end travel assistant for a final project. It combines **scraped Wikivoyage text**, **semantic search** with a Hugging Face sentence-transformer, and a **Streamlit** interface. Users describe where they want to go and what they care about; the app responds with an **itinerary**, **hotel-style ideas** from guide content, a **packing list**, and a **rough budget estimate**.

## How it works

1. **Scrape** — `scraper.py` pulls selected destination pages from Wikivoyage and saves structured rows to `data/raw/wikivoyage_raw.csv` (sections such as See, Do, Eat, Drink, Sleep).

2. **Clean** — `build_dataset.py` loads that CSV, adds simple heuristic tags (e.g. cost band, vibe), and writes `data/processed/travel_dataset.csv`.

3. **Plan** — `planner.py` filters rows by destination, ranks snippets with **cosine similarity** over embeddings from `model_utils.py`, and assembles checklist, day-by-day ideas, stay blurbs, packing hints, and dollar-range budget text.

4. **Serve** — `app.py` collects **destination**, **number of days**, **trip vibe**, **budget**, and **must-see interests**, then calls `get_recommendations` and displays the results in tabs.

## Data source

Guide text comes from **[Wikivoyage](https://www.wikivoyage.org/)** (English). The scraper is polite (descriptive `User-Agent`, spacing between requests) and stores only the extracted fields needed for the pipeline; respect Wikimedia [terms of use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use) if you extend or republish the data.

## Model used

Embeddings and similarity ranking use **[sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)** from **Hugging Face** via the `sentence-transformers` library. Vectors are L2-normalized so **cosine similarity** matches a dot product between the query and each candidate snippet.

## How to run

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Build the data (once you are happy with the destination list in `scraper.py`):

```bash
python scraper.py
python build_dataset.py
```

Launch the app:

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`). Fill in destination, days, vibe, budget, and must-see interests, then click **Build my trip**. The first run may download model weights.

## Reflection

This project was a useful way to connect **real unstructured travel text** to a **concrete UI** without relying on a paid LLM API. Wikivoyage gives rich, human-written coverage, but quality and section layout vary by page, so **heuristic tags and simple budgets** are approximations, not ground truth. The MiniLM model is fast and easy to run locally, yet retrieval is only as good as the query and the rows in the CSV—**garbage in, garbage out** still applies. If I continued the work, I would add evaluation (e.g. spot-check relevance per city), optional deduplication of near-duplicate snippets, and clearer attribution of each blurb to its source URL inside the app.

## Repository layout (short)

| File | Role |
|------|------|
| `scraper.py` | Wikivoyage → raw CSV |
| `build_dataset.py` | Raw CSV → processed CSV + derived columns |
| `model_utils.py` | Load MiniLM, `embed_texts`, `rank_by_similarity` |
| `planner.py` | `get_recommendations` for the Streamlit app |
| `app.py` | Streamlit front end |

Raw and processed data paths are under `data/` (see `.gitignore` for what stays local).
