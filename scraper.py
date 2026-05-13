"""
pull selected wikivoyage destination pages and dump see/do/eat/drink/sleep text to csv.
"""

from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

#wikimedia wants a clear user-agent; tweak the string if you publish this widely
HEADERS = {
    "User-Agent": "AITravelPlannerScraper/0.1 (educational project; Python requests)",
    "Accept-Language": "en",
}

BASE = "https://en.wikivoyage.org/wiki/"
RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"
OUT_CSV = RAW_DIR / "wikivoyage_raw.csv"

DESTINATIONS = ["Tokyo", "Kyoto", "Osaka", "Seoul", "Singapore"]
SECTIONS = ["See", "Do", "Eat", "Drink", "Sleep"]


def page_url(title: str) -> str:
    slug = title.replace(" ", "_")
    return BASE + quote(slug, safe="/_:()")


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.text


def clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def element_text(el: Tag | NavigableString | None) -> str:
    if el is None or isinstance(el, NavigableString):
        return ""
    return clean_ws(el.get_text(" ", strip=True))


def heading_block(h2: Tag) -> Tag:
    #vector skin wraps the h2 in div.mw-heading; content lives after that div
    p = h2.parent
    if p and isinstance(p, Tag) and "mw-heading" in (p.get("class") or []):
        return p
    return h2


def is_next_top_section(node: Tag) -> bool:
    if node.name == "h2":
        return True
    if node.name == "div" and "mw-heading2" in (node.get("class") or []):
        return bool(node.find("h2"))
    return False


def subsection_chunks(section_heading: Tag) -> list[tuple[str, str]]:
    #walk siblings after the heading block until the next big h2 section
    start = heading_block(section_heading)
    rows: list[tuple[str, str]] = []
    current_title = ""
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        desc = clean_ws(" ".join(buf))
        if current_title or desc:
            rows.append((current_title, desc))
        buf = []

    for sib in start.next_siblings:
        if isinstance(sib, NavigableString):
            t = clean_ws(str(sib))
            if t:
                buf.append(t)
            continue
        if not isinstance(sib, Tag):
            continue
        if is_next_top_section(sib):
            break
        if sib.name == "h3":
            flush()
            current_title = clean_ws(sib.get_text(" ", strip=True))
            continue
        if sib.name == "table" and "toc" in (sib.get("class") or []):
            continue
        txt = element_text(sib)
        if txt:
            buf.append(txt)

    flush()
    if not rows:
        rows.append(("", ""))
    return rows


def main_parser_output(soup: BeautifulSoup) -> Tag | None:
    #pick the big mw-parser-output; the first one is often just a stub wrapper
    candidates = soup.find_all("div", class_="mw-parser-output")
    if not candidates:
        return None
    return max(candidates, key=lambda d: len(d.find_all("h2")))


def extract_sections(html: str, source_url: str, destination: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    content = main_parser_output(soup)
    if not content:
        return []

    out: list[dict[str, str]] = []
    for name in SECTIONS:
        h2 = content.find("h2", id=name)
        if not h2:
            h2 = next(
                (
                    h
                    for h in content.find_all("h2")
                    if h.get_text(strip=True) == name
                ),
                None,
            )
        if not h2:
            continue
        for title, desc in subsection_chunks(h2):
            out.append(
                {
                    "destination": destination,
                    "section": name,
                    "title": title,
                    "description": desc,
                    "source_url": source_url,
                }
            )
    return out


def scrape_all() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, str]] = []

    for dest in DESTINATIONS:
        url = page_url(dest)
        time.sleep(1.0)
        html = fetch_html(url)
        all_rows.extend(extract_sections(html, url, dest))

    fieldnames = ["destination", "section", "title", "description", "source_url"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    return OUT_CSV


if __name__ == "__main__":
    path = scrape_all()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
